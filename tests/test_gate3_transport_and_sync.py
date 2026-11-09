"""
Gate G3 // Core Transport, Pinned Certificate Handshake & State Resync Verification.
Tests:
1. Dynamic X.509 TLS certificate generation with SAN coverage (loopback + subnet).
2. WebSocket handshake authentication & rejection of query parameter tokens.
3. Monotonic server sequence stamping on broadcast events.
4. Sequence-based state resynchronization on reconnect (replaying missed events).
5. 32 KiB safety ceiling bounding on control frames.
6. TV role approval restriction over WebSocket.
"""

import os
import sys
import json
import time
import tempfile
import asyncio
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TESTS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
else:
    sys.path.remove(_REPO_ROOT)
    sys.path.insert(0, _REPO_ROOT)

from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from aeonix.core.server import app, broadcast_message, _SERVER_SEQUENCE
from aeonix.core.auth import (
    issue_device_token,
    ROLE_POCO_CORE,
    ROLE_FIRETV_GLASS
)
from aeonix.core.tls_cert import ensure_sovereign_tls_credentials, get_active_ip
from cryptography import x509


class TestGate3TransportAndSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from aeonix.core.db import init_database
        cls.test_dir = tempfile.mkdtemp(prefix="aeonix_test_g3_")
        cls.db_path = os.path.join(cls.test_dir, "test_vault.db")
        cls.orig_db = os.environ.get("AEONIX_DB_PATH")
        os.environ["AEONIX_DB_PATH"] = cls.db_path
        init_database(cls.db_path)
        cls.client = TestClient(app)
        cls.poco_token = issue_device_token("poco_test_gate3", role=ROLE_POCO_CORE)
        cls.firetv_token = issue_device_token("firetv_sheldon_gate3", role=ROLE_FIRETV_GLASS)

    @classmethod
    def tearDownClass(cls):
        import shutil
        if cls.orig_db is not None:
            os.environ["AEONIX_DB_PATH"] = cls.orig_db
        else:
            os.environ.pop("AEONIX_DB_PATH", None)
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_dynamic_tls_certificate_and_san_coverage(self):
        """Verify sovereign X.509 certificate generation, fingerprint, and SAN IP coverage."""
        with tempfile.TemporaryDirectory(prefix="aeonix_tls_test_") as tmp_sec:
            cert_path, key_path, fp = ensure_sovereign_tls_credentials(secrets_dir=tmp_sec)
            self.assertTrue(os.path.exists(cert_path))
            self.assertTrue(os.path.exists(key_path))
            self.assertEqual(len(fp), 64, "SHA-256 fingerprint must be 64 hex characters")

            # Read back cert and verify SAN extension
            with open(cert_path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())
            
            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            san_ips = [str(item.value) for item in san_ext.value if isinstance(item, x509.IPAddress)]
            self.assertIn("127.0.0.1", san_ips)
            self.assertIn(get_active_ip(), san_ips)

    def test_02_websocket_rejects_query_token_and_missing_auth(self):
        """Verify WebSocket rejects token in query param and missing header with 4401."""
        # Query param token rejection
        with self.assertRaises(WebSocketDisconnect) as cm:
            with self.client.websocket_connect(f"/ws?token={self.firetv_token}") as ws:
                pass
        self.assertEqual(cm.exception.code, 4401)

        # Missing header rejection
        with self.assertRaises(WebSocketDisconnect) as cm:
            with self.client.websocket_connect("/ws") as ws:
                pass
        self.assertEqual(cm.exception.code, 4401)

    def test_03_websocket_handshake_and_ping_pong_sequence(self):
        """Verify successful connection receives layout and pong carries server_sequence."""
        headers = {"Authorization": f"Bearer {self.firetv_token}"}
        with self.client.websocket_connect("/ws", headers=headers) as ws:
            # 1. Initial layout update frame
            initial_msg = ws.receive_json()
            self.assertEqual(initial_msg.get("type"), "layout_update")
            self.assertIn("living_surface", initial_msg.get("screen", ""))

            # 2. Ping-pong
            ws.send_json({"type": "ping"})
            pong_msg = ws.receive_json()
            self.assertEqual(pong_msg.get("type"), "pong")
            self.assertIn("server_sequence", pong_msg)
            self.assertIsInstance(pong_msg["server_sequence"], int)

    def test_04_sequence_based_resync_replays_missed_events(self):
        """Verify disconnect-reconnect resync requests and replays missed broadcast events."""
        headers = {"Authorization": f"Bearer {self.firetv_token}"}
        
        # 1. First connection records sequence cursor
        with self.client.websocket_connect("/ws", headers=headers) as ws:
            ws.receive_json()
            ws.send_json({"type": "ping"})
            baseline_seq = ws.receive_json()["server_sequence"]

        # 2. While client is disconnected, server emits an event
        event_payload = {
            "type": "layout_update",
            "screen": "app_matrix",
            "notice": "Resync Missed Event"
        }
        asyncio.run(broadcast_message(event_payload))

        # 3. Client reconnects and requests resync of missed events
        with self.client.websocket_connect("/ws", headers=headers) as ws:
            ws.receive_json() # Drain initial layout

            ws.send_json({
                "type": "sync_request",
                "last_sequence": baseline_seq
            })
            resync_resp = ws.receive_json()
            self.assertEqual(resync_resp.get("type"), "sync_response")
            self.assertGreater(resync_resp.get("server_sequence"), baseline_seq)
            
            replayed = resync_resp.get("replayed_events", [])
            self.assertGreaterEqual(len(replayed), 1)
            matched = any(e.get("notice") == "Resync Missed Event" for e in replayed)
            self.assertTrue(matched, "Missed event must be replayed upon sync_request")

    def test_05_oversized_control_frame_rejected(self):
        """Verify frame exceeding 32 KiB returns FRAME_TOO_LARGE safety error."""
        headers = {"Authorization": f"Bearer {self.firetv_token}"}
        with self.client.websocket_connect("/ws", headers=headers) as ws:
            ws.receive_json() # Drain initial layout

            # Send 40 KiB payload
            oversized_data = "X" * (40 * 1024)
            ws.send_text(json.dumps({"type": "state_dump", "blob": oversized_data}))

            err_resp = ws.receive_json()
            self.assertEqual(err_resp.get("type"), "error")
            self.assertEqual(err_resp.get("code"), "FRAME_TOO_LARGE")

    def test_06_firetv_cannot_approve_sentinel_actions_over_ws(self):
        """Verify TV remote role attempting approval over WebSocket is rejected."""
        headers = {"Authorization": f"Bearer {self.firetv_token}"}
        with self.client.websocket_connect("/ws", headers=headers) as ws:
            ws.receive_json()

            ws.send_json({
                "type": "sentinel_action",
                "request_id": "req_fake_test_123",
                "approved": True
            })
            resp = ws.receive_json()
            self.assertEqual(resp.get("type"), "sentinel_rejected")
            self.assertIn("POCO_AUTHORITY_REQUIRED", resp.get("error", ""))


if __name__ == "__main__":
    unittest.main()
