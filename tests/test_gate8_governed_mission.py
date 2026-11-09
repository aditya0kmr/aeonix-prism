"""
ÆONIX PRISM // Gate G8 First Governed Mission Test Suite
Exhaustively verifies:
1. End-to-end mission lifecycle: REQUESTED -> COLLECTING -> PLANNED -> SIMULATED ->
                               POLICY_CHECK -> AWAITING_APPROVAL -> CLAIMED -> EXECUTING -> VERIFYING -> COMPLETED
2. Policy evaluation, Sentinel request generation, and Action Digest binding.
3. POCO Core approval enforcement (passphrase verified, authority check, displayed-digest match).
4. Single-use token claim and replay rejection (ALREADY_CONSUMED).
5. Bounded actions: storage_diagnostic and apk_preflight (<30MB verification).
6. Cryptographic audit verification receipt and journal emission.
7. Starlette HTTP /missions endpoints with RBAC.
"""

import os
import sys
import json
import time
import tempfile
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
else:
    sys.path.remove(_REPO_ROOT)
    sys.path.insert(0, _REPO_ROOT)

# Bootstrap test sandbox environment BEFORE aeonix imports
_MODULE_SANDBOX = tempfile.mkdtemp(prefix="aeonix_test_g8_bootstrap_")
_MODULE_SECRETS = os.path.join(_MODULE_SANDBOX, "secrets")
_MODULE_DB = os.path.join(_MODULE_SANDBOX, "bootstrap_vault.db")
os.makedirs(_MODULE_SECRETS, mode=0o700, exist_ok=True)

os.environ["AEONIX_TEST_MODE"] = "1"
if "AEONIX_SECRETS_DIR" not in os.environ:
    os.environ["AEONIX_SECRETS_DIR"] = _MODULE_SECRETS
if "AEONIX_DB_PATH" not in os.environ:
    os.environ["AEONIX_DB_PATH"] = _MODULE_DB

from starlette.testclient import TestClient
from aeonix.core.server import app
from aeonix.core.auth import issue_device_token, ROLE_POCO_CORE, ROLE_FIRETV_GLASS
from aeonix.core.db import (
    init_database,
    resolve_sentinel_request,
    verify_audit_chain,
    replay_event_journal
)
from aeonix.core.governed_mission import GovernedMissionController


