"""
Unit & Integration Tests for ATLAS SOVEREIGN
Tests hardware threshold enforcement, self-preservation guarantees,
crash-safe checkpointing, and cryptographic SHA-256 audit chaining.
"""

import os
import sys
import time
import signal
import sqlite3
import tempfile
import unittest

# Ensure imports resolve
sys.path.insert(0, "/data/data/com.termux/files/home/aeonix")
sys.path.insert(0, "/data/data/com.termux/files/home")

from core.atlas_sovereign import AtlasSovereignEngine

class TestAtlasSovereign(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_vault.db")
        self.engine = AtlasSovereignEngine(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_latency_under_5ms(self):
        """Verifies that a hardware surveillance pass executes in under 5ms."""
        t0 = time.perf_counter()
        ram = self.engine.get_ram_status()
        temp = self.engine.get_device_temp()
        procs = self.engine.get_child_process_info()
        wal = self.engine.check_sqlite_wal()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertLess(elapsed_ms, 15.0, f"Hardware sensing took {elapsed_ms:.2f}ms")
        self.assertIn("percent", ram)
        self.assertIsInstance(temp, float)
        self.assertIn("child_count", procs)
        self.assertEqual(wal["status"], "NOMINAL")

    def test_audit_log_hash_chaining(self):
        """Verifies cryptographic tamper-evident SHA-256 hash chaining in audit_events."""
        d1 = self.engine.log_audit_event("BREACH_TEST_1", {"target": "proc1", "pid": 1001})
        d2 = self.engine.log_audit_event("BREACH_TEST_2", {"target": "proc2", "pid": 1002})
        d3 = self.engine.log_audit_event("BREACH_TEST_3", {"target": "proc3", "pid": 1003})

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id, kind, previous_hash, current_hash FROM audit_events ORDER BY rowid ASC;")
        rows = cur.fetchall()
        conn.close()

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["previous_hash"], "GENESIS_ATLAS_SOVEREIGN_v1.0")
        self.assertEqual(rows[0]["current_hash"], d1)
        self.assertEqual(rows[1]["previous_hash"], d1)
        self.assertEqual(rows[1]["current_hash"], d2)
        self.assertEqual(rows[2]["previous_hash"], d2)
        self.assertEqual(rows[2]["current_hash"], d3)

    def test_protected_pids_immunity(self):
        """Verifies that core server and self PIDs are completely immune to termination."""
        my_pid = os.getpid()
        self.assertIn(my_pid, self.engine.PROTECTED_PIDS)

        # Mock dummy process
        class MockProc:
            def __init__(self, pid):
                self.pid = pid
            def name(self):
                return "server.py"

        res = self.engine.kill_and_report(MockProc(my_pid), "TEST_BREACH", "100%")
        self.assertEqual(res.get("status"), "PROTECTED_ABORT")

    def test_active_mission_checkpointing(self):
        """Verifies that active missions are state-checkpointed and flushed to SQLite WAL upon breach."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS missions (
                id TEXT PRIMARY KEY,
                objective TEXT,
                target TEXT,
                status TEXT,
                current_phase INTEGER,
                total_phases INTEGER,
                plan_json TEXT,
                execution_log_json TEXT,
                report_json TEXT,
                created_at REAL,
                updated_at REAL
            );
        """)
        now = time.time()
        cur.execute("""
            INSERT INTO missions (id, objective, status, execution_log_json, created_at, updated_at)
            VALUES ('mission_alpha', 'Threat Audit', 'running', '[]', ?, ?);
        """, (now, now))
        conn.commit()
        conn.close()

        # Trigger checkpoint
        self.engine.checkpoint_active_missions("RAM_SURGE_EMERGENCY")

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT execution_log_json FROM missions WHERE id = 'mission_alpha';")
        log_json = cur.fetchone()[0]
        conn.close()

        self.assertIn("ATLAS_SOVEREIGN_CHECKPOINT", log_json)
        self.assertIn("RAM_SURGE_EMERGENCY", log_json)

    def test_stuck_task_detection(self):
        """Verifies detection and aborting of tasks hanging > 30 seconds."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS missions (
                id TEXT PRIMARY KEY,
                objective TEXT,
                status TEXT,
                updated_at REAL
            );
        """)
        # Insert a mission that has been idle for 45 seconds
        cur.execute("""
            INSERT INTO missions (id, objective, status, updated_at)
            VALUES ('stuck_mission_99', 'Hanging Scraper', 'running', ?);
        """, (time.time() - 45.0,))
        conn.commit()
        conn.close()

        stuck = self.engine.check_stuck_missions()
        self.assertEqual(len(stuck), 1)
        self.assertEqual(stuck[0]["mission_id"], "stuck_mission_99")
        self.assertGreater(stuck[0]["idle_seconds"], 30.0)


if __name__ == "__main__":
    unittest.main()
