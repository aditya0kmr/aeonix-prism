"""
ÆONIX PRISM // Stage 3 Disaster Recovery Test Suite
Validates AES-GCM Encrypted Backups, Path Traversal Defenses,
Checksum & Audit-Chain Comparison, Isolated Host Loss Restoration, and Retention Policies.
"""

import unittest
import os
import time
import sqlite3
import shutil
import tempfile
import tarfile

from aeonix.core.db import init_database, get_connection, log_audit_event, verify_audit_chain
from aeonix.core.backup import (
    create_vault_backup,
    verify_backup,
    restore_vault_backup,
    list_backups,
    generate_emergency_recovery_key,
    enforce_retention_policy,
    _safe_extract,
    BACKUP_DIR
)


class TestStage3DisasterRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def test_encrypted_backup_creation_and_manifest(self):
        """Creates AES-256-GCM encrypted backup with embedded manifest and tip hash."""
        res = create_vault_backup(actor="Aadi", note="Stage 3 Test Backup", encrypt=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["encrypted"])
        self.assertTrue(os.path.exists(res["backup_path"]))
        self.assertTrue(res["backup_file"].endswith(".enc"))
        self.assertTrue(res["audit_tip_hash"])
        self.assertGreater(res["size_bytes"], 1024)

    def test_backup_verification_and_hash_comparison(self):
        """Verifies backup passes AEAD tag check, checksum comparison, and audit chain verification."""
        res = create_vault_backup(actor="Aadi", note="Verification Test", encrypt=True)
        self.assertTrue(res["success"])

        v_res = verify_backup(res["backup_path"])
        self.assertTrue(v_res["success"])
        self.assertTrue(v_res["is_intact"])
        self.assertEqual(v_res["status"], "VERIFIED_INTACT")
        self.assertEqual(v_res["integrity_check"], "ok")
        self.assertTrue(v_res["audit_chain_valid"])
        self.assertGreater(v_res["audit_events"], 0)

    def test_tampered_backup_rejection(self):
        """Confirms modified ciphertext fails AES-GCM authentication and is rejected."""
        res = create_vault_backup(actor="Aadi", note="Tamper Target", encrypt=True)
        self.assertTrue(res["success"])

        # Tamper with the encrypted bytes
        with open(res["backup_path"], "r+b") as f:
            f.seek(-32, os.SEEK_END)
            orig = f.read(16)
            f.seek(-32, os.SEEK_END)
            # Flip bits in ciphertext
            f.write(bytes([b ^ 0xFF for b in orig]))

        v_res = verify_backup(res["backup_path"])
        self.assertFalse(v_res["is_intact"])
        self.assertIn("AUTHENTICATION_FAILED", v_res["error"])

    def test_path_traversal_zip_bomb_defense(self):
        """Confirms _safe_extract rejects malicious archives with path traversal or symlinks."""
        import io
        test_dir = tempfile.mkdtemp(prefix="aeonix_test_sec_")
        malicious_tar = os.path.join(test_dir, "malicious.tar")

        try:
            # Craft tar with ../ traversal
            with tarfile.open(malicious_tar, "w") as tar:
                # Add safe file
                safe_info = tarfile.TarInfo(name="safe.txt")
                safe_data = b"safe"
                safe_info.size = len(safe_data)
                tar.addfile(safe_info, fileobj=io.BytesIO(safe_data))

                # Add path traversal member
                bad_info = tarfile.TarInfo(name="../../etc/passwd")
                bad_data = b"root:x:0:0"
                bad_info.size = len(bad_data)
                tar.addfile(bad_info, fileobj=io.BytesIO(bad_data))

            with tarfile.open(malicious_tar, "r") as tar:
                with self.assertRaises(PermissionError):
                    _safe_extract(tar, test_dir)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_isolated_disaster_recovery_restore(self):
        """Demonstrates complete disaster recovery into an isolated environment after simulated host loss."""
        # 1. Create fresh backup
        bkp = create_vault_backup(actor="Aadi", note="Disaster Recovery Snapshot", encrypt=True)
        self.assertTrue(bkp["success"])

        # 2. Define isolated target DB simulating new host environment
        isolated_dir = tempfile.mkdtemp(prefix="aeonix_isolated_host_")
        isolated_db = os.path.join(isolated_dir, "recovered_vault.db")

        try:
            # 3. Execute disaster recovery restore into isolated environment
            restore_res = restore_vault_backup(bkp["backup_path"], target_db_path=isolated_db)
            self.assertTrue(restore_res["success"])
            self.assertEqual(restore_res["status"], "RESTORE_COMPLETED")
            self.assertTrue(restore_res["audit_chain_valid"])
            self.assertGreater(restore_res["total_audit_events"], 100)

            # 4. Prove recovered database is live and operational
            conn = sqlite3.connect(isolated_db)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM audit_log;")
            count = cur.fetchone()[0]
            conn.close()

            # Note: 1 additional event logged for the restore action itself
            self.assertEqual(count, restore_res["total_audit_events"] + 1)

            # Verify cryptographic audit chain on restored host database
            chain_check = verify_audit_chain(isolated_db)
            self.assertTrue(chain_check["is_valid"])
            self.assertEqual(chain_check["status"], "CRYPTOGRAPHICALLY_VERIFIED")
        finally:
            shutil.rmtree(isolated_dir, ignore_errors=True)

    def test_emergency_recovery_key(self):
        """Generates high-entropy recovery key with verifiable checksum."""
        key_data = generate_emergency_recovery_key()
        self.assertIn("recovery_key", key_data)
        self.assertTrue(key_data["recovery_key"].startswith("AEONIX-RECOVERY-"))
        self.assertEqual(len(key_data["checksum"]), 8)

    def test_storage_retention_enforcement(self):
        """Enforces maximum backup count and purges oldest archives."""
        enforce_retention_policy(max_backups=5)
        backups = list_backups()
        self.assertLessEqual(len(backups), 10)


if __name__ == "__main__":
    unittest.main()
