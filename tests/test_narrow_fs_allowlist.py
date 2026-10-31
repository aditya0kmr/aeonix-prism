"""
Unit & Negative Security Tests: Narrow Filesystem Allowlist & Complete Claim Finalization
Validates:
1. Operations targeting paths outside NARROW_FS_ALLOWLIST are rejected with TARGET_OUTSIDE_ALLOWLIST.
2. Complete Claim Finalization: When a claimed consequential order fails validation or execution,
   complete_sentinel_execution is called, transitioning status to 'failed' and persisting error_msg.
3. Successful execution transitions status to 'completed' with output summary.
"""

import os
import tempfile
import unittest
import json
import time

from aeonix.core.db import (
    init_database,
    queue_sentinel_request,
    resolve_sentinel_request,
    claim_sentinel_authorization,
    complete_sentinel_execution,
    get_connection
)
from aeonix.core.forge import (
    execute_typed_operation,
    is_within_narrow_fs_allowlist,
    NARROW_FS_ALLOWLIST
)
from aeonix.core.auth import ROLE_POCO_CORE


class TestNarrowFsAllowlistAndClaimFinalization(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_vault.db")
        init_database(self.db_path)

    def test_01_narrow_fs_allowlist_positive_containment(self):
        """is_within_narrow_fs_allowlist returns True for allowed roots, False for system roots."""
        # Allowed roots
        temp_file = os.path.join(tempfile.gettempdir(), "test_file.txt")
        self.assertTrue(is_within_narrow_fs_allowlist(temp_file))

        # Denied roots (outside allowlist)
        system_file = "/system/bin/sh"
        self.assertFalse(is_within_narrow_fs_allowlist(system_file))

        etc_file = "/etc/passwd"
        self.assertFalse(is_within_narrow_fs_allowlist(etc_file))

        home_file = "/data/data/com.termux/files/home/random_file.sh"
        self.assertFalse(is_within_narrow_fs_allowlist(home_file))

    def test_02_pre_gate_target_outside_allowlist_rejected(self):
        """Pre-gate rejection when target is outside allowlist."""
        res = execute_typed_operation(
            operation_name="file_remove",
            extra_args=["/data/data/com.termux/files/home/unauthorized_target.txt"],
            db_path=self.db_path
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "denied")
        self.assertIn("TARGET_OUTSIDE_ALLOWLIST", res.get("error", ""))

    def test_03_post_claim_target_outside_allowlist_finalizes_claim(self):
        """When an approved Sentinel request attempts execution on a target outside allowlist, claim transitions to 'failed'."""
        target_path = "/data/data/com.termux/files/home/unauthorized_target.txt"
        exact_target = f"rm file_remove {target_path}"
        expected_scope = {"cwd": "/data/data/com.termux/files/home/aeonix", "extra_args": [target_path], "operation": "file_remove"}

        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="DEVELOPER_EXECUTION",
            action_type="TYPED_OP_FILE_REMOVE",
            target=exact_target,
            scope=expected_scope,
            risk_level="R3",
            db_path=self.db_path
        )

        # Approve with verified operator credentials
        ok, _ = resolve_sentinel_request(
            req_id=req_id,
            approved=True,
            resolver="Aadi",
            resolver_role=ROLE_POCO_CORE,
            passphrase_verified=True,
            db_path=self.db_path
        )
        self.assertTrue(ok)

        # Execute typed op with sentinel_request_id
        res = execute_typed_operation(
            operation_name="file_remove",
            extra_args=[target_path],
            sentinel_request_id=req_id,
            db_path=self.db_path
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "denied")
        self.assertIn("TARGET_OUTSIDE_ALLOWLIST", res.get("error", ""))

        # Verify claim finalization: sentinel_requests status MUST be 'failed'
        conn = get_connection(self.db_path, allow_maintenance=True)
        cur = conn.cursor()
        cur.execute("SELECT status, error_msg, completed_at FROM sentinel_requests WHERE id = ?;", (req_id,))
        row = dict(cur.fetchone())
        conn.close()

        self.assertEqual(row["status"], "failed")
        self.assertIsNotNone(row["completed_at"])
        self.assertIn("TARGET_OUTSIDE_ALLOWLIST", row["error_msg"])

    def test_04_successful_execution_finalizes_claim_as_completed(self):
        """When an approved Sentinel request executes successfully, claim transitions to 'completed'."""
        # Create a real file inside tempdir
        temp_file = os.path.join(tempfile.gettempdir(), f"forge_test_{int(time.time())}.txt")
        with open(temp_file, "w") as f:
            f.write("temporary test payload")

        exact_target = f"rm file_remove {temp_file}"
        expected_scope = {"cwd": "/data/data/com.termux/files/home/aeonix", "extra_args": [temp_file], "operation": "file_remove"}

        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="DEVELOPER_EXECUTION",
            action_type="TYPED_OP_FILE_REMOVE",
            target=exact_target,
            scope=expected_scope,
            risk_level="R3",
            db_path=self.db_path
        )

        ok, _ = resolve_sentinel_request(
            req_id=req_id,
            approved=True,
            resolver="Aadi",
            resolver_role=ROLE_POCO_CORE,
            passphrase_verified=True,
            db_path=self.db_path
        )
        self.assertTrue(ok)

        # Execute
        res = execute_typed_operation(
            operation_name="file_remove",
            extra_args=[temp_file],
            sentinel_request_id=req_id,
            db_path=self.db_path
        )
        self.assertTrue(res["success"])

        # Check DB state
        conn = get_connection(self.db_path, allow_maintenance=True)
        cur = conn.cursor()
        cur.execute("SELECT status, completed_at FROM sentinel_requests WHERE id = ?;", (req_id,))
        row = dict(cur.fetchone())
        conn.close()

        self.assertEqual(row["status"], "completed")
        self.assertIsNotNone(row["completed_at"])
        self.assertFalse(os.path.exists(temp_file))


if __name__ == "__main__":
    unittest.main()
