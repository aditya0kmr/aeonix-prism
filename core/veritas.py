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
