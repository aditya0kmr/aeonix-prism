"""
ÆONIX PRISM // VERITAS Digital Forensics & Immutable Evidence Vault
Cryptographic SHA-256 hashing, RFC 3161-style timestamping, and chain-of-custody tracking.
Zero External Cloud Dependencies.
"""

import os
import json
import time
import hashlib
import shutil
from typing import Dict, Any, List, Optional

from aeonix.core.db import get_connection, log_audit_event

VAULT_DIR = os.path.expanduser("~/aeonix/data/evidence")

def ensure_vault_dir():
    os.makedirs(VAULT_DIR, exist_ok=True)

def compute_sha256(file_path: str) -> str:
    """Computes standard cryptographic SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()

def create_case(
    title: str, 
    description: str, 
    legal_basis: str = "Authorized Sovereign Security Audit", 
    created_by: str = "Aadi"
) -> str:
    """Creates a new digital forensics case in the vault."""
    conn = get_connection()
    cur = conn.cursor()
    now = time.time()
    
    case_id = f"case_{int(now)}_{hashlib.sha256(title.encode()).hexdigest()[:6]}"
    cur.execute("""
        INSERT INTO cases (id, title, description, status, legal_basis, created_by, created_at)
        VALUES (?, ?, ?, 'open', ?, ?, ?);
    """, (case_id, title, description, legal_basis, created_by, now))
    
    conn.commit()
    conn.close()
    
    log_audit_event(
        actor=created_by,
        action="case_created",
        target=case_id,
        result="success",
        details={"title": title, "legal_basis": legal_basis}
    )
    return case_id

def ingest_evidence(
    case_id: str, 
    source_file: str, 
    mime_type: str = "application/octet-stream", 
    metadata: Optional[Dict[str, Any]] = None,
    collected_by: str = "Aadi"
) -> Dict[str, Any]:
    """
    Ingests a forensic file into the immutable evidence vault.
    Computes SHA-256, copies file to hashed storage, and appends to chain of custody.
    """
    if metadata is None:
        metadata = {}
    if not os.path.exists(source_file):
        raise FileNotFoundError(f"Source file not found: {source_file}")
    
    ensure_vault_dir()
    file_sha256 = compute_sha256(source_file)
    file_size = os.path.getsize(source_file)
    ext = os.path.splitext(source_file)[1]
    now = time.time()
    
    evidence_id = f"ev_{int(now)}_{file_sha256[:8]}"
    vault_dest = os.path.join(VAULT_DIR, f"{file_sha256}{ext}")
    
    # Store immutable copy
    if not os.path.exists(vault_dest):
        shutil.copy2(source_file, vault_dest)
        # Set file to read-only for tamper deterrence
        os.chmod(vault_dest, 0o444)
    
    chain_entry = [{
        "step": 1,
        "action": "ingested_to_vault",
        "actor": collected_by,
        "timestamp": now,
        "sha256": file_sha256,
        "size_bytes": file_size,
        "original_path": os.path.abspath(source_file)
    }]
    
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO evidence (id, case_id, file_path, sha256, mime_type, metadata_json, collected_at, collected_by, chain_of_custody)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        evidence_id, 
        case_id, 
        vault_dest, 
        file_sha256, 
        mime_type, 
        json.dumps(metadata), 
        now, 
        collected_by, 
        json.dumps(chain_entry)
    ))
    conn.commit()
    conn.close()
    
    audit_hash = log_audit_event(
        actor=collected_by,
        action="evidence_ingested",
        target=evidence_id,
        result="success",
        details={
            "case_id": case_id,
            "sha256": file_sha256,
            "size_bytes": file_size,
            "vault_path": vault_dest
        }
    )
    
    return {
        "evidence_id": evidence_id,
        "case_id": case_id,
        "sha256": file_sha256,
        "vault_path": vault_dest,
        "audit_hash": audit_hash,
        "status": "secured"
    }

def verify_evidence(evidence_id: str) -> Dict[str, Any]:
    """Verifies that an evidence item has not been altered since collection."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM evidence WHERE id = ?;", (evidence_id,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return {"error": "Evidence not found", "verified": False}
    
    vault_path = row["file_path"]
    expected_hash = row["sha256"]
    
    if not os.path.exists(vault_path):
        return {"error": "Vault file missing", "verified": False}
        
    actual_hash = compute_sha256(vault_path)
    is_valid = actual_hash == expected_hash
    
    return {
        "evidence_id": evidence_id,
        "vault_path": vault_path,
        "expected_sha256": expected_hash,
        "actual_sha256": actual_hash,
        "verified": is_valid,
        "is_intact": is_valid,
        "status": "intact" if is_valid else "TAMPERED_OR_CORRUPT"
    }

def generate_case_manifest(case_id: str) -> Dict[str, Any]:
    """Generates an exportable forensic manifest with cryptographic proof for a case."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM cases WHERE id = ?;", (case_id,))
    case_row = cur.fetchone()
    if not case_row:
        conn.close()
        return {"error": "Case not found"}
    
    cur.execute("SELECT * FROM evidence WHERE case_id = ? ORDER BY collected_at ASC;", (case_id,))
    evidence_rows = cur.fetchall()
    conn.close()
    
    items = []
    all_intact = True
    for ev in evidence_rows:
        ver = verify_evidence(ev["id"])
        if not ver["verified"]:
            all_intact = False
        items.append({
            "evidence_id": ev["id"],
            "sha256": ev["sha256"],
            "mime_type": ev["mime_type"],
            "collected_at": ev["collected_at"],
            "collected_by": ev["collected_by"],
            "chain_of_custody": json.loads(ev["chain_of_custody"]),
            "verification": ver
        })
        
    return {
        "case_id": case_id,
        "title": case_row["title"],
        "description": case_row["description"],
        "status": case_row["status"],
        "legal_basis": case_row["legal_basis"],
        "created_by": case_row["created_by"],
        "created_at": case_row["created_at"],
        "total_evidence_items": len(items),
        "all_evidence_intact": all_intact,
        "evidence_items": items
    }

def build_case_timeline(case_id: str) -> List[Dict[str, Any]]:
    """
    Builds a unified, chronological timeline of an investigation case.
    Merges case creation, evidence chain-of-custody events, and related audit log actions.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM cases WHERE id = ?;", (case_id,))
    case_row = cur.fetchone()
    if not case_row:
        conn.close()
        return []
        
    timeline = []
    
    # 1. Genesis event: Case Creation
    timeline.append({
        "timestamp": case_row["created_at"],
        "event_type": "CASE_CREATED",
        "actor": case_row["created_by"],
        "description": f"Case opened: {case_row['title']}",
        "details": {"legal_basis": case_row["legal_basis"]}
    })
    
    # 2. Evidence events and chain-of-custody steps
    cur.execute("SELECT * FROM evidence WHERE case_id = ?;", (case_id,))
    evidence_rows = cur.fetchall()
    evidence_ids = [e["id"] for e in evidence_rows]
    
    for ev in evidence_rows:
        chain = json.loads(ev["chain_of_custody"])
        for step in chain:
            timeline.append({
                "timestamp": step.get("timestamp", ev["collected_at"]),
                "event_type": "EVIDENCE_CUSTODY_STEP",
                "actor": step.get("actor", ev["collected_by"]),
                "description": f"Evidence {ev['id']} step: {step.get('action')}",
                "details": {
                    "evidence_id": ev["id"],
                    "sha256": step.get("sha256", ev["sha256"]),
                    "step": step.get("step")
                }
            })
            
    # 3. Correlated Audit Log records
    placeholders = ",".join("?" for _ in [case_id] + evidence_ids)
    cur.execute(f"""
        SELECT * FROM audit_log 
        WHERE target IN ({placeholders})
        ORDER BY timestamp ASC;
    """, [case_id] + evidence_ids)
    audit_rows = cur.fetchall()
    conn.close()
    
    for a in audit_rows:
        timeline.append({
            "timestamp": a["timestamp"],
            "event_type": "AUDIT_VERIFIED_ACTION",
            "actor": a["actor"],
            "description": f"Action '{a['action']}' on target '{a['target']}' ({a['result']})",
            "details": {
                "audit_id": a["id"],
                "audit_hash": a["current_hash"],
                "action": a["action"]
            }
        })
        
    timeline.sort(key=lambda x: x["timestamp"])
    return timeline

def export_case_report(case_id: str, export_format: str = "markdown") -> Dict[str, Any]:
    """
    Exports a cryptographically verified case dossier report.
    Generates an immutable report file with SHA-256 digest in the evidence vault.
    """
    manifest = generate_case_manifest(case_id)
    if "error" in manifest:
        return manifest
        
    timeline = build_case_timeline(case_id)
    ensure_vault_dir()
    
    now_str = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
    report_content = f"""# ÆONIX VERITAS // Official Forensic Examination Report
**Case Identifier:** `{manifest['case_id']}`  
**Case Title:** {manifest['title']}  
**Legal Basis:** {manifest['legal_basis']}  
**Lead Investigator:** {manifest['created_by']}  
**Report Exported:** {now_str}  
**Integrity Status:** {'VERIFIED INTACT' if manifest['all_evidence_intact'] else 'INTEGRITY ALERT - TAMPERING DETECTED'}

---

## 1. Executive Summary
- **Description:** {manifest['description']}
- **Status:** {manifest['status'].upper()}
- **Total Forensic Artifacts:** {manifest['total_evidence_items']}
- **Global Chain-of-Custody Intact:** {manifest['all_evidence_intact']}

---

## 2. Evidence Inventory & Cryptographic Proofs
"""
    for idx, item in enumerate(manifest["evidence_items"], 1):
        ver = item["verification"]
        report_content += f"""
### Artifact #{idx}: `{item['evidence_id']}`
- **SHA-256 Checksum:** `{item['sha256']}`
- **MIME Type:** `{item['mime_type']}`
- **Collected At:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(item['collected_at']))}
- **Collected By:** {item['collected_by']}
- **Vault Verification:** `{ver['status']}` (Match: `{ver['verified']}`)
"""

    report_content += """
---

## 3. Chronological Forensic Timeline
"""
    for entry in timeline:
        t_str = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(entry['timestamp']))
        report_content += f"- **[{t_str}]** `{entry['event_type']}` by **{entry['actor']}**: {entry['description']}\n"

    report_content += """
---
*Exported autonomously by ÆONIX PRISM Core Mind. 100% On-Device Provenance.*
"""

    report_filename = f"report_{case_id}_{int(time.time())}.md"
    report_path = os.path.join(VAULT_DIR, report_filename)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    os.chmod(report_path, 0o444)
    
    report_sha256 = compute_sha256(report_path)
    
    log_audit_event(
        actor=manifest['created_by'],
        action="case_report_exported",
        target=case_id,
        result="success",
        details={
            "report_path": report_path,
            "report_sha256": report_sha256,
            "total_items": manifest['total_evidence_items']
        }
    )
    
    return {
        "success": True,
        "case_id": case_id,
        "report_file": report_path,
        "report_sha256": report_sha256,
        "timeline_events": len(timeline),
        "all_evidence_intact": manifest['all_evidence_intact'],
        "content_preview": report_content[:500]
    }

get_case_manifest = generate_case_manifest


if __name__ == "__main__":
    import tempfile
    print("Testing VERITAS Forensics Vault...")
    cid = create_case("Operation Cyber Sentinel", "Subnet probe investigation", "Internal Audit")
    print("Created Case:", cid)
    
    test_file = os.path.join(tempfile.gettempdir(), "test_evidence.txt")
    with open(test_file, "w") as f:
        f.write("CONFIDENTIAL EVIDENCE DATA: Incident 2026-10-31\n")
    
    ing = ingest_evidence(cid, test_file, mime_type="text/plain", metadata={"source": "test_agent"})
    print("Ingested Evidence:", ing["evidence_id"], "SHA256:", ing["sha256"])
    
    ver = verify_evidence(ing["evidence_id"])
    print("Integrity Verification:", ver["status"], "Match:", ver["verified"])
    
    manifest = generate_case_manifest(cid)
    print(f"Manifest Generated: {manifest['total_evidence_items']} items, All Intact: {manifest['all_evidence_intact']}")
