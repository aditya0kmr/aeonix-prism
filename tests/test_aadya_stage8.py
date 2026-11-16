"""
Unit and Integration Tests for AADYA Stage 8 — Deployment Packaging & Controlled Runtime Validation
===================================================================================================
Verifies:
1. Stage 8 Deployment Engine initialization and properties
2. Production configuration validation (safe localhost defaults vs invalid ports/paths)
3. Production configuration validation catches exposed binds without TLS credentials
4. Dependency and import audit reports NO_KNOWN_CLOUD_LLM_SDK_IMPORTS_DETECTED with explicit scope limitation
5. Database integrity and schema verification across all 17 canonical tables
6. Server startup readiness validation without binding listening sockets
7. API endpoint contract validation for /api/aadya/priority, /api/aadya/radar, and /api/aadya/protection
8. Voice pipeline end-to-end dry-run validation
9. TV surface payload safety runtime validation
10. POCO escalation readiness validation using existing canonical table (aadya_escalations)
11. Audit-chain cryptographic verification and tamper detection in deployment validation
12. RAM guard integration and memory pressure detection
13. Deployment manifest generation with SHA-256 digests and zero leaked secrets
14. Dry-run rollback procedure validation with file-level restoration strategy
15. Preservation of all stages, backward-compatibility delegates, and degraded-state handling
"""

import os
import sys
import time
import json
import unittest
import tempfile
import sqlite3
from unittest.mock import patch

from core.db import init_database, query_db, execute_db, log_audit_event, verify_audit_chain, get_connection
from core.aadya import AadyaCrownZero
from core.aadya_deployment import AadyaDeploymentEngine, DeploymentValidationError
from core.aadya_context import ContextPrivacyTier


