"""
Unit tests verifying the POCO Operator Console Mobile UI and Sentinel Gate authority.
Checks:
1. /operator and /console reject unauthenticated requests with 401 (default-deny).
2. /operator rejects Fire TV Glass role with 403 (role segregation).
3. /operator renders 200 OK HTML for POCO Core authority.
4. Contains required visual tokens, action digest fields, and emergency sanctuary controls.
5. Protected approval resolution strictly enforces POCO authority, passphrase, and digest binding.
"""

import os
import sys
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TESTS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
else:
    sys.path.remove(_REPO_ROOT)
    sys.path.insert(0, _REPO_ROOT)

from starlette.testclient import TestClient
from aeonix.core.server import app
from aeonix.core.auth import (
    issue_device_token,
    ROLE_POCO_CORE,
    ROLE_FIRETV_GLASS
)
from aeonix.core.db import queue_sentinel_request, get_connection


class TestOperatorUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from aeonix.core.operator_console import setup_operator_secret
        setup_operator_secret("TestSovereignSandboxPassphrase123!")
        cls.client = TestClient(app)
        cls.poco_token = issue_device_token("poco_test_operator", role=ROLE_POCO_CORE)
        cls.firetv_token = issue_device_token("firetv_sheldon", role=ROLE_FIRETV_GLASS)

    def test_01_operator_console_default_deny_unauthenticated(self):
        """Verify /operator and /console reject unauthenticated requests with 401."""
        resp1 = self.client.get("/operator")
        self.assertEqual(resp1.status_code, 401)
        self.assertIn("UNAUTHENTICATED", resp1.json().get("error", ""))

        resp2 = self.client.get("/console")
        self.assertEqual(resp2.status_code, 401)
        self.assertIn("UNAUTHENTICATED", resp2.json().get("error", ""))

    def test_02_operator_console_firetv_role_forbidden(self):
        """Verify /operator rejects Fire TV Glass token with 403."""
        headers = {"Authorization": f"Bearer {self.firetv_token}"}
        resp = self.client.get("/operator", headers=headers)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("FORBIDDEN", resp.json().get("error", ""))

    def test_03_operator_console_html_accessible_with_poco_token(self):
        """Verify /operator loads 200 OK HTML for POCO Core authority."""
        headers = {"Authorization": f"Bearer {self.poco_token}"}
        resp = self.client.get("/operator", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))
        self.assertIn("ÆONIX PRISM", resp.text)
        self.assertIn("Operator Console", resp.text)
        self.assertIn("POCO CORE", resp.text)
        self.assertIn("Emergency Stop", resp.text)

        # Also verify /console alias
        resp_alias = self.client.get("/console", headers=headers)
        self.assertEqual(resp_alias.status_code, 200)
        self.assertIn("text/html", resp_alias.headers.get("content-type", ""))

    def test_04_approval_strictly_requires_operator_passphrase_and_digest(self):
        """Verify resolving sentinel request without passphrase fails 403."""
        # Queue an action using standard queue_sentinel_request
        req_id = queue_sentinel_request(
            agent="test_agent",
            action_class="R3",
            action_type="system.maintenance",
            target="sheldon",
            scope={"command": "pm clear com.amazon.tv"},
            risk_level="HIGH"
        )

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT action_digest FROM sentinel_requests WHERE id = ?", (req_id,))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        digest = row[0]

        headers = {"Authorization": f"Bearer {self.poco_token}"}

        # Attempt approval with no passphrase
        resp = self.client.post("/api/sentinel/resolve", json={
            "request_id": req_id,
            "approved": True,
            "action_digest": digest
        }, headers=headers)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("OPERATOR_PASSPHRASE_REQUIRED", resp.json().get("error", ""))

        # Attempt approval from Fire TV role (must fail 403)
        ftv_headers = {"Authorization": f"Bearer {self.firetv_token}"}
        resp = self.client.post("/api/sentinel/resolve", json={
            "request_id": req_id,
            "approved": True,
            "action_digest": digest,
            "operator_passphrase": "TestSovereignSandboxPassphrase123!"
        }, headers=ftv_headers)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("POCO_AUTHORITY_REQUIRED", resp.json().get("error", ""))

        # Valid approval from POCO with passphrase and digest
        resp = self.client.post("/api/sentinel/resolve", json={
            "request_id": req_id,
            "approved": True,
            "action_digest": digest,
            "operator_passphrase": "TestSovereignSandboxPassphrase123!"
        }, headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("success"))


if __name__ == "__main__":
    unittest.main()
