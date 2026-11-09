"""
ÆONIX PRISM // Gate G4 Chronos Context, Durable Events & Integrity Proofs Test Suite
Exhaustively verifies:
1. Event envelope schema validation (schema_version '1.0.0', classification, required fields).
2. Safety ceiling bounding: strict rejection of oversized payloads (> 32 KiB).
3. Server sequence stamping, monotonic ordering, and anti-replay duplicate prevention.
4. Cryptographic audit chaining and tamper detection in event journal & audit log.
5. SQLite WAL checkpointing (PASSIVE, FULL, TRUNCATE) and database integrity checks.
6. Weather & external cache provenance with honest staleness indicator (Open-Meteo CC BY 4.0).
7. Starlette HTTP endpoints (/events, /chronos/timeline, /gateway/weather, /system/wal-checkpoint) with RBAC.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
else:
    sys.path.remove(_REPO_ROOT)
    sys.path.insert(0, _REPO_ROOT)

# Bootstrap test sandbox environment BEFORE any aeonix imports
_MODULE_SANDBOX = tempfile.mkdtemp(prefix="aeonix_test_g4_bootstrap_")
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
from aeonix.core.auth import issue_device_token, ROLE_POCO_CORE, ROLE_FIRETV_GLASS, ROLE_AGENT_EXECUTOR
from aeonix.core.db import (
    init_database,
    get_connection,
    record_durable_event,
    replay_event_journal,
    checkpoint_wal,
    verify_database_integrity,
    verify_audit_chain,
    log_audit_event,
    SUPPORTED_EVENT_SCHEMA_VERSIONS,
    MAX_EVENT_PAYLOAD_BYTES,
    VALID_EVENT_CLASSIFICATIONS
)
from aeonix.core.atlas import atlas, DEFAULT_WEATHER_TTL_SECONDS, OPEN_METEO_ATTRIBUTION


class TestGate4ChronosAndIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="aeonix_gate4_test_")
        cls.db_path = os.path.join(cls.test_dir, "test_gate4_vault.db")
        os.environ["AEONIX_DB_PATH"] = cls.db_path
        os.environ["AEONIX_TEST_MODE"] = "1"
        init_database(cls.db_path)

        cls.client = TestClient(app)
        cls.poco_token = issue_device_token("test_poco_gate4", ROLE_POCO_CORE)
        cls.tv_token = issue_device_token("test_tv_gate4", ROLE_FIRETV_GLASS)
        cls.agent_token = issue_device_token("test_agent_gate4", ROLE_AGENT_EXECUTOR)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_event_envelope_schema_validation(self):
        """Verifies valid event envelope ingestion and rejection of invalid schema versions."""
        # 1. Valid event envelope
        event_id = f"evt_{int(time.time()*1000)}_001"
        ok, record, msg = record_durable_event(
            event_id=event_id,
            schema_version="1.0.0",
            observed_at=time.time() - 1.0,
            device_id="poco_core_m4",
            source="sensor_battery",
            event_type="thermal_sample",
            subject="battery_temperature",
            payload={"temp_c": 34.2, "status": "nominal"},
            classification="R1",
            evidence_refs=["ref_sensor_01"],
            correlation_id="corr_batch_101",
            db_path=self.db_path
        )
        self.assertTrue(ok, f"Failed to record valid event: {msg}")
        self.assertIsNotNone(record)
        self.assertEqual(record["event_id"], event_id)
        self.assertEqual(record["schema_version"], "1.0.0")
        self.assertEqual(record["classification"], "R1")
        self.assertIn("payload_hash", record)
        self.assertIn("previous_audit_hash", record)
        self.assertGreaterEqual(record["server_sequence"], 1)

        # 2. Reject unsupported schema version
        ok_bad, _, msg_bad = record_durable_event(
            event_id="evt_bad_schema",
            schema_version="2.0.0",
            observed_at=time.time(),
            device_id="tv_glass",
            source="app",
            event_type="click",
            subject="button",
            payload={"key": "home"},
            db_path=self.db_path
        )
        self.assertFalse(ok_bad)
        self.assertIn("UNSUPPORTED_SCHEMA_VERSION", msg_bad)

        # 3. Reject invalid classification
        ok_class, _, msg_class = record_durable_event(
            event_id="evt_bad_class",
            schema_version="1.0.0",
            observed_at=time.time(),
            device_id="tv_glass",
            source="app",
            event_type="click",
            subject="button",
            payload={"key": "home"},
            classification="R99_UNKNOWN",
            db_path=self.db_path
        )
        self.assertFalse(ok_class)
        self.assertIn("INVALID_CLASSIFICATION", msg_class)

    def test_02_oversized_payload_rejection_ceiling(self):
        """Strictly enforces 32 KiB safety ceiling for event payloads."""
        # 1. Payload > 32 KiB
        oversized_data = {"blob": "X" * 35000}
        ok, _, msg = record_durable_event(
            event_id="evt_oversized",
            schema_version="1.0.0",
            observed_at=time.time(),
            device_id="poco_core_m4",
            source="test",
            event_type="dump",
            subject="overflow",
            payload=oversized_data,
            db_path=self.db_path
        )
        self.assertFalse(ok)
        self.assertIn("PAYLOAD_TOO_LARGE", msg)

        # 2. Bounded payload <= 32 KiB
        bounded_data = {"blob": "Y" * 10000}
        ok_bounded, record_bounded, _ = record_durable_event(
            event_id="evt_bounded_ok",
            schema_version="1.0.0",
            observed_at=time.time(),
            device_id="poco_core_m4",
            source="test",
            event_type="dump",
            subject="bounded",
            payload=bounded_data,
            db_path=self.db_path
        )
        self.assertTrue(ok_bounded)
        self.assertIsNotNone(record_bounded)

    def test_03_duplicate_event_prevention_anti_replay(self):
        """Prevents duplicate event ingestion using unique event_id constraint."""
        dup_id = f"evt_dup_{int(time.time()*1000)}"
        ok1, _, _ = record_durable_event(
            event_id=dup_id,
            schema_version="1.0.0",
            observed_at=time.time(),
            device_id="poco_core_m4",
            source="telemetry",
            event_type="ping",
            subject="heartbeat",
            payload={"seq": 1},
            db_path=self.db_path
        )
        self.assertTrue(ok1)

        ok2, _, msg2 = record_durable_event(
            event_id=dup_id,
            schema_version="1.0.0",
            observed_at=time.time(),
            device_id="poco_core_m4",
            source="telemetry",
            event_type="ping",
            subject="heartbeat",
            payload={"seq": 1},
            db_path=self.db_path
        )
        self.assertFalse(ok2)
        self.assertIn("DUPLICATE_EVENT_ID", msg2)

    def test_04_server_sequence_monotonicity_and_replay(self):
        """Verifies deterministic server sequence stamping and event journal replay."""
        base_id = f"evt_mono_{int(time.time())}"
        for i in range(5):
            ok, rec, _ = record_durable_event(
                event_id=f"{base_id}_{i}",
                schema_version="1.0.0",
                observed_at=time.time(),
                device_id="test_device",
                source="test_runner",
                event_type="step",
                subject="sequence_test",
                payload={"step_index": i},
                db_path=self.db_path
            )
            self.assertTrue(ok)

        res = replay_event_journal(start_sequence=1, limit=50, db_path=self.db_path)
        self.assertTrue(res["is_valid"])
        self.assertGreaterEqual(res["count"], 5)
        sequences = [e["server_sequence"] for e in res["events"]]
        self.assertEqual(sequences, sorted(sequences), "Sequences must be strictly ascending")

    def test_05_tamper_detection_in_journal_and_audit_chain(self):
        """Verifies cryptographic tamper detection flags any corrupted payload, sequence, or audit row."""
        # 1. Audit Chain Integrity
        audit_check = verify_audit_chain(self.db_path)
        self.assertTrue(audit_check["is_valid"])
        self.assertEqual(audit_check["status"], "CRYPTOGRAPHICALLY_VERIFIED")

        # 2. Tamper with an audit row
        conn = get_connection(self.db_path, allow_maintenance=True)
        cur = conn.cursor()
        cur.execute("SELECT id, actor FROM audit_log ORDER BY id DESC LIMIT 1;")
        row = cur.fetchone()
        row_id = row["id"]
        original_actor = row["actor"]

        # Mutate the actor directly in SQLite
        cur.execute("UPDATE audit_log SET actor = 'MALICIOUS_IMPOSTOR' WHERE id = ?;", (row_id,))
        conn.commit()
        conn.close()

        tampered_audit = verify_audit_chain(self.db_path)
        self.assertFalse(tampered_audit["is_valid"], "Tamper detection must flag modified audit record")
        self.assertIn("Content tampering detected", tampered_audit.get("error", ""))

        # Restore original actor
        conn = get_connection(self.db_path, allow_maintenance=True)
        cur = conn.cursor()
        cur.execute("UPDATE audit_log SET actor = ? WHERE id = ?;", (original_actor, row_id))
        conn.commit()
        conn.close()

        restored_audit = verify_audit_chain(self.db_path)
        self.assertTrue(restored_audit["is_valid"])

        # 3. Tamper with an event payload
        conn = get_connection(self.db_path, allow_maintenance=True)
        cur = conn.cursor()
        cur.execute("SELECT event_id, payload_json FROM events ORDER BY server_sequence DESC LIMIT 1;")
        evt_row = cur.fetchone()
        evt_id = evt_row["event_id"]
        original_payload = evt_row["payload_json"]

        cur.execute("UPDATE events SET payload_json = '{\"tampered\": true}' WHERE event_id = ?;", (evt_id,))
        conn.commit()
        conn.close()

        replay_check = replay_event_journal(start_sequence=1, limit=100, db_path=self.db_path)
        self.assertFalse(replay_check["is_valid"], "Replay must flag tampered event payload")
        self.assertIn("Payload corruption detected", replay_check.get("error", ""))

        # Restore event payload
        conn = get_connection(self.db_path, allow_maintenance=True)
        cur = conn.cursor()
        cur.execute("UPDATE events SET payload_json = ? WHERE event_id = ?;", (original_payload, evt_id))
        conn.commit()
        conn.close()

        restored_replay = replay_event_journal(start_sequence=1, limit=100, db_path=self.db_path)
        self.assertTrue(restored_replay["is_valid"])

    def test_06_wal_checkpoint_and_integrity_check(self):
        """Verifies SQLite WAL checkpointing and quick/full integrity check routines."""
        # 1. WAL Checkpointing modes
        for mode in ["PASSIVE", "FULL", "TRUNCATE"]:
            cp = checkpoint_wal(mode=mode, db_path=self.db_path)
            self.assertEqual(cp["status"], "CHECKPOINT_SUCCESS")
            self.assertEqual(cp["mode"], mode)
            self.assertIn("checkpointed_frames", cp)

        # 2. Invalid checkpoint mode
        with self.assertRaises(ValueError):
            checkpoint_wal(mode="UNSUPPORTED_MODE", db_path=self.db_path)

        # 3. Quick and Full integrity checks
        quick = verify_database_integrity(db_path=self.db_path, full=False)
        self.assertTrue(quick["is_valid"])
        self.assertEqual(quick["result"], "ok")

        full = verify_database_integrity(db_path=self.db_path, full=True)
        self.assertTrue(full["is_valid"])
        self.assertEqual(full["result"], "ok")

    def test_07_weather_provenance_and_honest_staleness(self):
        """Verifies Open-Meteo cache provenance, attribution, and honest staleness calculation."""
        # 1. Retrieve weather telemetry
        weather = atlas.get_weather_with_provenance(db_path=self.db_path)
        self.assertIn(weather["provider"], ["Open-Meteo", "Offline Fallback Cache"])
        self.assertEqual(weather["license_attribution"], OPEN_METEO_ATTRIBUTION)
        self.assertIn("provenance_digest", weather)
        self.assertIn("is_stale", weather)
        self.assertIn("staleness_seconds", weather)
        self.assertIn("source", weather)

        # 2. Simulated stale cache calculation
        stale_cached = dict(weather)
        stale_cached["expires_at"] = time.time() - 3600.0  # 1 hour in the past
        atlas._memory_cache = stale_cached

        stale_result = atlas.get_weather_with_provenance(force_refresh=False, db_path=self.db_path)
        self.assertTrue(stale_result["is_stale"])
        self.assertGreater(stale_result["staleness_seconds"], 3500.0)
        self.assertEqual(stale_result["status"], "STALE")
        self.assertEqual(stale_result["source"], "cache")

        # Clear memory cache after test
        atlas._memory_cache = None

    def test_08_http_api_endpoints_and_rbac(self):
        """Verifies Starlette HTTP endpoints for weather, chronos timeline, events, and WAL checkpoint."""
        headers_poco = {"Authorization": f"Bearer {self.poco_token}"}
        headers_tv = {"Authorization": f"Bearer {self.tv_token}"}
        headers_agent = {"Authorization": f"Bearer {self.agent_token}"}

        # 1. GET /gateway/weather (allowed for POCO and Fire TV)
        r_tv = self.client.get("/gateway/weather", headers=headers_tv)
        self.assertEqual(r_tv.status_code, 200)
        self.assertTrue(r_tv.json()["success"])
        self.assertIn("weather", r_tv.json())

        # 2. GET /chronos/timeline (allowed for POCO and Fire TV)
        r_chrono = self.client.get("/chronos/timeline?start_sequence=1&limit=10", headers=headers_tv)
        self.assertEqual(r_chrono.status_code, 200)
        self.assertTrue(r_chrono.json()["is_valid"])

        # 3. POST /events via Agent Executor
        evt_payload = {
            "event_id": f"evt_http_{int(time.time()*1000)}",
            "schema_version": "1.0.0",
            "device_id": "agent_worker_01",
            "source": "worker",
            "event_type": "task_progress",
            "subject": "task_42",
            "payload": {"progress_pct": 75},
            "classification": "R1"
        }
        r_evt = self.client.post("/events", json=evt_payload, headers=headers_agent)
        self.assertEqual(r_evt.status_code, 200)
        self.assertTrue(r_evt.json()["success"])
        self.assertEqual(r_evt.json()["event"]["event_id"], evt_payload["event_id"])

        # 4. POST /events duplicate rejection (409)
        r_dup = self.client.post("/events", json=evt_payload, headers=headers_agent)
        self.assertEqual(r_dup.status_code, 409)

        # 5. POST /system/wal-checkpoint (POCO Core only)
        # POCO Core -> 200 OK
        r_cp_poco = self.client.post("/system/wal-checkpoint", json={"mode": "PASSIVE"}, headers=headers_poco)
        self.assertEqual(r_cp_poco.status_code, 200)
        self.assertEqual(r_cp_poco.json()["status"], "CHECKPOINT_SUCCESS")

        # Fire TV Glass -> 403 Forbidden (RBAC segregation)
        r_cp_tv = self.client.post("/system/wal-checkpoint", json={"mode": "PASSIVE"}, headers=headers_tv)
        self.assertEqual(r_cp_tv.status_code, 403)


if __name__ == "__main__":
    unittest.main()
