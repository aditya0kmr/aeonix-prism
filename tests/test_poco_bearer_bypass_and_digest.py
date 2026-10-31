"""
Unit & Negative Security Tests: POCO Bearer-Token Approval Bypass & Cryptographic Action Digest Binding
Validates:
1. POCO Core Bearer Token ALONE cannot approve consequential Sentinel orders without verified operator passphrase.
2. Operator passphrase verification required; invalid passphrase rejected (403).
3. Displayed Action Digest must bind exactly to the stored record parameters; tampered digest rejected (DIGEST_MISMATCH).
4. Fire TV Glass token strictly prohibited from approving (403 POCO_AUTHORITY_REQUIRED).
"""

import os
import tempfile
import unittest
import json
import time

from starlette.testclient import TestClient

from aeonix.core.db import (
    init_database,
    queue_sentinel_request,
    resolve_sentinel_request,
    claim_sentinel_authorization,
    compute_action_digest,
    get_connection
)
from aeonix.core.auth import (
    issue_device_token,
    ROLE_POCO_CORE,
    ROLE_FIRETV_GLASS
)
from aeonix.core.operator_console import (
    setup_operator_secret,
    verify_operator_secret
)
from aeonix.core.server import app


class TestPocoBearerBypassAndDigestBinding(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_vault.db")
        self.secrets_dir = os.path.join(self.temp_dir, "secrets")
        os.makedirs(self.secrets_dir, mode=0o700, exist_ok=True)
        init_database(self.db_path)

        # Initialize operator secret: Passphrase "SovereignPass123"
        self.passphrase = "SovereignPass123"
        setup_operator_secret(self.passphrase, secrets_dir=self.secrets_dir)
        try:
            setup_operator_secret(self.passphrase)
        except Exception:
            pass

        # Reset lockout in case previous tests triggered it
        from aeonix.core.operator_console import reset_lockout_state
        reset_lockout_state(self.secrets_dir)
        reset_lockout_state()

        # Issue tokens
        self.poco_token = issue_device_token("poco_test_dev", ROLE_POCO_CORE)
        self.tv_token = issue_device_token("tv_test_dev", ROLE_FIRETV_GLASS)

    def test_01_db_level_bearer_alone_approval_rejected(self):
        """DB level: resolve_sentinel_request rejects approval without passphrase_verified=True."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="consequential",
            action_type="file_remove",
            target="rm -f /tmp/test.txt",
            scope={"cwd": "/tmp"},
            risk_level="R3",
            db_path=self.db_path
        )

        # Attempt approval with POCO_CORE role but passphrase_verified=False (bearer alone bypass attempt)
        ok, reason = resolve_sentinel_request(
            req_id=req_id,
            approved=True,
            resolver="Aadi",
            resolver_role=ROLE_POCO_CORE,
            passphrase_verified=False,
            db_path=self.db_path
        )
        self.assertFalse(ok)
        self.assertIn("OPERATOR_PASSPHRASE_REQUIRED", reason)

    def test_02_db_level_approval_with_verified_passphrase_succeeds(self):
        """DB level: resolve_sentinel_request succeeds when passphrase_verified=True and digest matches."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="consequential",
            action_type="file_remove",
            target="rm -f /tmp/test.txt",
            scope={"cwd": "/tmp"},
            risk_level="R3",
            db_path=self.db_path
        )

        expected_digest = compute_action_digest(req_id, "FORGE", "file_remove", "rm -f /tmp/test.txt", {"cwd": "/tmp"})
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

    def test_03_db_level_digest_tampering_rejected(self):
        """DB level: resolve_sentinel_request rejects mismatched action digest."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="consequential",
            action_type="file_remove",
            target="rm -f /tmp/test.txt",
            scope={"cwd": "/tmp"},
            risk_level="R3",
            db_path=self.db_path
        )

        fake_digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ok, reason = resolve_sentinel_request(
            req_id=req_id,
            approved=True,
            resolver="Aadi",
            resolver_role=ROLE_POCO_CORE,
            passphrase_verified=True,
            expected_action_digest=fake_digest,
            db_path=self.db_path
        )
        self.assertFalse(ok)
        self.assertIn("DIGEST_MISMATCH", reason)

    def test_04_api_level_poco_bearer_alone_without_passphrase_rejected(self):
        """API level: POST /api/sentinel/resolve with valid POCO Bearer token but NO passphrase yields 403."""
        # Queue request directly
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="consequential",
            action_type="file_remove",
            target="rm -f /tmp/test.txt",
            scope={"cwd": "/tmp"},
            risk_level="R3"
        )

        client = TestClient(app)
        # Attempt approval with POCO bearer token alone
        resp = client.post(
            "/api/sentinel/resolve",
            json={"request_id": req_id, "approved": True},
            headers={"Authorization": f"Bearer {self.poco_token}"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("OPERATOR_PASSPHRASE_REQUIRED", resp.json().get("error", ""))

    def test_05_api_level_poco_bearer_with_wrong_passphrase_rejected(self):
        """API level: POST /api/sentinel/resolve with incorrect operator passphrase yields 403."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="consequential",
            action_type="file_remove",
            target="rm -f /tmp/test.txt",
            scope={"cwd": "/tmp"},
            risk_level="R3"
        )

        client = TestClient(app)
        resp = client.post(
            "/api/sentinel/resolve",
            json={
                "request_id": req_id, 
                "approved": True,
                "operator_passphrase": "WrongPassphrase123"
            },
            headers={"Authorization": f"Bearer {self.poco_token}"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("OPERATOR_AUTH_FAILED", resp.json().get("error", ""))

    def test_06_firetv_glass_cannot_approve(self):
        """Fire TV Glass bearer token cannot approve even if passphrase was supplied."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="consequential",
            action_type="file_remove",
            target="rm -f /tmp/test.txt",
            scope={"cwd": "/tmp"},
            risk_level="R3"
        )

        client = TestClient(app)
        resp = client.post(
            "/api/sentinel/resolve",
            json={
                "request_id": req_id,
                "approved": True,
                "operator_passphrase": self.passphrase
            },
            headers={"Authorization": f"Bearer {self.tv_token}"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("POCO_AUTHORITY_REQUIRED", resp.json().get("error", ""))


if __name__ == "__main__":
    unittest.main()
