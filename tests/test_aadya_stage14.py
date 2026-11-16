"""
ÆONIX PRISM // AADYA Stage 14 Test Suite
Controlled Local Activation Readiness Certification & Operator Go/No-Go Verification
Verifies:
1. Stage 14 Certification Engine initialization, degraded state handling, and availability guards.
2. Consolidated activation readiness certification nominal evaluation.
3. Certification fails closed on bad bind / non-loopback host or invalid port.
4. Certification fails closed on corrupted audit chain.
5. Operator Go/No-Go nominal GO decision evaluation.
6. Operator Go/No-Go critical failure NO_GO decision evaluation.
7. Operator Go/No-Go conditional review decision on non-critical degradation / RAM pressure.
8. Emergency sanctuary and kill-switch readiness with truthful capability reporting.
9. Final local endpoint health validation.
10. Safe local API smoke nominal evaluation and permanent financial quarantine refusal.
11. Voice ownership and single-response concurrency lock exclusivity.
12. TV-safe surface readiness and strict privacy quarantine.
13. POCO physical escalation readiness and lifecycle.
14. RAM guard threshold evaluation and truthful status reporting.
15. In-memory operator certification report generation (AADYA_STAGE14_V1), persistence gate, and rollback dry-run.
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
from core.aadya_certification import AadyaCertificationEngine


class TestAadyaStage14(unittest.TestCase):
    """Exhaustive tests for AADYA Stage 14: Activation Readiness Certification & Operator Go/No-Go."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="aeonix_stage14_test_")
        self.db_path = os.path.join(self.temp_dir, "test_vault_stage14.db")
        self.secrets_dir = os.path.join(self.temp_dir, "secrets")
        os.makedirs(self.secrets_dir, mode=0o700, exist_ok=True)

        os.environ["AEONIX_VAULT_DB"] = self.db_path
        os.environ["AEONIX_SECRETS_DIR"] = self.secrets_dir
        os.environ["AEONIX_TEST_MODE"] = "1"
        os.environ["AEONIX_ALLOW_HTTP"] = "1"

        init_database(self.db_path)
        self.aadya = AadyaCrownZero(db_path=self.db_path)
        self.engine = AadyaCertificationEngine(db_path=self.db_path, parent_crown_zero=self.aadya)

    def tearDown(self):
        try:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_stage14_certification_engine_initialization_and_status(self):
        """Verifies AadyaCertificationEngine initializes properly and handles degraded database failure."""
        self.assertIsNotNone(self.aadya.certification)
        self.assertEqual(self.aadya.certification_initialization_status, "INITIALIZED")
        self.assertIsNone(self.aadya.certification_initialization_error)

        # Degraded initialization test with invalid DB path
        degraded = AadyaCrownZero(db_path="/proc/illegal_path")
        self.assertEqual(degraded.certification_initialization_status, "INITIALIZATION_FAILED")
        with self.assertRaises(RuntimeError):
            degraded.certify_local_activation_readiness()

    def test_consolidated_activation_readiness_certification_nominal(self):
        """Validates that consolidated activation readiness certification succeeds nominally under loopback."""
        res = self.engine.certify_local_activation_readiness(
            host="127.0.0.1", port=8000, db_path=self.db_path, secrets_dir=self.secrets_dir
        )
        self.assertEqual(res["certification_status"], "CERTIFIED")
        self.assertTrue(res["is_certified"])
        self.assertEqual(
            res["autonomous_execution_bypass_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )
        self.assertEqual(res["financial_quarantine_status"], "PERMANENTLY_QUARANTINED")
        self.assertEqual(len(res["certification_digest"]), 64)

    def test_certification_fails_closed_on_bad_bind(self):
        """Validates certification fails closed on non-loopback host or invalid port."""
        res_bad_host = self.engine.certify_local_activation_readiness(
            host="192.168.1.100", port=8000, db_path=self.db_path, secrets_dir=self.secrets_dir
        )
        self.assertEqual(res_bad_host["certification_status"], "CERTIFICATION_FAILED")
        self.assertFalse(res_bad_host["is_certified"])

        res_bad_port = self.engine.certify_local_activation_readiness(
            host="127.0.0.1", port=99999, db_path=self.db_path, secrets_dir=self.secrets_dir
        )
        self.assertEqual(res_bad_port["certification_status"], "CERTIFICATION_FAILED")
        self.assertFalse(res_bad_port["is_certified"])

    def test_certification_fails_closed_on_corrupt_audit(self):
        """Validates certification fails closed if audit chain integrity is broken."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("UPDATE audit_log SET current_hash = 'corrupted_hash' WHERE id = (SELECT MAX(id) FROM audit_log);")
        conn.commit()
        conn.close()

        res = self.engine.certify_local_activation_readiness(
            host="127.0.0.1", port=8000, db_path=self.db_path, secrets_dir=self.secrets_dir
        )
        self.assertEqual(res["certification_status"], "CERTIFICATION_FAILED")
        self.assertFalse(res["is_certified"])

    def test_operator_go_no_go_nominal_go(self):
        """Validates formal Operator Go/No-Go decision produces GO_FOR_LOCAL_ACTIVATION when nominal."""
        res = self.engine.evaluate_operator_go_no_go_decision(
            host="127.0.0.1", port=8000, db_path=self.db_path, secrets_dir=self.secrets_dir
        )
        self.assertEqual(res["decision"], "GO_FOR_LOCAL_ACTIVATION")
        self.assertTrue(res["can_proceed_to_activation"])
        self.assertEqual(res["certification_status"], "CERTIFIED")
        self.assertTrue(res["is_certified"])
        self.assertEqual(
            res["autonomous_execution_bypass_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )

    def test_operator_go_no_go_critical_failure_no_go(self):
        """Validates formal Operator Go/No-Go decision produces NO_GO_ACTIVATION_HALTED on critical failure."""
        # Force critical failure via non-loopback bind
        cert = self.engine.certify_local_activation_readiness(host="10.0.0.1", port=8000, db_path=self.db_path)
        res = self.engine.evaluate_operator_go_no_go_decision(certification_result=cert, db_path=self.db_path)
        self.assertEqual(res["decision"], "NO_GO_ACTIVATION_HALTED")
        self.assertFalse(res["can_proceed_to_activation"])

    def test_operator_go_no_go_conditional_review_on_pressure(self):
        """Validates formal Operator Go/No-Go produces CONDITIONAL_GO_OPERATOR_REVIEW_REQUIRED on non-critical degradation."""
        # Simulated certification result with degraded non-critical state
        simulated_cert = {
            "certification_status": "DEGRADED_CONDITIONAL",
            "is_certified": False,
            "gate_evaluations": {
                "ram_guard": {"status": "PRESSURE", "critical": False}
            }
        }
        res = self.engine.evaluate_operator_go_no_go_decision(certification_result=simulated_cert, db_path=self.db_path)
        self.assertEqual(res["decision"], "CONDITIONAL_GO_OPERATOR_REVIEW_REQUIRED")
        self.assertFalse(res["can_proceed_to_activation"])

    def test_emergency_controls_readiness_and_truthful_reporting(self):
        """Validates verified control paths for sanctuary_mode and kill_switch."""
        res = self.engine._check_emergency_controls()
        self.assertIn("controls_verified", res)
        self.assertIn("sanctuary_mode", res)
        self.assertIn("kill_switch", res)

    def test_final_local_health_validation(self):
        """Validates final local endpoint health using existing server behavior."""
        res = self.engine.validate_final_local_health()
        self.assertEqual(res["status"], "VALIDATED")
        self.assertIn("/api/status", res["endpoint_results"])
        self.assertTrue(res["endpoint_results"]["/api/status"]["healthy"])

    def test_safe_local_api_smoke_nominal_and_financial_quarantine(self):
        """Validates safe local API smoke pipeline and permanent financial quarantine refusal."""
        # Nominal intent
        res_nom = self.engine.validate_safe_local_api_smoke(transcript="System diagnostic health check")
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

    def test_operator_certification_report_in_memory_and_persistence_gate(self):
        """Validates in-memory report generation, persistence gate, and rollback dry-run."""
        # 1. In-memory generation
        report = self.aadya.generate_operator_activation_report(
            stage=14, host="127.0.0.1", port=8000, db_path=self.db_path, secrets_dir=self.secrets_dir
        )
        self.assertEqual(report["report_version"], "AADYA_STAGE14_V1")
        self.assertEqual(report["stage"], 14)
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
        rollback = self.aadya.execute_certification_rollback_dry_run()
        self.assertEqual(rollback["status"], "DRY_RUN_ROLLBACK_VERIFIED")
        self.assertEqual(rollback["base_checkpoint_commit"], "028b2877069e351ae7bf8b8e2e7ce4e86a7f0ab3")
        self.assertFalse(rollback["execution_performed"])
        self.assertEqual(len(rollback["files_mutated"]), 0)


if __name__ == "__main__":
    unittest.main()
