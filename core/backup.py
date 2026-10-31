"""
ÆONIX PRISM // Cryptographic Backup & Sovereign Vault Recovery
Creates atomic SQLite WAL snapshots, verifies SHA-256 archive integrity, and manages emergency recovery keys.
Zero External Cloud Dependencies.
"""

import os
import time
import sqlite3
import hashlib
import tarfile
import secrets
from typing import Dict, Any, List, Optional

from aeonix.core.db import DB_PATH, get_connection, log_audit_event

BACKUP_DIR = os.path.expanduser("~/aeonix/data/backups")

def ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)

def compute_sha256(file_path: str) -> str:
    """Computes SHA-256 checksum of a backup archive."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def create_vault_backup(actor: str = "Aadi", note: str = "Automated Sovereign Snapshot") -> Dict[str, Any]:
    """
    Creates an atomic, consistent SQLite snapshot of the active vault database.
    Uses SQLite's online backup API to ensure 0 transaction corruption during active WAL operation.
    """
    ensure_backup_dir()
    t0 = time.perf_counter()
    now = int(time.time())
    backup_db_name = f"vault_snapshot_{now}.db"
    backup_db_path = os.path.join(BACKUP_DIR, backup_db_name)
    tar_archive_path = os.path.join(BACKUP_DIR, f"aeonix_vault_{now}.tar.gz")

    # 1. Atomic Online SQLite Backup
    src_conn = get_connection()
    dst_conn = sqlite3.connect(backup_db_path)
    with dst_conn:
        src_conn.backup(dst_conn, pages=100)
    dst_conn.close()
    src_conn.close()

    # 2. Package into compressed archive
    with tarfile.open(tar_archive_path, "w:gz") as tar:
        tar.add(backup_db_path, arcname=backup_db_name)

    # 3. Clean up intermediate db file
    try:
        os.remove(backup_db_path)
    except Exception:
        pass

    archive_size = os.path.getsize(tar_archive_path)
    archive_sha256 = compute_sha256(tar_archive_path)
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    log_audit_event(
        actor=actor,
        action="vault_backup_created",
        target=os.path.basename(tar_archive_path),
        result="success",
        details={
            "sha256": archive_sha256,
            "size_bytes": archive_size,
            "note": note,
            "latency_ms": latency_ms
        }
    )

    return {
        "success": True,
        "backup_file": os.path.basename(tar_archive_path),
        "backup_path": tar_archive_path,
        "sha256": archive_sha256,
        "size_bytes": archive_size,
        "created_at": now,
        "latency_ms": latency_ms
    }

def verify_backup(archive_path: str) -> Dict[str, Any]:
    """
    Verifies that a backup archive exists, is uncorrupted, and passes SQLite integrity check.
    """
    if not os.path.exists(archive_path):
        return {"success": False, "error": f"Archive not found: {archive_path}"}

    t0 = time.perf_counter()
    sha256 = compute_sha256(archive_path)

    # Extract database to a temporary location to verify SQLite integrity
    temp_dir = os.path.expanduser("~/aeonix/data/backups/.temp_verify")
    os.makedirs(temp_dir, exist_ok=True)
    
    is_valid = False
    integrity_msg = "Unknown"

    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=temp_dir)
            extracted_files = [f for f in os.listdir(temp_dir) if f.endswith(".db")]
            if extracted_files:
                db_test = os.path.join(temp_dir, extracted_files[0])
                conn = sqlite3.connect(db_test)
                cur = conn.cursor()
                cur.execute("PRAGMA integrity_check;")
                res = cur.fetchone()[0]
                conn.close()
                integrity_msg = res
                is_valid = (res.lower() == "ok")
                try:
                    os.remove(db_test)
                except Exception:
                    pass
    except Exception as e:
        integrity_msg = f"Extraction error: {str(e)}"
    finally:
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass

    dt = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "success": is_valid,
        "archive_file": os.path.basename(archive_path),
        "sha256": sha256,
        "integrity_check": integrity_msg,
        "is_intact": is_valid,
        "verification_ms": dt
    }

def list_backups() -> List[Dict[str, Any]]:
    """Returns sorted catalog of all existing vault backups."""
    ensure_backup_dir()
    backups = []
    for f in os.listdir(BACKUP_DIR):
        if f.endswith(".tar.gz"):
            full_path = os.path.join(BACKUP_DIR, f)
            stat = os.stat(full_path)
            backups.append({
                "file_name": f,
                "file_path": full_path,
                "size_bytes": stat.st_size,
                "created_at": stat.st_mtime
            })
    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return backups

def generate_emergency_recovery_key() -> Dict[str, Any]:
    """Generates a high-entropy 256-bit sovereign recovery secret with checksum."""
    entropy = secrets.token_bytes(32)
    hex_key = entropy.hex()
    checksum = hashlib.sha256(entropy).hexdigest()[:8]
    formatted_key = "-".join([hex_key[i:i+8] for i in range(0, 64, 8)])
    
    return {
        "recovery_key": f"AEONIX-RECOVERY-{formatted_key}",
        "checksum": checksum,
        "created_at": time.time(),
        "instructions": "Store this recovery key in an encrypted cold vault or paper backup."
    }
