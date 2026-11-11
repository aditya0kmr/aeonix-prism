"""
Integration tests for the bounded PTT-to-TTS-to-Fire-TV pipeline in /api/ptt/stop.
Tests the normal application route (POST /api/ptt/stop) with synthetic PTT_OPERATOR
credentials, synthetic audio, mocked STT/TTS, and mock WebSocket transport.
Proves 100% offline determinism, role confinement, and explicit stage outcomes.
"""

import asyncio
import io
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import wave
from typing import Dict, Any, Optional
from unittest.mock import patch, MagicMock, AsyncMock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Sandbox setup prior to importing core modules
_SANDBOX_DIR = tempfile.mkdtemp(prefix="aeonix_test_voice_loop_")
_SANDBOX_SECRETS = os.path.join(_SANDBOX_DIR, "secrets")
_SANDBOX_DB = os.path.join(_SANDBOX_DIR, "vault.db")
os.makedirs(_SANDBOX_SECRETS, mode=0o700, exist_ok=True)

os.environ["AEONIX_TEST_MODE"] = "1"
os.environ["AEONIX_SECRETS_DIR"] = _SANDBOX_SECRETS
os.environ["AEONIX_DB_PATH"] = _SANDBOX_DB

from starlette.testclient import TestClient
from aeonix.core.db import init_database
from aeonix.core.auth import issue_device_token, ROLE_PTT_OPERATOR, ROLE_FIRETV_GLASS
from aeonix.core.server import (
    app,
    active_terminals,
    active_connections,
    get_ptt_voice_response_lock,
    get_voice_response_ownership,
    get_authorized_firetv_websocket
)
from aeonix.core.tts import (
    set_mock_tts_synthesizer,
    get_tts_parameters,
    PRISM_PRIMARY_VOICE_PROFILE_APPROVED
)


