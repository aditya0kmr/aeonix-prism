"""
ÆONIX PRISM // Stage 1 Foundation & Security Unit Tests
Tests:
1. Authentication & Role-based device tokens (issuance, verification, expiry, revocation)
2. POCO-only Sentinel approval authority & atomic rejection of expired/replayed requests
3. Cryptographic Signed Execution Orders (HMAC-SHA256, payload digest, replay prevention)
4. Persistent Emergency Kill Switch & Sanctuary Privacy Lockdown
5. Sandboxed Typed Forge Operations (shell=False, metacharacter filtering, output bounding)
"""

import unittest
import time
import os
import json
import secrets

from aeonix.core.auth import (
    issue_device_token, 
    verify_token, 
    ROLE_POCO_CORE, 
    ROLE_FIRETV_GLASS, 
    ROLE_AGENT_EXECUTOR
)
from aeonix.core.db import (
    init_database, 
    queue_sentinel_request, 
    resolve_sentinel_request, 
    check_sentinel_authorization,
    revoke_token,
    is_token_revoked
)
from aeonix.core.trust import trust
from aeonix.core.sanctuary import (
    engage_sanctuary, 
    release_sanctuary, 
    is_sanctuary_active
)
from aeonix.core.forge import (
    execute_typed_operation, 
    draft_command_from_prompt, 
    TYPED_OPERATIONS
)

