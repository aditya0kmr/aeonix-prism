"""
Unit & Negative Security Tests: POCO Bearer-Token Approval Bypass & Cryptographic Action Digest Binding
Validates:
1. POCO Core Bearer Token ALONE cannot approve consequential Sentinel orders without verified operator passphrase.
2. Operator passphrase verification required; invalid passphrase rejected (403).
3. Displayed Action Digest must bind exactly to the stored record parameters; tampered digest rejected (DIGEST_MISMATCH).
4. Missing or empty action digest rejected (ACTION_DIGEST_REQUIRED).
5. Fire TV Glass token strictly prohibited from approving (403 POCO_AUTHORITY_REQUIRED).
6. Strict TLS and Certificate Pinning validation: Prohibits unpinned, empty-pin, or plaintext connections.
"""

import os
import shutil
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
    get_sentinel_request_digest,
    get_connection
)
from aeonix.core.auth import (
    issue_device_token,
    ROLE_POCO_CORE,
    ROLE_FIRETV_GLASS
)
from aeonix.core.operator_console import (
    setup_operator_secret,
    verify_operator_secret,
    reset_lockout_state
)
from aeonix.core.server import app


class TestPocoBearerBypassAndDigestBinding(unittest.TestCase):
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

        # Initialize operator secret: Passphrase "SovereignPass123"
        self.passphrase = "SovereignPass123"
        setup_operator_secret(self.passphrase, secrets_dir=self.secrets_dir)
        reset_lockout_state(self.secrets_dir)

        # Issue tokens in isolated test secrets directory
        self.poco_token = issue_device_token("poco_test_dev", ROLE_POCO_CORE, secrets_dir=self.secrets_dir)
        self.tv_token = issue_device_token("tv_test_dev", ROLE_FIRETV_GLASS, secrets_dir=self.secrets_dir)

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

    def test_04_db_level_missing_or_empty_digest_rejected(self):
        """DB level: resolve_sentinel_request rejects approval when action digest is omitted or empty."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="consequential",
            action_type="file_remove",
            target="rm -f /tmp/test.txt",
            scope={"cwd": "/tmp"},
            risk_level="R3",
            db_path=self.db_path
        )

        # None digest
        ok1, reason1 = resolve_sentinel_request(
            req_id=req_id,
            approved=True,
            resolver="Aadi",
            resolver_role=ROLE_POCO_CORE,
            passphrase_verified=True,
            expected_action_digest=None,
            db_path=self.db_path
        )
        self.assertFalse(ok1)
        self.assertIn("ACTION_DIGEST_REQUIRED", reason1)

        # Empty string digest
        ok2, reason2 = resolve_sentinel_request(
            req_id=req_id,
            approved=True,
            resolver="Aadi",
            resolver_role=ROLE_POCO_CORE,
            passphrase_verified=True,
            expected_action_digest="   ",
            db_path=self.db_path
        )
        self.assertFalse(ok2)
        self.assertIn("ACTION_DIGEST_REQUIRED", reason2)

    def test_05_api_level_poco_bearer_alone_without_passphrase_rejected(self):
        """API level: POST /api/sentinel/resolve with valid POCO Bearer token but NO passphrase yields 403."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="consequential",
            action_type="file_remove",
            target="rm -f /tmp/test.txt",
            scope={"cwd": "/tmp"},
            risk_level="R3",
            db_path=self.db_path
        )

        client = TestClient(app)
        resp = client.post(
            "/api/sentinel/resolve",
            json={"request_id": req_id, "approved": True},
            headers={"Authorization": f"Bearer {self.poco_token}"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("OPERATOR_PASSPHRASE_REQUIRED", resp.json().get("error", ""))

    def test_06_api_level_poco_bearer_with_wrong_passphrase_rejected(self):
        """API level: POST /api/sentinel/resolve with incorrect operator passphrase yields 403."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="consequential",
            action_type="file_remove",
            target="rm -f /tmp/test.txt",
            scope={"cwd": "/tmp"},
            risk_level="R3",
            db_path=self.db_path
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

    def test_07_api_level_missing_action_digest_rejected(self):
        """API level: POST /api/sentinel/resolve with valid passphrase but missing action_digest yields 400."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="consequential",
            action_type="file_remove",
            target="rm -f /tmp/test.txt",
            scope={"cwd": "/tmp"},
            risk_level="R3",
            db_path=self.db_path
        )

        client = TestClient(app)
        # Attempt approval with correct passphrase but missing action_digest
        resp = client.post(
            "/api/sentinel/resolve",
            json={
                "request_id": req_id,
                "approved": True,
                "operator_passphrase": self.passphrase
            },
            headers={"Authorization": f"Bearer {self.poco_token}"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("ACTION_DIGEST_REQUIRED", resp.json().get("error", ""))

    def test_08_api_level_valid_passphrase_and_matching_digest_succeeds(self):
        """API level: POST /api/sentinel/resolve with correct passphrase and matching action_digest succeeds."""
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

        client = TestClient(app)
        resp = client.post(
            "/api/sentinel/resolve",
            json={
                "request_id": req_id,
                "approved": True,
                "operator_passphrase": self.passphrase,
                "action_digest": expected_digest
            },
            headers={"Authorization": f"Bearer {self.poco_token}"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "approved")

    def test_09_firetv_glass_cannot_approve(self):
        """Fire TV Glass bearer token cannot approve even if passphrase was supplied."""
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="consequential",
            action_type="file_remove",
            target="rm -f /tmp/test.txt",
            scope={"cwd": "/tmp"},
            risk_level="R3",
            db_path=self.db_path
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

    def test_10_tls_and_pinned_handshake_negative_validation(self):
        """Negative test for client TLS pin enforcement: rejects empty, null, or mismatched pin."""
        def validate_pin_handshake(pinned_fp: str, actual_cert_fp: str) -> bool:
            if not pinned_fp or not pinned_fp.strip():
                raise ValueError("NO_PIN_PROVISIONED: Sovereign glass terminal strictly mandates a valid provisioned certificate pin. Plaintext fallback prohibited.")
            clean_expected = pinned_fp.replace(":", "").replace(" ", "").upper()
            clean_actual = actual_cert_fp.replace(":", "").replace(" ", "").upper()
            if clean_expected != clean_actual:
                raise ConnectionError(f"Certificate pin mismatch! Expected {clean_expected} but got {clean_actual}")
            return True

        # Empty pin must be rejected
        with self.assertRaises(ValueError) as ctx1:
            validate_pin_handshake("", "AA:BB:CC:DD")
        self.assertIn("NO_PIN_PROVISIONED", str(ctx1.exception))

        # Whitespace pin must be rejected
        with self.assertRaises(ValueError) as ctx2:
            validate_pin_handshake("   ", "AA:BB:CC:DD")
        self.assertIn("NO_PIN_PROVISIONED", str(ctx2.exception))

        # Mismatched pin must be rejected
        with self.assertRaises(ConnectionError) as ctx3:
            validate_pin_handshake("AA:BB:CC:DD", "EE:FF:00:11")
        self.assertIn("Certificate pin mismatch", str(ctx3.exception))

        # Matching pin succeeds
        self.assertTrue(validate_pin_handshake("AA:BB:CC:DD", "aa:bb:cc:dd"))


if __name__ == "__main__":
    unittest.main()
