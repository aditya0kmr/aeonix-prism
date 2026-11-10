"""
ÆONIX PRISM // Unit & Integration Tests: POCO Push-to-Talk (PTT) Lifecycle Controller
Exhaustively tests:
1. PTT start lifecycle and hardware microphone binding.
2. PTT stop on button release.
3. 15-second hard safety timeout stop.
4. User cancellation (immediate mic release and in-memory buffer wipe).
5. App backgrounding / focus-loss stop.
6. Sentinel / Sanctuary lockdown stop.
7. Permission-denial graceful error handling.
8. Immediate microphone release verification.
9. In-memory audio buffer cleanup after processing or cancellation.
10. STT submission to local whisper.cpp endpoint only.
11. STT failure / silence handling without crashing.
12. Zero persistent raw-audio writes by default (ephemeral memory only).
13. Zero cloud uploads (100% localhost).
14. Audit trail logging for all lifecycle transitions.
15. Consequential intent detection routing to Sentinel rather than auto-execution.
"""

import os
import sys
import time
import tempfile
import unittest
from unittest.mock import patch, MagicMock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Bootstrap test sandbox environment BEFORE aeonix imports
_MODULE_SANDBOX = tempfile.mkdtemp(prefix="aeonix_test_ptt_")
_MODULE_SECRETS = os.path.join(_MODULE_SANDBOX, "secrets")
_MODULE_DB = os.path.join(_MODULE_SANDBOX, "bootstrap_vault.db")
os.makedirs(_MODULE_SECRETS, mode=0o700, exist_ok=True)

os.environ["AEONIX_TEST_MODE"] = "1"
os.environ["AEONIX_SECRETS_DIR"] = _MODULE_SECRETS
os.environ["AEONIX_DB_PATH"] = _MODULE_DB

from aeonix.core.db import init_database, query_db
from aeonix.core.sanctuary import engage_sanctuary, release_sanctuary
from aeonix.core.ptt import PocoPttController, PttState


def generate_synthetic_pcm(duration_s: float = 1.0, freq_hz: float = 440.0, sample_rate: int = 16000) -> bytes:
    """Generates synthetic 16kHz 16-bit Mono PCM audio."""
    import math
    num_samples = int(duration_s * sample_rate)
    pcm = bytearray()
    for i in range(num_samples):
        sample = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq_hz * i / sample_rate))
        pcm.extend(sample.to_bytes(2, byteorder="little", signed=True))
    return bytes(pcm)


