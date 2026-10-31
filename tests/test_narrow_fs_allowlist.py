"""
Unit & Negative Security Tests: Narrow Filesystem Allowlist & Complete Claim Finalization
Validates:
1. Operations targeting paths outside NARROW_FS_ALLOWLIST are rejected with TARGET_OUTSIDE_ALLOWLIST.
2. Root Protection: Mutation of allowlist root directories themselves is prohibited (ROOT_DELETION_PROHIBITED).
3. Agent State Protection: Critical agent state directories (.gemini, antigravity-cli, brain) are strictly protected (PROTECTED_RESOURCE).
4. Complete Claim Finalization: When a claimed consequential order fails validation or execution,
   complete_sentinel_execution is called, transitioning status to 'failed' and persisting error_msg.
5. Successful execution transitions status to 'completed' with output summary.
"""

import os
import shutil
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
    compute_action_digest,
    get_connection
)
from aeonix.core.forge import (
    execute_typed_operation,
    is_within_narrow_fs_allowlist,
    NARROW_FS_ALLOWLIST,
    ALLOWLIST_ROOTS
)
from aeonix.core.auth import ROLE_POCO_CORE


class TestNarrowFsAllowlistAndClaimFinalization(unittest.TestCase):
    def setUp(self):
        self.orig_secrets = os.environ.get("AEONIX_SECRETS_DIR")
        self.orig_db = os.environ.get("AEONIX_DB_PATH")

        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_vault.db")
        self.secrets_dir = os.path.join(self.temp_dir, "secrets")
        os.makedirs(self.secrets_dir, mode=0o700, exist_ok=True)

        os.environ["AEONIX_SECRETS_DIR"] = self.secrets_dir
        os.environ["AEONIX_DB_PATH"] = self.db_path

        init_database(self.db_path)

    def tearDown(self):
        if self.orig_secrets is not None:
            os.environ["AEONIX_SECRETS_DIR"] = self.orig_secrets
        else:
            os.environ.pop("AEONIX_SECRETS_DIR", None)

        if self.orig_db is not None:
            os.environ["AEONIX_DB_PATH"] = self.orig_db
        else:
            os.environ.pop("AEONIX_DB_PATH", None)

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_narrow_fs_allowlist_positive_containment(self):
        """is_within_narrow_fs_allowlist returns True for allowed subpaths, False for system roots."""
        # Allowed subpaths inside tempdir
        temp_file = os.path.join(tempfile.gettempdir(), "test_file.txt")
        allowed, reason = is_within_narrow_fs_allowlist(temp_file)
        self.assertTrue(allowed)
        self.assertEqual(reason, "OK")

        # Denied roots (outside allowlist)
        system_file = "/system/bin/sh"
        allowed_sys, reason_sys = is_within_narrow_fs_allowlist(system_file)
        self.assertFalse(allowed_sys)
        self.assertEqual(reason_sys, "TARGET_OUTSIDE_ALLOWLIST")

        etc_file = "/etc/passwd"
        allowed_etc, reason_etc = is_within_narrow_fs_allowlist(etc_file)
        self.assertFalse(allowed_etc)
        self.assertEqual(reason_etc, "TARGET_OUTSIDE_ALLOWLIST")

        home_file = "/data/data/com.termux/files/home/random_file.sh"
        allowed_home, reason_home = is_within_narrow_fs_allowlist(home_file)
        self.assertFalse(allowed_home)
        self.assertEqual(reason_home, "TARGET_OUTSIDE_ALLOWLIST")

    def test_02_allowlist_root_deletion_prohibited(self):
        """Mutation or deletion of the allowlist root itself is strictly prohibited."""
        for root in ALLOWLIST_ROOTS:
            allowed, reason = is_within_narrow_fs_allowlist(root)
            self.assertFalse(allowed)
            self.assertEqual(reason, "ROOT_DELETION_PROHIBITED")

        # Calling file_remove on an allowlist root must be denied
        target_root = list(ALLOWLIST_ROOTS)[0]
        res = execute_typed_operation(
            operation_name="file_remove",
            extra_args=[target_root],
            db_path=self.db_path
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "denied")
        self.assertIn("ROOT_DELETION_PROHIBITED", res.get("error", ""))

    def test_03_agent_state_directories_protected(self):
        """Removal of agent state (.gemini, antigravity-cli, brain) is blocked as PROTECTED_RESOURCE."""
        test_targets = [
            "/data/data/com.termux/files/home/.gemini/antigravity-cli",
            "/data/data/com.termux/files/home/.gemini/antigravity-cli/brain",
            "/tmp/.gemini/test_state",
            "/tmp/brain_dump"
        ]
        for target in test_targets:
            res = execute_typed_operation(
                operation_name="file_remove",
                extra_args=[target],
                db_path=self.db_path
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "denied")
            self.assertIn("PROTECTED_RESOURCE", res.get("error", ""))

    def test_04_pre_gate_target_outside_allowlist_rejected(self):
        """Pre-gate rejection when target is outside allowlist."""
        res = execute_typed_operation(
            operation_name="file_remove",
            extra_args=["/data/data/com.termux/files/home/unauthorized_target.txt"],
            db_path=self.db_path
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "denied")
        self.assertIn("TARGET_OUTSIDE_ALLOWLIST", res.get("error", ""))

    def test_05_post_claim_target_outside_allowlist_finalizes_claim(self):
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

        expected_digest = compute_action_digest(req_id, "FORGE", "TYPED_OP_FILE_REMOVE", exact_target, expected_scope)

        # Approve with verified operator credentials and exact action digest
        ok, reason = resolve_sentinel_request(
            req_id=req_id,
            approved=True,
            resolver="Aadi",
            resolver_role=ROLE_POCO_CORE,
            passphrase_verified=True,
            expected_action_digest=expected_digest,
            db_path=self.db_path
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "approved")

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

    def test_06_successful_execution_finalizes_claim_as_completed(self):
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

        expected_digest = compute_action_digest(req_id, "FORGE", "TYPED_OP_FILE_REMOVE", exact_target, expected_scope)

        ok, reason = resolve_sentinel_request(
            req_id=req_id,
            approved=True,
            resolver="Aadi",
            resolver_role=ROLE_POCO_CORE,
            passphrase_verified=True,
            expected_action_digest=expected_digest,
            db_path=self.db_path
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "approved")

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
