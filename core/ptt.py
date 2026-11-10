"""
ÆONIX PRISM // Sovereign Push-to-Talk (PTT) Lifecycle Controller
Hardware: POCO M4 Pro 5G Internal Microphone.
Enforces strict hardware release guarantees, 100% ephemeral in-memory audio buffers,
Voice Activity Detection (VAD), Sentinel Gate authority boundaries, and zero cloud leaks.
"""

import os
import time
import shutil
import subprocess
import tempfile
import threading
from enum import Enum
from typing import Dict, Any, Optional, Callable

from aeonix.core.sanctuary import is_sanctuary_active
from aeonix.core.db import log_audit_event
from aeonix.core.stt import detect_voice_activity, transcribe_pcm
from aeonix.core.model_queue import is_query_consequential

TERMUX_MIC_BIN = "/data/data/com.termux/files/usr/bin/termux-microphone-record"
MAX_RECORDING_SECONDS = 15.0
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1


class PttState(str, Enum):
    IDLE = "IDLE"
    ARMED = "ARMED"
    RECORDING = "RECORDING"
    STOPPED = "STOPPED"
    CANCELLED = "CANCELLED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    LOCKDOWN = "LOCKDOWN"


class PocoPttController:
    """
    Controls the physical push-to-talk audio capture lifecycle on the POCO handset.
    Ensures that microphone access is strictly ephemeral, never continuous, and
    aborts instantly on release, timeout, backgrounding, permission denial, or lockdown.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        tmp_dir: Optional[str] = None,
        max_duration_seconds: float = MAX_RECORDING_SECONDS,
        diagnostic_mode: bool = False
    ):
        self.db_path = db_path
        self.tmp_dir = tmp_dir or tempfile.gettempdir()
        self.max_duration_seconds = max_duration_seconds
        self.diagnostic_mode = diagnostic_mode

        self._state: PttState = PttState.IDLE
        self._record_proc: Optional[subprocess.Popen] = None
        self._current_temp_file: Optional[str] = None
        self._audio_buffer: bytearray = bytearray()
        self._start_time: Optional[float] = None
        self._lock = threading.Lock()

    def get_state(self) -> PttState:
        with self._lock:
            return self._state

    def is_recording(self) -> bool:
        with self._lock:
            return self._state == PttState.RECORDING

    def get_audio_buffer(self) -> bytes:
        with self._lock:
            return bytes(self._audio_buffer)

    def _spawn_record_process(self, output_path: str, limit_seconds: float):
        """Spawns termux-microphone-record in background."""
        cmd = [
            TERMUX_MIC_BIN,
            "-f", output_path,
            "-l", str(int(limit_seconds)),
            "-r", str(DEFAULT_SAMPLE_RATE),
            "-c", str(DEFAULT_CHANNELS)
        ]
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _terminate_record_process(self):
        """Signals termux-microphone-record to quit and releases microphone handle."""
        try:
            # 1. Native clean quit
            if os.path.exists(TERMUX_MIC_BIN):
                subprocess.run([TERMUX_MIC_BIN, "-q"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0)
        except Exception:
            pass

        if self._record_proc:
            try:
                self._record_proc.terminate()
                self._record_proc.wait(timeout=0.2)
            except Exception:
                try:
                    self._record_proc.kill()
                except Exception:
                    pass
            self._record_proc = None

    def _read_and_cleanup_temp_file(self, file_path: str) -> bytes:
        """Reads raw captured bytes and immediately unlinks temporary file from disk."""
        data = b""
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    data = f.read()
            except Exception:
                data = b""
            finally:
                if not self.diagnostic_mode:
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
        return data

    def start_recording(self, actor: str = "Aadi") -> Dict[str, Any]:
        """
        Begins user-initiated physical audio capture on POCO microphone.
        Strict Safety: Fails closed if Sanctuary lockdown is active or permissions are missing.
        """
        with self._lock:
            # 1. Check for Sanctuary / Sentinel lockdown
            if is_sanctuary_active() or self._state == PttState.LOCKDOWN:
                self._state = PttState.LOCKDOWN
                try:
                    log_audit_event(
                        actor=actor,
                        action="ptt_lockdown_blocked",
                        target="poco_microphone",
                        result="blocked",
                        details={"reason": "sanctuary_lockdown_active"},
                        db_path=self.db_path
                    )
                except Exception:
                    pass
                return {
                    "status": "blocked_lockdown",
                    "recording_indicator": False,
                    "error": "SENTINEL_LOCKDOWN: Sanctuary mode is active. Microphone recording is prohibited."
                }

            if self._state == PttState.RECORDING:
                return {
                    "status": "recording",
                    "recording_indicator": True,
                    "notice": "Already recording"
                }

            # 2. Prepare ephemeral temporary file path
            now = time.time()
            self._current_temp_file = os.path.join(self.tmp_dir, f"aeonix_mic_{int(now*1000)}.raw")
            self._audio_buffer.clear()
            self._start_time = now

            # 3. Spawn recording process
            try:
                self._record_proc = self._spawn_record_process(self._current_temp_file, self.max_duration_seconds)
                self._state = PttState.RECORDING
            except Exception as e:
                self._state = PttState.PERMISSION_DENIED
                self._current_temp_file = None
                self._record_proc = None
                try:
                    log_audit_event(
                        actor=actor,
                        action="ptt_permission_denied",
                        target="poco_microphone",
                        result="error",
                        details={"error": str(e)},
                        db_path=self.db_path
                    )
                except Exception:
                    pass
                return {
                    "status": "permission_denied",
                    "recording_indicator": False,
                    "error": f"MIC_PERMISSION_DENIED: Unable to access POCO microphone ({e}). Grant RECORD_AUDIO permission to Termux / Termux:API."
                }

            try:
                log_audit_event(
                    actor=actor,
                    action="ptt_started",
                    target="poco_microphone",
                    result="success",
                    details={"max_duration_s": self.max_duration_seconds},
                    db_path=self.db_path
                )
            except Exception:
                pass

            return {
                "status": "recording",
                "recording_indicator": True,
                "started_at": now,
                "max_duration_s": self.max_duration_seconds
            }

    def check_timeout(self) -> bool:
        """Checks if active recording has exceeded the max duration safety limit."""
        with self._lock:
            if self._state == PttState.RECORDING and self._start_time:
                elapsed = time.time() - self._start_time
                if elapsed >= self.max_duration_seconds:
                    self._stop_recording_locked(reason="timeout", actor="SystemSafety")
                    return True
        return False

    def _stop_recording_locked(self, reason: str = "release", actor: str = "Aadi") -> Dict[str, Any]:
        """Internal helper to stop recording while lock is held."""
        if self._state != PttState.RECORDING:
            return {"status": "idle", "recording_indicator": False}

        # 1. Terminate process and release hardware microphone immediately
        self._terminate_record_process()

        # 2. Read ephemeral audio into memory and clean file
        raw_bytes = b""
        if self._current_temp_file:
            raw_bytes = self._read_and_cleanup_temp_file(self._current_temp_file)
            self._current_temp_file = None

        self._audio_buffer = bytearray(raw_bytes)
        self._state = PttState.STOPPED
        elapsed = round(time.time() - (self._start_time or time.time()), 2)
        self._start_time = None

        action_name = "ptt_timeout" if reason == "timeout" else (
            "ptt_background_stopped" if reason == "background" else "ptt_stopped"
        )

        try:
            log_audit_event(
                actor=actor,
                action=action_name,
                target="poco_microphone",
                result="success",
                details={
                    "reason": reason,
                    "duration_s": elapsed,
                    "buffer_bytes": len(raw_bytes),
                    "timeout_reached": (reason == "timeout")
                },
                db_path=self.db_path
            )
        except Exception:
            pass

        return {
            "status": "stopped",
            "reason": reason,
            "duration_s": elapsed,
            "audio_bytes_length": len(raw_bytes),
            "recording_indicator": False
        }

    def stop_recording(self, reason: str = "release", actor: str = "Aadi") -> Dict[str, Any]:
        """Stops active recording on button release or manual trigger."""
        with self._lock:
            return self._stop_recording_locked(reason=reason, actor=actor)

    def cancel(self, actor: str = "Aadi", reason: str = "user_cancel") -> Dict[str, Any]:
        """
        Immediately halts recording, releases hardware microphone,
        and completely wipes any captured audio buffer from memory.
        """
        with self._lock:
            self._terminate_record_process()

            if self._current_temp_file and os.path.exists(self._current_temp_file):
                try:
                    os.remove(self._current_temp_file)
                except OSError:
                    pass
                self._current_temp_file = None

            # Completely zero and clear in-memory buffer
            self._audio_buffer.clear()
            self._state = PttState.CANCELLED
            self._start_time = None

            try:
                log_audit_event(
                    actor=actor,
                    action="ptt_cancelled",
                    target="poco_microphone",
                    result="cancelled",
                    details={"reason": reason},
                    db_path=self.db_path
                )
            except Exception:
                pass

            return {
                "status": "cancelled",
                "reason": reason,
                "recording_indicator": False
            }

    def on_background(self, actor: str = "Aadi") -> Dict[str, Any]:
        """App losing focus or backgrounded halts recording immediately."""
        with self._lock:
            if self._state == PttState.RECORDING:
                return self._stop_recording_locked(reason="background", actor=actor)
            return {"status": "idle", "recording_indicator": False}

    def on_sentinel_lockdown(self, actor: str = "Sentinel") -> Dict[str, Any]:
        """Sentinel / Sanctuary lockdown aborts capture and zeroes buffer."""
        res = self.cancel(actor=actor, reason="sentinel_lockdown")
        with self._lock:
            self._state = PttState.LOCKDOWN
        return res

    def release_lockdown(self):
        """Releases lockdown state back to IDLE."""
        with self._lock:
            if self._state == PttState.LOCKDOWN:
                self._state = PttState.IDLE

    def clear_buffer(self):
        """Manually zeroes and clears in-memory audio buffer."""
        with self._lock:
            self._audio_buffer.clear()

    def submit_to_stt(
        self,
        stt_fn: Optional[Callable[[bytes], str]] = None,
        actor: str = "Aadi"
    ) -> Dict[str, Any]:
        """
        Submits ephemeral in-memory audio to the local whisper.cpp STT engine.
        Enforces Voice Activity Detection (VAD) silence rejection and
        guarantees in-memory buffer cleanup immediately after transcription.
        Consequential voice intents are routed to Sentinel approval rather than auto-executed.
        """
        with self._lock:
            raw_pcm = bytes(self._audio_buffer)
            # Wipe in-memory buffer immediately to ensure zero audio retention
            self._audio_buffer.clear()

        if not raw_pcm:
            return {
                "status": "empty_audio",
                "transcript": "",
                "requires_sentinel_approval": False
            }

        # 1. Voice Activity Detection (RMS energy check)
        vad = detect_voice_activity(raw_pcm)
        if vad.get("is_silent"):
            return {
                "status": "silence_rejected",
                "transcript": "",
                "vad": vad,
                "requires_sentinel_approval": False
            }

        # 2. Local STT transcription (whisper.cpp)
        try:
            if stt_fn:
                transcript = stt_fn(raw_pcm)
            else:
                transcript = transcribe_pcm(raw_pcm)
        except Exception as e:
            return {
                "status": "stt_error",
                "transcript": "",
                "error": str(e),
                "requires_sentinel_approval": False
            }

        clean_transcript = transcript.strip() if transcript else ""

        # 3. Sentinel security boundary check: consequential commands cannot auto-execute!
        is_consequential = is_query_consequential(clean_transcript)
        sentinel_action = "sentinel_approval_required" if is_consequential else "safe"

        try:
            log_audit_event(
                actor=actor,
                action="ptt_stt_submitted",
                target="whisper_cpp",
                result="success",
                details={
                    "transcript": clean_transcript,
                    "is_consequential": is_consequential,
                    "duration_s": vad.get("duration_s", 0)
                },
                db_path=self.db_path
            )
            if is_consequential:
                log_audit_event(
                    actor=actor,
                    action="ptt_consequential_detected",
                    target="sentinel_boundary",
                    result="hold_for_approval",
                    details={"transcript": clean_transcript},
                    db_path=self.db_path
                )
        except Exception:
            pass

        return {
            "status": "transcribed",
            "transcript": clean_transcript,
            "requires_sentinel_approval": is_consequential,
            "sentinel_action": sentinel_action,
            "vad": vad
        }

    def get_status(self) -> Dict[str, Any]:
        """Returns runtime status of the PTT controller."""
        with self._lock:
            now = time.time()
            elapsed = round(now - self._start_time, 2) if self._start_time else 0.0
            return {
                "state": self._state.value,
                "recording_indicator": (self._state == PttState.RECORDING),
                "elapsed_seconds": elapsed,
                "max_duration_seconds": self.max_duration_seconds,
                "audio_buffer_bytes": len(self._audio_buffer),
                "diagnostic_mode": self.diagnostic_mode,
                "is_sanctuary_active": is_sanctuary_active()
            }
