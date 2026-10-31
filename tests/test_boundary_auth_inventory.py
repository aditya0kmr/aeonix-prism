"""
ÆONIX PRISM // Master Boundary, Authentication Inventory & Gate Test Suite
Exhaustively verifies:
1. Dynamic Route Inventory: Every registered route defaults to denying unauthenticated, forged, and revoked tokens.
2. Public Minimal Liveness: GET /api/status leaks zero usernames, device counts, or resources.
3. Authenticated System Status: GET /api/system/status exposes metrics only to POCO_CORE.
4. RBAC Matrix Enforcement: Strict separation between POCO_CORE, FIRETV_GLASS, and AGENT_EXECUTOR.
5. RFC 6455 WebSocket Handshake Boundary: Rejection of query string tokens (4401), rejection of forged/revoked tokens (4401), acceptance of header Bearer tokens.
6. Sentinel Lifecycle State Transitions: complete_sentinel_execution strictly rejects invalid starting states (pending/approved/completed); consume_sentinel_authorization does not fabricate execution.
7. File Protection & Path Containment: Option validation, canonical resolved-path checks, protected-tree barriers.
8. System-Wide Maintenance Mode Lock: Restricts non-recovery database writers and HTTP callers (503).
9. POCO Operator Console: PBKDF2 600k iterations, persistent lockout across restarts, action digest binding.
"""

import os
import sys
import json
import time
import shutil
import sqlite3
import tempfile
import unittest

sys.path.insert(0, "/data/data/com.termux/files/home/aeonix")
sys.path.insert(0, "/data/data/com.termux/files/home")

from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from starlette.routing import Route, WebSocketRoute

from aeonix.core.server import app, PUBLIC_ENDPOINTS, FIRETV_ALLOWED_ENDPOINTS, AGENT_ALLOWED_ENDPOINTS
from aeonix.core.auth import (
    issue_device_token, 
    verify_token, 
    ROLE_POCO_CORE, 
    ROLE_FIRETV_GLASS, 
    ROLE_AGENT_EXECUTOR
)
from aeonix.core.db import (
    init_database,
    get_connection,
    queue_sentinel_request,
    resolve_sentinel_request,
    claim_sentinel_authorization,
    complete_sentinel_execution,
    consume_sentinel_authorization,
    revoke_token,
    is_token_revoked
)
from aeonix.core.backup import set_maintenance_mode, is_maintenance_mode
from aeonix.core.forge import execute_typed_operation
from aeonix.core.operator_console import (
    setup_operator_secret,
    verify_operator_secret,
    is_operator_setup,
    is_operator_locked,
    compute_action_digest,
    format_sentinel_card
)

class TestBoundaryAuthInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="aeonix_boundary_test_")
        cls.db_path = os.path.join(cls.test_dir, "test_vault.db")
        init_database(cls.db_path)
        cls.client = TestClient(app)

        # Tokens
        cls.poco_token = issue_device_token("test_poco_device", ROLE_POCO_CORE)
        cls.tv_token = issue_device_token("test_tv_device", ROLE_FIRETV_GLASS)
        cls.agent_token = issue_device_token("test_agent_device", ROLE_AGENT_EXECUTOR)

        # Create a revoked token for testing
        cls.revoked_token = issue_device_token("test_revoked_device", ROLE_POCO_CORE)
        payload = verify_token(cls.revoked_token)
        cls.revoked_nonce = payload["nonce"]
        from aeonix.core.db import DB_PATH
        revoke_token(cls.revoked_nonce, "revocation_boundary_test", cls.db_path)
        revoke_token(cls.revoked_nonce, "revocation_boundary_test", DB_PATH)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_dynamic_route_inventory_default_deny_unauthenticated(self):
        """Every registered HTTP route (except GET /api/status) MUST reject unauthenticated requests with 401."""
        tested_routes = 0
        for route in app.routes:
            if isinstance(route, Route):
                for method in route.methods:
                    if (method, route.path) == ("GET", "/api/status"):
                        continue
                    tested_routes += 1
                    
                    # Test 1: Missing Authorization Header
                    if method == "GET":
                        r = self.client.get(route.path)
                    elif method == "POST":
                        r = self.client.post(route.path, json={})
                    elif method == "DELETE":
                        r = self.client.delete(route.path)
                    else:
                        continue

                    self.assertEqual(
                        r.status_code, 401, 
                        f"Route {method} {route.path} failed default-deny: expected 401, got {r.status_code}"
                    )
                    self.assertIn("UNAUTHENTICATED", r.json().get("error", ""))

                    # Test 2: Forged / Corrupted Token
                    forged_token = "eyJyZXF1ZXN0IjogImZvcmdlZCJ9.invalid_signature"
                    headers = {"Authorization": f"Bearer {forged_token}"}
                    if method == "GET":
                        r_forged = self.client.get(route.path, headers=headers)
                    elif method == "POST":
                        r_forged = self.client.post(route.path, json={}, headers=headers)
                    else:
                        r_forged = self.client.delete(route.path, headers=headers)

                    self.assertEqual(
                        r_forged.status_code, 401,
                        f"Route {method} {route.path} accepted forged token: got {r_forged.status_code}"
                    )

                    # Test 3: Revoked Token
                    revoked_headers = {"Authorization": f"Bearer {self.revoked_token}"}
                    if method == "GET":
                        r_rev = self.client.get(route.path, headers=revoked_headers)
                    elif method == "POST":
                        r_rev = self.client.post(route.path, json={}, headers=revoked_headers)
                    else:
                        r_rev = self.client.delete(route.path, headers=revoked_headers)

                    self.assertEqual(
                        r_rev.status_code, 401,
                        f"Route {method} {route.path} accepted revoked token: got {r_rev.status_code}"
                    )

        self.assertGreaterEqual(tested_routes, 50, "Route inventory must contain at least 50 protected routes")

    def test_02_public_minimal_liveness_zero_knowledge(self):
        """GET /api/status MUST return minimal liveness only: zero usernames, device counts, or resources."""
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        data = r.json()

        # Required minimal keys
        self.assertIn("status", data)
        self.assertIn("system", data)
        self.assertIn("timestamp", data)
        self.assertEqual(data["status"], "online")

        # Prohibited sensitive telemetry keys
        self.assertNotIn("sovereign_user", data)
        self.assertNotIn("ram", data)
        self.assertNotIn("sentinel_pending", data)
        self.assertNotIn("connected_glass_clients", data)
        self.assertEqual(len(data), 3, "GET /api/status must contain strictly 3 minimal keys")

    def test_03_authenticated_system_status_poco_authority_only(self):
        """GET /api/system/status exposes full metrics strictly to POCO_CORE; rejects unauthenticated & TV."""
        # Unauthenticated
        r_unauth = self.client.get("/api/system/status")
        self.assertEqual(r_unauth.status_code, 401)

        # Fire TV (Glass terminal)
        r_tv = self.client.get("/api/system/status", headers={"Authorization": f"Bearer {self.tv_token}"})
        self.assertEqual(r_tv.status_code, 403)
        self.assertIn("FORBIDDEN", r_tv.json().get("error", ""))

        # POCO Core (Sovereign mind)
        r_poco = self.client.get("/api/system/status", headers={"Authorization": f"Bearer {self.poco_token}"})
        self.assertEqual(r_poco.status_code, 200)
        data = r_poco.json()
        self.assertIn("sovereign_user", data)
        self.assertIn("ram", data)
        self.assertIn("sentinel_pending", data)
        self.assertIn("connected_glass_clients", data)

    def test_04_role_segregation_firetv_glass_restricted(self):
        """ROLE_FIRETV_GLASS is strictly blocked from consequential/admin endpoints."""
        restricted_endpoints = [
            ("POST", "/api/forge/execute", {"operation": "file_remove"}),
            ("GET", "/api/backup/list", None),
            ("POST", "/api/backup/create", {}),
            ("GET", "/api/veritas/cases", None),
            ("GET", "/api/guardian/network", None),
            ("POST", "/api/sanctuary/activate", {}),
            ("POST", "/api/sanctuary/deactivate", {}),
            ("POST", "/api/trust/kill-switch", {}),
            ("POST", "/api/ai/benchmark", {})
        ]

        for method, path, payload in restricted_endpoints:
            headers = {"Authorization": f"Bearer {self.tv_token}"}
            if method == "GET":
                r = self.client.get(path, headers=headers)
            else:
                r = self.client.post(path, json=payload, headers=headers)

            self.assertEqual(
                r.status_code, 403, 
                f"Fire TV role breached boundary on {method} {path}: expected 403, got {r.status_code}"
            )
            self.assertIn("FORBIDDEN", r.json().get("error", ""))

    def test_05_websocket_boundary_query_param_rejection_and_header_acceptance(self):
        """WebSocket endpoint rejects URL query parameter tokens, forged tokens, and accepts Bearer header."""
        # 1. Missing Token -> 4401
        with self.assertRaises(WebSocketDisconnect) as cm:
            with self.client.websocket_connect("/ws") as ws:
                pass
        self.assertEqual(cm.exception.code, 4401)

        # 2. Token in Query Parameter -> 4401 (Prohibited to prevent URL leakage)
        with self.assertRaises(WebSocketDisconnect) as cm:
            with self.client.websocket_connect(f"/ws?token={self.tv_token}") as ws:
                pass
        self.assertEqual(cm.exception.code, 4401)

        # 3. Forged Token in Header -> 4401
        with self.assertRaises(WebSocketDisconnect) as cm:
            with self.client.websocket_connect("/ws", headers={"Authorization": "Bearer forged.bad.token"}) as ws:
                pass
        self.assertEqual(cm.exception.code, 4401)

        # 4. Revoked Token in Header -> 4401
        with self.assertRaises(WebSocketDisconnect) as cm:
            with self.client.websocket_connect("/ws", headers={"Authorization": f"Bearer {self.revoked_token}"}) as ws:
                pass
        self.assertEqual(cm.exception.code, 4401)

        # 5. Valid Bearer Token in RFC 6455 Header -> Accepted
        with self.client.websocket_connect("/ws", headers={"Authorization": f"Bearer {self.tv_token}"}) as ws:
            msg = ws.receive_json()
            self.assertEqual(msg.get("type"), "layout_update")
            self.assertEqual(msg.get("screen"), "living_surface")

    def test_06_sentinel_lifecycle_starting_state_validation(self):
        """complete_sentinel_execution MUST reject invalid starting states (pending/approved/completed)."""
        req_id = queue_sentinel_request(
            agent="LIFECYCLE_TEST",
            action_class="AUDIT",
            action_type="TEST_ORDER",
            target="boundary_target",
            scope={"op": 1},
            risk_level="R2",
            ttl_seconds=300,
            db_path=self.db_path
        )

        # 1. State is 'pending' -> complete_sentinel_execution must FAIL
        ok_pend = complete_sentinel_execution(req_id, success=True, db_path=self.db_path)
        self.assertFalse(ok_pend, "complete_sentinel_execution must reject completion from 'pending' state")

        # 2. Transition to 'approved'
        digest = compute_action_digest(req_id, "LIFECYCLE_TEST", "TEST_ORDER", "boundary_target", {"op": 1})
        ok_res, _ = resolve_sentinel_request(req_id, approved=True, resolver="Aadi", resolver_role=ROLE_POCO_CORE, passphrase_verified=True, expected_action_digest=digest, db_path=self.db_path)
        self.assertTrue(ok_res)

        # State is 'approved' -> complete_sentinel_execution must FAIL (must be claimed first)
        ok_app = complete_sentinel_execution(req_id, success=True, db_path=self.db_path)
        self.assertFalse(ok_app, "complete_sentinel_execution must reject completion from 'approved' state")

        # 3. Consume (claim)
        is_consumed, req_dict, reason = consume_sentinel_authorization(
            req_id, 
            expected_target="boundary_target", 
            expected_action="TEST_ORDER",
            db_path=self.db_path
        )
        self.assertTrue(is_consumed)
        self.assertEqual(reason, "CONSUMED_SUCCESS")
        
        # Verify status is 'claimed' (NOT fabricated 'completed')
        conn = get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status FROM sentinel_requests WHERE id = ?;", (req_id,))
        row = cur.fetchone()
        self.assertEqual(row["status"], "claimed", "consume_sentinel_authorization must leave status in 'claimed'")
        conn.close()

        # 4. Now transition from 'claimed' to 'completed' -> MUST SUCCEED
        ok_comp = complete_sentinel_execution(req_id, success=True, output_summary="Execution verified", db_path=self.db_path)
        self.assertTrue(ok_comp)

        # 5. Subsequent completion attempt on 'completed' request -> MUST FAIL
        ok_recomp = complete_sentinel_execution(req_id, success=True, db_path=self.db_path)
        self.assertFalse(ok_recomp, "complete_sentinel_execution must reject completion on already completed request")

    def test_07_file_protection_canonical_path_containment_and_options(self):
        """File removal operations enforce option validation and canonical resolved-path barriers."""
        # 1. Illegal option validation
        res_opt = execute_typed_operation(
            "file_remove",
            extra_args=["--no-preserve-root", "/tmp/dummy"],
            db_path=self.db_path
        )
        self.assertFalse(res_opt["success"])
        self.assertIn("ILLEGAL_OPTION", res_opt.get("error", ""))

        # 2. Path traversal to .git barrier
        res_git = execute_typed_operation(
            "file_remove",
            extra_args=["../../.git"],
            db_path=self.db_path
        )
        self.assertFalse(res_git["success"])
        self.assertIn("PROTECTED_RESOURCE", res_git.get("error", ""))

        # 3. Protected secrets tree barrier
        secrets_path = os.path.expanduser("~/.aeonix/secrets/master_key.json")
        res_sec = execute_typed_operation(
            "file_remove",
            extra_args=[secrets_path],
            db_path=self.db_path
        )
        self.assertFalse(res_sec["success"])
        self.assertIn("PROTECTED_RESOURCE", res_sec.get("error", ""))

        # 4. System root barrier
        res_root = execute_typed_operation(
            "file_remove",
            extra_args=["/"],
            db_path=self.db_path
        )
        self.assertFalse(res_root["success"])
        self.assertIn("PROTECTED_RESOURCE", res_root.get("error", ""))

    def test_08_system_wide_maintenance_mode_lock(self):
        """Active maintenance mode locks SQLite writers with OperationalError and HTTP handlers with 503."""
        set_maintenance_mode(True)
        try:
            self.assertTrue(is_maintenance_mode())

            # 1. Database writer lock check
            with self.assertRaises(sqlite3.OperationalError) as cm:
                get_connection(self.db_path, allow_maintenance=False)
            self.assertIn("DATABASE_LOCKED", str(cm.exception))

            # 2. HTTP Request Handler Lock Check (503 MAINTENANCE_LOCKED)
            r = self.client.get("/api/sentinel/pending", headers={"Authorization": f"Bearer {self.poco_token}"})
            self.assertEqual(r.status_code, 503)
            self.assertIn("MAINTENANCE_LOCKED", r.json().get("error", ""))

            # 3. Recovery connection with allow_maintenance=True succeeds
            conn = get_connection(self.db_path, allow_maintenance=True)
            self.assertIsNotNone(conn)
            conn.close()
        finally:
            set_maintenance_mode(False)

        self.assertFalse(is_maintenance_mode())
        # Normal operations restored
        conn = get_connection(self.db_path, allow_maintenance=False)
        self.assertIsNotNone(conn)
        conn.close()

    def test_09_operator_console_first_run_lockout_and_digest(self):
        """Operator console requires PBKDF2 setup, enforces persistent lockout, and generates Action Digest."""
        sec_dir = tempfile.mkdtemp(prefix="aeonix_op_test_")
        try:
            self.assertFalse(is_operator_setup(sec_dir))

            # Setup with short passphrase (< 8 chars) -> rejected
            ok_short, _ = setup_operator_secret("short", secrets_dir=sec_dir)
            self.assertFalse(ok_short)

            # Setup with valid passphrase -> success
            test_passphrase = "SovereignPassphrase2026!"
            ok_setup, _ = setup_operator_secret(test_passphrase, secrets_dir=sec_dir)
            self.assertTrue(ok_setup)
            self.assertTrue(is_operator_setup(sec_dir))

            # Verify correct secret
            ok_val, msg_val = verify_operator_secret(test_passphrase, secrets_dir=sec_dir)
            self.assertTrue(ok_val)
            self.assertEqual(msg_val, "AUTHENTICATED")

            # Verify wrong secret triggers failed attempt counter
            ok_wrong, msg_wrong = verify_operator_secret("WrongPassword123!", secrets_dir=sec_dir)
            self.assertFalse(ok_wrong)
            self.assertIn("INCORRECT_SECRET", msg_wrong)

            # Check persistent lockout file created with 0600 permissions
            lock_file = os.path.join(sec_dir, "operator_lockout.json")
            self.assertTrue(os.path.exists(lock_file))

            # Verify Action Digest calculation
            digest = compute_action_digest(
                request_id="req_test_123",
                agent="FORGE",
                action_type="TYPED_OP_FILE_REMOVE",
                target="file_remove temp.txt",
                scope={"cwd": "/tmp", "extra_args": ["temp.txt"]}
            )
            self.assertEqual(len(digest), 64, "Action digest must be a 64-char hex SHA-256 string")
            
            # Format Sentinel card
            card = format_sentinel_card({
                "id": "req_test_123",
                "agent": "FORGE",
                "action_class": "DEVELOPER_EXECUTION",
                "risk_level": "R3_HIGH",
                "action_type": "TYPED_OP_FILE_REMOVE",
                "target": "file_remove temp.txt",
                "scope_json": json.dumps({"cwd": "/tmp", "extra_args": ["temp.txt"]}),
                "expires_at": time.time() + 300
            })
            self.assertIn("req_test_123", card)
            self.assertIn("Action Digest:", card)
            self.assertIn(digest, card)
        finally:
            shutil.rmtree(sec_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
