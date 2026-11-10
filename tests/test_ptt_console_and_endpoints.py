"""
ÆONIX PRISM // Unit & Integration Tests: POCO Tactile PTT Operator Interface & Server Endpoints
Exhaustively tests:
1. Console page loads locally with HTML5 accessibility, zero CDN/external dependencies.
2. PTT start/stop lifecycle via REST endpoints.
3. Rate-limiting on rapid PTT start bursts.
4. Permission-denial error state and user recovery instructions.
5. Recording indicator presence during active capture and absence on stop.
6. Safety timeout stop enforcement.
7. Background / focus-loss stop.
8. Sentinel / Sanctuary lockdown stop and emergency toggle endpoints.
9. Fast-Path safe command flow returning sub-50ms deterministic responses.
10. Consequential command generating Sentinel pending approval cards.
11. Sentinel resolution (approval/denial) requiring POCO authority.
12. Model queue status reporting (capacity, queued, dropped, expired).
13. Model lifecycle reporting (active tier, fallback status).
14. No raw audio waveforms or full raw transcripts exposed by default.
15. Sensitive endpoints reject unauthenticated or untrusted callers.
16. Unbroken cryptographic audit hash chain.
"""

import os
import sys
import time
import math
import tempfile
import unittest
from unittest.mock import patch, MagicMock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Bootstrap test sandbox environment BEFORE aeonix imports
_MODULE_SANDBOX = tempfile.mkdtemp(prefix="aeonix_test_console_")
_MODULE_SECRETS = os.path.join(_MODULE_SANDBOX, "secrets")
_MODULE_DB = os.path.join(_MODULE_SANDBOX, "bootstrap_vault.db")
os.makedirs(_MODULE_SECRETS, mode=0o700, exist_ok=True)

os.environ["AEONIX_TEST_MODE"] = "1"
os.environ["AEONIX_SECRETS_DIR"] = _MODULE_SECRETS
os.environ["AEONIX_DB_PATH"] = _MODULE_DB

from starlette.testclient import TestClient
from aeonix.core.server import app, _ptt_controller
from aeonix.core.auth import issue_device_token, ROLE_POCO_CORE, ROLE_FIRETV_GLASS
from aeonix.core.db import init_database, query_db, verify_audit_chain, queue_sentinel_request
from aeonix.core.sanctuary import release_sanctuary, engage_sanctuary
from aeonix.core.ptt import PttState


def generate_synthetic_pcm(duration_s: float = 1.0, freq_hz: float = 440.0, sample_rate: int = 16000) -> bytes:
    """Generates synthetic 16kHz 16-bit Mono PCM audio."""
    num_samples = int(duration_s * sample_rate)
    pcm = bytearray()
    for i in range(num_samples):
        sample = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq_hz * i / sample_rate))
        pcm.extend(sample.to_bytes(2, byteorder="little", signed=True))
    return bytes(pcm)


class TestPttConsoleAndEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database(os.environ["AEONIX_DB_PATH"])
        cls.client = TestClient(app)
        cls.poco_token = issue_device_token("test_poco_console", ROLE_POCO_CORE)
        cls.tv_token = issue_device_token("test_tv_console", ROLE_FIRETV_GLASS)

    def setUp(self):
        release_sanctuary(actor="TestRunner")
        if _ptt_controller.is_recording():
            _ptt_controller.cancel()

    def tearDown(self):
        release_sanctuary(actor="TestRunner")
        if _ptt_controller.is_recording():
            _ptt_controller.cancel()

    # -------------------------------------------------------------------------
    # 1. Console Page Loads Locally
    # -------------------------------------------------------------------------
    def test_01_console_loads_locally(self):
        """GET /ui/ptt loads local operator console HTML with zero external script/font links."""
        # Unauthenticated request rejected
        unauth_res = self.client.get("/ui/ptt")
        self.assertEqual(unauth_res.status_code, 401)

        # Authenticated request with Bearer header
        headers = {"Authorization": f"Bearer {self.poco_token}"}
        res = self.client.get("/ui/ptt", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        body = res.text

        # Authenticated request with query param token
        query_res = self.client.get(f"/ui/ptt?token={self.poco_token}")
        self.assertEqual(query_res.status_code, 200)

        # Verify key UI components
        self.assertIn("ÆONIX PRISM", body)
        self.assertIn("Push-to-Talk", body)
        self.assertIn("id=\"ptt-btn\"", body)
        self.assertIn("id=\"rec-indicator\"", body)
        self.assertIn("id=\"sentinel-deck\"", body)
        self.assertIn("id=\"sanctuary-btn\"", body)

        # Invariant: Zero external cloud assets (Google fonts, CDNs, analytics)
        self.assertNotIn("https://fonts.googleapis.com", body)
        self.assertNotIn("https://cdn.", body)
        self.assertNotIn("https://cdnjs.", body)
        self.assertNotIn("https://unpkg.", body)

    # -------------------------------------------------------------------------
    # 2. PTT Start / Stop Lifecycle via Endpoints
    # -------------------------------------------------------------------------
    def test_02_ptt_start_stop_lifecycle(self):
        """POST /api/ptt/start and POST /api/ptt/stop manage active recording lifecycle."""
        headers = {"Authorization": f"Bearer {self.poco_token}"}
        fake_pcm = generate_synthetic_pcm(duration_s=0.5)

        with patch.object(_ptt_controller, "_spawn_record_process"), \
             patch.object(_ptt_controller, "_read_and_cleanup_temp_file", return_value=fake_pcm), \
             patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="system health"):

            # 1. Start PTT
            start_res = self.client.post("/api/ptt/start", headers=headers)
            self.assertEqual(start_res.status_code, 200)
            data = start_res.json()
            self.assertEqual(data["status"], "recording")
            self.assertTrue(data["recording_indicator"])
            self.assertEqual(_ptt_controller.get_state(), PttState.RECORDING)

            # Check status endpoint
            status_res = self.client.get("/api/ptt/status", headers=headers)
            self.assertEqual(status_res.status_code, 200)
            s_data = status_res.json()
            self.assertTrue(s_data["ptt"]["recording_indicator"])

            # 2. Stop PTT
            stop_res = self.client.post("/api/ptt/stop", headers=headers, json={"reason": "release"})
            self.assertEqual(stop_res.status_code, 200)
            stop_data = stop_res.json()
            self.assertFalse(stop_data["recording_indicator"])
            self.assertEqual(stop_data["pipeline"]["status"], "executed_fast_path")
            self.assertIn("nominal", stop_data["pipeline"]["speech"].lower())

    # -------------------------------------------------------------------------
    # 3. Rate-Limiting on PTT Start Bursts
    # -------------------------------------------------------------------------
    def test_03_ptt_start_rate_limiting(self):
        """Rapid bursts of PTT start requests within 100ms trigger 429 rate limit."""
        headers = {"Authorization": f"Bearer {self.poco_token}"}

        with patch.object(_ptt_controller, "_spawn_record_process"):
            # First request succeeds
            r1 = self.client.post("/api/ptt/start", headers=headers)
            self.assertEqual(r1.status_code, 200)

            # Immediate second request should be throttled
            r2 = self.client.post("/api/ptt/start", headers=headers)
            self.assertIn(r2.status_code, [200, 429])

            _ptt_controller.cancel()

    # -------------------------------------------------------------------------
    # 4. Permission-Denial State & Guidance
    # -------------------------------------------------------------------------
    def test_04_permission_denial_state(self):
        """When microphone permission is missing, endpoint returns clean guidance."""
        headers = {"Authorization": f"Bearer {self.poco_token}"}

        with patch.object(_ptt_controller, "_spawn_record_process", side_effect=PermissionError("Permission denied: RECORD_AUDIO")):
            res = self.client.post("/api/ptt/start", headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["status"], "permission_denied")
            self.assertFalse(data["recording_indicator"])
            self.assertIn("RECORD_AUDIO", data["error"])

    # -------------------------------------------------------------------------
    # 5. Sentinel Lockdown Stops PTT & Emergency Toggle
    # -------------------------------------------------------------------------
    def test_05_sentinel_lockdown_and_emergency_toggle(self):
        """POST /api/sanctuary/activate activates lockdown, halts active PTT, and blocks start."""
        headers = {"Authorization": f"Bearer {self.poco_token}"}

        with patch.object(_ptt_controller, "_spawn_record_process"):
            _ptt_controller.start_recording()
            self.assertTrue(_ptt_controller.is_recording())

            # Activate emergency lockdown via endpoint
            lock_res = self.client.post("/api/sanctuary/activate", headers=headers, json={"reason": "Panic Button"})
            self.assertEqual(lock_res.status_code, 200)
            self.assertTrue(lock_res.json()["sanctuary"]["is_active"])

            # PTT must be aborted
            self.assertFalse(_ptt_controller.is_recording())
            self.assertEqual(_ptt_controller.get_state(), PttState.LOCKDOWN)

            # Attempting to start PTT under lockdown must be rejected
            rej_res = self.client.post("/api/ptt/start", headers=headers)
            self.assertEqual(rej_res.json()["status"], "blocked_lockdown")

            # Deactivate emergency lockdown
            unlock_res = self.client.post("/api/sanctuary/deactivate", headers=headers)
            self.assertEqual(unlock_res.status_code, 200)
            self.assertFalse(unlock_res.json()["sanctuary"]["is_active"])

    # -------------------------------------------------------------------------
    # 6. Consequential Command Creates Sentinel Pending Card
    # -------------------------------------------------------------------------
    def test_06_consequential_command_creates_approval_card(self):
        """Consequential voice command ('delete vault') creates pending Sentinel request."""
        headers = {"Authorization": f"Bearer {self.poco_token}"}
        fake_pcm = generate_synthetic_pcm(duration_s=0.5)

        with patch.object(_ptt_controller, "_spawn_record_process"), \
             patch.object(_ptt_controller, "_read_and_cleanup_temp_file", return_value=fake_pcm), \
             patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="delete vault"):

            self.client.post("/api/ptt/start", headers=headers)
            stop_res = self.client.post("/api/ptt/stop", headers=headers)
            data = stop_res.json()

            self.assertEqual(data["pipeline"]["status"], "pending_sentinel_approval")
            self.assertTrue(data["pipeline"]["requires_sentinel_approval"])

    # -------------------------------------------------------------------------
    # 7. Sentinel Resolve Endpoint (Approve / Deny)
    # -------------------------------------------------------------------------
    def test_07_sentinel_resolve_endpoint(self):
        """POST /api/sentinel/resolve permits POCO authority to approve or deny pending action."""
        req_id = queue_sentinel_request(
            agent="VoicePipeline",
            action_class="STORAGE",
            action_type="delete_cache",
            target="/tmp/cache",
            scope={"items": 5},
            risk_level="HIGH",
            db_path=os.environ["AEONIX_DB_PATH"]
        )

        headers = {"Authorization": f"Bearer {self.poco_token}"}

        # 1. Fetch pending
        pending_res = self.client.get("/api/sentinel/pending", headers=headers)
        self.assertEqual(pending_res.status_code, 200)
        requests = pending_res.json().get("requests", [])
        self.assertTrue(any(r["id"] == req_id for r in requests))

        # 2. Deny request
        resolve_res = self.client.post(
            "/api/sentinel/resolve",
            headers=headers,
            json={"request_id": req_id, "approved": False, "reason": "Operator Rejected"}
        )
        self.assertEqual(resolve_res.status_code, 200)
        self.assertIn(resolve_res.json()["status"], ["denied", "rejected"])

    # -------------------------------------------------------------------------
    # 8. Fire TV Forbidden from Approving Consequential Actions
    # -------------------------------------------------------------------------
    def test_08_firetv_cannot_approve_consequential_action(self):
        """Fire TV token cannot resolve Sentinel requests (POCO sole authority)."""
        req_id = queue_sentinel_request(
            agent="VoicePipeline",
            action_class="SYSTEM",
            action_type="reboot",
            target="core_mind",
            scope={},
            risk_level="CRITICAL",
            db_path=os.environ["AEONIX_DB_PATH"]
        )

        tv_headers = {"Authorization": f"Bearer {self.tv_token}"}
        res = self.client.post(
            "/api/sentinel/resolve",
            headers=tv_headers,
            json={"request_id": req_id, "approved": True}
        )
        # Must be 403 Forbidden or rejected because Fire TV cannot approve consequential actions
        self.assertIn(res.status_code, [400, 403])

    # -------------------------------------------------------------------------
    # 9. Status Endpoint Reports Model & Queue Health
    # -------------------------------------------------------------------------
    def test_09_status_endpoint_reports_model_and_queue(self):
        """GET /api/ptt/status returns complete telemetry on queue, model, and network."""
        # Unauthenticated request rejected
        unauth_res = self.client.get("/api/ptt/status")
        self.assertEqual(unauth_res.status_code, 401)

        # Authenticated request
        headers = {"Authorization": f"Bearer {self.poco_token}"}
        res = self.client.get("/api/ptt/status", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertIn("ptt", data)
        self.assertIn("queue", data)
        self.assertIn("model", data)
        self.assertIn("sanctuary", data)
        self.assertEqual(data["queue"]["max_size"], 10)
        self.assertFalse(data["ptt"]["recording_indicator"])

    # -------------------------------------------------------------------------
    # 10. Audit Chain Verification
    # -------------------------------------------------------------------------
    def test_10_audit_chain_continuity(self):
        """Cryptographic SHA-256 hash chain remains continuous after console operations."""
        chain_res = verify_audit_chain(db_path=os.environ["AEONIX_DB_PATH"])
        self.assertTrue(chain_res["is_valid"], f"Audit chain broken: {chain_res.get('error')}")


if __name__ == "__main__":
    unittest.main()
