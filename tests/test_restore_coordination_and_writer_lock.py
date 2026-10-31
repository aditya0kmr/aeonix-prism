"""
Unit & Negative Security Tests: Disaster Recovery Maintenance Lock & Overlapping Restore Prevention
Validates:
1. Active writers attempting database operations during maintenance mode fail with DATABASE_LOCKED.
2. Concurrent/overlapping restore requests are blocked with OVERLAPPING_RESTORE_BLOCKED.
3. System transitions cleanly out of maintenance mode after restore completes.
"""

import os
import tempfile
import unittest
import sqlite3
import threading
import time

from aeonix.core.db import (
    init_database,
    get_connection,
    log_audit_event
)
from aeonix.core.backup import (
    create_vault_backup,
    restore_vault_backup,
    set_maintenance_mode,
    is_maintenance_mode,
    _restore_thread_lock
)


class TestRestoreCoordinationAndWriterLock(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_vault.db")
        init_database(self.db_path)

        # Create an initial backup archive
        self.backup_res = create_vault_backup(db_path=self.db_path, encrypt=False)
        self.archive_path = self.backup_res["backup_path"]

    def tearDown(self):
        set_maintenance_mode(False)

    def test_01_active_writer_blocked_during_maintenance(self):
        """Active writers calling get_connection or log_audit_event during maintenance raise OperationalError."""
        set_maintenance_mode(True)
        self.assertTrue(is_maintenance_mode())

        # Attempting get_connection without allow_maintenance=True must fail
        with self.assertRaises(sqlite3.OperationalError) as ctx:
            get_connection(self.db_path, allow_maintenance=False)
        self.assertIn("DATABASE_LOCKED", str(ctx.exception))

        # Attempting log_audit_event without allow_maintenance=True must fail
        with self.assertRaises(sqlite3.OperationalError) as ctx:
            log_audit_event("TEST", "write_attempt", "vault", "fail", {"note": "test"}, db_path=self.db_path, allow_maintenance=False)
        self.assertIn("DATABASE_LOCKED", str(ctx.exception))

        # Disabling maintenance mode allows writes again
        set_maintenance_mode(False)
        conn = get_connection(self.db_path, allow_maintenance=False)
        self.assertIsNotNone(conn)
        conn.close()

    def test_02_overlapping_restore_blocked(self):
        """Concurrent overlapping restore attempts return OVERLAPPING_RESTORE_BLOCKED."""
        # Acquire thread lock to simulate an active restore currently running
        acquired = _restore_thread_lock.acquire(blocking=False)
        self.assertTrue(acquired)

        try:
            # Second restore call must be immediately rejected
            res = restore_vault_backup(self.archive_path, target_db_path=self.db_path)
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "OVERLAPPING_RESTORE_BLOCKED")
            self.assertIn("Another restore operation is currently in progress", res["error"])
        finally:
            _restore_thread_lock.release()

    def test_03_clean_restore_and_maintenance_release(self):
        """A complete restore finishes cleanly and releases maintenance mode."""
        res = restore_vault_backup(self.archive_path, target_db_path=self.db_path)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "RESTORE_COMPLETED")
        self.assertFalse(is_maintenance_mode())

        # Connections can open normally after restore
        conn = get_connection(self.db_path)
        self.assertIsNotNone(conn)
        conn.close()


if __name__ == "__main__":
    unittest.main()