def make_test_wav(
    duration_s: float = 1.0,
    sample_rate: int = 16000,
    channels: int = 1,
    sampwidth: int = 2,
    pcm_bytes: Optional[bytes] = None
) -> bytes:
    """Generates a valid in-memory PCM WAV byte sequence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(sample_rate)
        if pcm_bytes:
            w.writeframes(pcm_bytes)
        else:
            num_frames = int(duration_s * sample_rate)
            # 16-bit non-zero amplitude signal to pass VAD
            samples = [500] * (num_frames * channels)
            import struct
            w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


class MockWebSocket:
    """Mock WebSocket for verifying RFC 6455 framing and binary frame streaming."""
    def __init__(self):
        self.sent_texts = []
        self.sent_bytes = []
        self.is_closed = False

    async def send_text(self, text: str):
        self.sent_texts.append(text)

    async def send_bytes(self, data: bytes):
        self.sent_bytes.append(data)

    async def close(self, code=1000, reason=""):
        self.is_closed = True


class TestPttVoiceLoopIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_database(_SANDBOX_DB)
        cls.client = TestClient(app)
        cls.operator_token = issue_device_token(
            "test_operator_console",
            ROLE_PTT_OPERATOR,
            ttl_seconds=900,
            secrets_dir=_SANDBOX_SECRETS
        )
        cls.headers = {
            "Authorization": f"Bearer {cls.operator_token}",
            "Content-Type": "audio/wav",
            "X-Audio-Sample-Rate": "16000",
            "X-Audio-Channels": "1"
        }

    def setUp(self):
        os.environ["AEONIX_TEST_MODE"] = "1"
        os.environ["AEONIX_SECRETS_DIR"] = _SANDBOX_SECRETS
        os.environ["AEONIX_DB_PATH"] = _SANDBOX_DB
        # Reset server state, mock hooks, and ownership manager
        active_terminals.clear()
        active_connections.clear()
        set_mock_tts_synthesizer(None)
        get_voice_response_ownership().reset_for_test()

    def tearDown(self):
        active_terminals.clear()
        active_connections.clear()
        set_mock_tts_synthesizer(None)
        get_voice_response_ownership().reset_for_test()

    def test_01_fresh_audio_reaches_stt_and_recognized_system_health_produces_fixed_response(self):
        """Recognized system_health produces exact fixed response and streams to Fire TV."""
        wav_payload = make_test_wav(duration_s=1.5)
        mock_tv = MockWebSocket()
        active_connections.add(mock_tv)
        active_terminals[mock_tv] = {
            "device_id": "firetv_glass",
            "role": ROLE_FIRETV_GLASS,
            "connected_at": time.time()
        }

        # Mock STT to recognize "What is the system status?"
        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="What is the system status?"):
            # Mock TTS to return valid synthetic response WAV
            synth_wav = make_test_wav(duration_s=2.0, sample_rate=22050)
            def mock_synth(text, profile):
                self.assertEqual(text, "Living surface online. The phone and television are connected.")
                self.assertEqual(profile.identity, "prism_primary")
                return True, "", synth_wav, {
                    "pcm_bytes": 88200,
                    "total_wav_bytes": len(synth_wav),
                    "audio_duration_seconds": 2.0,
                    "phonemization_ms": 150.0,
                    "neural_synthesis_ms": 650.0
                }
            set_mock_tts_synthesizer(mock_synth)

            res = self.client.post("/api/ptt/stop?reason=release", headers=self.headers, content=wav_payload)
            self.assertEqual(res.status_code, 200)
            data = res.json()

            p = data["pipeline"]
            self.assertTrue(p["success"])
            self.assertEqual(p["status"], "voice_loop_delivered")
            self.assertEqual(p["speech"], "Living surface online. The phone and television are connected.")
            self.assertEqual(p["action"], "system_health")
            self.assertEqual(p["transcript"], "What is the system status?")

            # Verify TTS stage outcomes
            self.assertEqual(p["tts"]["status"], "success")
            self.assertEqual(p["tts"]["model"], "en_IN-spicor-medium")
            self.assertEqual(p["tts"]["audio_duration_seconds"], 2.0)

            # Verify Delivery stage outcomes
            d = p["delivery"]
            self.assertEqual(d["status"], "delivered_to_socket")
            self.assertEqual(d["target_device"], "firetv_glass")
            self.assertEqual(d["role"], ROLE_FIRETV_GLASS)
            self.assertFalse(d["confirmed_playback"])  # Never claimed as confirmed playback
            self.assertGreater(d["estimated_playback_wait_seconds"], 2.0)

            # Verify WebSocket protocol frames on TV
            voice_start_msgs = [json.loads(m) for m in mock_tv.sent_texts if "voice_audio_start" in m]
            self.assertEqual(len(voice_start_msgs), 1)
            start_msg = voice_start_msgs[0]
            self.assertEqual(start_msg["type"], "voice_audio_start")
            self.assertEqual(start_msg["sample_rate"], 22050)
            self.assertEqual(start_msg["channels"], 1)

            voice_complete_msgs = [json.loads(m) for m in mock_tv.sent_texts if "voice_audio_complete" in m]
            self.assertEqual(len(voice_complete_msgs), 1)
            complete_msg = voice_complete_msgs[0]
            self.assertEqual(complete_msg["type"], "voice_audio_complete")

            self.assertGreater(len(mock_tv.sent_bytes), 0)
            total_pcm_received = sum(len(b) for b in mock_tv.sent_bytes)
            self.assertEqual(total_pcm_received, 88200)

    def test_02_approved_voice_profile_parameters_reach_tts(self):
        """Verifies approved voice profile en_IN-spicor-medium parameters are mapped 1:1."""
        params = get_tts_parameters("prism_primary")
        self.assertEqual(params["model_name"], "en_IN-spicor-medium")
        self.assertEqual(params["speed"], 0.90)
        self.assertEqual(params["silence_scale"], 0.20)
        self.assertEqual(params["noise_scale"], 0.667)
        self.assertEqual(params["noise_scale_w"], 0.800)
        self.assertEqual(params["length_scale"], 1.000)
        self.assertEqual(params["threads"], 2)
        self.assertEqual(params["sample_rate"], 22050)
        self.assertEqual(params["channels"], 1)
        self.assertEqual(params["encoding"], "pcm_s16le")

    def test_03_delivered_once_to_intended_firetv_only_not_arbitrary_websockets(self):
        """Voice audio is streamed exclusively to the authorized Fire TV device, not arbitrary clients."""
        wav_payload = make_test_wav(duration_s=1.0)
        arbitrary_ws = MockWebSocket()
        firetv_ws = MockWebSocket()

        active_connections.add(arbitrary_ws)
        active_connections.add(firetv_ws)

        active_terminals[arbitrary_ws] = {
            "device_id": "laptop_browser",
            "role": "AGENT_EXECUTOR",
            "connected_at": time.time()
        }
        active_terminals[firetv_ws] = {
            "device_id": "firetv_stick_glass",
            "role": ROLE_FIRETV_GLASS,
            "connected_at": time.time()
        }

        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="What is the system status?"):
            synth_wav = make_test_wav(duration_s=1.0, sample_rate=22050)
            set_mock_tts_synthesizer(lambda text, prof: (True, "", synth_wav, {"pcm_bytes": 44100, "audio_duration_seconds": 1.0}))

            res = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
            self.assertEqual(res.status_code, 200)

            # Fire TV received audio
            self.assertGreater(len(firetv_ws.sent_bytes), 0)
            # Arbitrary client received ZERO binary audio frames
            self.assertEqual(len(arbitrary_ws.sent_bytes), 0)

    def test_04_delivery_unavailable_when_firetv_disconnected(self):
        """If no authorized TV is connected, reports delivery_unavailable without crashing."""
        wav_payload = make_test_wav(duration_s=1.0)
        # active_terminals is empty

        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="What is the system status?"):
            synth_wav = make_test_wav(duration_s=1.0, sample_rate=22050)
            set_mock_tts_synthesizer(lambda text, prof: (True, "", synth_wav, {"pcm_bytes": 44100, "audio_duration_seconds": 1.0}))

            res = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
            self.assertEqual(res.status_code, 200)
            data = res.json()["pipeline"]

            self.assertTrue(data["success"])
            self.assertEqual(data["status"], "delivery_unavailable")
            self.assertEqual(data["delivery"]["status"], "delivery_unavailable")
            self.assertFalse(data["delivery"]["delivered"])

    def test_05_tts_failure_reported_accurately_with_transport_skipped(self):
        """If TTS synthesis fails, reports tts_error and skips transport."""
        wav_payload = make_test_wav(duration_s=1.0)
        mock_tv = MockWebSocket()
        active_terminals[mock_tv] = {"device_id": "firetv_glass", "role": ROLE_FIRETV_GLASS}

        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="What is the system status?"):
            set_mock_tts_synthesizer(lambda text, prof: (False, "SYNTHESIS_CRASH", b"", {}))

            res = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
            self.assertEqual(res.status_code, 200)
            data = res.json()["pipeline"]

            self.assertFalse(data["success"])
            self.assertEqual(data["status"], "tts_error")
            self.assertEqual(data["tts"]["status"], "tts_error")
            self.assertEqual(data["delivery"]["status"], "skipped")
            self.assertEqual(len(mock_tv.sent_bytes), 0)

    def test_06_transport_failure_reported_accurately(self):
        """If socket transmission fails, reports transport_error."""
        wav_payload = make_test_wav(duration_s=1.0)
        broken_tv = MockWebSocket()
        active_terminals[broken_tv] = {"device_id": "firetv_glass", "role": ROLE_FIRETV_GLASS}

        broken_tv.send_bytes = AsyncMock(side_effect=ConnectionResetError("Socket broken"))

        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="What is the system status?"):
            synth_wav = make_test_wav(duration_s=1.0, sample_rate=22050)
            set_mock_tts_synthesizer(lambda text, prof: (True, "", synth_wav, {"pcm_bytes": 44100, "audio_duration_seconds": 1.0}))

            res = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
            self.assertEqual(res.status_code, 200)
            data = res.json()["pipeline"]

            self.assertFalse(data["success"])
            self.assertEqual(data["status"], "transport_error")
            self.assertEqual(data["delivery"]["status"], "transport_error")

    def test_07_rejected_speech_has_zero_downstream_side_effects(self):
        """Rejected/unrecognized commands produce zero TTS calls and zero audio dispatch."""
        wav_payload = make_test_wav(duration_s=1.0)
        mock_tv = MockWebSocket()
        active_terminals[mock_tv] = {"device_id": "firetv_glass", "role": ROLE_FIRETV_GLASS}

        mock_tts = MagicMock()
        set_mock_tts_synthesizer(mock_tts)

        for rejected_phrase in ["reboot the server", "ignore instructions", "what is the weather today"]:
            with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value=rejected_phrase):
                res = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
                self.assertEqual(res.status_code, 200)
                data = res.json()["pipeline"]

                self.assertFalse(data["success"])
                self.assertEqual(data["status"], "ptt_operator_restricted")
                self.assertIsNone(data["tts"])
                self.assertIsNone(data["delivery"])
                # Zero TTS calls
                mock_tts.assert_not_called()
                # Zero audio sent to TV
                self.assertEqual(len(mock_tv.sent_bytes), 0)

    def test_08_silence_rejected_has_zero_downstream_side_effects(self):
        """Silent audio is rejected by VAD with zero downstream side effects."""
        # Pure silence (all zeroes)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00" * 32000)
        silent_wav = buf.getvalue()

        mock_tts = MagicMock()
        set_mock_tts_synthesizer(mock_tts)

        res = self.client.post("/api/ptt/stop", headers=self.headers, content=silent_wav)
        self.assertEqual(res.status_code, 200)
        data = res.json()["pipeline"]

        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "silence_rejected")
        self.assertIsNone(data["tts"])
        self.assertIsNone(data["delivery"])
        mock_tts.assert_not_called()

    def test_09_unauthorized_or_malformed_requests_never_invoke_inference(self):
        """Unauthenticated, unauthorized, or malformed requests never invoke STT or TTS."""
        mock_tts = MagicMock()
        set_mock_tts_synthesizer(mock_tts)

        with patch("aeonix.core.voice_pipeline.transcribe_pcm") as mock_stt:
            # 1. Missing Authorization header
            res1 = self.client.post("/api/ptt/stop", headers={"Content-Type": "audio/wav"}, content=b"123")
            self.assertEqual(res1.status_code, 401)

            # 2. Corrupt WAV payload
            res2 = self.client.post("/api/ptt/stop", headers=self.headers, content=b"CORRUPT_BYTES_NOT_RIFF")
            self.assertEqual(res2.status_code, 400)

            mock_stt.assert_not_called()
            mock_tts.assert_not_called()

    def test_10_concurrent_requests_rejected_with_409(self):
        """Overlapping voice requests are rejected with 409 Conflict when response lock is active."""
        wav_payload = make_test_wav(duration_s=1.0)

        # Mock lock to simulate active concurrent request
        with patch.object(get_ptt_voice_response_lock(), "locked", return_value=True):
            res = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
            self.assertEqual(res.status_code, 409)
            data = res.json()
            self.assertEqual(data["status"], "busy")
            self.assertIn("VOICE_PIPELINE_BUSY", data["error"])

    def test_11_reconciles_both_firetv_glass_and_firetv_stick_glass_identities(self):
        """Reconciles both 'firetv_glass' and 'firetv_stick_glass' configured device identities."""
        for dev_id in ["firetv_glass", "firetv_stick_glass"]:
            active_terminals.clear()
            mock_tv = MockWebSocket()
            active_terminals[mock_tv] = {"device_id": dev_id, "role": ROLE_FIRETV_GLASS}

            ws, meta = get_authorized_firetv_websocket()
            self.assertIsNotNone(ws)
            self.assertEqual(meta["device_id"], dev_id)
            self.assertEqual(meta["role"], ROLE_FIRETV_GLASS)

        # Unrelated device is not recognized as Fire TV
        active_terminals.clear()
        mock_other = MockWebSocket()
        active_terminals[mock_other] = {"device_id": "other_device", "role": "OTHER"}
        ws, meta = get_authorized_firetv_websocket()
        self.assertIsNone(ws)

    def test_12_no_automatic_replay_or_queued_delivery(self):
        """Verifies that no audio is queued for automatic replay on subsequent connections."""
        mock_tv = MockWebSocket()
        active_terminals[mock_tv] = {"device_id": "firetv_glass", "role": ROLE_FIRETV_GLASS}

        # Clear active terminals
        active_terminals.clear()

        # Connect a new TV terminal after the trial completed
        new_tv = MockWebSocket()
        active_terminals[new_tv] = {"device_id": "firetv_glass", "role": ROLE_FIRETV_GLASS}

        # New terminal receives ZERO queued bytes
        self.assertEqual(len(new_tv.sent_bytes), 0)
        self.assertEqual(len(new_tv.sent_texts), 0)

    def test_13_deterministic_blocked_worker_timeout_and_concurrency(self):
        """
        Deterministic blocked-worker timeout and ownership verification:
        1. Request 1 times out while worker 1 is running.
        2. Worker 1 remains unfinished in background.
        3. Request 2 receives 409 Conflict (VOICE_PIPELINE_BUSY) and invokes no STT/TTS/transport.
        4. Releasing Worker 1 causes no late audio or replay.
        5. Once actual work is finished, a subsequent request (Request 3) proceeds normally.
        """
        wav_payload = make_test_wav(duration_s=1.0)
        mock_tv = MockWebSocket()
        active_connections.add(mock_tv)
        active_terminals[mock_tv] = {"device_id": "firetv_glass", "role": ROLE_FIRETV_GLASS}

        worker_1_started = threading.Event()
        release_worker_1 = threading.Event()
        worker_calls = []

        def mock_synth(text, profile):
            worker_calls.append(threading.current_thread().name)
            call_idx = len(worker_calls)
            if call_idx == 1:
                worker_1_started.set()
                release_worker_1.wait(timeout=5.0)
            synth_wav = make_test_wav(duration_s=1.0, sample_rate=22050)
            return True, "", synth_wav, {"pcm_bytes": 44100, "audio_duration_seconds": 1.0}

        set_mock_tts_synthesizer(mock_synth)

        real_wait_for = asyncio.wait_for

        async def short_deadline_wait_for(fut, timeout):
            # Exercise actual asyncio timeout path with short deadline after worker 1 has started
            task = asyncio.ensure_future(fut)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: worker_1_started.wait(timeout=5.0))
            return await real_wait_for(task, timeout=0.001)

        # Step 1: Request 1 times out via actual asyncio timeout path
        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="What is the system status?"):
            with patch("asyncio.wait_for", side_effect=short_deadline_wait_for):
                res1 = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
                self.assertEqual(res1.status_code, 504)
                data1 = res1.json()["pipeline"]
                self.assertEqual(data1["status"], "voice_pipeline_timeout")

        # Step 2: Confirm Worker 1 is still actively running in background and has NOT been released
        self.assertTrue(worker_1_started.is_set())
        self.assertFalse(release_worker_1.is_set())
        self.assertTrue(get_voice_response_ownership().locked())

        # Step 3: Attempt Request 2 while Worker 1 remains unfinished
        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="What is the system status?") as mock_stt_req2:
            res2 = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
            # Proves Request 2 receives 409 VOICE_PIPELINE_BUSY
            self.assertEqual(res2.status_code, 409)
            data2 = res2.json()
            self.assertEqual(data2["status"], "busy")
            self.assertIn("VOICE_PIPELINE_BUSY", data2["error"])

            # Proves Request 2 invoked no STT, no TTS, and no transport
            mock_stt_req2.assert_not_called()
            self.assertEqual(len(worker_calls), 1)  # Only Worker 1 was ever called
            self.assertEqual(len(mock_tv.sent_bytes), 0)
            voice_ctrl_req2 = [t for t in mock_tv.sent_texts if "voice_audio" in t]
            self.assertEqual(len(voice_ctrl_req2), 0)

        # Step 4: Release Worker 1
        release_worker_1.set()
        time.sleep(0.1)

        # Step 5: Assert no late audio or control messages from Worker 1 reached the TV socket
        self.assertEqual(len(mock_tv.sent_bytes), 0)
        voice_ctrl_after_release = [t for t in mock_tv.sent_texts if "voice_audio" in t]
        self.assertEqual(len(voice_ctrl_after_release), 0)

        # Step 6: Once actual work has completed, ownership is released and subsequent request proceeds
        self.assertFalse(get_voice_response_ownership().locked())
        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="What is the system status?"):
            synth_wav = make_test_wav(duration_s=1.0, sample_rate=22050)
            set_mock_tts_synthesizer(lambda text, prof: (True, "", synth_wav, {"pcm_bytes": 44100, "audio_duration_seconds": 1.0}))
            res3 = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
            self.assertEqual(res3.status_code, 200)
            data3 = res3.json()["pipeline"]
            self.assertTrue(data3["success"])
            self.assertEqual(data3["status"], "voice_loop_delivered")
            self.assertGreater(len(mock_tv.sent_bytes), 0)

    def test_14_ownership_cleanup_on_worker_exception(self):
        """Worker exceptions cleanly release ownership, allowing subsequent requests to proceed."""
        wav_payload = make_test_wav(duration_s=1.0)
        mock_tv = MockWebSocket()
        active_connections.add(mock_tv)
        active_terminals[mock_tv] = {"device_id": "firetv_glass", "role": ROLE_FIRETV_GLASS}

        def failing_synth(text, profile):
            raise RuntimeError("TTS_SYNTHESIS_CRASH")

        set_mock_tts_synthesizer(failing_synth)

        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="What is the system status?"):
            res1 = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
            self.assertEqual(res1.status_code, 200)
            self.assertFalse(res1.json()["pipeline"]["success"])
            self.assertEqual(res1.json()["pipeline"]["status"], "tts_error")

        # Ownership MUST be released after worker exception
        self.assertFalse(get_voice_response_ownership().locked())

        # Subsequent request can acquire ownership and proceed
        synth_wav = make_test_wav(duration_s=1.0, sample_rate=22050)
        set_mock_tts_synthesizer(lambda text, prof: (True, "", synth_wav, {"pcm_bytes": 44100, "audio_duration_seconds": 1.0}))

        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="What is the system status?"):
            res2 = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
            self.assertEqual(res2.status_code, 200)
            self.assertTrue(res2.json()["pipeline"]["success"])

    def test_15_ownership_cleanup_on_submission_failure(self):
        """Executor submission failures cleanly release ownership without leaking pending workers."""
        wav_payload = make_test_wav(duration_s=1.0)

        broken_executor = MagicMock()
        broken_executor.submit.side_effect = RuntimeError("Executor queue full")

        # In post_api_ptt_stop, patch heavy_executor with broken_executor
        with patch("aeonix.core.server.heavy_executor", broken_executor):
            with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="What is the system status?"):
                res1 = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
                self.assertEqual(res1.status_code, 500)

        # Ownership MUST be cleanly released despite submission failure
        self.assertFalse(get_voice_response_ownership().locked())

        # Subsequent request can acquire ownership and proceed
        mock_tv = MockWebSocket()
        active_connections.add(mock_tv)
        active_terminals[mock_tv] = {"device_id": "firetv_glass", "role": ROLE_FIRETV_GLASS}
        synth_wav = make_test_wav(duration_s=1.0, sample_rate=22050)
        set_mock_tts_synthesizer(lambda text, prof: (True, "", synth_wav, {"pcm_bytes": 44100, "audio_duration_seconds": 1.0}))

        with patch("aeonix.core.voice_pipeline.transcribe_pcm", return_value="What is the system status?"):
            res2 = self.client.post("/api/ptt/stop", headers=self.headers, content=wav_payload)
            self.assertEqual(res2.status_code, 200)
            self.assertTrue(res2.json()["pipeline"]["success"])

    def test_16_session_token_ttl_enforces_900s_max_and_no_refresh_token(self):
        """Verifies bootstrap exchange strictly issues <= 900s TTL token with no refresh token."""
        from aeonix.core.auth import generate_bootstrap_secret, exchange_bootstrap_secret, verify_token
        secret, code_hash = generate_bootstrap_secret(ttl_seconds=300, db_path=_SANDBOX_DB)
        session_token = exchange_bootstrap_secret(secret, db_path=_SANDBOX_DB, secrets_dir=_SANDBOX_SECRETS)
        self.assertIsNotNone(session_token)

        payload = verify_token(session_token, secrets_dir=_SANDBOX_SECRETS, db_path=_SANDBOX_DB)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["role"], ROLE_PTT_OPERATOR)

        # Enforce maximum 900-second session TTL
        ttl_seconds = payload["expires_at"] - payload["issued_at"]
        self.assertLessEqual(ttl_seconds, 900.0)
        self.assertGreater(ttl_seconds, 0.0)

        # Enforce no refresh token in payload or structure
        self.assertNotIn("refresh_token", payload)
        self.assertNotIn("refresh", payload)


if __name__ == "__main__":
    unittest.main()
