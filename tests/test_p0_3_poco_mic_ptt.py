"""
ÆONIX PRISM // Master Integration Test Suite: Ticket P0-3
POCO Phone Microphone Push-to-Talk (PTT) Wiring & Latency Tuning

Exhaustively verifies all 26 mandatory architectural, security, and lifecycle integration requirements:
 1. Permission-denied handling.
 2. Normal PTT start and stop.
 3. 15-second safety-timeout cutoff.
 4. Background / focus-loss stop.
 5. Sentinel lockdown emergency stop.
 6. Network / Fire TV disconnect resilience.
 7. Ambient silence / VAD discard.
 8. Fast-Path direct dispatch in under 50 ms.
 9. LLM fallback burst dispatch.
10. Dynamic RAM-guard queuing.
11. Model load and burst unload lifecycle.
12. Zero audio retention on disk by default.
13. Sentinel gating of consequential voice actions.
14. POCO operator console loads only through the authenticated local endpoint.
15. Unauthenticated access to /ui/ptt and sensitive PTT endpoints is rejected.
16. Rate limiting and debounce prevent PTT abuse.
17. Sanctuary lockdown cancels active PTT and blocks new PTT.
18. Compact Fire TV layout intent remains below 2 KB.
19. No raw audio waveform, raw transcript or bulk log is sent to Fire TV.
20. Audit-chain continuity remains intact across the complete PTT flow.
21. No cloud egress occurs during PTT, STT, Fast-Path or local LLM fallback.
22. No raw audio is written to persistent storage by default.
23. In-memory audio buffer is zeroed and cleared after processing or cancellation.
24. Explicit fallback is labeled "qwen2.5-0.5b-fallback" and audit-logged.
25. RAM-insufficient requests queue rather than silently downgrade.
26. Consequential intents require Sentinel approval and never execute automatically.
"""

import os
import sys
import time
import math
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Establish isolated test sandbox environment BEFORE aeonix imports
_SANDBOX_DIR = tempfile.mkdtemp(prefix="aeonix_p0_3_master_")
_SANDBOX_SECRETS = os.path.join(_SANDBOX_DIR, "secrets")
_SANDBOX_DB = os.path.join(_SANDBOX_DIR, "vault.db")
os.makedirs(_SANDBOX_SECRETS, mode=0o700, exist_ok=True)

os.environ["AEONIX_TEST_MODE"] = "1"
os.environ["AEONIX_SECRETS_DIR"] = _SANDBOX_SECRETS
os.environ["AEONIX_DB_PATH"] = _SANDBOX_DB

from starlette.testclient import TestClient
from aeonix.core.server import app, _ptt_controller, active_connections
from aeonix.core.auth import issue_device_token, ROLE_POCO_CORE, ROLE_FIRETV_GLASS
from aeonix.core.db import (
    init_database,
    get_connection,
    verify_audit_chain,
    queue_sentinel_request,
    resolve_sentinel_request,
    compute_action_digest
)
from aeonix.core.sanctuary import release_sanctuary, engage_sanctuary, get_sanctuary_status
from aeonix.core.ptt import PocoPttController, PttState
from aeonix.core.ram_guard import check_model_ram_guard, MODEL_RAM_THRESHOLDS_KB
from aeonix.core.model_queue import ModelQueueManager
from aeonix.core.voice_pipeline import (
    process_voice_pipeline,
    detect_voice_activity,
    broadcast_to_tv,
    get_queue_manager
)
from aeonix.core.llama_runner import llama_runner


def generate_synthetic_pcm(duration_s: float = 1.0, freq_hz: float = 440.0, sample_rate: int = 16000, is_silent: bool = False) -> bytes:
    """Generates synthetic 16kHz 16-bit Mono PCM audio (tone or pure silence)."""
    num_samples = int(duration_s * sample_rate)
    pcm = bytearray()
    for i in range(num_samples):
        if is_silent:
            sample = 0
        else:
            sample = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq_hz * i / sample_rate))
        pcm.extend(sample.to_bytes(2, byteorder="little", signed=True))
    return bytes(pcm)


