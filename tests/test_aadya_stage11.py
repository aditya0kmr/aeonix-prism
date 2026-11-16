"""
Unit & Integration Tests for AADYA Stage 11:
Operator Activation Dry Run & Controlled Local Service Startup.
"""

import os
import sys
import shutil
import tempfile
import unittest

from core.aadya import AadyaCrownZero
from core.aadya_startup import AadyaStartupEngine
from core.db import init_database, execute_db, query_db, log_audit_event


class TestAadyaStage11(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_aadya_stage11_")
        self.db_path = os.path.join(self.test_dir, "test_vault.db")
        init_database(self.db_path)
        self.aadya = AadyaCrownZero(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_stage11_startup_engine_initialization_and_status(self):
        """Verifies AadyaStartupEngine initializes properly and handles degraded database failure."""
        self.assertIsNotNone(self.aadya.startup)
        self.assertEqual(self.aadya.startup_initialization_status, "INITIALIZED")
        self.assertIsNone(self.aadya.startup_initialization_error)

        # Initialization failure with invalid path
        degraded = AadyaCrownZero(db_path="/proc/illegal_path/db.sqlite")
        self.assertEqual(degraded.startup_initialization_status, "INITIALIZATION_FAILED")
        with self.assertRaises(RuntimeError):
            degraded.execute_operator_activation_dry_run()

    def test_operator_activation_dry_run_nominal(self):
        """Validates that operator activation dry run passes with loopback and valid database."""
        res = self.aadya.execute_operator_activation_dry_run()
        self.assertEqual(res["dry_run_verdict"], "READY_FOR_STARTUP")
        self.assertTrue(res["can_proceed_to_startup"])
        self.assertEqual(
            res["autonomous_execution_bypass_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )
        self.assertIn("digest", res)
        self.assertEqual(len(res["digest"]), 64)

    def test_operator_activation_dry_run_catches_invalid_configuration(self):
        """Validates that activation dry run fails closed on invalid port or non-loopback bind without TLS."""
        # Non-loopback host without TLS
        res_host = self.aadya.execute_operator_activation_dry_run(env_overrides={"AEONIX_BIND_HOST": "0.0.0.0"})
        self.assertFalse(res_host["can_proceed_to_startup"])
        self.assertEqual(res_host["dry_run_verdict"], "ACTIVATION_HALTED")
        host_checks = [c for c in res_host["checks"] if c["gate"] == "HOST_BINDING_SECURITY"]
        self.assertTrue(any(c["status"] == "FAILED" for c in host_checks))

        # Invalid port
        res_port = self.aadya.execute_operator_activation_dry_run(env_overrides={"AEONIX_PORT": "invalid_port"})
        self.assertFalse(res_port["can_proceed_to_startup"])
        self.assertEqual(res_port["dry_run_verdict"], "ACTIVATION_HALTED")
        port_checks = [c for c in res_port["checks"] if c["gate"] == "PORT_CONFIGURATION"]
        self.assertTrue(any(c["status"] == "FAILED" for c in port_checks))

    def test_operator_activation_dry_run_fails_closed_on_corrupt_audit_chain(self):
        """Validates that a corrupted audit chain blocks can_proceed_to_startup."""
        # Tamper with an audit entry in the database
        execute_db(
            "INSERT INTO audit_log (timestamp, actor, action, target, result, details_json, previous_hash, current_hash) "
            "VALUES (12345.0, 'TAMPER', 'TAMPER', 'TAMPER', 'FAIL', '{}', 'bad_prev', 'bad_curr');",
            db_path=self.db_path
        )
        res = self.aadya.execute_operator_activation_dry_run()
        self.assertFalse(res["can_proceed_to_startup"])
        self.assertEqual(res["dry_run_verdict"], "ACTIVATION_HALTED")
        audit_checks = [c for c in res["checks"] if c["gate"] == "AUDIT_CHAIN_INTEGRITY"]
        self.assertTrue(any(c["status"] == "FAILED" for c in audit_checks))

    def test_controlled_local_service_startup_in_process(self):
        """Validates the in-process service startup lifecycle without background daemons or socket binding."""
        res = self.aadya.validate_controlled_service_startup()
        self.assertEqual(res["startup_status"], "STARTUP_SUCCESS_LOCAL_CONTROLLED")
        self.assertTrue(res["can_accept_requests"])
        self.assertEqual(res["service_mode"], "IN_PROCESS_ASGI_CONTROLLED")
        self.assertTrue(res["lifecycle_hooks"]["routes_mounted"])
        self.assertTrue(res["lifecycle_hooks"]["in_process_call_succeeded"])
        self.assertIn("digest", res)

    def test_local_endpoint_health_validation(self):
        """Validates local endpoint health using isolated test credentials and existing behavior."""
        res = self.aadya.validate_local_endpoint_health()
        self.assertEqual(res["status"], "VALIDATED")
        results = res["endpoint_results"]
        self.assertTrue(results["/api/status"]["healthy"])
        self.assertTrue(results["/api/system/status"]["enforces_security"])
        self.assertTrue(results["/operator"]["enforces_security"])

    def test_safe_local_api_smoke_nominal(self):
        """Validates safe local API smoke pipeline with simulated transcript input."""
        res = self.aadya.validate_safe_local_api_smoke("What is our primary mission today?")
        self.assertEqual(res["status"], "VALIDATED")
        self.assertTrue(res["success"])
        self.assertTrue(res["dry_run"])

    def test_permanent_financial_quarantine_in_startup_smoke(self):
        """Validates that financial intents are blocked immediately at the startup smoke boundary."""
        res = self.aadya.validate_safe_local_api_smoke("transfer funds to external wallet")
        self.assertEqual(res["status"], "FINANCIAL_BLOCKED")
        self.assertFalse(res["success"])
        self.assertEqual(res["action_type"], "FINANCIAL_EXECUTION_REFUSED")

    def test_voice_ownership_and_single_response_concurrency(self):
        """Validates single-response voice concurrency lock exclusivity."""
        res = self.aadya.startup.verify_voice_ownership_and_concurrency()
        self.assertEqual(res["status"], "VALIDATED")
        self.assertTrue(res.get("lock_acquired_and_released", False))
        self.assertTrue(res.get("busy_rejection_verified", False))

    def test_tv_safe_surface_readiness_and_privacy_quarantine(self):
        """Validates TV surface payload sanitization and strict suppression of operator-only data."""
        res = self.aadya.validate_tv_safe_surface_readiness()
        self.assertEqual(res["status"], "VALIDATED")
        self.assertTrue(res["privacy_quarantine_enforced"])
        self.assertTrue(res["operator_data_suppressed"])

    def test_poco_escalation_readiness_and_lifecycle(self):
        """Validates POCO physical escalation queue and reports autonomous execution bypass status."""
        res = self.aadya.validate_poco_escalation_readiness()
        self.assertEqual(res["status"], "VALIDATED")
        self.assertTrue(res["deny_first_enforced"])
        self.assertEqual(
            res["autonomous_execution_bypass_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )

    def test_audit_chain_verification_and_tamper_detection(self):
        """Validates genesis-to-tip SHA-256 audit verification through the startup engine."""
        res = self.aadya.startup.verify_audit_and_hardware_guards()
        self.assertTrue(res["audit_valid"])
        self.assertEqual(res["audit_status"], "AUDIT_CHAIN_VERIFIED")

    def test_ram_guard_integration_and_truthful_reporting(self):
        """Validates RAM guard threshold evaluation and truthful status reporting."""
        res = self.aadya.startup.verify_audit_and_hardware_guards()
        self.assertIn(res["ram_status"], ("NOMINAL", "PRESSURE", "DEGRADED"))

    def test_controlled_rollback_dry_run_non_destructive(self):
        """Validates rollback dry run returns explicit commands without deleting files or mutating git."""
        res = self.aadya.execute_startup_rollback_dry_run()
        self.assertEqual(res["status"], "DRY_RUN_ROLLBACK_VERIFIED")
        self.assertEqual(res["base_checkpoint_commit"], "d838608")
        self.assertGreaterEqual(len(res["routine_rollback_commands"]), 3)
        self.assertIn("LAST_RESORT_REQUIRES_SEPARATE_OPERATOR_APPROVAL", res["last_resort_recovery_command"])
        self.assertGreaterEqual(len(res["preconditions"]), 2)
        self.assertFalse(res["execution_performed"])

        # Confirm target file still exists and was not deleted
        startup_file = "/data/data/com.termux/files/home/aeonix-prism/core/aadya_startup.py"
        self.assertTrue(os.path.exists(startup_file))

    def test_operator_activation_report_in_memory_and_persistence_gate(self):
        """Validates in-memory report generation and that persistence strictly requires operator approval."""
        report = self.aadya.generate_operator_activation_report()
        self.assertEqual(report["report_version"], "AADYA_STAGE11_V1")
        self.assertIn(
            report["overall_verdict"],
            ("READY_FOR_OPERATOR_ACTIVATION", "DEGRADED_OPERATOR_REVIEW_REQUIRED", "ACTIVATION_HALTED")
        )
        self.assertEqual(
            report["autonomous_execution_bypass_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )
        self.assertIn("report_digest", report)
        self.assertEqual(len(report["report_digest"]), 64)

        # Unapproved persistence fails closed
        with self.assertRaises(PermissionError):
            self.aadya.persist_operator_activation_report(report, operator_approved=False)

        # Approved persistence succeeds
        persisted = self.aadya.persist_operator_activation_report(report, operator_approved=True)
        self.assertEqual(persisted["status"], "PERSISTED")
        self.assertEqual(persisted["report_digest"], report["report_digest"])


if __name__ == "__main__":
    unittest.main()
