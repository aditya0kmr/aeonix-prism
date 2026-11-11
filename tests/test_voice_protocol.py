"""
Unit tests for ÆONIX PRISM Voice Audio Streaming Protocol (P1-2 Transport Contract).
Tests extract_pcm_from_wav, control message construction, bounds enforcement,
mock streaming, and authenticated WebSocket transport.
"""

import io
import json
import time
import unittest
import wave
from unittest.mock import AsyncMock

from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from aeonix.core.server import app, active_connections
from aeonix.core.auth import issue_device_token, ROLE_POCO_CORE, ROLE_FIRETV_GLASS
from aeonix.core.voice_protocol import (
    MAX_VOICE_AUDIO_BYTES,
    EXPECTED_SAMPLE_RATE,
    EXPECTED_CHANNELS,
    EXPECTED_SAMPLE_WIDTH,
    extract_pcm_from_wav,
    create_start_message,
    create_complete_message,
    create_cancel_message,
    create_error_message,
    stream_voice_audio,
    broadcast_voice_audio,
)


def make_dummy_wav(channels=1, sampwidth=2, framerate=22050, num_frames=1000) -> bytes:
    """Creates an in-memory WAV bytes payload for testing."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(framerate)
        # 16-bit silence (zeros)
        raw_pcm = b"\x00" * (num_frames * channels * sampwidth)
        w.writeframes(raw_pcm)
    return buf.getvalue()


class TestVoiceProtocol(unittest.TestCase):

    def test_extract_pcm_valid(self):
        wav_bytes = make_dummy_wav(channels=1, sampwidth=2, framerate=22050, num_frames=500)
        pcm, meta = extract_pcm_from_wav(wav_bytes)
        self.assertEqual(len(pcm), 1000)  # 500 frames * 2 bytes
        self.assertEqual(meta["channels"], 1)
        self.assertEqual(meta["sample_rate"], 22050)
        self.assertEqual(meta["sample_width"], 2)
        self.assertEqual(meta["encoding"], "pcm_s16le")

    def test_extract_pcm_rejects_stereo(self):
        wav_bytes = make_dummy_wav(channels=2, sampwidth=2, framerate=22050, num_frames=100)
        with self.assertRaises(ValueError) as ctx:
            extract_pcm_from_wav(wav_bytes)
        self.assertIn("Unsupported channel count", str(ctx.exception))

    def test_extract_pcm_rejects_wrong_rate(self):
        wav_bytes = make_dummy_wav(channels=1, sampwidth=2, framerate=44100, num_frames=100)
        with self.assertRaises(ValueError) as ctx:
            extract_pcm_from_wav(wav_bytes)
        self.assertIn("Unsupported sample rate", str(ctx.exception))

    def test_extract_pcm_rejects_wrong_sample_width(self):
        wav_bytes = make_dummy_wav(channels=1, sampwidth=1, framerate=22050, num_frames=100)
        with self.assertRaises(ValueError) as ctx:
            extract_pcm_from_wav(wav_bytes)
        self.assertIn("Unsupported sample width", str(ctx.exception))

    def test_create_start_message_valid(self):
        msg = create_start_message("msg-001", 57856, ttl_seconds=20)
        self.assertEqual(msg["type"], "voice_audio_start")
        self.assertEqual(msg["message_id"], "msg-001")
        self.assertEqual(msg["encoding"], "pcm_s16le")
        self.assertEqual(msg["sample_rate"], 22050)
        self.assertEqual(msg["channels"], 1)
        self.assertEqual(msg["total_bytes"], 57856)
        self.assertGreater(msg["expires_at"], int(time.time()))

    def test_create_start_message_rejects_empty_id(self):
        with self.assertRaises(ValueError):
            create_start_message("", 1000)
        with self.assertRaises(ValueError):
            create_start_message("   ", 1000)

    def test_create_start_message_rejects_invalid_bytes(self):
        with self.assertRaises(ValueError):
            create_start_message("msg-1", 0)
        with self.assertRaises(ValueError):
            create_start_message("msg-1", -50)
        with self.assertRaises(ValueError):
            create_start_message("msg-1", MAX_VOICE_AUDIO_BYTES + 1)

    def test_create_complete_message(self):
        msg = create_complete_message("msg-002")
        self.assertEqual(msg["type"], "voice_audio_complete")
        self.assertEqual(msg["message_id"], "msg-002")

    def test_create_cancel_message(self):
        msg = create_cancel_message("msg-003", reason="user_cancelled")
        self.assertEqual(msg["type"], "voice_audio_cancel")
        self.assertEqual(msg["message_id"], "msg-003")
        self.assertEqual(msg["reason"], "user_cancelled")

    def test_create_error_message(self):
        msg = create_error_message("msg-004", error="buffer_overflow")
        self.assertEqual(msg["type"], "voice_audio_error")
        self.assertEqual(msg["message_id"], "msg-004")
        self.assertEqual(msg["error"], "buffer_overflow")

    def test_stream_voice_audio_mock(self):
        import asyncio
        wav_bytes = make_dummy_wav(channels=1, sampwidth=2, framerate=22050, num_frames=2048)
        # 2048 frames * 2 bytes = 4096 bytes

        mock_ws = AsyncMock()
        text_frames = []
        binary_frames = []

        async def fake_send_text(txt):
            text_frames.append(json.loads(txt))

        async def fake_send_bytes(b):
            binary_frames.append(b)

        mock_ws.send_text.side_effect = fake_send_text
        mock_ws.send_bytes.side_effect = fake_send_bytes

        res = asyncio.run(stream_voice_audio(mock_ws, wav_bytes, message_id="mock-1", chunk_size=1024))
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["total_bytes"], 4096)
        self.assertEqual(res["bytes_sent"], 4096)
        self.assertEqual(res["chunks_sent"], 4)  # 4096 / 1024 = 4 chunks

        # Verify control frames
        self.assertEqual(len(text_frames), 2)
        self.assertEqual(text_frames[0]["type"], "voice_audio_start")
        self.assertEqual(text_frames[0]["message_id"], "mock-1")
        self.assertEqual(text_frames[0]["total_bytes"], 4096)
        self.assertEqual(text_frames[1]["type"], "voice_audio_complete")
        self.assertEqual(text_frames[1]["message_id"], "mock-1")

        # Verify binary chunks
        self.assertEqual(len(binary_frames), 4)
        for chunk in binary_frames:
            self.assertEqual(len(chunk), 1024)

    def test_websocket_trigger_voice_test_authenticated(self):
        """Verifies voice streaming triggered over authenticated WebSocket."""
        token = issue_device_token("test_tv", role=ROLE_FIRETV_GLASS)
        client = TestClient(app)

        with client.websocket_connect(
            "/ws",
            headers={"Authorization": f"Bearer {token}"}
        ) as websocket:
            # First message from server is layout_update
            first_msg = websocket.receive_json()
            self.assertEqual(first_msg.get("type"), "layout_update")

            # Trigger voice test
            websocket.send_json({
                "type": "trigger_voice_test",
                "message_id": "test-live-1"
            })

            # Server should send voice_audio_start control frame
            start_frame = websocket.receive_json()
            self.assertEqual(start_frame["type"], "voice_audio_start")
            self.assertEqual(start_frame["message_id"], "test-live-1")
            self.assertEqual(start_frame["encoding"], "pcm_s16le")
            self.assertEqual(start_frame["sample_rate"], 22050)
            self.assertEqual(start_frame["channels"], 1)
            total_bytes = start_frame["total_bytes"]
            self.assertGreater(total_bytes, 0)

            # Receive binary frames
            received_bytes = 0
            while received_bytes < total_bytes:
                chunk = websocket.receive_bytes()
                self.assertIsInstance(chunk, bytes)
                received_bytes += len(chunk)

            self.assertEqual(received_bytes, total_bytes)

            # Server should send voice_audio_complete
            complete_frame = websocket.receive_json()
            self.assertEqual(complete_frame["type"], "voice_audio_complete")
            self.assertEqual(complete_frame["message_id"], "test-live-1")

            # Second trigger on same connection must be rejected
            websocket.send_json({
                "type": "trigger_voice_test",
                "message_id": "test-live-2"
            })
            error_frame = websocket.receive_json()
            self.assertEqual(error_frame["type"], "voice_audio_error")
            self.assertIn("SINGLE_USE_EXCEEDED", error_frame["error"])



if __name__ == "__main__":
    unittest.main()