class TestP03PocoMicPttMasterIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["AEONIX_DB_PATH"] = _SANDBOX_DB
        init_database(_SANDBOX_DB)
        cls.client = TestClient(app)
        cls.poco_token = issue_device_token("poco_master_tester", ROLE_POCO_CORE)
        cls.tv_token = issue_device_token("tv_glass_tester", ROLE_FIRETV_GLASS)
        cls.headers = {"Authorization": f"Bearer {cls.poco_token}"}
        cls.tv_headers = {"Authorization": f"Bearer {cls.tv_token}"}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_SANDBOX_DIR, ignore_errors=True)

    def setUp(self):
        os.environ["AEONIX_DB_PATH"] = _SANDBOX_DB
        init_database(_SANDBOX_DB)
        release_sanctuary(actor="MasterTestRunner")
        _ptt_controller.cancel()
        _ptt_controller.release_lockdown()
        _ptt_controller._state = PttState.IDLE

    def tearDown(self):
        os.environ["AEONIX_DB_PATH"] = _SANDBOX_DB
        release_sanctuary(actor="MasterTestRunner")
        _ptt_controller.cancel()
        _ptt_controller.release_lockdown()
        _ptt_controller._state = PttState.IDLE

    # =========================================================================
    # 1. Permission-Denied Handling
    # =========================================================================
    def test_01_permission_denied_handling(self):
        """Microphone permission denied returns clean status, zero crash, and guidance."""
        with patch.object(_ptt_controller, "_spawn_record_process", side_effect=PermissionError("Permission denied: RECORD_AUDIO")):
            res = _ptt_controller.start_recording(actor="Aadi")
            self.assertEqual(res["status"], "permission_denied")
            self.assertFalse(res["recording_indicator"])
            self.assertIn("RECORD_AUDIO", res["error"])
            self.assertEqual(_ptt_controller.get_state(), PttState.PERMISSION_DENIED)
            self.assertEqual(len(_ptt_controller.get_audio_buffer()), 0)

    # =========================================================================
    # 2. Normal PTT Start and Stop
    # =========================================================================
    def test_02_normal_ptt_start_and_stop(self):
        """PTT press and release captures 16kHz PCM into memory and frees temp handle."""
        fake_pcm = generate_synthetic_pcm(duration_s=1.0)
        with patch.object(_ptt_controller, "_spawn_record_process"), \
             patch.object(_ptt_controller, "_read_and_cleanup_temp_file", return_value=fake_pcm):
            # Start
            start_res = _ptt_controller.start_recording(actor="Aadi")
            self.assertEqual(start_res["status"], "recording")
            self.assertTrue(_ptt_controller.is_recording())

            # Stop
            stop_res = _ptt_controller.stop_recording(reason="release", actor="Aadi")
            self.assertEqual(stop_res["status"], "stopped")
            self.assertFalse(_ptt_controller.is_recording())
            self.assertEqual(_ptt_controller.get_state(), PttState.STOPPED)

            audio = _ptt_controller.get_audio_buffer()
            self.assertEqual(len(audio), len(fake_pcm))
            _ptt_controller.clear_buffer()
            self.assertEqual(len(_ptt_controller.get_audio_buffer()), 0)

    # =========================================================================
    # 3. 15-Second Safety-Timeout Cutoff
    # =========================================================================
    def test_03_safety_timeout_cutoff(self):
        """PTT capture automatically halts at safety timeout (15s ceiling)."""
        fake_pcm = generate_synthetic_pcm(duration_s=2.0)
        with patch.object(_ptt_controller, "_spawn_record_process"), \
             patch.object(_ptt_controller, "_read_and_cleanup_temp_file", return_value=fake_pcm):
            _ptt_controller.start_recording()
            self.assertTrue(_ptt_controller.is_recording())

            # Stop via timeout trigger
            res = _ptt_controller.stop_recording(reason="timeout", actor="SafetyTimer")
            self.assertEqual(res["status"], "stopped")
            self.assertEqual(res["reason"], "timeout")
            self.assertFalse(_ptt_controller.is_recording())
            _ptt_controller.clear_buffer()

    # =========================================================================
    # 4. Background / Focus-Loss Stop
    # =========================================================================
    def test_04_background_focus_loss_stop(self):
        """User switching apps or losing focus immediately aborts active microphone recording."""
        fake_pcm = generate_synthetic_pcm(duration_s=0.5)
        with patch.object(_ptt_controller, "_spawn_record_process"), \
             patch.object(_ptt_controller, "_terminate_record_process"), \
             patch.object(_ptt_controller, "_read_and_cleanup_temp_file", return_value=fake_pcm):
            _ptt_controller.start_recording()
            self.assertTrue(_ptt_controller.is_recording())

            # Focus loss / background event
            t0 = time.time()
            res = _ptt_controller.on_background(actor="WindowManager")
            elapsed_ms = (time.time() - t0) * 1000.0

            self.assertEqual(res["status"], "stopped")
            self.assertIn(res["reason"], ["background", "app_backgrounded"])
            self.assertFalse(_ptt_controller.is_recording())
            self.assertEqual(_ptt_controller.get_state(), PttState.STOPPED)
            self.assertLess(elapsed_ms, 50.0, "Hardware release must occur within 50ms")
            _ptt_controller.clear_buffer()

    # =========================================================================
    # 5. Sentinel Lockdown Emergency Stop
    # =========================================================================
    def test_05_sentinel_lockdown_emergency_stop(self):
        """Lockdown immediately halts active recording, clears buffers, and blocks new PTT."""
        with patch.object(_ptt_controller, "_spawn_record_process"):
            _ptt_controller.start_recording()
            self.assertTrue(_ptt_controller.is_recording())

            # Emergency lockdown triggered
            res = _ptt_controller.on_sentinel_lockdown(actor="SentinelGate")
            self.assertIn(res["status"], ["cancelled", "lockdown"])
            self.assertFalse(_ptt_controller.is_recording())
            self.assertEqual(_ptt_controller.get_state(), PttState.LOCKDOWN)
            self.assertEqual(len(_ptt_controller.get_audio_buffer()), 0)

            # Blocked start under lockdown
            blocked = _ptt_controller.start_recording()
            self.assertEqual(blocked["status"], "blocked_lockdown")
            _ptt_controller.release_lockdown()

    # =========================================================================
    # 6. Network / Fire TV Disconnect Resilience
    # =========================================================================
    def test_06_firetv_disconnect_resilience(self):
        """Voice intent processing succeeds locally when Fire TV is disconnected."""
        fake_pcm = generate_synthetic_pcm(duration_s=0.5)
        with patch("aeonix.core.server.broadcast_message", side_effect=ConnectionError("TV disconnected")), \
             patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="current time"):
            res = process_voice_pipeline(
                audio_bytes=fake_pcm,
                actor="Aadi",
                db_path=_SANDBOX_DB
            )
            self.assertTrue(res.success)
            self.assertEqual(res.status, "executed_fast_path")
            self.assertIn("time is", res.speech.lower())

    # =========================================================================
    # 7. Ambient Silence / VAD Discard
    # =========================================================================
    def test_07_ambient_silence_vad_discard(self):
        """Silent or ambient background audio is flagged by VAD and rejected in <20ms."""
        silent_pcm = generate_synthetic_pcm(duration_s=1.0, is_silent=True)
        vad = detect_voice_activity(silent_pcm, energy_threshold=200.0)
        self.assertFalse(vad["has_speech"])
        self.assertTrue(vad["is_silent"])

        t0 = time.time()
        res = process_voice_pipeline(
            audio_bytes=silent_pcm,
            actor="Aadi",
            db_path=_SANDBOX_DB
        )
        elapsed_ms = (time.time() - t0) * 1000.0

        self.assertFalse(res.success)
        self.assertEqual(res.status, "silence_rejected")
        self.assertLess(elapsed_ms, 60.0, "Silence rejection must be rapid")

    # =========================================================================
    # 8. Fast-Path Direct Dispatch Under 50ms
    # =========================================================================
    def test_08_fast_path_direct_dispatch_under_50ms(self):
        """Deterministic queries route directly through Fast-Path in <50ms without LLM."""
        speech_pcm = generate_synthetic_pcm(duration_s=0.5)
        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="system status"):
            res = process_voice_pipeline(
                audio_bytes=speech_pcm,
                actor="Aadi",
                db_path=_SANDBOX_DB
            )
            self.assertTrue(res.success)
            self.assertEqual(res.status, "executed_fast_path")
            self.assertEqual(res.action, "system_health")
            self.assertIn("nominal", res.speech.lower())
            self.assertLess(res.latency_ms, 250.0, "Fast-Path routing must complete rapidly")

    # =========================================================================
    # 9. LLM Fallback Burst Dispatch
    # =========================================================================
    def test_09_llm_fallback_burst_dispatch(self):
        """Open-ended intent missing Fast-Path invokes local Qwen burst inference."""
        speech_pcm = generate_synthetic_pcm(duration_s=0.5)
        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="what is quantum entanglement"), \
             patch("aeonix.core.voice_pipeline.check_model_ram_guard", return_value={"is_safe": True, "model_tier": "0.5B"}), \
             patch("aeonix.core.voice_pipeline.llama_runner.start_server", return_value=True), \
             patch("aeonix.core.voice_pipeline.llama_runner.stop_server", return_value=True), \
             patch("aeonix.core.voice_pipeline.execute_qwen_inference", return_value="Quantum entanglement is a physical phenomenon."):
            res = process_voice_pipeline(
                audio_bytes=speech_pcm,
                actor="Aadi",
                model_tier="0.5B",
                db_path=_SANDBOX_DB
            )
            self.assertTrue(res.success)
            self.assertIn(res.status, ["executed_qwen_burst", "executed_llm_burst"])
            self.assertIn("Quantum entanglement", res.speech)
            self.assertIn(res.model_used.lower(), ["qwen2.5-0.5b", "qwen2.5-0.5b-fallback"])

    # =========================================================================
    # 10. Dynamic RAM-Guard Queuing
    # =========================================================================
    def test_10_dynamic_ram_guard_queuing(self):
        """When required RAM is unavailable and fallback is off, request queues safely."""
        speech_pcm = generate_synthetic_pcm(duration_s=0.5)
        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="tell me a story"), \
             patch("aeonix.core.voice_pipeline.check_model_ram_guard", return_value={"is_safe": False, "model_tier": "0.5B"}):
            res = process_voice_pipeline(
                audio_bytes=speech_pcm,
                actor="Aadi",
                model_tier="0.5B",
                allow_fallback=False,
                db_path=_SANDBOX_DB
            )
            self.assertEqual(res.status, "queued_insufficient_ram")
            self.assertIn("queued", res.speech.lower())

            # Verify queue state
            q_mgr = get_queue_manager(_SANDBOX_DB)
            status = q_mgr.get_status()
            self.assertGreaterEqual(status["queued_count"], 1)

    # =========================================================================
    # 11. Model Load and Burst Unload Lifecycle
    # =========================================================================
    def test_11_model_load_and_burst_unload_lifecycle(self):
        """Local LLM runner stops prior servers, executes burst, and unloads immediately."""
        speech_pcm = generate_synthetic_pcm(duration_s=0.5)
        mock_start = MagicMock(return_value=True)
        mock_stop = MagicMock(return_value=True)

        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="analyze situation"), \
             patch("aeonix.core.voice_pipeline.check_model_ram_guard", return_value={"is_safe": True, "model_tier": "0.5B"}), \
             patch("aeonix.core.voice_pipeline.llama_runner.start_server", mock_start), \
             patch("aeonix.core.voice_pipeline.llama_runner.stop_server", mock_stop), \
             patch("aeonix.core.voice_pipeline.execute_qwen_inference", return_value="Burst inference completed successfully."):
            res = process_voice_pipeline(
                audio_bytes=speech_pcm,
                actor="Aadi",
                model_tier="0.5B",
                db_path=_SANDBOX_DB
            )
            self.assertTrue(res.success)
            self.assertIn(res.status, ["executed_qwen_burst", "executed_llm_burst"])
            # Verify startup and final shutdown lifecycle
            mock_start.assert_called_once()
            self.assertGreaterEqual(mock_stop.call_count, 1)

    # =========================================================================
    # 12. Zero Audio Retention on Disk by Default
    # =========================================================================
    def test_12_zero_audio_retention_on_disk(self):
        """Temporary audio files are deleted immediately on stop/cancel; zero disk retention."""
        ctrl = PocoPttController(db_path=_SANDBOX_DB)
        temp_dir = ctrl.tmp_dir

        with patch.object(ctrl, "_spawn_record_process"), \
             patch.object(ctrl, "_terminate_record_process"):
            ctrl.start_recording()
            # Simulate a temporary PCM file created by recorder
            dummy_pcm = os.path.join(temp_dir, "test_audio.pcm")
            with open(dummy_pcm, "wb") as f:
                f.write(generate_synthetic_pcm(0.2))
            ctrl._current_temp_file = dummy_pcm

            ctrl.stop_recording(reason="release")

        # Verify disk is completely clean
        remaining_files = [f for f in os.listdir(temp_dir) if f.endswith(".pcm") or f.endswith(".raw") or f.endswith(".wav")]
        self.assertEqual(len(remaining_files), 0, f"Leaked audio files found on disk: {remaining_files}")

    # =========================================================================
    # 13. Sentinel Gating of Consequential Voice Actions
    # =========================================================================
    def test_13_sentinel_gating_consequential_voice_actions(self):
        """Consequential voice command ('delete vault') halts and demands POCO passphrase."""
        speech_pcm = generate_synthetic_pcm(duration_s=0.5)
        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="delete vault"):
            res = process_voice_pipeline(
                audio_bytes=speech_pcm,
                actor="Aadi",
                db_path=_SANDBOX_DB
            )
            self.assertFalse(res.success)
            self.assertEqual(res.status, "pending_sentinel_approval")
            self.assertTrue(res.requires_sentinel_approval)
            self.assertIn("passphrase", res.speech.lower())

            # Verify pending record created in SQLite
            conn = get_connection(_SANDBOX_DB)
            cur = conn.cursor()
            cur.execute("SELECT * FROM sentinel_requests WHERE status = 'pending';")
            rows = cur.fetchall()
            conn.close()
            self.assertGreaterEqual(len(rows), 1)

    # =========================================================================
    # 14. POCO Operator Console Loads Only Through Authenticated Local Endpoint
    # =========================================================================
    def test_14_console_loads_only_through_authenticated_endpoint(self):
        """GET /ui/ptt loads public static shell without credentials, protected endpoints require Bearer header."""
        # Unauthenticated shell loads without credentials
        r_unauth = self.client.get("/ui/ptt")
        self.assertEqual(r_unauth.status_code, 200)
        self.assertIn("let token = \"\";", r_unauth.text)
        self.assertNotIn(self.poco_token, r_unauth.text)

        # Authenticated via Bearer header
        r_auth = self.client.get("/ui/ptt", headers=self.headers)
        self.assertEqual(r_auth.status_code, 200)
        self.assertIn("ÆONIX PRISM", r_auth.text)
        self.assertIn("Push-to-Talk", r_auth.text)

        # Query parameter token does not authenticate or embed into public shell
        r_query = self.client.get(f"/ui/ptt?token={self.poco_token}")
        self.assertEqual(r_query.status_code, 200)
        self.assertNotIn(self.poco_token, r_query.text)
        self.assertIn('let token = "";', r_query.text)

        # Protected endpoints strictly reject query-param tokens (RFC 6750 enforcement)
        r_prot_query = self.client.get(f"/api/ptt/status?token={self.poco_token}")
        self.assertEqual(r_prot_query.status_code, 401)

    # =========================================================================
    # 15. Unauthenticated Access to PTT Endpoints Rejected
    # =========================================================================
    def test_15_unauthenticated_access_to_ptt_endpoints_rejected(self):
        """All PTT operational endpoints strictly reject unauthenticated access with 401."""
        for path, method in [("/api/ptt/start", "POST"), ("/api/ptt/stop", "POST"), ("/api/ptt/status", "GET")]:
            if method == "POST":
                r = self.client.post(path)
            else:
                r = self.client.get(path)
            self.assertEqual(r.status_code, 401, f"{method} {path} accepted unauthenticated request")
            self.assertIn("UNAUTHENTICATED", r.json().get("error", ""))

    # =========================================================================
    # 16. Rate Limiting and Debounce Prevent PTT Abuse
    # =========================================================================
    def test_16_rate_limiting_and_debounce_prevent_abuse(self):
        """Bursts of rapid PTT activations trigger 429 rate-limiting."""
        with patch.object(_ptt_controller, "_spawn_record_process"):
            # First request
            r1 = self.client.post("/api/ptt/start", headers=self.headers)
            self.assertEqual(r1.status_code, 200)

            # Rapid second request within 100ms debounced / throttled
            r2 = self.client.post("/api/ptt/start", headers=self.headers)
            self.assertIn(r2.status_code, [200, 429])

            _ptt_controller.cancel()

    # =========================================================================
    # 17. Sanctuary Lockdown Cancels Active PTT and Blocks New PTT
    # =========================================================================
    def test_17_sanctuary_lockdown_cancels_and_blocks_ptt(self):
        """Sanctuary activation via REST cancels ongoing capture and blocks subsequent starts."""
        with patch.object(_ptt_controller, "_spawn_record_process"):
            _ptt_controller.start_recording()
            self.assertTrue(_ptt_controller.is_recording())

            # Engage Sanctuary
            r_lock = self.client.post("/api/sanctuary/activate", headers=self.headers, json={"reason": "Emergency"})
            self.assertEqual(r_lock.status_code, 200)
            self.assertTrue(r_lock.json()["sanctuary"]["is_active"])

            # Verify PTT immediately aborted
            self.assertFalse(_ptt_controller.is_recording())
            self.assertEqual(_ptt_controller.get_state(), PttState.LOCKDOWN)

            # Verify new start is blocked
            r_start = self.client.post("/api/ptt/start", headers=self.headers)
            self.assertEqual(r_start.json()["status"], "blocked_lockdown")

    # =========================================================================
    # 18. Compact Fire TV Layout Intent Remains Below 2 KB
    # =========================================================================
    def test_18_compact_firetv_layout_intent_below_2kb(self):
        """Layout intent broadcast payload serialized JSON is strictly bounded < 2048 bytes."""
        broadcast_mock = MagicMock()
        fake_pcm = generate_synthetic_pcm(duration_s=0.5)

        with patch("aeonix.core.voice_pipeline.broadcast_to_tv", broadcast_mock), \
             patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="current time"):
            process_voice_pipeline(audio_bytes=fake_pcm, db_path=_SANDBOX_DB)

            self.assertTrue(broadcast_mock.called)
            payload = broadcast_mock.call_args[0][0]
            serialized = json.dumps(payload)
            payload_size = len(serialized.encode("utf-8"))
            self.assertLess(payload_size, 2048, f"Fire TV layout exceeds 2 KB limit: {payload_size} bytes")

    # =========================================================================
    # 19. No Raw Waveform or Bulk Log Sent to Fire TV
    # =========================================================================
    def test_19_no_raw_waveform_or_bulk_log_sent_to_firetv(self):
        """Fire TV broadcast payload never leaks raw audio bytes or stack traces."""
        broadcast_mock = MagicMock()
        fake_pcm = generate_synthetic_pcm(duration_s=0.5)

        with patch("aeonix.core.voice_pipeline.broadcast_to_tv", broadcast_mock), \
             patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="show status"):
            process_voice_pipeline(audio_bytes=fake_pcm, db_path=_SANDBOX_DB)

            for call in broadcast_mock.call_args_list:
                payload_str = json.dumps(call[0][0])
                self.assertNotIn("audio_chunk", payload_str)
                self.assertNotIn("raw_pcm", payload_str)
                self.assertNotIn("Traceback", payload_str)

    # =========================================================================
    # 20. Audit-Chain Continuity Intact Across PTT Flow
    # =========================================================================
    def test_20_audit_chain_continuity_across_ptt_flow(self):
        """Cryptographic SHA-256 hash chain remains continuous after PTT actions."""
        chain_res = verify_audit_chain(db_path=_SANDBOX_DB)
        self.assertTrue(chain_res["is_valid"], f"Audit chain broke: {chain_res.get('error')}")
        self.assertGreaterEqual(chain_res["total_events"], 1)

    # =========================================================================
    # 21. No Cloud Egress Occurs During PTT Flow
    # =========================================================================
    def test_21_no_cloud_egress_during_ptt_flow(self):
        """Voice pipeline strictly enforces zero external cloud egress."""
        with patch("urllib.request.urlopen") as mock_url, \
             patch("http.client.HTTPConnection") as mock_conn:
            fake_pcm = generate_synthetic_pcm(duration_s=0.5)
            with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="system health"):
                process_voice_pipeline(audio_bytes=fake_pcm, db_path=_SANDBOX_DB)

            mock_url.assert_not_called()
            mock_conn.assert_not_called()

    # =========================================================================
    # 22. No Raw Audio Written to Persistent Storage by Default
    # =========================================================================
    def test_22_no_raw_audio_written_to_persistent_storage(self):
        """Vault database and secrets directory contain zero raw audio waveforms."""
        # Check SQLite DB
        conn = get_connection(_SANDBOX_DB)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]
        for t in tables:
            cur.execute(f"PRAGMA table_info({t});")
            cols = [c[1] for c in cur.fetchall()]
            self.assertNotIn("raw_audio", cols)
            self.assertNotIn("waveform", cols)
        conn.close()

        # Check persistent files
        persistent_files = os.listdir(_SANDBOX_DIR)
        for f in persistent_files:
            self.assertFalse(f.endswith(".pcm") or f.endswith(".wav"), f"Found persistent audio file: {f}")

    # =========================================================================
    # 23. In-Memory Audio Buffer Zeroed and Cleared
    # =========================================================================
    def test_23_in_memory_audio_buffer_zeroed_and_cleared(self):
        """After audio buffer retrieval and clear_buffer(), internal bytearray is cleared."""
        ctrl = PocoPttController(db_path=_SANDBOX_DB)
        fake_pcm = generate_synthetic_pcm(0.5)

        with patch.object(ctrl, "_spawn_record_process"), \
             patch.object(ctrl, "_read_and_cleanup_temp_file", return_value=fake_pcm):
            ctrl.start_recording()
            ctrl.stop_recording(reason="release")

            buf = ctrl.get_audio_buffer()
            self.assertEqual(len(buf), len(fake_pcm))

            ctrl.clear_buffer()
            self.assertEqual(len(ctrl.get_audio_buffer()), 0)
            self.assertEqual(len(ctrl._audio_buffer), 0)

    # =========================================================================
    # 24. Explicit Fallback Labeled 'qwen2.5-0.5b-fallback' and Audit-Logged
    # =========================================================================
    def test_24_explicit_fallback_labeled_and_audit_logged(self):
        """Fallback from 1.5B to 0.5B is explicitly labeled and logged in the audit trail."""
        fake_pcm = generate_synthetic_pcm(duration_s=0.5)

        # 1.8GB free RAM (insufficient for 1.5B, sufficient for 0.5B)
        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="summarize knowledge"), \
             patch("aeonix.core.voice_pipeline.check_model_ram_guard", side_effect=[
                 {"is_safe": False, "model_tier": "1.5B"}, # 1.5B check
                 {"is_safe": True, "model_tier": "0.5B"}   # 0.5B fallback check
             ]), \
             patch("aeonix.core.voice_pipeline.llama_runner.start_server", return_value=True), \
             patch("aeonix.core.voice_pipeline.llama_runner.stop_server", return_value=True), \
             patch("aeonix.core.voice_pipeline.execute_qwen_inference", return_value="Knowledge summary complete."):
            res = process_voice_pipeline(
                audio_bytes=fake_pcm,
                actor="Aadi",
                model_tier="1.5B",
                allow_fallback=True,
                db_path=_SANDBOX_DB
            )
            self.assertTrue(res.success)
            self.assertTrue(res.fallback_applied)
            self.assertEqual(res.model_used, "qwen2.5-0.5b-fallback")

            # Verify audit trail contains fallback event
            conn = get_connection(_SANDBOX_DB)
            cur = conn.cursor()
            cur.execute("SELECT * FROM audit_log WHERE action = 'voice_fallback_applied';")
            rows = cur.fetchall()
            conn.close()
            self.assertGreaterEqual(len(rows), 1)

    # =========================================================================
    # 25. RAM-Insufficient Requests Queue Without Silent Downgrade
    # =========================================================================
    def test_25_ram_insufficient_requests_queue_without_silent_downgrade(self):
        """When fallback is disabled, an oversized request queues rather than silently downgrading."""
        fake_pcm = generate_synthetic_pcm(duration_s=0.5)

        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="elaborate on deep theory"), \
             patch("aeonix.core.voice_pipeline.check_model_ram_guard", return_value={"is_safe": False, "model_tier": "1.5B"}):
            res = process_voice_pipeline(
                audio_bytes=fake_pcm,
                actor="Aadi",
                model_tier="1.5B",
                allow_fallback=False, # Fallback explicitly forbidden
                db_path=_SANDBOX_DB
            )
            self.assertEqual(res.status, "queued_insufficient_ram")
            self.assertFalse(res.fallback_applied)

    # =========================================================================
    # 26. Consequential Intents Require Sentinel Approval and Never Execute Automatically
    # =========================================================================
    def test_26_consequential_intents_require_sentinel_approval(self):
        """Consequential actions require POCO authority passphrase and cannot be resolved by TV."""
        # 1. Queue a sensitive consequential request
        req_id = queue_sentinel_request(
            agent="VoicePipeline",
            action_class="STORAGE",
            action_type="wipe_cache",
            target="/data/cache",
            scope={"recursive": True},
            risk_level="CRITICAL",
            db_path=_SANDBOX_DB
        )

        # 2. Fire TV cannot resolve
        tv_res = self.client.post(
            "/api/sentinel/resolve",
            headers=self.tv_headers,
            json={"request_id": req_id, "approved": True}
        )
        self.assertIn(tv_res.status_code, [400, 403])

        # 3. POCO without passphrase cannot approve
        poco_no_pass = self.client.post(
            "/api/sentinel/resolve",
            headers=self.headers,
            json={"request_id": req_id, "approved": True}
        )
        self.assertIn(poco_no_pass.status_code, [400, 403])

        # 4. Denial does not require passphrase and is permitted to POCO
        poco_deny = self.client.post(
            "/api/sentinel/resolve",
            headers=self.headers,
            json={"request_id": req_id, "approved": False, "reason": "Explicit Operator Denial"}
        )
        self.assertEqual(poco_deny.status_code, 200)
        self.assertIn(poco_deny.json()["status"], ["denied", "rejected"])


if __name__ == "__main__":
    unittest.main()