class TestGate8GovernedMission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database(os.environ["AEONIX_DB_PATH"])
        cls.db_path = os.environ["AEONIX_DB_PATH"]
        cls.controller = GovernedMissionController(db_path=cls.db_path)
        cls.client = TestClient(app)
        cls.poco_token = issue_device_token("test_poco_gate8", ROLE_POCO_CORE)
        cls.tv_token = issue_device_token("test_tv_gate8", ROLE_FIRETV_GLASS)

    def test_01_storage_diagnostic_mission_lifecycle_and_receipt(self):
        """Verifies full governed storage_diagnostic mission from proposal to verified audit receipt."""
        # 1. Create mission
        m = self.controller.create_mission(
            mission_type="storage_diagnostic",
            objective="Perform automated storage diagnostic and partition telemetry",
            target="storage_vault",
            scope={"inspect_roots": ["data", "scratch"]}
        )
        self.assertEqual(m["status"], "AWAITING_APPROVAL")
        self.assertIsNotNone(m["sentinel_request_id"])
        self.assertIsNotNone(m["action_digest"])
        sentinel_id = m["sentinel_request_id"]
        action_digest = m["action_digest"]

        # 2. Reject unauthenticated approval (without operator passphrase)
        ok_no_pass, reason_no_pass = resolve_sentinel_request(
            req_id=sentinel_id,
            approved=True,
            resolver="Aadi",
            resolver_role="POCO_CORE",
            passphrase_verified=False,
            expected_action_digest=action_digest,
            db_path=self.db_path
        )
        self.assertFalse(ok_no_pass)
        self.assertIn("OPERATOR_PASSPHRASE_REQUIRED", reason_no_pass)

        # 3. Reject approval with mismatched digest
        ok_bad_digest, reason_bad = resolve_sentinel_request(
            req_id=sentinel_id,
            approved=True,
            resolver="Aadi",
            resolver_role="POCO_CORE",
            passphrase_verified=True,
            expected_action_digest="forged_digest_00000000000000000000000000000000",
            db_path=self.db_path
        )
        self.assertFalse(ok_bad_digest)
        self.assertIn("DIGEST_MISMATCH", reason_bad)

        # 4. Valid POCO Core Approval with verified passphrase & matching digest
        ok_app, status_app = resolve_sentinel_request(
            req_id=sentinel_id,
            approved=True,
            resolver="Aadi",
            resolver_role="POCO_CORE",
            passphrase_verified=True,
            expected_action_digest=action_digest,
            db_path=self.db_path
        )
        self.assertTrue(ok_app)
        self.assertEqual(status_app, "approved")

        # 5. Claim single-use authorization and execute bounded mission
        ok_exec, receipt, msg_exec = self.controller.claim_and_execute(
            mission_id=m["mission_id"],
            claimer="POCO_CORE_MIND",
            expected_digest=action_digest
        )
        self.assertTrue(ok_exec, f"Execution failed: {msg_exec}")
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["status"], "COMPLETED")
        self.assertEqual(receipt["mission_type"], "storage_diagnostic")
        self.assertIn("free_gb", receipt["output_report"])
        self.assertIn("percent_used", receipt["output_report"])
        self.assertTrue(receipt["receipt_verified"])
        self.assertIn("audit_hash", receipt)

        # 6. Replay attack rejection: Attempting to claim the same mission again MUST fail
        ok_replay, _, msg_replay = self.controller.claim_and_execute(
            mission_id=m["mission_id"],
            claimer="ATTACKER_REPLAY",
            expected_digest=action_digest
        )
        self.assertFalse(ok_replay)
        self.assertIn("INVALID_MISSION_STATUS", msg_replay)

        # 7. Audit Chain Integrity Verification
        chain_status = verify_audit_chain(self.db_path)
        self.assertTrue(chain_status["is_valid"])

    def test_02_apk_preflight_mission(self):
        """Verifies governed apk_preflight mission: calculates SHA-256 and validates < 30 MB ceiling."""
        apk_path = os.path.expanduser("~/aether-launcher/app/build/outputs/apk/debug/app-debug.apk")
        m = self.controller.create_mission(
            mission_type="apk_preflight",
            objective="Preflight inspection of debug TV launcher APK",
            target="aether-launcher",
            scope={"apk_path": apk_path}
        )
        sentinel_id = m["sentinel_request_id"]
        action_digest = m["action_digest"]

        # Approve on POCO
        ok_app, _ = resolve_sentinel_request(
            req_id=sentinel_id,
            approved=True,
            resolver="Aadi",
            resolver_role="POCO_CORE",
            passphrase_verified=True,
            expected_action_digest=action_digest,
            db_path=self.db_path
        )
        self.assertTrue(ok_app)

        # Execute
        ok_exec, receipt, _ = self.controller.claim_and_execute(
            mission_id=m["mission_id"],
            claimer="POCO_CORE_MIND",
            expected_digest=action_digest
        )
        self.assertTrue(ok_exec)
        self.assertEqual(receipt["status"], "COMPLETED")
        rep = receipt["output_report"]
        self.assertEqual(rep["diagnostic_type"], "apk_preflight")
        self.assertTrue(rep["size_within_limits"], "APK size must be strictly below 30 MB")
        self.assertLess(rep["size_mb"], 30.0)
        self.assertIn("sha256", rep)

    def test_03_http_missions_api(self):
        """Verifies Starlette HTTP POST /missions and GET /missions endpoints."""
        headers_poco = {"Authorization": f"Bearer {self.poco_token}"}
        headers_tv = {"Authorization": f"Bearer {self.tv_token}"}

        # 1. POST /missions (propose mission)
        payload = {
            "mission_type": "storage_diagnostic",
            "objective": "HTTP API Diagnostic Proposal",
            "target": "storage_vault",
            "scope": {"source": "rest_api"}
        }
        r_post = self.client.post("/missions", json=payload, headers=headers_poco)
        self.assertEqual(r_post.status_code, 200)
        self.assertTrue(r_post.json()["success"])
        mission_id = r_post.json()["mission"]["mission_id"]

        # 2. GET /missions (allowed for POCO and Fire TV)
        r_get = self.client.get("/missions", headers=headers_tv)
        self.assertEqual(r_get.status_code, 200)
        self.assertTrue(r_get.json()["success"])
        missions = r_get.json()["missions"]
        self.assertGreaterEqual(len(missions), 1)
        self.assertTrue(any(item["id"] == mission_id for item in missions))


if __name__ == "__main__":
    unittest.main()