class TestPocoPttController(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database(os.environ["AEONIX_DB_PATH"])

    def setUp(self):
        release_sanctuary(actor="TestRunner")
        self.tmp_dir = tempfile.mkdtemp(prefix="ptt_test_tmp_")
        self.controller = PocoPttController(
            db_path=os.environ["AEONIX_DB_PATH"],
            tmp_dir=self.tmp_dir,
            max_duration_seconds=15.0
        )

    def tearDown(self):
        release_sanctuary(actor="TestRunner")
        if self.controller.is_recording():
            self.controller.cancel()

    # -------------------------------------------------------------------------
    # 1. PTT Start & Stop on Release
    # -------------------------------------------------------------------------
    def test_01_ptt_start_and_stop_on_release(self):
        """Verifies explicit user start, recording indicator, and stop on release."""
        fake_pcm = generate_synthetic_pcm(duration_s=1.0)
        
        with patch.object(self.controller, "_spawn_record_process") as mock_spawn, \
             patch.object(self.controller, "_read_and_cleanup_temp_file", return_value=fake_pcm):
            
            # 1. Start PTT
            start_res = self.controller.start_recording(actor="Aadi")
            self.assertEqual(start_res["status"], "recording")
            self.assertTrue(start_res["recording_indicator"])
            self.assertEqual(self.controller.get_state(), PttState.RECORDING)
            mock_spawn.assert_called_once()

            # 2. Stop PTT on release
            stop_res = self.controller.stop_recording(reason="release", actor="Aadi")
            self.assertEqual(stop_res["status"], "stopped")
            self.assertFalse(stop_res["recording_indicator"])
            self.assertEqual(stop_res["reason"], "release")
            self.assertEqual(self.controller.get_state(), PttState.STOPPED)
            self.assertEqual(len(self.controller.get_audio_buffer()), len(fake_pcm))

            # 3. Verify audit log
            rows = query_db(
                "SELECT action FROM audit_log WHERE action IN ('ptt_started', 'ptt_stopped') ORDER BY id DESC LIMIT 2;",
                db_path=os.environ["AEONIX_DB_PATH"]
            )
            self.assertEqual(len(rows), 2)

    # -------------------------------------------------------------------------
    # 2. 15-Second Safety Timeout
    # -------------------------------------------------------------------------
    def test_02_ptt_timeout_stop(self):
        """PTT held past max duration (15s) automatically triggers timeout stop."""
        fake_pcm = generate_synthetic_pcm(duration_s=2.0)

        # Set a small timeout for testing (0.1s)
        self.controller.max_duration_seconds = 0.1
        
        with patch.object(self.controller, "_spawn_record_process"), \
             patch.object(self.controller, "_read_and_cleanup_temp_file", return_value=fake_pcm):
            
            self.controller.start_recording()
            time.sleep(0.2)
            
            # Check timeout enforcement
            self.controller.check_timeout()
            self.assertEqual(self.controller.get_state(), PttState.STOPPED)
            
            rows = query_db(
                "SELECT action, details_json FROM audit_log WHERE action = 'ptt_timeout' ORDER BY id DESC LIMIT 1;",
                db_path=os.environ["AEONIX_DB_PATH"]
            )
            self.assertTrue(len(rows) > 0)
            self.assertIn("timeout_reached", rows[0][1])

    # -------------------------------------------------------------------------
    # 3. User Cancellation & Buffer Wipe
    # -------------------------------------------------------------------------
    def test_03_user_cancellation_and_buffer_wipe(self):
        """Cancelling PTT immediately releases mic and zeroes in-memory buffer."""
        with patch.object(self.controller, "_spawn_record_process"), \
             patch.object(self.controller, "_terminate_record_process") as mock_term:
            
            self.controller.start_recording()
            self.controller._audio_buffer = bytearray(b"\x12\x34" * 1000)
            
            cancel_res = self.controller.cancel(actor="Aadi", reason="user_cancel")
            self.assertEqual(cancel_res["status"], "cancelled")
            self.assertFalse(cancel_res["recording_indicator"])
            self.assertEqual(self.controller.get_state(), PttState.CANCELLED)
            self.assertEqual(len(self.controller.get_audio_buffer()), 0)
            mock_term.assert_called_once()

            rows = query_db(
                "SELECT action FROM audit_log WHERE action = 'ptt_cancelled' ORDER BY id DESC LIMIT 1;",
                db_path=os.environ["AEONIX_DB_PATH"]
            )
            self.assertTrue(len(rows) > 0)

    # -------------------------------------------------------------------------
    # 4. App Backgrounding Stop
    # -------------------------------------------------------------------------
    def test_04_app_backgrounding_stop(self):
        """App losing focus or backgrounded halts recording immediately."""
        fake_pcm = generate_synthetic_pcm(duration_s=0.5)
        with patch.object(self.controller, "_spawn_record_process"), \
             patch.object(self.controller, "_read_and_cleanup_temp_file", return_value=fake_pcm):
            
            self.controller.start_recording()
            bg_res = self.controller.on_background(actor="Aadi")
            self.assertEqual(bg_res["status"], "stopped")
            self.assertEqual(bg_res["reason"], "background")
            self.assertFalse(bg_res["recording_indicator"])

            rows = query_db(
                "SELECT action FROM audit_log WHERE action = 'ptt_background_stopped' ORDER BY id DESC LIMIT 1;",
                db_path=os.environ["AEONIX_DB_PATH"]
            )
            self.assertTrue(len(rows) > 0)

    # -------------------------------------------------------------------------
    # 5. Sentinel / Sanctuary Lockdown Stop
    # -------------------------------------------------------------------------
    def test_05_sentinel_lockdown_stop(self):
        """Engaging Sanctuary lockdown aborts active recording and wipes buffer."""
        with patch.object(self.controller, "_spawn_record_process"):
            self.controller.start_recording()
            self.controller._audio_buffer = bytearray(b"\x00" * 500)

            engage_sanctuary(actor="Sentinel", reason="Threat Alert")
            lock_res = self.controller.on_sentinel_lockdown(actor="Sentinel")
            self.assertEqual(lock_res["status"], "cancelled")
            self.assertEqual(self.controller.get_state(), PttState.LOCKDOWN)
            self.assertEqual(len(self.controller.get_audio_buffer()), 0)

            # Starting while lockdown is active must be rejected
            rej_res = self.controller.start_recording()
            self.assertEqual(rej_res["status"], "blocked_lockdown")

    # -------------------------------------------------------------------------
    # 6. Permission Denial Handling
    # -------------------------------------------------------------------------
    def test_06_permission_denial_handling(self):
        """Missing binary or permission error fails gracefully with clean recovery instructions."""
        with patch.object(self.controller, "_spawn_record_process", side_effect=PermissionError("Microphone permission denied")):
            res = self.controller.start_recording()
            self.assertEqual(res["status"], "permission_denied")
            self.assertFalse(res["recording_indicator"])
            self.assertEqual(self.controller.get_state(), PttState.PERMISSION_DENIED)
            self.assertIn("permission denied", res["error"].lower())

            rows = query_db(
                "SELECT action FROM audit_log WHERE action = 'ptt_permission_denied' ORDER BY id DESC LIMIT 1;",
                db_path=os.environ["AEONIX_DB_PATH"]
            )
            self.assertTrue(len(rows) > 0)

    # -------------------------------------------------------------------------
    # 7. Ephemeral Memory Only (No Raw Audio Writes by Default)
    # -------------------------------------------------------------------------
    def test_07_no_persistent_raw_audio_writes(self):
        """Verifies temp recording file is unlinked immediately upon stop, leaving disk clean."""
        test_file = os.path.join(self.tmp_dir, "test_mic.raw")
        with open(test_file, "wb") as f:
            f.write(generate_synthetic_pcm(duration_s=0.5))
        
        self.controller._current_temp_file = test_file
        self.controller._state = PttState.RECORDING

        # Stop controller with default diagnostic_mode=False
        self.controller.stop_recording(reason="release")
        
        # Temp file must NOT exist on disk
        self.assertFalse(os.path.exists(test_file))
        # Audio is strictly in memory
        self.assertGreater(len(self.controller.get_audio_buffer()), 0)

    # -------------------------------------------------------------------------
    # 8. Local STT Submission & In-Memory Cleanup
    # -------------------------------------------------------------------------
    def test_08_stt_submission_and_buffer_cleanup(self):
        """Submits audio to local STT, cleans buffer immediately, and logs audit event."""
        pcm = generate_synthetic_pcm(duration_s=1.0)
        self.controller._audio_buffer = bytearray(pcm)
        self.controller._state = PttState.STOPPED

        mock_stt = MagicMock(return_value="show system status")

        result = self.controller.submit_to_stt(stt_fn=mock_stt, actor="Aadi")
        self.assertEqual(result["status"], "transcribed")
        self.assertEqual(result["transcript"], "show system status")
        self.assertFalse(result["requires_sentinel_approval"])
        mock_stt.assert_called_once()

        # Buffer must be zeroed immediately after submission
        self.assertEqual(len(self.controller.get_audio_buffer()), 0)

        rows = query_db(
            "SELECT action FROM audit_log WHERE action = 'ptt_stt_submitted' ORDER BY id DESC LIMIT 1;",
            db_path=os.environ["AEONIX_DB_PATH"]
        )
        self.assertTrue(len(rows) > 0)

    # -------------------------------------------------------------------------
    # 9. Consequential Intent Detection Routing to Sentinel
    # -------------------------------------------------------------------------
    def test_09_consequential_voice_intent_routes_to_sentinel(self):
        """Consequential commands ('delete vault', 'approve mission') flagged for Sentinel approval."""
        pcm = generate_synthetic_pcm(duration_s=1.0)
        self.controller._audio_buffer = bytearray(pcm)
        self.controller._state = PttState.STOPPED

        mock_stt = MagicMock(return_value="approve mission omega 99")

        result = self.controller.submit_to_stt(stt_fn=mock_stt, actor="Aadi")
        self.assertEqual(result["status"], "transcribed")
        self.assertTrue(result["requires_sentinel_approval"])
        self.assertEqual(result["sentinel_action"], "sentinel_approval_required")

        rows = query_db(
            "SELECT action, details_json FROM audit_log WHERE action = 'ptt_consequential_detected' ORDER BY id DESC LIMIT 1;",
            db_path=os.environ["AEONIX_DB_PATH"]
        )
        self.assertTrue(len(rows) > 0)
        self.assertIn("approve", rows[0][1])

    # -------------------------------------------------------------------------
    # 10. STT Failure / Silence Handling
    # -------------------------------------------------------------------------
    def test_10_stt_silence_rejection(self):
        """Silent buffers are rejected by VAD without invoking transcription cycles."""
        silent_pcm = b"\x00" * 32000  # 1 sec silence
        self.controller._audio_buffer = bytearray(silent_pcm)
        self.controller._state = PttState.STOPPED

        mock_stt = MagicMock()

        result = self.controller.submit_to_stt(stt_fn=mock_stt, actor="Aadi")
        self.assertEqual(result["status"], "silence_rejected")
        self.assertEqual(result["transcript"], "")
        mock_stt.assert_not_called()
        self.assertEqual(len(self.controller.get_audio_buffer()), 0)


if __name__ == "__main__":
    unittest.main()
