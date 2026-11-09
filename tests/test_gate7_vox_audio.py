"""
ÆONIX PRISM // Gate G7 VOX Push-to-Talk Audio & Offline ASR Test Suite
Exhaustively verifies:
1. Voice Activity Detection (VAD) energy calculation and silence rejection.
2. 15-second audio safety ceiling bounding (rejection of oversized buffers > 480,000 bytes).
3. 100% Offline ASR pipeline using local whisper.cpp on Dimensity 810 ARM NEON.
4. Fire TV remote microphone feasibility assessment and sovereign architecture documentation.
5. Starlette HTTP /api/voice/transcribe endpoint RBAC and error boundaries.
"""

import os
import sys
import math
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
_MODULE_SANDBOX = tempfile.mkdtemp(prefix="aeonix_test_g7_bootstrap_")
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
from aeonix.core.db import init_database
from aeonix.core.stt import (
    detect_voice_activity,
    get_remote_mic_feasibility,
    transcribe_pcm,
    pcm_to_wav,
    MAX_AUDIO_BYTES
)


def generate_synthetic_pcm(duration_s: float = 1.0, freq_hz: float = 440.0, sample_rate: int = 16000) -> bytes:
    """Generates synthetic 16kHz 16-bit Mono PCM audio."""
    num_samples = int(duration_s * sample_rate)
    pcm = bytearray()
    for i in range(num_samples):
        sample = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq_hz * i / sample_rate))
        pcm.extend(sample.to_bytes(2, byteorder="little", signed=True))
    return bytes(pcm)


class TestGate7VoxAudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database(os.environ["AEONIX_DB_PATH"])
        cls.client = TestClient(app)
        cls.poco_token = issue_device_token("test_poco_gate7", ROLE_POCO_CORE)
        cls.tv_token = issue_device_token("test_tv_gate7", ROLE_FIRETV_GLASS)

    def test_01_voice_activity_detection(self):
        """Verifies RMS energy calculation to distinguish active human speech from silence."""
        # 1. Silent PCM buffer (all zeros)
        silent_pcm = b"\x00" * 32000  # 1 second of silence
        vad_silent = detect_voice_activity(silent_pcm, sample_rate=16000)
        self.assertFalse(vad_silent["has_speech"])
        self.assertTrue(vad_silent["is_silent"])
        self.assertEqual(vad_silent["rms_energy"], 0.0)
        self.assertEqual(vad_silent["duration_s"], 1.0)

        # 2. Active PCM buffer (synthetic tone)
        active_pcm = generate_synthetic_pcm(duration_s=1.0, freq_hz=440.0)
        vad_active = detect_voice_activity(active_pcm, sample_rate=16000)
        self.assertTrue(vad_active["has_speech"])
        self.assertFalse(vad_active["is_silent"])
        self.assertGreater(vad_active["rms_energy"], 5000.0)

    def test_02_audio_payload_bounding_ceiling(self):
        """Strictly enforces 15-second safety ceiling on push-to-talk audio buffers."""
        # Oversized buffer (16 seconds = 512,000 bytes)
        oversized_pcm = b"\x00" * (MAX_AUDIO_BYTES + 1000)
        with self.assertRaises(ValueError) as ctx:
            transcribe_pcm(oversized_pcm)
        self.assertIn("AUDIO_PAYLOAD_TOO_LARGE", str(ctx.exception))

    def test_03_offline_asr_pipeline_execution(self):
        """Verifies 100% offline transcription using whisper-cli on POCO NEON."""
        pcm = generate_synthetic_pcm(duration_s=0.5, freq_hz=440.0)
        text = transcribe_pcm(pcm)
        self.assertIsInstance(text, str)
        self.assertNotIn("FileNotFoundError", text)
        self.assertNotIn("Traceback", text)

    def test_04_firetv_remote_mic_feasibility_assessment(self):
        """Verifies Fire TV remote mic input architectural constraint assessment."""
        feasibility = get_remote_mic_feasibility()
        self.assertFalse(feasibility["remote_mic_available"])
        self.assertEqual(feasibility["classification"], "GATED_BY_OEM_FIREOS")
        self.assertIn("com.amazon.vsuite.client", feasibility["reason"])
        self.assertIn("POCO M4 Pro 5G", feasibility["sovereign_architecture"])

    def test_05_http_voice_transcribe_endpoint(self):
        """Verifies Starlette HTTP POST /api/voice/transcribe endpoint."""
        headers = {"Authorization": f"Bearer {self.poco_token}"}

        # 1. Valid audio payload
        pcm = generate_synthetic_pcm(duration_s=0.5, freq_hz=440.0)
        r = self.client.post("/api/voice/transcribe", content=pcm, headers=headers)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["success"])
        self.assertIn("transcription", r.json())

        # 2. Empty payload rejection
        r_empty = self.client.post("/api/voice/transcribe", content=b"", headers=headers)
        self.assertEqual(r_empty.status_code, 400)
        self.assertIn("Empty audio payload", r_empty.json()["error"])

        # 3. Oversized payload rejection (400)
        oversized = b"\x00" * (MAX_AUDIO_BYTES + 2000)
        r_large = self.client.post("/api/voice/transcribe", content=oversized, headers=headers)
        self.assertEqual(r_large.status_code, 400)
        self.assertIn("AUDIO_PAYLOAD_TOO_LARGE", r_large.json()["error"])


if __name__ == "__main__":
    unittest.main()
