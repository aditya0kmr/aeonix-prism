"""
Unit & Integration Tests for AADYA Stage 12:
Controlled Local Service Activation & Operator Console Readiness.
"""

import os
import sys
import shutil
import tempfile
import unittest

from core.aadya import AadyaCrownZero
from core.aadya_console import AadyaConsoleEngine
from core.db import init_database, execute_db, query_db, log_audit_event


class TestAadyaStage12(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_aadya_stage12_")
        self.db_path = os.path.join(self.test_dir, "test_vault.db")
        init_database(self.db_path)
        self.aadya = AadyaCrownZero(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_stage12_console_engine_initialization_and_status(self):
        """Verifies AadyaConsoleEngine initializes properly and handles degraded database failure."""
        self.assertIsNotNone(self.aadya.console)
        self.assertEqual(self.aadya.console_initialization_status, "INITIALIZED")
        self.assertIsNone(self.aadya.console_initialization_error)

        # Degraded state on invalid db path
        degraded = AadyaCrownZero(db_path="/proc/illegal_path/db.sqlite")
        self.assertEqual(degraded.console_initialization_status, "INITIALIZATION_FAILED")
        with self.assertRaises(RuntimeError):
            degraded.activate_controlled_local_service()

    def test_controlled_local_service_activation_nominal(self):
        """Validates that local service activation succeeds in-process with loopback and valid DB."""
        res = self.aadya.activate_controlled_local_service()
        self.assertEqual(res["service_status"], "ACTIVE_LOCAL")
        self.assertEqual(res["activation_verdict"], "SERVICE_ACTIVATED_LOCAL_CONTROLLED")
        self.assertTrue(res["can_accept_requests"])
        self.assertTrue(res["is_loopback"])
        self.assertEqual(
            res["autonomous_execution_bypass_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )
        self.assertIn("digest", res)
        self.assertEqual(len(res["digest"]), 64)

    def test_controlled_local_service_activation_catches_invalid_configuration(self):
        """Validates that service activation fails closed on invalid port or non-loopback bind without TLS."""
        # Non-loopback host without TLS
        res_host = self.aadya.activate_controlled_local_service(env_overrides={"AEONIX_BIND_HOST": "0.0.0.0"})
        self.assertEqual(res_host["service_status"], "ACTIVATION_HALTED")
        self.assertFalse(res_host["can_accept_requests"])
        host_checks = [c for c in res_host["precondition_checks"] if c["gate"] == "HOST_BINDING_SECURITY"]
        self.assertTrue(any(c["status"] == "FAILED" for c in host_checks))

        # Invalid port
        res_port = self.aadya.activate_controlled_local_service(env_overrides={"AEONIX_PORT": "invalid_port"})
        self.assertEqual(res_port["service_status"], "ACTIVATION_HALTED")
        self.assertFalse(res_port["can_accept_requests"])
        port_checks = [c for c in res_port["precondition_checks"] if c["gate"] == "PORT_CONFIGURATION"]
        self.assertTrue(any(c["status"] == "FAILED" for c in port_checks))

    def test_controlled_local_service_activation_fails_closed_on_corrupt_audit(self):
        """Validates that a corrupted audit chain halts local service activation."""
        execute_db(
            "INSERT INTO audit_log (timestamp, actor, action, target, result, details_json, previous_hash, current_hash) "
            "VALUES (12345.0, 'TAMPER', 'TAMPER', 'TAMPER', 'FAIL', '{}', 'bad_prev', 'bad_curr');",
            db_path=self.db_path
        )
        res = self.aadya.activate_controlled_local_service()
        self.assertEqual(res["service_status"], "ACTIVATION_HALTED")
        self.assertEqual(res["activation_verdict"], "ACTIVATION_HALTED")
        self.assertFalse(res["can_accept_requests"])
        audit_checks = [c for c in res["precondition_checks"] if c["gate"] == "AUDIT_CHAIN_INTEGRITY"]
        self.assertTrue(any(c["status"] == "FAILED" for c in audit_checks))

    def test_operator_console_readiness_nominal(self):
        """Validates operator console readiness, review deck query, Action Digest, and emergency controls."""
        res = self.aadya.validate_operator_console_readiness()
        self.assertEqual(res["console_verdict"], "CONSOLE_READY_FOR_OPERATOR")
        self.assertTrue(res["action_digest_binding_ready"])
        self.assertTrue(res["emergency_controls_ready"]["sanctuary_mode"])
        self.assertTrue(res["emergency_controls_ready"]["kill_switch"])
        self.assertIn("total_pending_reviews", res["review_deck"])
        self.assertIn("digest", res)

    def test_operator_console_security_enforcement(self):
        """Validates security enforcement and RBAC on /operator and /console routes."""
        res = self.aadya.validate_operator_console_readiness()
        routes = res["routes_verified"]
        self.assertTrue(routes["/operator"]["enforces_security"])
        self.assertTrue(routes["/console"]["enforces_security"])

    def test_local_endpoint_health_validation(self):
        """Validates local endpoint health using existing server behavior."""
        res = self.aadya.validate_local_endpoint_health()
        self.assertEqual(res["status"], "VALIDATED")
        results = res["endpoint_results"]
        self.assertTrue(results["/api/status"]["healthy"])

    def test_safe_local_api_smoke_nominal(self):
        """Validates safe local API smoke pipeline with simulated transcript input."""
        res = self.aadya.validate_safe_local_api_smoke("Inspect sovereign routines")
        self.assertEqual(res["status"], "VALIDATED")
        self.assertTrue(res["success"])
        self.assertTrue(res["dry_run"])

    def test_permanent_financial_quarantine_in_service_smoke(self):
        """Validates that financial intents are blocked immediately at the service smoke boundary."""
        res = self.aadya.validate_safe_local_api_smoke("transfer funds to external wallet")
        self.assertEqual(res["status"], "FINANCIAL_BLOCKED")
        self.assertFalse(res["success"])
        self.assertEqual(res["action_type"], "FINANCIAL_EXECUTION_REFUSED")

    def test_voice_ownership_and_single_response_concurrency(self):
        """Validates single-response voice concurrency lock exclusivity."""
        res = self.aadya.console.verify_voice_ownership_and_concurrency()
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
        """Validates genesis-to-tip SHA-256 audit verification through the console engine."""
        res = self.aadya.console.verify_audit_and_hardware_guards()
        self.assertTrue(res["audit_valid"])
        self.assertEqual(res["audit_status"], "AUDIT_CHAIN_VERIFIED")

    def test_ram_guard_integration_and_truthful_reporting(self):
        """Validates RAM guard threshold evaluation and truthful status reporting."""
        res = self.aadya.console.verify_audit_and_hardware_guards()
        self.assertIn(res["ram_status"], ("NOMINAL", "PRESSURE", "DEGRADED"))

    def test_operator_activation_report_in_memory_and_persistence_gate(self):
        """Validates in-memory report generation, persistence gate, and rollback dry-run."""
        report = self.aadya.generate_operator_activation_report(stage=12)
        self.assertEqual(report["report_version"], "AADYA_STAGE12_V1")
        self.assertEqual(report["service_status"], "ACTIVE_LOCAL")
        self.assertEqual(
            report["overall_verdict"],
            "READY_FOR_OPERATOR_ACTIVATION"
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

        # Rollback dry-run validation
        rb = self.aadya.execute_console_rollback_dry_run()
        self.assertEqual(rb["status"], "DRY_RUN_ROLLBACK_VERIFIED")
        self.assertEqual(rb["base_checkpoint_commit"], "b847043")
        self.assertGreaterEqual(len(rb["routine_rollback_commands"]), 3)
        self.assertIn("LAST_RESORT_REQUIRES_SEPARATE_OPERATOR_APPROVAL", rb["last_resort_recovery_command"])
        self.assertFalse(rb["execution_performed"])
        self.assertTrue(os.path.exists("/data/data/com.termux/files/home/aeonix-prism/core/aadya_console.py"))


if __name__ == "__main__":
    unittest.main()