class TestStage1Security(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def setUp(self):
        # Reset kill switch and sanctuary before each test
        trust.reset_kill_switch(actor_role=ROLE_POCO_CORE)
        release_sanctuary(actor_role=ROLE_POCO_CORE)

    def test_auth_token_issuance_and_verification(self):
        """Test cryptographic bearer token issuance and constant-time verification."""
        token = issue_device_token("poco_test_device", ROLE_POCO_CORE, ttl_seconds=60)
        self.assertIsInstance(token, str)
        self.assertIn(".", token)

        payload = verify_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["device_id"], "poco_test_device")
        self.assertEqual(payload["role"], ROLE_POCO_CORE)

    def test_auth_token_tampering_rejected(self):
        """Tampered tokens must be cryptographically rejected."""
        token = issue_device_token("poco_test_device", ROLE_POCO_CORE, ttl_seconds=60)
        b64_payload, b64_sig = token.split(".", 1)
        
        # Tamper payload
        tampered_token = f"{b64_payload[:-2]}AA.{b64_sig}"
        self.assertIsNone(verify_token(tampered_token))

        # Tamper signature
        tampered_sig_token = f"{b64_payload}.{b64_sig[:-2]}00"
        self.assertIsNone(verify_token(tampered_sig_token))

    def test_auth_token_expiration(self):
        """Expired tokens must be rejected."""
        expired_token = issue_device_token("short_lived", ROLE_FIRETV_GLASS, ttl_seconds=-5)
        self.assertIsNone(verify_token(expired_token))

    def test_auth_token_revocation(self):
        """Revoked tokens must be permanently rejected."""
        token = issue_device_token("revocable_node", ROLE_FIRETV_GLASS, ttl_seconds=3600)
        payload = verify_token(token)
        self.assertIsNotNone(payload)

        # Revoke nonce
        revoke_token(payload["nonce"], reason="Test Revocation")
        self.assertTrue(is_token_revoked(payload["nonce"]))
        self.assertIsNone(verify_token(token))

    def test_poco_only_approval_authority(self):
        """POCO_CORE can approve, but FIRETV_GLASS is strictly rejected when attempting approval."""
        req_id = queue_sentinel_request(
            agent="TEST_AGENT",
            action_class="consequential",
            action_type="TEST_ACTION",
            target="test_target",
            scope={"reason": "test"},
            risk_level="R3",
            ttl_seconds=300
        )

        # 1. Fire TV attempts to approve -> MUST BE REJECTED
        tv_ok, tv_reason = resolve_sentinel_request(
            req_id=req_id,
            approved=True,
            resolver="FireTV_Remote",
            resolver_role=ROLE_FIRETV_GLASS
        )
        self.assertFalse(tv_ok)
        self.assertIn("POCO_AUTHORITY_REQUIRED", tv_reason)

        # 2. POCO approves -> MUST SUCCEED
        poco_ok, poco_reason = resolve_sentinel_request(
            req_id=req_id,
            approved=True,
            resolver="Operator_Aadi",
            resolver_role=ROLE_POCO_CORE,
            passphrase_verified=True
        )
        self.assertTrue(poco_ok)
        self.assertEqual(poco_reason, "approved")

    def test_firetv_safe_denial_permitted(self):
        """Fire TV is allowed to safely deny/cancel requests."""
        req_id = queue_sentinel_request(
            agent="TEST_AGENT",
            action_class="consequential",
            action_type="TEST_CANCEL",
            target="test_target",
            scope={},
            risk_level="R3",
            ttl_seconds=300
        )
        tv_ok, tv_reason = resolve_sentinel_request(
            req_id=req_id,
            approved=False,
            resolver="FireTV_Remote",
            resolver_role=ROLE_FIRETV_GLASS
        )
        self.assertTrue(tv_ok)
        self.assertEqual(tv_reason, "denied")

    def test_sentinel_rejection_of_already_resolved(self):
        """Attempting to resolve an already-resolved request must be atomically rejected."""
        req_id = queue_sentinel_request(
            agent="TEST_AGENT",
            action_class="consequential",
            action_type="ONCE_ONLY",
            target="test_target",
            scope={},
            risk_level="R3",
            ttl_seconds=300
        )
        ok1, _ = resolve_sentinel_request(req_id, approved=False, resolver="Aadi", resolver_role=ROLE_POCO_CORE)
        self.assertTrue(ok1)

        # Second attempt
        ok2, reason2 = resolve_sentinel_request(req_id, approved=True, resolver="Aadi", resolver_role=ROLE_POCO_CORE)
        self.assertFalse(ok2)
        self.assertIn("ALREADY_RESOLVED", reason2)

    def test_sentinel_rejection_of_expired_request(self):
        """Expired Sentinel requests must be rejected."""
        req_id = queue_sentinel_request(
            agent="TEST_AGENT",
            action_class="consequential",
            action_type="EXPIRE_TEST",
            target="test_target",
            scope={},
            risk_level="R3",
            ttl_seconds=-1 # Already expired!
        )
        ok, reason = resolve_sentinel_request(req_id, approved=True, resolver="Aadi", resolver_role=ROLE_POCO_CORE)
        self.assertFalse(ok)
        self.assertIn("EXPIRED", reason)

    def test_sentinel_strict_boolean_validation(self):
        """Passing non-boolean for approved must be rejected."""
        req_id = queue_sentinel_request(
            agent="TEST_AGENT", action_class="consequential", action_type="BOOL_TEST",
            target="target", scope={}, risk_level="R1", ttl_seconds=100
        )
        ok, reason = resolve_sentinel_request(req_id, approved="yes", resolver="Aadi", resolver_role=ROLE_POCO_CORE) # type: ignore
        self.assertFalse(ok)
        self.assertIn("INVALID_INPUT", reason)

    def test_cryptographic_signed_execution_order(self):
        """Test HMAC-SHA256 signed execution order generation and verification."""
        order = trust.generate_signed_order(
            mission_name="AuditNetworkMission",
            scope=["port_scan", "device_fingerprint"],
            target="10.116.23.0/24",
            user_verified=True,
            actor_role=ROLE_POCO_CORE,
            ttl_seconds=300
        )
        self.assertIn("signature", order)
        self.assertTrue(order["signature"].startswith(("POCO_SIGNED_", "HMAC_SHA256_")))
        self.assertTrue(order["user_verified"])

        is_valid, reason = trust.verify_order(order)
        self.assertTrue(is_valid)
        self.assertEqual(reason, "VERIFIED_VALID")

    def test_signed_order_tampering_detected(self):
        """Tampering with parameters or mission scope invalidates the cryptographic order."""
        order = trust.generate_signed_order(
            mission_name="TamperTest",
            scope=["read_only"],
            actor_role=ROLE_POCO_CORE
        )
        # Malicious modification: elevate scope
        order["scope"] = ["read_only", "delete_all_files"]

        is_valid, reason = trust.verify_order(order)
        self.assertFalse(is_valid)
        self.assertIn("TAMPERING_DETECTED", reason)

    def test_signed_order_replay_attack_prevention(self):
        """A consumed execution order nonce cannot be replayed."""
        order = trust.generate_signed_order(
            mission_name="ReplayTest",
            scope=["single_action"],
            actor_role=ROLE_POCO_CORE
        )
        # First verification consumes nonce -> Valid
        v1, _ = trust.verify_order(order)
        self.assertTrue(v1)

        # Replay attempt with same nonce -> MUST FAIL
        v2, reason2 = trust.verify_order(order)
        self.assertFalse(v2)
        self.assertIn("REPLAY_ATTACK_DETECTED", reason2)

    def test_persistent_kill_switch_blocks_operations(self):
        """Persistent kill switch halts orders and typed Forge executions."""
        trust.trigger_kill_switch(rationale="Operator emergency", actor_role=ROLE_POCO_CORE)
        self.assertTrue(trust.is_kill_switch_active())

        # Cannot generate signed orders
        with self.assertRaises(RuntimeError):
            trust.generate_signed_order("MissionWhilePaused", ["scope"], actor_role=ROLE_POCO_CORE)

        # Typed Forge execution blocked
        res = execute_typed_operation("disk_usage")
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "kill_switch_hold")

        # Recovery requires POCO_CORE authority
        fake_ok, fake_res = trust.reset_kill_switch(actor_role=ROLE_FIRETV_GLASS)
        self.assertFalse(fake_ok)
        self.assertTrue(trust.is_kill_switch_active())

        # Authorized reset
        real_ok, real_res = trust.reset_kill_switch(actor_role=ROLE_POCO_CORE)
        self.assertTrue(real_ok)
        self.assertFalse(trust.is_kill_switch_active())

    def test_sanctuary_mode_persistence_and_policy(self):
        """Sanctuary mode persistently engages and blocks tool executions."""
        res_eng = engage_sanctuary(actor="Aadi", actor_role=ROLE_POCO_CORE, reason="Privacy review")
        self.assertTrue(is_sanctuary_active())
        self.assertEqual(res_eng["theme"], "obsidian_crimson")

        # Forge operations blocked during Sanctuary
        res_forge = execute_typed_operation("memory_usage")
        self.assertFalse(res_forge["success"])
        self.assertEqual(res_forge["status"], "sanctuary_hold")

        release_sanctuary(actor="Aadi", actor_role=ROLE_POCO_CORE)
        self.assertFalse(is_sanctuary_active())

    def test_forge_typed_execution_safe(self):
        """Safe allowlisted operations run with shell=False without Sentinel hold."""
        res = execute_typed_operation("disk_usage")
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "completed")
        self.assertIn("Filesystem", res["output"])

    def test_forge_consequential_operation_sentinel_hold(self):
        """Consequential operations halt at Sentinel Gate when request_id is not provided."""
        res = execute_typed_operation("file_remove", extra_args=["/tmp/nonexistent.txt"])
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "sentinel_gate_hold")
        self.assertIn("request_id", res)

    def test_forge_metacharacter_injection_rejected(self):
        """Shell injection attempts in arguments are strictly rejected."""
        res = execute_typed_operation("disk_usage", extra_args=["; rm -rf /"])
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "denied")
        self.assertIn("ILLEGAL_ARGUMENT", res["error"])

if __name__ == "__main__":
    unittest.main()
