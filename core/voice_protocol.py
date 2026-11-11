"""
ÆONIX PRISM Voice Audio Streaming Protocol (Section 10 / P1-2 Transport Contract).
Handles binary PCM emission over authenticated WebSocket connections.
Zero base64 encoding; raw PCM frames delivered as binary WebSocket frames.
"""

import io
import json
import time
import uuid
import wave
from typing import Dict, Any, Tuple, Optional

# Safety boundaries
MAX_VOICE_AUDIO_BYTES = 5 * 1024 * 1024  # 5 MB safety ceiling
DEFAULT_CHUNK_SIZE = 4096                # 4 KiB per binary frame
DEFAULT_TTL_SECONDS = 30                 # Expiry safety window
EXPECTED_SAMPLE_RATE = 22050
EXPECTED_CHANNELS = 1
EXPECTED_SAMPLE_WIDTH = 2                # 16-bit PCM (pcm_s16le)


def extract_pcm_from_wav(wav_source: Any) -> Tuple[bytes, Dict[str, Any]]:
    """
    Extracts raw 16-bit mono 22050Hz PCM audio bytes and metadata from a WAV source
    (either file path str or bytes).
    Strictly validates format and enforces safety boundaries.
    """
    if isinstance(wav_source, bytes):
        wav_file = io.BytesIO(wav_source)
    elif isinstance(wav_source, str):
        wav_file = open(wav_source, "rb")
    else:
        raise ValueError("wav_source must be a file path string or bytes")

    try:
        with wave.open(wav_file, "rb") as w:
            channels = w.getnchannels()
            sample_width = w.getsampwidth()
            sample_rate = w.getframerate()
            num_frames = w.getnframes()

            if channels != EXPECTED_CHANNELS:
                raise ValueError(f"Unsupported channel count: {channels} (expected {EXPECTED_CHANNELS})")
            if sample_width != EXPECTED_SAMPLE_WIDTH:
                raise ValueError(f"Unsupported sample width: {sample_width} bytes (expected {EXPECTED_SAMPLE_WIDTH})")
            if sample_rate != EXPECTED_SAMPLE_RATE:
                raise ValueError(f"Unsupported sample rate: {sample_rate} Hz (expected {EXPECTED_SAMPLE_RATE})")

            pcm_data = w.readframes(num_frames)
            total_bytes = len(pcm_data)

            if total_bytes > MAX_VOICE_AUDIO_BYTES:
                raise ValueError(f"Audio payload exceeds safety ceiling: {total_bytes} > {MAX_VOICE_AUDIO_BYTES}")

            metadata = {
                "channels": channels,
                "sample_width": sample_width,
                "sample_rate": sample_rate,
                "total_bytes": total_bytes,
                "encoding": "pcm_s16le",
            }
            return pcm_data, metadata
    finally:
        if isinstance(wav_source, str):
            wav_file.close()


def create_start_message(message_id: str, total_bytes: int, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Dict[str, Any]:
    """Creates a validated voice_audio_start control message."""
    if not message_id or not message_id.strip():
        raise ValueError("message_id is required")
    if total_bytes <= 0 or total_bytes > MAX_VOICE_AUDIO_BYTES:
        raise ValueError(f"total_bytes must be between 1 and {MAX_VOICE_AUDIO_BYTES}")

    now = int(time.time())
    return {
        "type": "voice_audio_start",
        "message_id": message_id.strip(),
        "encoding": "pcm_s16le",
        "sample_rate": EXPECTED_SAMPLE_RATE,
        "channels": EXPECTED_CHANNELS,
        "total_bytes": total_bytes,
        "expires_at": now + ttl_seconds
    }


def create_complete_message(message_id: str) -> Dict[str, Any]:
    """Creates a voice_audio_complete control message."""
    if not message_id or not message_id.strip():
        raise ValueError("message_id is required")
    return {
        "type": "voice_audio_complete",
        "message_id": message_id.strip()
    }


def create_cancel_message(message_id: str, reason: str = "cancelled") -> Dict[str, Any]:
    """Creates a voice_audio_cancel control message."""
    if not message_id or not message_id.strip():
        raise ValueError("message_id is required")
    return {
        "type": "voice_audio_cancel",
        "message_id": message_id.strip(),
        "reason": reason[:64]
    }


def create_error_message(message_id: str, error: str) -> Dict[str, Any]:
    """Creates a voice_audio_error control message."""
    if not message_id or not message_id.strip():
        raise ValueError("message_id is required")
    return {
        "type": "voice_audio_error",
        "message_id": message_id.strip(),
        "error": error[:128]
    }


async def stream_voice_audio(
    websocket,
    wav_source: Any,
    message_id: Optional[str] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> Dict[str, Any]:
    """
    Streams a WAV file over an active WebSocket connection using the P1-2 Transport Contract:
      1. Validates WAV format and extracts raw PCM.
      2. Sends voice_audio_start JSON control message.
      3. Sends raw PCM in binary WebSocket frames.
      4. Sends voice_audio_complete JSON control message.
    Returns transmission stats.
    """
    if message_id is None:
        message_id = f"voice-{uuid.uuid4().hex[:12]}"

    pcm_data, meta = extract_pcm_from_wav(wav_source)
    total_bytes = len(pcm_data)

    start_msg = create_start_message(message_id, total_bytes, ttl_seconds)
    await websocket.send_text(json.dumps(start_msg))

    bytes_sent = 0
    chunks_sent = 0
    for offset in range(0, total_bytes, chunk_size):
        chunk = pcm_data[offset:offset + chunk_size]
        await websocket.send_bytes(chunk)
        bytes_sent += len(chunk)
        chunks_sent += 1

    complete_msg = create_complete_message(message_id)
    await websocket.send_text(json.dumps(complete_msg))

    return {
        "message_id": message_id,
        "total_bytes": total_bytes,
        "bytes_sent": bytes_sent,
        "chunks_sent": chunks_sent,
        "status": "completed"
    }


async def broadcast_voice_audio(
    connections,
    wav_source: Any,
    message_id: Optional[str] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> Dict[str, Any]:
    """
    Streams voice audio to all connections in the provided iterable.
    """
    if message_id is None:
        message_id = f"voice-{uuid.uuid4().hex[:12]}"

    pcm_data, meta = extract_pcm_from_wav(wav_source)
    total_bytes = len(pcm_data)

    start_msg = create_start_message(message_id, total_bytes, ttl_seconds)
    start_json = json.dumps(start_msg)

    # Deliver start message to all
    for ws in list(connections):
        try:
            await ws.send_text(start_json)
        except Exception:
            pass

    # Stream chunks in lockstep
    for offset in range(0, total_bytes, chunk_size):
        chunk = pcm_data[offset:offset + chunk_size]
        for ws in list(connections):
            try:
                await ws.send_bytes(chunk)
            except Exception:
                pass

    complete_msg = create_complete_message(message_id)
    complete_json = json.dumps(complete_msg)
    for ws in list(connections):
        try:
            await ws.send_text(complete_json)
        except Exception:
            pass

    return {
        "message_id": message_id,
        "total_bytes": total_bytes,
        "status": "completed"
    }

