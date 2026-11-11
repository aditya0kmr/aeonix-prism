"""
Unit tests for browser-based microphone audio ingestion in /api/ptt/stop.
Verifies format contracts, WAV/RIFF validation, bounding, authentication,
ephemeral buffer cleanup, and backward compatibility with existing controller lifecycle.
"""

import io
import os
import sys
import tempfile
import unittest
import wave
from unittest.mock import patch, MagicMock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Isolated test sandbox
_SANDBOX_DIR = tempfile.mkdtemp(prefix="aeonix_test_browser_audio_")
_SANDBOX_SECRETS = os.path.join(_SANDBOX_DIR, "secrets")
_SANDBOX_DB = os.path.join(_SANDBOX_DIR, "vault.db")
os.makedirs(_SANDBOX_SECRETS, mode=0o700, exist_ok=True)

os.environ["AEONIX_TEST_MODE"] = "1"
os.environ["AEONIX_SECRETS_DIR"] = _SANDBOX_SECRETS
os.environ["AEONIX_DB_PATH"] = _SANDBOX_DB

from starlette.testclient import TestClient
from aeonix.core.server import app, _ptt_controller, validate_browser_wav_payload
from aeonix.core.auth import issue_device_token, ROLE_POCO_CORE


def make_test_wav(
    duration_s: float = 1.0,
    sample_rate: int = 16000,
    channels: int = 1,
    sampwidth: int = 2
) -> bytes:
    """Generates a valid in-memory PCM WAV byte sequence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(sample_rate)
        # Generate silence / synthetic frames
        num_frames = int(duration_s * sample_rate)
        w.writeframes(b"\x00" * (num_frames * channels * sampwidth))
    return buf.getvalue()


class TestPttBrowserAudioIngest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.valid_token = issue_device_token("test_poco_mic", ROLE_POCO_CORE, ttl_seconds=3600)
        cls.headers = {"Authorization": f"Bearer {cls.valid_token}"}

    def test_01_valid_16k_mono_pcm_ingest(self):
        """Valid 16kHz mono 16-bit PCM WAV is accepted, parsed, and forwarded to pipeline."""
        wav_data = make_test_wav(duration_s=1.0, sample_rate=16000, channels=1, sampwidth=2)
        
        headers = {
            **self.headers,
            "Content-Type": "audio/wav",
            "X-Audio-Sample-Rate": "16000",
            "X-Audio-Channels": "1"
        }
        
        with patch("aeonix.core.server.process_voice_pipeline") as mock_pipe:
            mock_pipe.return_value = MagicMock(
                success=True,
                status="success",
                speech="System status nominal.",
                action="status_report",
                tier="Tier 0 (Deterministic)",
                model_used=None,
                fallback_applied=False,
                requires_sentinel_approval=False,
                latency_ms=12.5
            )
            res = self.client.post("/api/ptt/stop?reason=release", headers=headers, content=wav_data)
            
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["status"], "stopped")
            self.assertEqual(data["source"], "browser_mic")
            self.assertEqual(data["audio_bytes_length"], 32000)  # 1.0s * 16000 * 2
            self.assertEqual(data["pipeline"]["speech"], "System status nominal.")
            mock_pipe.assert_called_once()
            # Assert forwarded audio matches raw PCM payload
            forwarded_pcm = mock_pipe.call_args[1]["audio_bytes"]
            self.assertEqual(len(forwarded_pcm), 32000)

    def test_02_invalid_missing_wav_header_rejected(self):
        """Non-WAV or corrupted binary data is rejected with 400 Bad Request."""
        headers = {**self.headers, "Content-Type": "audio/wav"}
        corrupt_data = b"NOT_A_VALID_RIFF_WAV_HEADER_CORRUPTED_BYTES"
        
        res = self.client.post("/api/ptt/stop", headers=headers, content=corrupt_data)
        self.assertEqual(res.status_code, 400)
        self.assertIn("MALFORMED_WAV_HEADER", res.json().get("error", ""))

    def test_03_empty_audio_payload_rejected(self):
        """Empty audio/wav payload is rejected with 400 Bad Request."""
        headers = {**self.headers, "Content-Type": "audio/wav"}
        res = self.client.post("/api/ptt/stop", headers=headers, content=b"")
        self.assertEqual(res.status_code, 400)
        self.assertIn("EMPTY_AUDIO", res.json().get("error", ""))

    def test_04_oversized_payload_rejected(self):
        """Audio payload exceeding 480,000 bytes (>15 seconds) is rejected with 400."""
        # 16 seconds * 16000 * 2 = 512,000 bytes
        oversized_wav = make_test_wav(duration_s=16.0, sample_rate=16000, channels=1, sampwidth=2)
        headers = {**self.headers, "Content-Type": "audio/wav"}
        
        res = self.client.post("/api/ptt/stop", headers=headers, content=oversized_wav)
        self.assertEqual(res.status_code, 400)
        err = res.json().get("error", "")
        self.assertTrue("PAYLOAD_TOO_LARGE" in err or "EXCESSIVE_DURATION" in err)

    def test_05_unsupported_sample_rate_rejected(self):
        """Audio with non-16kHz sample rate (e.g. 44.1kHz or 22.05kHz) is rejected."""
        wav_44k = make_test_wav(duration_s=1.0, sample_rate=44100, channels=1, sampwidth=2)
        headers = {**self.headers, "Content-Type": "audio/wav"}
        
        res = self.client.post("/api/ptt/stop", headers=headers, content=wav_44k)
        self.assertEqual(res.status_code, 400)
        self.assertIn("UNSUPPORTED_SAMPLE_RATE", res.json().get("error", ""))

    def test_06_unsupported_channels_rejected(self):
        """Multi-channel (stereo) audio is rejected with 400 Bad Request."""
        stereo_wav = make_test_wav(duration_s=1.0, sample_rate=16000, channels=2, sampwidth=2)
        headers = {**self.headers, "Content-Type": "audio/wav"}
        
        res = self.client.post("/api/ptt/stop", headers=headers, content=stereo_wav)
        self.assertEqual(res.status_code, 400)
        self.assertIn("UNSUPPORTED_CHANNELS", res.json().get("error", ""))

    def test_07_unsupported_bit_depth_rejected(self):
        """8-bit PCM audio is rejected with 400 Bad Request."""
        pcm_8bit_wav = make_test_wav(duration_s=1.0, sample_rate=16000, channels=1, sampwidth=1)
        headers = {**self.headers, "Content-Type": "audio/wav"}
        
        res = self.client.post("/api/ptt/stop", headers=headers, content=pcm_8bit_wav)
        self.assertEqual(res.status_code, 400)
        self.assertIn("UNSUPPORTED_BIT_DEPTH", res.json().get("error", ""))

    def test_08_unauthenticated_request_rejected(self):
        """Unauthenticated requests are rejected with 401 Unauthorized."""
        wav_data = make_test_wav(duration_s=1.0, sample_rate=16000, channels=1, sampwidth=2)
        res = self.client.post("/api/ptt/stop", headers={"Content-Type": "audio/wav"}, content=wav_data)
        self.assertEqual(res.status_code, 401)
        self.assertIn("UNAUTHENTICATED", res.json().get("error", ""))

    def test_09_ephemeral_reference_cleanup_no_disk_retention(self):
        """Browser audio is processed entirely in-memory with zero disk persistence."""
        tmp_dir = tempfile.gettempdir()
        before_files = set(os.listdir(tmp_dir))
        
        wav_data = make_test_wav(duration_s=1.0, sample_rate=16000, channels=1, sampwidth=2)
        headers = {**self.headers, "Content-Type": "audio/wav"}
        
        with patch("aeonix.core.server.process_voice_pipeline") as mock_pipe:
            mock_pipe.return_value = MagicMock(
                success=True, status="success", speech="Clean.", action="none",
                tier="Tier 0 (Deterministic)", model_used=None, fallback_applied=False,
                requires_sentinel_approval=False, latency_ms=1.0
            )
            res = self.client.post("/api/ptt/stop", headers=headers, content=wav_data)
            self.assertEqual(res.status_code, 200)

        after_files = set(os.listdir(tmp_dir))
        # Ensure no persistent mic/raw/wav files were left behind in temp dir
        new_audio_files = [f for f in (after_files - before_files) if any(f.endswith(ext) for ext in [".raw", ".wav", ".pcm"])]
        self.assertEqual(new_audio_files, [], "Raw audio files were unexpectedly persisted to disk")

    def test_10_existing_ptt_controller_backward_compatibility(self):
        """Legacy JSON invocation without audio payload still utilizes _ptt_controller."""
        with patch.object(_ptt_controller, "stop_recording", return_value={"status": "stopped", "reason": "release"}), \
             patch.object(_ptt_controller, "get_audio_buffer", return_value=b"\x00" * 3200), \
             patch.object(_ptt_controller, "clear_buffer") as mock_clear, \
             patch("aeonix.core.server.process_voice_pipeline") as mock_pipe:
            
            mock_pipe.return_value = MagicMock(
                success=True, status="success", speech="Legacy OK.", action="none",
                tier="Tier 0 (Deterministic)", model_used=None, fallback_applied=False,
                requires_sentinel_approval=False, latency_ms=1.0
            )
            
            res = self.client.post("/api/ptt/stop", headers=self.headers, json={"reason": "release"})
            self.assertEqual(res.status_code, 200)
            mock_clear.assert_called_once()
            mock_pipe.assert_called_once()


if __name__ == "__main__":
    unittest.main()
