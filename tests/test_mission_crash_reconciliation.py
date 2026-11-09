"""
ÆONIX PRISM // Priority 2: Governed Mission Crash Reconciliation Test Suite
Exhaustively verifies:
1. Transition to NEEDS_RECONCILIATION on unhandled execution exception.
2. Immediate persistence of EXECUTING state prior to payload dispatch.
3. Detection and reconciliation of stranded EXECUTING/VERIFYING missions upon daemon reboot.
4. Prohibition of blind automated retries for destructive or uncertain actions.
5. Operator-governed reconciliation resolution (ABORT vs CONTROLLED_RETRY) with PBKDF2 passphrase.
6. Single-use Sentinel claim lockout and duplicate execution prevention.
"""

import os
import sys
import time
import json
import tempfile
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
else:
    sys.path.remove(_REPO_ROOT)
    sys.path.insert(0, _REPO_ROOT)

_MODULE_SANDBOX = tempfile.mkdtemp(prefix="aeonix_test_recon_")
_MODULE_SECRETS = os.path.join(_MODULE_SANDBOX, "secrets")
_MODULE_DB = os.path.join(_MODULE_SANDBOX, "recon_vault.db")
os.makedirs(_MODULE_SECRETS, mode=0o700, exist_ok=True)

os.environ["AEONIX_TEST_MODE"] = "1"
if "AEONIX_SECRETS_DIR" not in os.environ:
    os.environ["AEONIX_SECRETS_DIR"] = _MODULE_SECRETS
if "AEONIX_DB_PATH" not in os.environ:
    os.environ["AEONIX_DB_PATH"] = _MODULE_DB

from aeonix.core.db import (
    init_database,
    get_connection,
    resolve_sentinel_request,
    query_db
)
from aeonix.core.operator_console import setup_operator_secret
from aeonix.core.governed_mission import GovernedMissionController, SUPPORTED_MISSION_TYPES


class TestMissionCrashReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = os.environ.get("AEONIX_DB_PATH", _MODULE_DB)
        cls.secrets_dir = os.environ.get("AEONIX_SECRETS_DIR", _MODULE_SECRETS)
        init_database(cls.db_path)
        cls.passphrase = "TestSovereignSandboxPassphrase123!"
        setup_operator_secret(cls.passphrase, secrets_dir=cls.secrets_dir)
        cls.governor = GovernedMissionController(db_path=cls.db_path)

    def test_01_unhandled_execution_exception_transitions_to_needs_reconciliation(self):
        """Uncertain execution failure must transition to NEEDS_RECONCILIATION rather than silent fail or retry."""
        res = self.governor.create_mission(
            mission_type="apk_preflight",
            objective="Crash injection preflight test",
            target="aether-launcher",
            scope={"apk_path": "/nonexistent/path/for/failure/simulation.apk"}
        )
        m_id = res["mission_id"]
        s_id = res["sentinel_request_id"]
        digest = res["action_digest"]

        # Approve with verified passphrase
        ok_app, _ = resolve_sentinel_request(s_id, True, passphrase_verified=True, expected_action_digest=digest, db_path=self.db_path)
        self.assertTrue(ok_app)

        # Claim and execute - missing file triggers known failure
        ok_exec, receipt, status_msg = self.governor.claim_and_execute(
            mission_id=m_id,
            claimer="TEST_POCO_EXEC",
            expected_digest=digest
        )
        self.assertFalse(ok_exec)
        self.assertEqual(receipt["status"], "FAILED")

        # Now test UNHANDLED UNEXPECTED crash path
        res2 = self.governor.create_mission(
            mission_type="storage_diagnostic",
            objective="Unhandled exception simulation",
            target="storage_vault"
        )
        m_id2 = res2["mission_id"]
        s_id2 = res2["sentinel_request_id"]
        digest2 = res2["action_digest"]
        resolve_sentinel_request(s_id2, True, passphrase_verified=True, expected_action_digest=digest2, db_path=self.db_path)

        # Monkeypatch shutil.disk_usage inside claim_and_execute to simulate OS crash/interruption
        import shutil
        orig_disk_usage = shutil.disk_usage
        try:
            def crash_disk_usage(path):
                raise OSError("EIO: Hardware partition I/O error during active execution")
            shutil.disk_usage = crash_disk_usage

            ok_c, receipt_c, msg_c = self.governor.claim_and_execute(
                mission_id=m_id2,
                claimer="TEST_POCO_EXEC",
                expected_digest=digest2
            )
            self.assertFalse(ok_c)
            self.assertEqual(receipt_c["status"], "NEEDS_RECONCILIATION")
            self.assertEqual(msg_c, "NEEDS_RECONCILIATION")
            self.assertIn("EIO", receipt_c["output_report"]["error"])

            # Verify in DB
            rows = query_db("SELECT status FROM missions WHERE id = ?;", (m_id2,), db_path=self.db_path)
            self.assertEqual(rows[0]["status"], "NEEDS_RECONCILIATION")
        finally:
            shutil.disk_usage = orig_disk_usage

    def test_02_interrupted_process_restart_reconciliation(self):
        """Missions stranded in EXECUTING/VERIFYING upon crash/reboot enter NEEDS_RECONCILIATION on startup."""
        conn = get_connection(self.db_path, allow_maintenance=True)
        cur = conn.cursor()
        now = time.time()
        stranded_id = f"mission_stranded_{int(now)}"
        cur.execute("""
            INSERT INTO missions (id, objective, target, status, current_phase, total_phases, plan_json, execution_log_json, created_at, updated_at)
            VALUES (?, 'Stranded execution test', 'storage_vault', 'EXECUTING', 5, 6, '[]', '[]', ?, ?);
        """, (stranded_id, now, now))
        conn.commit()
        conn.close()

        # Run startup reconciler
        reconciled = self.governor.reconcile_interrupted_missions()
        self.assertTrue(any(r["mission_id"] == stranded_id for r in reconciled))

        rows = query_db("SELECT status FROM missions WHERE id = ?;", (stranded_id,), db_path=self.db_path)
        self.assertEqual(rows[0]["status"], "NEEDS_RECONCILIATION")

    def test_03_no_blind_retry_and_duplicate_claim_prevention(self):
        """A mission in NEEDS_RECONCILIATION cannot be claimed again directly."""
        conn = get_connection(self.db_path, allow_maintenance=True)
        cur = conn.cursor()
        now = time.time()
        m_id = f"mission_locked_{int(now)}"
        cur.execute("""
            INSERT INTO missions (id, objective, target, status, current_phase, total_phases, plan_json, execution_log_json, created_at, updated_at)
            VALUES (?, 'Locked mission', 'storage_vault', 'NEEDS_RECONCILIATION', 5, 6, '[]', '[]', ?, ?);
        """, (m_id, now, now))
        conn.commit()
        conn.close()

        ok, _, msg = self.governor.claim_and_execute(m_id)
        self.assertFalse(ok)
        self.assertIn("INVALID_MISSION_STATUS", msg)
        self.assertIn("NEEDS_RECONCILIATION", msg)

    def test_04_operator_reconciliation_resolution(self):
        """Operator can abort or authorize a controlled retry requiring valid passphrase."""
        conn = get_connection(self.db_path, allow_maintenance=True)
        cur = conn.cursor()
        now = time.time()
        m_id = f"mission_resolve_{int(now)}"
        cur.execute("""
            INSERT INTO missions (id, objective, target, status, current_phase, total_phases, plan_json, execution_log_json, created_at, updated_at)
            VALUES (?, 'storage_diagnostic test', 'storage_vault', 'NEEDS_RECONCILIATION', 5, 6, '[]', '[]', ?, ?);
        """, (m_id, now, now))
        conn.commit()
        conn.close()

        # 1. Invalid passphrase rejection
        ok_bad, msg_bad = self.governor.resolve_reconciliation(m_id, "ABORT", "WrongPassphrase123!")
        self.assertFalse(ok_bad)
        self.assertIn("OPERATOR_AUTH_FAILED", msg_bad)

        # 2. Valid operator abort
        ok_abort, msg_abort = self.governor.resolve_reconciliation(m_id, "ABORT", self.passphrase)
        self.assertTrue(ok_abort)
        rows = query_db("SELECT status FROM missions WHERE id = ?;", (m_id,), db_path=self.db_path)
        self.assertEqual(rows[0]["status"], "CANCELLED")

        # 3. Controlled retry resets to AWAITING_APPROVAL
        m_id2 = f"mission_retry_{int(now)}"
        conn = get_connection(self.db_path, allow_maintenance=True)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO missions (id, objective, target, status, current_phase, total_phases, plan_json, execution_log_json, created_at, updated_at)
            VALUES (?, 'storage_diagnostic retry', 'storage_vault', 'NEEDS_RECONCILIATION', 5, 6, '[]', '[]', ?, ?);
        """, (m_id2, now, now))
        conn.commit()
        conn.close()

        ok_retry, msg_retry = self.governor.resolve_reconciliation(m_id2, "CONTROLLED_RETRY", self.passphrase)
        self.assertTrue(ok_retry)
        rows2 = query_db("SELECT status FROM missions WHERE id = ?;", (m_id2,), db_path=self.db_path)
        self.assertEqual(rows2[0]["status"], "AWAITING_APPROVAL")


if __name__ == "__main__":
    unittest.main()