class TestAadyaStage8(unittest.TestCase):

    def setUp(self):
        # Create unique isolated temporary SQLite database for each test
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # Initialize schema and seed genuine genesis audit event
        init_database(self.db_path)
        log_audit_event(
            actor="AZ-001_AADYA",
            action="STAGE8_TEST_SETUP",
            target="test_setup",
            result="INITIALIZED",
            details={"env": "testing_isolated"},
            db_path=self.db_path
        )

        # Initialize sovereign Crown-0 mind bound to the isolated database
        self.aadya = AadyaCrownZero(db_path=self.db_path)
        self.deployment = self.aadya.deployment

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # 1. Deployment Engine Initialization & Status
    # -------------------------------------------------------------------------
    def test_stage8_deployment_engine_initialization_and_status(self):
        self.assertIsNotNone(self.deployment)
        self.assertTrue(self.deployment.is_initialized)
        self.assertEqual(self.deployment.initialization_status, "INITIALIZED")
        self.assertIsNone(self.deployment.init_error)

    # -------------------------------------------------------------------------
    # 2. Production Configuration Validation (Nominal Localhost)
    # -------------------------------------------------------------------------
    def test_production_configuration_validation_nominal(self):
        res = self.aadya.validate_production_configuration({
            "bind_host": "127.0.0.1",
            "port": 8080,
            "db_path": self.db_path
        })
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_loopback"])
        self.assertEqual(len(res["violations"]), 0)

        # Catch invalid port
        res_bad_port = self.aadya.validate_production_configuration({"port": 70000})
        self.assertFalse(res_bad_port["is_valid"])
        self.assertIn("out of valid range", res_bad_port["violations"][0])

    # -------------------------------------------------------------------------
    # 3. Production Configuration Validation (Catches Exposed Bind Without TLS)
    # -------------------------------------------------------------------------
    def test_production_configuration_validation_catches_exposed_bind_without_tls(self):
        # Non-loopback bind without TLS
        res_exposed = self.aadya.validate_production_configuration({
            "bind_host": "0.0.0.0",
            "port": 8080,
            "tls_enabled": False,
            "tls_cert_file": "/tmp/nonexistent_cert.pem",
            "tls_key_file": "/tmp/nonexistent_key.pem"
        })
        self.assertFalse(res_exposed["is_valid"])
        self.assertEqual(res_exposed["status"], "INVALID_CONFIGURATION")
        self.assertIn("strictly requires TLS", res_exposed["violations"][0])

    # -------------------------------------------------------------------------
    # 4. Dependency & Import Audit (Reports NO_KNOWN_CLOUD_LLM_SDK_IMPORTS_DETECTED)
    # -------------------------------------------------------------------------
    def test_dependency_and_import_audit_reports_no_known_cloud_sdks(self):
        res = self.aadya.audit_subsystem_dependencies()
        self.assertTrue(res["is_clean"])
        self.assertEqual(res["status"], "NO_KNOWN_CLOUD_LLM_SDK_IMPORTS_DETECTED")
        self.assertTrue(res["scanned_files_count"] >= 7)
        self.assertIn("scope_limitation", res)
        self.assertIn("static AST parsing", res["scope_limitation"])
        self.assertEqual(len(res["detected_violations"]), 0)

    # -------------------------------------------------------------------------
    # 5. Database & Schema Integrity Verification
    # -------------------------------------------------------------------------
    def test_database_and_schema_integrity_verification(self):
        res = self.aadya.verify_database_and_schema_integrity()
        self.assertTrue(res["is_healthy"])
        self.assertEqual(res["status"], "HEALTHY")
        self.assertEqual(res["sqlite_integrity_check"], "ok")
        self.assertEqual(len(res["missing_tables"]), 0)
        self.assertTrue(res["audit_chain_valid"])

    # -------------------------------------------------------------------------
    # 6. Server Startup Readiness Validation (Socket-Free)
    # -------------------------------------------------------------------------
    def test_server_startup_readiness_validation(self):
        res = self.aadya.validate_server_startup_readiness()
        self.assertTrue(res["is_ready"])
        self.assertEqual(res["status"], "READY")
        self.assertFalse(res["socket_bound"])
        self.assertTrue(len(res["aadya_routes_found"]) >= 3)
        self.assertEqual(len(res["missing_expected_routes"]), 0)

    # -------------------------------------------------------------------------
    # 7. API Endpoint Contract Validation via Isolated TestClient
    # -------------------------------------------------------------------------
    def test_api_endpoint_contracts_via_isolated_test_client(self):
        res = self.aadya.validate_api_endpoint_contracts()
        self.assertTrue(res["all_passed"])
        self.assertEqual(res["status"], "CONTRACTS_VERIFIED")
        self.assertTrue(res["endpoints"]["/api/aadya/radar"]["passed"])
        self.assertTrue(res["endpoints"]["/api/aadya/protection"]["passed"])
        self.assertTrue(res["endpoints"]["/api/aadya/priority"]["passed"])

    # -------------------------------------------------------------------------
    # 8. Voice Pipeline Dry-Run Validation
    # -------------------------------------------------------------------------
    def test_voice_pipeline_dry_run_validation(self):
        # Initial voice interaction count
        initial_interactions = len(self.aadya.list_voice_interactions())

        # Process voice command in dry_run mode
        turn_res = self.aadya.process_voice_command("give me a morning briefing", dry_run=True)
        self.assertTrue(turn_res["success"])
        self.assertEqual(turn_res["intent"], "BRIEFING_REQUEST")
        self.assertIn("Aadi", turn_res["speech"])

        # In dry_run mode, interaction must not be persisted to SQLite
        after_interactions = len(self.aadya.list_voice_interactions())
        self.assertEqual(initial_interactions, after_interactions)

    # -------------------------------------------------------------------------
    # 9. TV Surface Payload Safety Runtime Validation
    # -------------------------------------------------------------------------
    def test_tv_surface_payload_safety_runtime_validation(self):
        payload = self.aadya.render_living_surface(create_snapshot=False)
        self.assertIn("cards", payload)
        self.assertEqual(payload["screen"], "living_surface")

        # Must pass assertion without raising exception
        self.aadya.surface.assert_tv_payload_safety(payload)

        # Check for absolute exclusion of private tier markers in JSON
        serialized = json.dumps(payload)
        self.assertNotIn("OPERATOR_ONLY", serialized)
        self.assertNotIn("SOVEREIGN_VAULT_RESTRICTED", serialized)

    # -------------------------------------------------------------------------
    # 10. POCO Escalation Readiness Validation
    # -------------------------------------------------------------------------
    def test_poco_escalation_readiness_validation(self):
        initial_escalations = len(query_db("SELECT id FROM aadya_escalations;", db_path=self.db_path))

        # Perform escalation through Crown-0
        esc = self.aadya.escalate_to_poco(
            action_type="modify_security_policy",
            details={"target": "core_sentinel", "policy": "strict"}
        )
        self.assertIsNotNone(esc.get("escalation_id"))
        self.assertEqual(esc.get("action_type"), "modify_security_policy")

        # Announcement check must remain neutral
        announcement = self.aadya.announce_pending_escalations()
        self.assertIn("pending action", announcement)
        self.assertNotIn("modify_security_policy", announcement)

        # Verify record in canonical table
        after_escalations = len(query_db("SELECT id FROM aadya_escalations;", db_path=self.db_path))
        self.assertEqual(after_escalations, initial_escalations + 1)

    # -------------------------------------------------------------------------
    # 11. Audit-Chain Cryptographic Integrity & Tamper Detection
    # -------------------------------------------------------------------------
    def test_audit_chain_tamper_detection_in_deployment_validation(self):
        # Baseline is healthy
        baseline = self.aadya.verify_database_and_schema_integrity()
        self.assertTrue(baseline["audit_chain_valid"])

        # Tamper with row 1
        conn = get_connection(self.db_path, allow_maintenance=True)
        try:
            with conn:
                conn.execute("UPDATE audit_log SET result = 'TAMPERED' WHERE id = 1;")
        finally:
            conn.close()

        # Re-check integrity
        tampered = self.aadya.verify_database_and_schema_integrity()
        self.assertFalse(tampered["audit_chain_valid"])
        self.assertEqual(tampered["status"], "INTEGRITY_COMPROMISED")

    # -------------------------------------------------------------------------
    # 12. RAM Guard Integration & Pressure Detection
    # -------------------------------------------------------------------------
    def test_ram_guard_integration_in_deployment_validation(self):
        mock_pressure = {
            "can_proceed": False,
            "is_safe": False,
            "available_mb": 350.0,
            "threshold_mb": 800.0,
            "available_kb": 350000,
            "threshold_kb": 800000,
            "child_processes": 8,
            "process_limit_ok": True
        }
        with patch("core.aadya_readiness.check_ram_guard", return_value=mock_pressure):
            readiness = self.aadya.evaluate_operational_readiness()
            self.assertEqual(readiness["overall_status"], "DEGRADED")
            self.assertEqual(readiness["ram_guard"]["status"], "PRESSURE_WARNING")
            self.assertIn("System Memory Pressure", readiness["degraded_reasons"])

    # -------------------------------------------------------------------------
    # 13. Deployment Manifest Generation & Checksum Verification
    # -------------------------------------------------------------------------
    def test_deployment_manifest_generation_and_checksum_verification(self):
        manifest = self.aadya.generate_deployment_manifest(package_version="1.0.0")

        self.assertEqual(manifest["package_version"], "1.0.0")
        self.assertEqual(manifest["identity"]["rank"], "CROWN-0")
        self.assertEqual(manifest["baseline_verified_tests"], 440)
        self.assertTrue(len(manifest["component_checksums"]) >= 7)
        self.assertIsNotNone(manifest["manifest_digest"])

        # Verify checksums against disk
        verify_res = self.aadya.verify_deployment_checksums(manifest)
        self.assertTrue(verify_res["is_valid"])
        self.assertEqual(verify_res["status"], "CHECKSUMS_VERIFIED")
        self.assertEqual(len(verify_res["mismatches"]), 0)

    # -------------------------------------------------------------------------
    # 14. Dry-Run Rollback Procedure Validation
    # -------------------------------------------------------------------------
    def test_dry_run_rollback_procedure(self):
        rollback_res = self.aadya.execute_dry_run_rollback_procedure("test_manifest_id")
        self.assertTrue(rollback_res["dry_run"])
        self.assertTrue(rollback_res["rollback_possible"])
        self.assertEqual(rollback_res["strategy"], "FILE_LEVEL_RESTORE")
        self.assertIn("git checkout -- <file>", rollback_res["verification_steps"])
        self.assertIn("last-resort recovery", rollback_res["disaster_recovery_note"])

    # -------------------------------------------------------------------------
    # 15. Preservation of All Stages & Degraded Handling Delegates
    # -------------------------------------------------------------------------
    def test_preservation_of_all_stages_and_degraded_handling(self):
        # 1. Crown-0 Apex Core
        self.assertIsNotNone(self.aadya.IDENTITY_ID)

        # 2. Memory & Context Engine
        self.assertTrue(self.aadya.context.is_initialized)

        # 3. Autonomous Operations Engine
        self.assertTrue(self.aadya.missions.is_initialized)

        # 4. Learning & Self-Improvement Engine
        self.assertTrue(self.aadya.learning.is_initialized)

        # 5. Adaptive Interface & Living Surface Engine
        self.assertTrue(self.aadya.surface.is_initialized)

        # 6. Voice-First Command & Response Integration
        self.assertTrue(self.aadya.voice.is_initialized)

        # 7. End-to-End Operational Readiness Engine
        self.assertTrue(self.aadya.readiness.is_initialized)

        # 8. Deployment Packaging Engine
        self.assertTrue(self.aadya.deployment.is_initialized)

        # Execute full controlled runtime validation
        validation = self.aadya.execute_controlled_runtime_validation()
        self.assertTrue(validation["validation_passed"])
        self.assertEqual(validation["overall_status"], "VALIDATION_PASSED")


if __name__ == "__main__":
    unittest.main()
