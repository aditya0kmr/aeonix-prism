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
8. Exact argument and directory scope binding mismatch rejection.
9. Protected resource removal rejection even under valid POCO approval.
10. Strict execution lifecycle state transitions (pending -> approved -> claimed -> completed).
11. REST API authentication enforcement (401 unauthenticated, 403 role violation).
12. WebSocket handshake rejection without token / forged token, and acceptance with valid token.
13. Disaster recovery maintenance mode lock and automatic safety rollback on corrupted archive.
"""

import os
import unittest
import time
import tempfile
import sqlite3
import tarfile
import json
import shutil
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from aeonix.core.db import (
    init_database, 
    queue_sentinel_request, 
    resolve_sentinel_request, 
    consume_sentinel_authorization,
    claim_sentinel_authorization,
    complete_sentinel_execution,
    check_sentinel_authorization,
    log_audit_event,
    verify_audit_chain,
    get_connection
)
from aeonix.core.auth import issue_device_token, verify_token, ROLE_POCO_CORE, ROLE_FIRETV_GLASS, ROLE_AGENT_EXECUTOR
from aeonix.core.forge import execute_typed_operation
from aeonix.core.sanctuary import engage_sanctuary, release_sanctuary
from aeonix.core.server import app
from aeonix.core.backup import create_vault_backup, restore_vault_backup, is_maintenance_mode, compute_sha256

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

    def test_08_scope_mismatch_arguments_and_cwd_rejected(self):
        """Approval granted for specific arguments and directory cannot be repurposed."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="DEVELOPER_EXECUTION",
            action_type="TYPED_OP_FILE_REMOVE",
            target="file_remove /tmp/safe/temp_a.txt",
            scope={"cwd": "/tmp/safe", "extra_args": ["temp_a.txt"]},
            risk_level="R3_HIGH",
            ttl_seconds=300,
            db_path=self.db_path
        )
        # POCO approval
        ok, _ = resolve_sentinel_request(req_id, approved=True, resolver="Aadi", resolver_role=ROLE_POCO_CORE, db_path=self.db_path)
        self.assertTrue(ok)

        # 1. Attempt to claim with modified extra_args (temp_b.txt)
        is_claimed, _, reason = claim_sentinel_authorization(
            req_id,
            expected_target="file_remove /tmp/safe/temp_a.txt",
            expected_action="TYPED_OP_FILE_REMOVE",
            expected_scope={"cwd": "/tmp/safe", "extra_args": ["temp_b.txt"]},
            db_path=self.db_path
        )
        self.assertFalse(is_claimed)
        self.assertIn("SCOPE_MISMATCH", reason)

        # 2. Attempt to claim with modified cwd
        is_claimed, _, reason = claim_sentinel_authorization(
            req_id,
            expected_target="file_remove /tmp/safe/temp_a.txt",
            expected_action="TYPED_OP_FILE_REMOVE",
            expected_scope={"cwd": "/tmp/other_dir", "extra_args": ["temp_a.txt"]},
            db_path=self.db_path
        )
        self.assertFalse(is_claimed)
        self.assertIn("SCOPE_MISMATCH", reason)

    def test_09_protected_resource_removal_rejected_under_valid_approval(self):
        """Even if an attacker tricks approval for .git or vault.db, Forge must halt and mark failed."""
        safe_dir = tempfile.mkdtemp(prefix="aeonix_prot_test_")
        target_path = os.path.join(safe_dir, ".git")
        exact_target = "rm file_remove .git"
        expected_scope = {"cwd": safe_dir, "extra_args": [".git"], "operation": "file_remove"}

        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="DEVELOPER_EXECUTION",
            action_type="TYPED_OP_FILE_REMOVE",
            target=exact_target,
            scope=expected_scope,
            risk_level="R4_CRITICAL",
            ttl_seconds=300,
            db_path=self.db_path
        )
        # Simulate approval granted by POCO
        ok, _ = resolve_sentinel_request(req_id, approved=True, resolver="Aadi", resolver_role=ROLE_POCO_CORE, db_path=self.db_path)
        self.assertTrue(ok)

        # Execute Forge operation with valid request_id
        res = execute_typed_operation(
            operation_name="file_remove",
            extra_args=[".git"],
            cwd=safe_dir,
            sentinel_request_id=req_id,
            actor="Aadi",
            actor_role=ROLE_POCO_CORE,
            db_path=self.db_path
        )
        self.assertFalse(res["success"])
        self.assertIn("PROTECTED_RESOURCE", res.get("error", ""))

        # Check Sentinel request status transitioned to 'failed' in database
        conn = get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status FROM sentinel_requests WHERE id = ?;", (req_id,))
        status = cur.fetchone()["status"]
        conn.close()
        self.assertEqual(status, "failed")

    def test_10_execution_lifecycle_state_transitions(self):
        """Verifies full lifecycle states: pending -> approved -> claimed -> completed."""
        req_id = queue_sentinel_request(
            agent="TEST",
            action_class="LIFECYCLE_TEST",
            action_type="TEST_OP",
            target="target_lifecycle",
            scope={"test": True},
            risk_level="R2_MODERATE",
            ttl_seconds=300,
            db_path=self.db_path
        )
        conn = get_connection(self.db_path)
        
        # 1. Verify pending
        cur = conn.cursor()
        cur.execute("SELECT status FROM sentinel_requests WHERE id = ?;", (req_id,))
        self.assertEqual(cur.fetchone()["status"], "pending")

        # 2. Approve
        resolve_sentinel_request(req_id, approved=True, resolver="Aadi", resolver_role=ROLE_POCO_CORE, db_path=self.db_path)
        cur.execute("SELECT status FROM sentinel_requests WHERE id = ?;", (req_id,))
        self.assertEqual(cur.fetchone()["status"], "approved")

        # 3. Claim
        is_claimed, _, _ = claim_sentinel_authorization(
            req_id, 
            expected_target="target_lifecycle", 
            expected_action="TEST_OP", 
            expected_scope={"test": True}, 
            db_path=self.db_path
        )
        self.assertTrue(is_claimed)
        cur.execute("SELECT status FROM sentinel_requests WHERE id = ?;", (req_id,))
        self.assertEqual(cur.fetchone()["status"], "claimed")

        # Attempt to claim while already claimed -> must fail
        is_reclaim, _, reason = claim_sentinel_authorization(
            req_id, 
            expected_target="target_lifecycle", 
            expected_action="TEST_OP", 
            db_path=self.db_path
        )
        self.assertFalse(is_reclaim)
        self.assertIn("ALREADY_CONSUMED", reason)

        # 4. Complete
        complete_sentinel_execution(req_id, success=True, output_summary="Execution succeeded", db_path=self.db_path)
        cur.execute("SELECT status FROM sentinel_requests WHERE id = ?;", (req_id,))
        self.assertEqual(cur.fetchone()["status"], "completed")

        # Attempt to claim while completed -> must fail
        is_reclaim2, _, reason2 = claim_sentinel_authorization(
            req_id, 
            expected_target="target_lifecycle", 
            expected_action="TEST_OP", 
            db_path=self.db_path
        )
        self.assertFalse(is_reclaim2)
        self.assertIn("ALREADY_CONSUMED", reason2)
        conn.close()

    def test_11_rest_api_auth_rejection_and_role_enforcement(self):
        """Verifies HTTP endpoints strictly enforce 401 unauthenticated and 403 role violation."""
        client = TestClient(app)

        # 1. /api/sentinel/resolve without auth -> 401
        r = client.post("/api/sentinel/resolve", json={"request_id": "test_id", "approved": True})
        self.assertEqual(r.status_code, 401)
        self.assertIn("authorization header", r.json().get("error", ""))

        # 2. /api/sentinel/resolve with forged token -> 401
        r = client.post("/api/sentinel/resolve", json={"request_id": "test_id", "approved": True}, headers={"Authorization": "Bearer forged.bad.token"})
        self.assertEqual(r.status_code, 401)

        # 3. /api/sentinel/resolve with Fire TV token (approved=True) -> 403 POCO_AUTHORITY_REQUIRED
        tv_token = issue_device_token("firetv_stick_lite", ROLE_FIRETV_GLASS)
        r = client.post("/api/sentinel/resolve", json={"request_id": "test_id", "approved": True}, headers={"Authorization": f"Bearer {tv_token}"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("POCO_AUTHORITY_REQUIRED", r.json().get("error", ""))

        # 4. /api/forge/execute without auth -> 401
        r = client.post("/api/forge/execute", json={"operation": "file_remove"})
        self.assertEqual(r.status_code, 401)

        # 5. /api/forge/execute with Fire TV token -> 403 FORBIDDEN
        r = client.post("/api/forge/execute", json={"operation": "file_remove"}, headers={"Authorization": f"Bearer {tv_token}"})
        self.assertEqual(r.status_code, 403)

        # 6. /api/sanctuary/activate without auth -> 401
        r = client.post("/api/sanctuary/activate")
        self.assertEqual(r.status_code, 401)

        # 7. /api/sanctuary/activate with Fire TV token -> 403 POCO_AUTHORITY_REQUIRED
        r = client.post("/api/sanctuary/activate", headers={"Authorization": f"Bearer {tv_token}"})
        self.assertEqual(r.status_code, 403)

    def test_12_websocket_unauthenticated_handshake_rejected(self):
        """Verifies WebSocket endpoint rejects missing, query param, or forged tokens and accepts valid header tokens."""
        client = TestClient(app)

        # 1. Handshake without token -> rejected
        with self.assertRaises(WebSocketDisconnect) as cm:
            with client.websocket_connect("/ws") as ws:
                pass
        self.assertEqual(cm.exception.code, 4401)

        # 2. Handshake with token in query string -> strictly rejected with 4401 (URL token leakage prevention)
        tv_token = issue_device_token("firetv_stick_lite", ROLE_FIRETV_GLASS)
        with self.assertRaises(WebSocketDisconnect) as cm:
            with client.websocket_connect(f"/ws?token={tv_token}") as ws:
                pass
        self.assertEqual(cm.exception.code, 4401)

        # 3. Handshake with forged token in Authorization header -> rejected with code 4401
        with self.assertRaises(WebSocketDisconnect) as cm:
            with client.websocket_connect("/ws", headers={"Authorization": "Bearer forged.invalid.token"}) as ws:
                pass
        self.assertEqual(cm.exception.code, 4401)

        # 4. Handshake with valid Fire TV token via RFC 6455 Authorization header -> accepted
        with client.websocket_connect("/ws", headers={"Authorization": f"Bearer {tv_token}"}) as ws:
            msg = ws.receive_json()
            self.assertEqual(msg.get("type"), "layout_update")

    def test_13_maintenance_mode_and_automatic_restore_rollback(self):
        """Verifies maintenance mode locking and automatic rollback when post-restore audit fails."""
        td = tempfile.mkdtemp(prefix="aeonix_maint_test_")
        target_db = os.path.join(td, "target_vault.db")
        init_database(target_db)
        log_audit_event("INIT", "test_entry", "system", "ok", {"state": 1}, db_path=target_db)
        self.assertTrue(verify_audit_chain(target_db)["is_valid"])

        # Check maintenance mode is False initially
        self.assertFalse(is_maintenance_mode())

        # Create a corrupt archive to force post-restore failure
        extract_dir = tempfile.mkdtemp(prefix="aeonix_corrupt_")
        corrupt_db = os.path.join(extract_dir, "aeonix_vault.db")
        shutil.copy2(target_db, corrupt_db)
        
        # Corrupt the audit chain in corrupt_db
        conn = sqlite3.connect(corrupt_db)
        conn.execute("UPDATE audit_log SET actor = 'TAMPERED_ATTACKER' WHERE id = 1;")
        conn.commit()
        conn.close()

        manifest = {
            "backup_id": "test_corrupt",
            "created_at": time.time(),
            "actor": "Attacker",
            "schema_version": "2.0",
            "db_file": "aeonix_vault.db",
            "db_sha256": compute_sha256(corrupt_db),
            "total_audit_events": 1,
            "encrypted": False
        }
        manifest_path = os.path.join(extract_dir, "manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        corrupt_tar = os.path.join(td, "corrupt_backup.tar.gz")
        with tarfile.open(corrupt_tar, "w:gz") as tar:
            tar.add(manifest_path, arcname="manifest.json")
            tar.add(corrupt_db, arcname="aeonix_vault.db")

        # Attempt restore with force=True (to bypass pre-extract check and test active post-replacement rollback)
        res = restore_vault_backup(corrupt_tar, target_db_path=target_db, force=True)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "RESTORE_FAILED_ROLLED_BACK")

        # Maintenance mode must be released back to False
        self.assertFalse(is_maintenance_mode())

        # Original database must be preserved and intact
        chain_check = verify_audit_chain(target_db)
        self.assertTrue(chain_check["is_valid"])


if __name__ == "__main__":
    unittest.main()
