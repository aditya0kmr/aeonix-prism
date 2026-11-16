"""
ÆONIX PRISM // AADYA Stage 13 Test Suite
Operator Console Integration & Controlled Local Activation Readiness Verification
Verifies:
1. Stage 13 Console Integration Engine initialization, degraded state handling, and availability guards.
2. Operator console route RBAC and security enforcement for /operator and /console.
3. Review queue aggregation contract (sentinel requests, aadya escalations, poco reconciliations).
4. Action Digest contract and tamper rejection verification.
5. Emergency sanctuary and kill-switch readiness with truthful capability reporting.
6. Controlled local activation readiness nominal evaluation.
7. Controlled local activation readiness fails closed on bad bind / non-loopback host.
8. Controlled local activation readiness fails closed on corrupted audit chain.
9. Local endpoint health validation.
10. Safe local API smoke nominal evaluation and permanent financial quarantine refusal.
11. Voice ownership and single-response concurrency lock exclusivity.
12. TV-safe surface readiness and strict privacy quarantine.
13. POCO physical escalation readiness and lifecycle.
14. RAM guard threshold evaluation and truthful status reporting.
15. In-memory operator activation report generation (AADYA_STAGE13_V1), persistence gate, and rollback dry-run.
"""

import os
import sys
import unittest
import tempfile
import sqlite3
import json
import hashlib
from typing import Dict, Any

from core.db import init_database, log_audit_event, execute_db
from core.aadya import AadyaCrownZero
from core.aadya_console_integration import AadyaConsoleIntegrationEngine


