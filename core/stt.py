"""
ÆONIX PRISM // Sovereign Speech-To-Text (STT) Subsystem
100% Offline, Zero Cloud Inference using whisper.cpp on Dimensity 810 ARM NEON.
"""

import os
import subprocess
import wave
import io
import time
import tempfile
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHISPER_BIN = os.path.join(BASE_DIR, "bin", "whisper-cli")
MODEL_PATH = os.path.join(BASE_DIR, "models", "ggml-tiny.en.bin")
LIB_PATH = os.path.join(BASE_DIR, "bin")

def transcribe_wav(wav_path: str) -> str:
    """Transcribes a 16kHz WAV file using whisper-cli."""
    if not os.path.exists(WHISPER_BIN) or not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Whisper binary ({WHISPER_BIN}) or model ({MODEL_PATH}) not found.")
    
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{LIB_PATH}:{env.get('LD_LIBRARY_PATH', '')}"
    
    cmd = [
        WHISPER_BIN,
        "-m", MODEL_PATH,
        "-f", wav_path,
        "-nt",           # No timestamps
        "-t", "4",       # 4 threads for Dimensity 810
        "--no-prints",   # Suppress banner
        "-l", "en"
    ]
    
    try:
        res = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
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

def transcribe_pcm(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """Transcribes raw PCM bytes by writing a temporary WAV file and invoking whisper-cli."""
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
        return transcribe_wav(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

if __name__ == "__main__":
    test_wav = os.path.join(BASE_DIR, "whisper.cpp", "samples", "jfk.wav")
    print(f"Testing STT with {test_wav}...")
    t0 = time.time()
    out = transcribe_wav(test_wav)
    dt = time.time() - t0
    print(f"Transcribed in {dt:.2f}s: \"{out}\"")
