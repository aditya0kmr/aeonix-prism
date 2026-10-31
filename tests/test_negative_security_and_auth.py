"""
ÆONIX PRISM // Negative Security & Authorization Test Suite
Verifies strict negative-path enforcement:
1. Unauthenticated / forged token rejection.
2. Fire TV Glass approval attempt rejection (POCO-only authority).
3. Altered target / action parameter mismatch rejection.
4. Sentinel single-use atomic consumption (replay attack prevention).
5. Expired approval TTL rejection.
6. Execution rejection while Sanctuary Mode is active.
7. Protected file removal rejection.
"""

import os
import unittest
import time
import tempfile
import sqlite3

from aeonix.core.db import (
    init_database, 
    queue_sentinel_request, 
    resolve_sentinel_request, 
    consume_sentinel_authorization,
    check_sentinel_authorization
)
from aeonix.core.auth import issue_device_token, verify_token, ROLE_POCO_CORE, ROLE_FIRETV_GLASS
from aeonix.core.forge import execute_typed_operation
from aeonix.core.sanctuary import engage_sanctuary, release_sanctuary

class TestNegativeSecurityAndAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="aeonix_neg_test_")
        cls.db_path = os.path.join(cls.test_dir, "test_vault.db")
        init_database(cls.db_path)

    def test_01_forged_or_invalid_token_rejected(self):
        """Tokens with invalid signatures or altered payloads must fail verification."""
        valid_token = issue_device_token("poco_m4_pro", ROLE_POCO_CORE)
        parts = valid_token.split(".")
        self.assertEqual(len(parts), 2)

        # Alter payload
        tampered_token = f"eyRhbGllbiI6IHRydWV9.{parts[1]}"
        self.assertIsNone(verify_token(tampered_token))

        # Bogus string
        self.assertIsNone(verify_token("invalid.bogus.token"))
        self.assertIsNone(verify_token(""))

    def test_02_firetv_approval_attempt_rejected(self):
        """Fire TV Glass terminal is strictly forbidden from approving consequential actions."""
        req_id = queue_sentinel_request(
            agent="GUARDIAN",
            action_class="NETWORK_DEFENSE",
            action_type="ISOLATE_HOST",
            target="10.116.23.250",
            scope={"interface": "wlan0"},
            risk_level="R4_CRITICAL",
            ttl_seconds=300,
            db_path=self.db_path
        )
        # Attempt approval with FIRETV_GLASS role
        ok, reason = resolve_sentinel_request(
            req_id, 
            approved=True, 
            resolver="FireTV_Remote", 
            resolver_role=ROLE_FIRETV_GLASS,
            db_path=self.db_path
        )
        self.assertFalse(ok)
        self.assertIn("POCO_AUTHORITY_REQUIRED", reason)

        # Verify request remains pending
        is_auth, req, _ = check_sentinel_authorization(req_id, db_path=self.db_path)
        self.assertFalse(is_auth)

    def test_03_altered_target_mismatch_rejected(self):
        """An approval granted for Target A cannot be used to execute on Target B."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="DEVELOPER_EXECUTION",
            action_type="TYPED_OP_FILE_REMOVE",
            target="rm file_remove",
            scope={"target": "temp.txt"},
            risk_level="R3_HIGH",
            ttl_seconds=300,
            db_path=self.db_path
        )
        # Legitimate POCO approval
        ok, _ = resolve_sentinel_request(req_id, approved=True, resolver="Aadi", resolver_role=ROLE_POCO_CORE, db_path=self.db_path)
        self.assertTrue(ok)

        # Attempt to consume with altered target
        is_consumed, _, reason = consume_sentinel_authorization(
            req_id, 
            expected_target="rm different_operation",
            expected_action="TYPED_OP_FILE_REMOVE",
            db_path=self.db_path
        )
        self.assertFalse(is_consumed)
        self.assertIn("TARGET_MISMATCH", reason)

    def test_04_sentinel_replay_rejected_atomically_consumed(self):
        """An approval order is single-use: subsequent reuse attempts must be rejected."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="DEVELOPER_EXECUTION",
            action_type="TYPED_OP_FILE_REMOVE",
            target="rm file_remove",
            scope={"target": "temp.txt"},
            risk_level="R3_HIGH",
            ttl_seconds=300,
            db_path=self.db_path
        )
        ok, _ = resolve_sentinel_request(req_id, approved=True, resolver="Aadi", resolver_role=ROLE_POCO_CORE, db_path=self.db_path)
        self.assertTrue(ok)

        # First consumption: SUCCESS
        is_consumed, _, reason = consume_sentinel_authorization(
            req_id,
            expected_target="rm file_remove",
            expected_action="TYPED_OP_FILE_REMOVE",
            db_path=self.db_path
        )
        self.assertTrue(is_consumed)
        self.assertEqual(reason, "CONSUMED_SUCCESS")

        # Second consumption (Replay Attack): REJECTED
        is_replayed, _, replay_reason = consume_sentinel_authorization(
            req_id,
            expected_target="rm file_remove",
            expected_action="TYPED_OP_FILE_REMOVE",
            db_path=self.db_path
        )
        self.assertFalse(is_replayed)
        self.assertIn("ALREADY_CONSUMED", replay_reason)

    def test_05_expired_approval_rejected(self):
        """Expired approvals (TTL elapsed) must not be executable."""
        req_id = queue_sentinel_request(
            agent="SYSTEM",
            action_class="MAINTENANCE",
            action_type="TEST_EXPIRE",
            target="test_target",
            scope={"test": True},
            risk_level="R1_LOW",
            ttl_seconds=1, # 1 second TTL
            db_path=self.db_path
        )
        resolve_sentinel_request(req_id, approved=True, resolver="Aadi", resolver_role=ROLE_POCO_CORE, db_path=self.db_path)

        # Wait for TTL expiry
        time.sleep(1.2)

        is_consumed, _, reason = consume_sentinel_authorization(
            req_id,
            expected_target="test_target",
            expected_action="TEST_EXPIRE",
            db_path=self.db_path
        )
        self.assertFalse(is_consumed)
        self.assertIn("EXPIRED", reason)

    def test_06_execution_blocked_in_sanctuary_mode(self):
        """Consequential developer operations must be blocked if Sanctuary Mode is active."""
        engage_sanctuary(actor="Aadi", actor_role="POCO_CORE", reason="Automated Security Test")
        try:
            res = execute_typed_operation("file_remove", extra_args=["dummy.txt"], sentinel_request_id="some_id")
            self.assertFalse(res["success"])
            self.assertIn("Sanctuary", res.get("error", ""))
        finally:
            release_sanctuary(actor="Aadi", actor_role="POCO_CORE")

    def test_07_protected_resource_removal_rejected(self):
        """Attempts to delete critical repositories or databases must be rejected."""
        res = execute_typed_operation("file_remove", extra_args=["aeonix_vault.db"], sentinel_request_id=None)
        self.assertFalse(res["success"])
        # Should be caught by path/resource protection or sentinel gate
        self.assertTrue("PROTECTED_RESOURCE" in res.get("error", "") or res.get("status") == "sentinel_gate_hold")


if __name__ == "__main__":
    unittest.main()
