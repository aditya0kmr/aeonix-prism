"""
Targeted Verification Suite: Port Configuration, Fail-Closed TLS, and Warden Observe-Only Safety
Project: ÆONIX PRISM
Verifies:
1. AEONIX_PORT validation, range checking, and mDNS propagation.
2. Fail-closed TLS credential verification.
3. Atlas Sovereign Warden observe-only invariants (zero os.kill, zero mission aborts).
4. Exclusion of unrelated same-user processes from expendable target selection.
5. RBAC boundaries (FIRETV_GLASS cannot approve protected Sentinel actions).
"""

import os
import sys
import ssl
import time
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, "/data/data/com.termux/files/home/aeonix-prism")

from aeonix.core.server import get_configured_port
from aeonix.core.discovery import AeonixDiscoveryService
from aeonix.core.atlas_sovereign import AtlasSovereignEngine
from aeonix.core.auth import ROLE_POCO_CORE, ROLE_FIRETV_GLASS
from aeonix.core.db import resolve_sentinel_request, init_database, queue_sentinel_request
from aeonix.core.fast_path import match_fast_path, execute_fast_path

class TestTransportAndWardenSafety(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = os.path.join(self.temp_dir.name, "test_safety.db")
        init_database(self.test_db)

    def tearDown(self):
        self.temp_dir.cleanup()

    # 1. Port Validation & Propagation
    def test_port_validation_default(self):
        with patch.dict(os.environ, {}, clear=False):
            if "AEONIX_PORT" in os.environ:
                del os.environ["AEONIX_PORT"]
            self.assertEqual(get_configured_port(), 8080)

    def test_port_validation_custom_valid(self):
        with patch.dict(os.environ, {"AEONIX_PORT": "8443"}):
            self.assertEqual(get_configured_port(), 8443)

    def test_port_validation_out_of_range(self):
        for invalid_port in ["0", "-1", "65536", "99999", "abc", ""]:
            with patch.dict(os.environ, {"AEONIX_PORT": invalid_port}):
                with self.assertRaises(ValueError):
                    get_configured_port()

    def test_discovery_advertised_port(self):
        svc = AeonixDiscoveryService(port=8443)
        self.assertEqual(svc.port, 8443)

    def test_live_link_check_fast_path(self):
        match = match_fast_path("live link check")
        self.assertIsNotNone(match)
        action, conf = match
        self.assertEqual(action, "live_link_check")
        self.assertEqual(conf, 1.0)

        res = execute_fast_path(action, actor="Aadi")
        self.assertEqual(res["speech"], "POCO core connected. Transport verification in progress.")
        card = res["layout_intent"]["cards"][0]
        self.assertEqual(card["title"], "ÆONIX PRISM — Live Link Check")
        self.assertEqual(card["content"], "POCO core connected. Transport verification in progress.")

    # 2. TLS Fail-Closed Verification
    def test_tls_pair_validation_success(self):
        cert_path = "/data/data/com.termux/files/home/.aeonix/secrets/aeonix_cert.pem"
        key_path = "/data/data/com.termux/files/home/.aeonix/secrets/aeonix_key.pem"
        self.assertTrue(os.path.exists(cert_path), "Cert file must exist")
        self.assertTrue(os.path.exists(key_path), "Key file must exist")

        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        # Must load cleanly without raising exceptions
        ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)

    def test_tls_missing_credentials_fails_closed(self):
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        with self.assertRaises((FileNotFoundError, ssl.SSLError)):
            ctx.load_cert_chain(
                certfile="/nonexistent/cert.pem",
                keyfile="/nonexistent/key.pem"
            )

    # 3. Warden Observe-Only Invariants
    def test_warden_observe_only_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            if "ATLAS_OBSERVE_ONLY" in os.environ:
                del os.environ["ATLAS_OBSERVE_ONLY"]
            engine = AtlasSovereignEngine(db_path=self.test_db, enable_bg_threads=False)
            self.assertTrue(engine.observe_only)

    def test_warden_observe_only_no_signals_or_kill(self):
        engine = AtlasSovereignEngine(db_path=self.test_db, enable_bg_threads=False, observe_only=True)
        
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_proc.name.return_value = "unrelated_worker"

        with patch("os.kill") as mock_kill:
            report = engine.kill_and_report(mock_proc, "TEST_BREACH", "95%")
            mock_kill.assert_not_called()
            self.assertEqual(report["action_taken"], "OBSERVE_ONLY_NO_ACTION")
            self.assertEqual(report["event"], "HARD_LIMIT_BREACH_OBSERVED")

    def test_warden_observe_only_does_not_abort_missions(self):
        engine = AtlasSovereignEngine(db_path=self.test_db, enable_bg_threads=False, observe_only=True)
        
        # Insert a stuck mission
        conn = sqlite3.connect(self.test_db)
        now = time.time()
        conn.execute("""
            INSERT INTO missions (id, objective, target, status, current_phase, total_phases, plan_json, execution_log_json, report_json, created_at, updated_at)
            VALUES ('stuck_m1', 'Test', 'target', 'running', 1, 1, '{}', '[]', '{}', ?, ?);
        """, (now - 60.0, now - 60.0))
        conn.commit()
        conn.close()

        # Run surveillance pass in observe-only mode
        engine.run_surveillance_pass()

        # Verify mission is STILL 'running', NOT 'aborted'
        conn = sqlite3.connect(self.test_db)
        cur = conn.cursor()
        cur.execute("SELECT status FROM missions WHERE id = 'stuck_m1'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "running")

    # 4. Unrelated Process Exclusion
    def test_unrelated_process_never_eligible(self):
        engine = AtlasSovereignEngine(db_path=self.test_db, enable_bg_threads=False, observe_only=True)

        class FakeProc:
            def __init__(self, pid, name, cmdline, mem):
                self.pid = pid
                self.info = {'pid': pid, 'name': name, 'cmdline': cmdline, 'memory_percent': mem}

        # Mock process pool containing an unrelated server (e.g. lumina_hub) with high RAM
        fake_lumina = FakeProc(9604, "python3", ["python3", "/data/data/com.termux/files/home/lumina_hub/server.py"], 25.0)
        fake_shell = FakeProc(9999, "bash", ["bash"], 5.0)

        target = engine.find_expendable_target("RAM_LIMIT_EXCEEDED", proc_pool=[fake_lumina, fake_shell])
        # Under no circumstance should an unrelated process be selected
        self.assertIsNone(target, "Unrelated processes must never be selected as expendable targets")

    # 5. RBAC & Sentinel Boundary
    def test_firetv_role_cannot_approve_sentinel(self):
        req_id = queue_sentinel_request(
            agent="Tester",
            action_class="system",
            action_type="wipe",
            target="storage",
            scope={"path": "/storage"},
            risk_level="CRITICAL",
            ttl_seconds=300,
            db_path=self.test_db
        )

        # Attempt approval with ROLE_FIRETV_GLASS
        ok, reason = resolve_sentinel_request(
            req_id,
            approved=True,
            resolver="firetv_glass",
            resolver_role=ROLE_FIRETV_GLASS,
            db_path=self.test_db
        )
        self.assertFalse(ok)
        self.assertIn("POCO_AUTHORITY_REQUIRED", reason)

        # Verify still pending in database
        conn = sqlite3.connect(self.test_db)
        cur = conn.cursor()
        cur.execute("SELECT status, approved_by FROM sentinel_requests WHERE id = ?", (req_id,))
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "pending")
        self.assertIsNone(row[1])

if __name__ == "__main__":
    unittest.main()