class TestAadyaStage13(unittest.TestCase):
    """Exhaustive tests for AADYA Stage 13: Operator Console Integration & Local Activation Readiness."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="aeonix_stage13_test_")
        self.db_path = os.path.join(self.temp_dir, "test_vault_stage13.db")
        self.secrets_dir = os.path.join(self.temp_dir, "secrets")
        os.makedirs(self.secrets_dir, mode=0o700, exist_ok=True)

        os.environ["AEONIX_VAULT_DB"] = self.db_path
        os.environ["AEONIX_SECRETS_DIR"] = self.secrets_dir
        os.environ["AEONIX_TEST_MODE"] = "1"
        os.environ["AEONIX_ALLOW_HTTP"] = "1"

        init_database(self.db_path)
        self.aadya = AadyaCrownZero(db_path=self.db_path)
        self.engine = AadyaConsoleIntegrationEngine(db_path=self.db_path, parent_crown_zero=self.aadya)

    def tearDown(self):
        try:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_stage13_console_integration_engine_initialization_and_status(self):
        """Verifies AadyaConsoleIntegrationEngine initializes properly and handles degraded database failure."""
        self.assertIsNotNone(self.aadya.console_integration)
        self.assertEqual(self.aadya.console_integration_status, "INITIALIZED")
        self.assertIsNone(self.aadya.console_integration_error)

        # Degraded initialization test with invalid DB path
        degraded = AadyaCrownZero(db_path="/proc/illegal_path")
        self.assertEqual(degraded.console_integration_status, "INITIALIZATION_FAILED")
        with self.assertRaises(RuntimeError):
            degraded.validate_operator_console_integration()

    def test_operator_console_route_rbac_and_security(self):
        """Validates actual existing RBAC behavior on /operator and /console routes."""
        res = self.engine.validate_operator_console_integration(secrets_dir=self.secrets_dir, db_path=self.db_path)
        self.assertIn("route_results", res)
        routes = res["route_results"]

        for route_path in ("/operator", "/console"):
            self.assertIn(route_path, routes)
            r_info = routes[route_path]
            # Verify actual observed statuses
            self.assertIn(r_info["unauthenticated_status"], (401, 403))
            self.assertEqual(r_info["poco_status"], 200)
            self.assertIn(r_info["firetv_status"], (401, 403))
            self.assertTrue(r_info["is_protected"])
            self.assertTrue(r_info["allows_poco"])

        self.assertIn(res["console_integration_status"], ("INTEGRATED", "DEGRADED"))
        self.assertEqual(
            res["autonomous_execution_bypass_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )

    def test_review_queue_aggregation_contract(self):
        """Validates review queue aggregation from sentinel requests and escalations."""
        # Insert test sentinel request
        execute_db("""
            INSERT INTO sentinel_requests (
                id, agent, action_type, target, scope_json, risk_level, action_class, status, created_at, expires_at
            ) VALUES (
                'sent_test_1', 'AZ-001', 'WRITE_CONFIG', 'sys.cfg', '{}', 'HIGH', 'SYSTEM', 'pending', 1000.0, 9999999999.0
            );
        """, db_path=self.db_path)

        res = self.engine._aggregate_review_queue(db_path=self.db_path)
        self.assertGreaterEqual(res["sentinel_pending_count"], 1)
        self.assertGreaterEqual(res["total_pending_count"], 1)

    def test_action_digest_contract_and_tamper_rejection(self):
        """Validates deterministic Action Digest calculation and tamper rejection."""
        res = self.engine.validate_review_queue_and_action_digest_contract(
            db_path=self.db_path, secrets_dir=self.secrets_dir
        )
        self.assertEqual(res["status"], "VALIDATED")
        self.assertTrue(res["contract_valid"])
        self.assertTrue(res["binding_enforced"])
        self.assertTrue(res["tamper_rejection_verified"])
        self.assertEqual(
            res["autonomous_execution_bypass_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )

    def test_emergency_controls_readiness_and_truthful_reporting(self):
        """Validates verified control paths for sanctuary_mode and kill_switch."""
        res = self.engine.validate_emergency_controls_readiness()
        self.assertIn(res["status"], ("VALIDATED", "DEGRADED"))
        self.assertIn("sanctuary_mode", res)
        self.assertIn("kill_switch", res)
        self.assertEqual(
            res["autonomous_execution_bypass_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )

    def test_controlled_local_activation_readiness_nominal(self):
        """Validates controlled local activation readiness succeeds nominally under loopback."""
        res = self.engine.validate_controlled_local_activation_readiness(
            host="127.0.0.1", port=8000, db_path=self.db_path, secrets_dir=self.secrets_dir
        )
        self.assertEqual(res["readiness_verdict"], "ACTIVATION_READY")
        self.assertTrue(res["can_proceed_to_activation"])
        self.assertEqual(
            res["autonomous_execution_bypass_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )
        self.assertEqual(len(res["digest"]), 64)

    def test_controlled_local_activation_readiness_fails_closed_on_bad_bind(self):
        """Validates activation readiness fails closed on non-loopback host or invalid port."""
        res_bad_host = self.engine.validate_controlled_local_activation_readiness(
            host="192.168.1.100", port=8000, db_path=self.db_path, secrets_dir=self.secrets_dir
        )
        self.assertEqual(res_bad_host["readiness_verdict"], "ACTIVATION_HALTED")
        self.assertFalse(res_bad_host["can_proceed_to_activation"])

        res_bad_port = self.engine.validate_controlled_local_activation_readiness(
            host="127.0.0.1", port=99999, db_path=self.db_path, secrets_dir=self.secrets_dir
        )
        self.assertEqual(res_bad_port["readiness_verdict"], "ACTIVATION_HALTED")
        self.assertFalse(res_bad_port["can_proceed_to_activation"])

    def test_controlled_local_activation_readiness_fails_closed_on_corrupt_audit(self):
        """Validates activation readiness fails closed if audit chain integrity is broken."""
        # Corrupt audit chain by tampering with hashes in SQLite
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("UPDATE audit_log SET current_hash = 'corrupt_hash_val' WHERE id = (SELECT MAX(id) FROM audit_log);")
        conn.commit()
        conn.close()

        res = self.engine.validate_controlled_local_activation_readiness(
            host="127.0.0.1", port=8000, db_path=self.db_path, secrets_dir=self.secrets_dir
        )
        self.assertEqual(res["readiness_verdict"], "ACTIVATION_HALTED")
        self.assertFalse(res["can_proceed_to_activation"])

    def test_local_endpoint_health_validation(self):
        """Validates local endpoint health using existing server behavior."""
        res = self.engine.validate_local_endpoint_health()
        self.assertEqual(res["status"], "VALIDATED")
        self.assertIn("/api/status", res["endpoint_results"])
        self.assertTrue(res["endpoint_results"]["/api/status"]["healthy"])

    def test_safe_local_api_smoke_nominal_and_financial_quarantine(self):
        """Validates safe local API smoke pipeline and permanent financial quarantine refusal."""
        # Nominal intent
        res_nom = self.engine.validate_safe_local_api_smoke(transcript="System status diagnostic query")
        self.assertEqual(res_nom["status"], "VALIDATED")
        self.assertTrue(res_nom["success"])

        # Financial intents blocked
        for financial_prompt in ("transfer funds to external wallet", "purchase bitcoin shares"):
            res_fin = self.engine.validate_safe_local_api_smoke(transcript=financial_prompt)
            self.assertEqual(res_fin["status"], "FINANCIAL_BLOCKED")
            self.assertFalse(res_fin["success"])
            self.assertEqual(res_fin["action_type"], "FINANCIAL_EXECUTION_REFUSED")

    def test_voice_ownership_and_single_response_concurrency(self):
        """Validates single-response voice concurrency lock exclusivity."""
        res = self.engine.validate_voice_ownership_and_concurrency()
        self.assertEqual(res["status"], "VALIDATED")
        self.assertTrue(res["lock_enforced"])
        self.assertTrue(res["busy_state_handled"])

    def test_tv_safe_surface_readiness_and_privacy_quarantine(self):
        """Validates TV surface payload sanitization and strict suppression of operator-only data."""
        res = self.engine.validate_tv_safe_surface_readiness()
        self.assertEqual(res["status"], "VALIDATED")
        self.assertFalse(res.get("leaks_detected", True))

    def test_poco_escalation_readiness_and_lifecycle(self):
        """Validates POCO physical escalation queue and reports autonomous execution bypass status."""
        res = self.engine.validate_poco_escalation_readiness(db_path=self.db_path)
        self.assertIn(res["status"], ("VALIDATED", "DEGRADED"))
        self.assertEqual(
            res["autonomous_execution_bypass_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )

    def test_ram_guard_integration_and_threshold_reporting(self):
        """Validates RAM guard threshold evaluation and truthful status reporting."""
        res = self.engine.verify_audit_and_hardware_guards(db_path=self.db_path)
        self.assertIn(res["ram_status"], ("NOMINAL", "PRESSURE", "DEGRADED"))
        self.assertIsInstance(res["ram_safe"], bool)

    def test_operator_activation_report_in_memory_and_persistence_gate(self):
        """Validates in-memory report generation, persistence gate, and rollback dry-run."""
        # 1. In-memory generation
        report = self.aadya.generate_operator_activation_report(
            stage=13, host="127.0.0.1", port=8000, db_path=self.db_path, secrets_dir=self.secrets_dir
        )
        self.assertEqual(report["report_version"], "AADYA_STAGE13_V1")
        self.assertEqual(report["stage"], 13)
        self.assertIn("report_digest", report)
        self.assertEqual(len(report["report_digest"]), 64)
        self.assertFalse(report["persisted"])

        # 2. Persistence Gate without approval raises PermissionError
        with self.assertRaises(PermissionError):
            self.aadya.persist_operator_activation_report(report, operator_approved=False)

        # 3. Persistence Gate with approval succeeds
        save_res = self.aadya.persist_operator_activation_report(report, operator_approved=True)
        self.assertEqual(save_res["status"], "PERSISTED")
        self.assertEqual(save_res["report_digest"], report["report_digest"])

        # 4. Rollback Dry-Run validation
        rollback = self.aadya.execute_console_integration_rollback_dry_run()
        self.assertEqual(rollback["status"], "DRY_RUN_ROLLBACK_VERIFIED")
        self.assertEqual(rollback["base_checkpoint_commit"], "8f70b718468fec362cbee32ce92ae5afdf349abd")
        self.assertFalse(rollback["execution_performed"])
        self.assertEqual(len(rollback["files_mutated"]), 0)


if __name__ == "__main__":
    unittest.main()
