"""
ÆONIX PRISM // Sovereign Speech-To-Text (STT) Subsystem
100% Offline, Zero Cloud Inference using whisper.cpp on Dimensity 810 ARM NEON.
Includes Voice Activity Detection (VAD), 15s audio bounding, and Fire TV remote mic policy.
Supports both English-only (ggml-tiny.en.bin) and Multilingual (ggml-tiny.bin) Whisper models.
"""

import os
import subprocess
import wave
import io
import time
import math
import struct
import hashlib
import tempfile
from typing import Optional, Dict, Any, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHISPER_BIN = os.path.join(BASE_DIR, "bin", "whisper-cli")
MODELS_DIR = os.path.join(BASE_DIR, "models")
LIB_PATH = os.path.join(BASE_DIR, "bin")

DEFAULT_EN_MODEL = os.path.join(MODELS_DIR, "ggml-tiny.en.bin")
DEFAULT_MULTILINGUAL_MODEL = os.path.join(MODELS_DIR, "ggml-tiny.bin")

MAX_AUDIO_DURATION_SECONDS = 15
MAX_AUDIO_BYTES = 16000 * 2 * MAX_AUDIO_DURATION_SECONDS  # 480,000 bytes (15s ceiling)


def get_active_model_path() -> str:
    """Returns the resolved Whisper model path with English-only fallback."""
    env_model = os.getenv("AEONIX_WHISPER_MODEL")
    if env_model and os.path.exists(env_model):
        return env_model
    if os.path.exists(DEFAULT_MULTILINGUAL_MODEL):
        return DEFAULT_MULTILINGUAL_MODEL
    return DEFAULT_EN_MODEL


def get_active_language(model_path: Optional[str] = None) -> str:
    """Returns the target transcription language ('auto' or specific ISO-639-1 code)."""
    env_lang = os.getenv("AEONIX_WHISPER_LANG")
    if env_lang:
        return env_lang.strip().lower()
    m_path = model_path or get_active_model_path()
    if m_path.endswith(".en.bin"):
        return "en"
    return "auto"


def get_stt_model_info() -> Dict[str, Any]:
    """Returns detailed forensic metadata on active and available Whisper models."""
    m_path = get_active_model_path()
    available = []
    if os.path.exists(MODELS_DIR):
        for fname in os.listdir(MODELS_DIR):
            if fname.startswith("ggml-") and fname.endswith(".bin"):
                available.append(fname)

    file_size = os.path.getsize(m_path) if os.path.exists(m_path) else 0
    sha256 = ""
    if os.path.exists(m_path):
        h = hashlib.sha256()
        with open(m_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        sha256 = h.hexdigest()

    is_multilingual = not m_path.endswith(".en.bin")
    return {
        "active_model_path": m_path,
        "active_model_name": os.path.basename(m_path),
        "is_multilingual": is_multilingual,
        "active_language": get_active_language(m_path),
        "model_sha256": sha256,
        "model_size_bytes": file_size,
        "available_models": sorted(available),
        "multilingual_model_installed": os.path.exists(DEFAULT_MULTILINGUAL_MODEL),
        "english_fallback_available": os.path.exists(DEFAULT_EN_MODEL),
        "whisper_bin_installed": os.path.exists(WHISPER_BIN)
    }


def detect_voice_activity(
    pcm_bytes: bytes, 
    sample_rate: int = 16000, 
    energy_threshold: float = 200.0
) -> Dict[str, Any]:
    """
    Computes root-mean-square (RMS) energy to detect presence of human voice activity.
    Rejects silent buffers to save inference cycles on Dimensity 810.
    """
    if pcm_bytes.startswith(b"RIFF") and len(pcm_bytes) >= 44:
        raw_pcm = pcm_bytes[44:]
    else:
        raw_pcm = pcm_bytes

    num_samples = len(raw_pcm) // 2
    if num_samples == 0:
        return {"has_speech": False, "rms_energy": 0.0, "duration_s": 0.0, "is_silent": True}

    samples = struct.unpack(f"<{num_samples}h", raw_pcm[:num_samples * 2])
    sum_sq = sum(s * s for s in samples)
    rms = math.sqrt(sum_sq / num_samples)
    duration_s = round(num_samples / sample_rate, 2)

    has_speech = (rms >= energy_threshold)
    return {
        "has_speech": has_speech,
        "rms_energy": round(rms, 2),
        "duration_s": duration_s,
        "is_silent": not has_speech
    }


def get_remote_mic_feasibility() -> Dict[str, Any]:
    """
    Assesses Fire TV remote microphone accessibility.
    Documented OS restriction: Amazon Fire OS 7 intercepts the Alexa microphone button at the kernel/vsuite level.
    """
    return {
        "remote_mic_available": False,
        "classification": "GATED_BY_OEM_FIREOS",
        "reason": "Alexa voice button intercepted by com.amazon.vsuite.client. Third-party home launchers cannot bind mic button without rooting.",
        "sovereign_architecture": "POCO M4 Pro 5G serves as primary push-to-talk input; transcription and intent updates stream dynamically to Living Glass."
    }


def transcribe_wav(
    wav_path: str,
    model_path: Optional[str] = None,
    lang: Optional[str] = None
) -> str:
    """Transcribes a 16kHz WAV file using whisper-cli on POCO ARM NEON."""
    m_path = model_path or get_active_model_path()
    if not os.path.exists(WHISPER_BIN) or not os.path.exists(m_path):
        raise FileNotFoundError(f"Whisper binary ({WHISPER_BIN}) or model ({m_path}) not found.")
    
    target_lang = lang or get_active_language(m_path)
    if m_path.endswith(".en.bin"):
        target_lang = "en"  # Enforce English for English-only model

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{LIB_PATH}:{env.get('LD_LIBRARY_PATH', '')}"
    
    cmd = [
        WHISPER_BIN,
        "-m", m_path,
        "-f", wav_path,
        "-nt",           # No timestamps
        "-t", "4",       # 4 threads for Dimensity 810
        "--no-prints",   # Suppress banner
        "-l", target_lang
    ]
    
    try:
        res = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
        text = res.stdout.strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned = " ".join(lines)
        return cleaned
    except Exception as e:
        return f"[STT Error: {str(e)}]"


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Converts 16-bit Mono PCM raw bytes to standard WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)      # Mono
        wav_file.setsampwidth(2)      # 16-bit (2 bytes)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buf.getvalue()


def transcribe_pcm(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    model_path: Optional[str] = None,
    lang: Optional[str] = None
) -> str:
    """Transcribes raw PCM bytes by writing a temporary WAV file and invoking whisper-cli."""
    if len(pcm_bytes) > MAX_AUDIO_BYTES:
        raise ValueError(f"AUDIO_PAYLOAD_TOO_LARGE: Audio payload {len(pcm_bytes)} bytes exceeds 15-second ceiling ({MAX_AUDIO_BYTES} bytes)")

    # If the bytes already start with 'RIFF', it's already a WAV file!
    if pcm_bytes.startswith(b"RIFF"):
        wav_bytes = pcm_bytes
    else:
        wav_bytes = pcm_to_wav(pcm_bytes, sample_rate)
    
    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, f"aeonix_ptt_{int(time.time()*1000)}.wav")
    try:
        with open(tmp_path, "wb") as f:
            f.write(wav_bytes)
        return transcribe_wav(tmp_path, model_path=model_path, lang=lang)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


if __name__ == "__main__":
    info = get_stt_model_info()
    print("STT Model Info:", info)
