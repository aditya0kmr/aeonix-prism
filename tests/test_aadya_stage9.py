"""
Tests for AADYA Stage 9: Controlled Local Service Validation & Operator Readiness.
Verifies:
1. In-process local server startup readiness without socket binding.
2. Local endpoint authentication enforcement using isolated test credentials.
3. Read-only AADYA subsystem health aggregation.
4. Voice ownership and concurrency lock validation.
5. TV-safe surface payload generation and privacy quarantine.
6. POCO escalation queue readiness with AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS.
7. Audit-chain integrity and tamper detection.
8. RAM guard integration and truthful threshold reporting.
9. Controlled local smoke test execution using simulated transcripts.
10. In-memory operator readiness report synthesis and digest generation.
11. Report persistence strictly requiring explicit operator approval.
12. Truthful degraded-state handling across subsystems.
13. Sensitive data non-exposure across operator surfaces.
14. Permanent financial quarantine non-bypass across operator paths.
15. Preservation of all existing stages and backward compatibility.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, "/data/data/com.termux/files/home/aeonix-prism")

from core.db import init_database, query_db, execute_db, log_audit_event, get_connection
from core.aadya import AadyaCrownZero
from core.aadya_context import ContextPrivacyTier
from core.aadya_voice import VoiceBusyError
from core.aadya_operator import AadyaOperatorEngine


class TestAadyaStage9(unittest.TestCase):
    """Exhaustive test suite for AADYA Stage 9 Operator Engine."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_aeonix.db")
        init_database(self.db_path)
        self.aadya = AadyaCrownZero(db_path=self.db_path)
        self.operator = self.aadya.operator

    def tearDown(self):
        try:
            shutil.rmtree(self.test_dir, ignore_errors=True)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 1. Stage 9 Operator Engine Initialization and Status
    # -------------------------------------------------------------------------
    def test_stage9_operator_engine_initialization_and_status(self):
        self.assertIsNotNone(self.operator)
        self.assertIsInstance(self.operator, AadyaOperatorEngine)
        self.assertTrue(self.operator.is_initialized)
        self.assertEqual(self.aadya.operator_initialization_status, "INITIALIZED")
        self.assertIsNone(self.aadya.operator_initialization_error)

    # -------------------------------------------------------------------------
    # 2. Controlled Local Server Startup Validation
    # -------------------------------------------------------------------------
    def test_controlled_local_server_startup_validation(self):
        # Nominal in-process validation
        res = self.aadya.validate_local_service_readiness(config={"bind_host": "127.0.0.1", "port": 8080})
        self.assertEqual(res["status"], "VALIDATED")
        self.assertTrue(res["ready"])
        self.assertTrue(res["in_process_compilation"])
        self.assertGreater(res["total_routes"], 10)

        # Non-loopback bind host rejected during controlled validation
        bad_bind = self.aadya.validate_local_service_readiness(config={"bind_host": "0.0.0.0", "port": 8080})
        self.assertEqual(bad_bind["status"], "VALIDATION_FAILED")
        self.assertFalse(bad_bind["ready"])

    # -------------------------------------------------------------------------
    # 3. Local Endpoint Authentication Enforcement
    # -------------------------------------------------------------------------
    def test_local_endpoint_authentication_enforcement(self):
        auth_res = self.aadya.verify_local_endpoint_authentication()
        self.assertEqual(auth_res["status"], "VALIDATED")
        self.assertTrue(auth_res["ready"])
        self.assertTrue(auth_res["unauthenticated_public_accessible"])
        self.assertTrue(auth_res["unauthenticated_protected_rejected_401"])
        self.assertTrue(auth_res["authenticated_poco_core_accepted_200"])
        self.assertTrue(auth_res["unauthorized_role_rejected_403"])
        self.assertTrue(auth_res["isolated_credentials_used"])

    # -------------------------------------------------------------------------
    # 4. Read-Only AADYA Subsystem Health Aggregation
    # -------------------------------------------------------------------------
    def test_readonly_aadya_subsystem_health_aggregation(self):
        health = self.aadya.aggregate_subsystem_operator_health()
        self.assertEqual(health["overall_status"], "ALL_SYSTEMS_NOMINAL")
        self.assertEqual(health["degraded_count"], 0)
        self.assertTrue(health["is_operable"])

        subsystems = health["subsystems"]
        expected_engines = ["crown_zero", "context", "missions", "learning", "surface", "voice", "readiness", "deployment", "operator"]
        for eng in expected_engines:
            self.assertIn(eng, subsystems)
            self.assertEqual(subsystems[eng], "INITIALIZED")

    # -------------------------------------------------------------------------
    # 5. Truthful Degraded-State Handling across Subsystems
    # -------------------------------------------------------------------------
    def test_subsystem_health_aggregation_degraded_state_handling(self):
        # Simulate non-critical sub-engine failure
        orig_status = self.aadya.context_initialization_status
        self.aadya.context_initialization_status = "INITIALIZATION_FAILED"

        try:
            health = self.aadya.aggregate_subsystem_operator_health()
            self.assertEqual(health["overall_status"], "DEGRADED")
            self.assertIn("context", health["degraded_subsystems"])
            self.assertTrue(health["is_operable"])
        finally:
            self.aadya.context_initialization_status = orig_status

        # Simulate critical Crown-0 apex failure
        orig_crown = self.aadya.initialization_status
        self.aadya.initialization_status = "INITIALIZATION_FAILED"
        try:
            crit_health = self.aadya.aggregate_subsystem_operator_health()
            self.assertEqual(crit_health["overall_status"], "NOT_READY")
            self.assertFalse(crit_health["is_operable"])
        finally:
            self.aadya.initialization_status = orig_crown

    # -------------------------------------------------------------------------
    # 6. Voice Ownership and Concurrency Lock Validation
    # -------------------------------------------------------------------------
    def test_voice_ownership_and_concurrency_lock(self):
        voice_res = self.aadya.verify_voice_ownership_and_concurrency()
        self.assertEqual(voice_res["status"], "VALIDATED")
        self.assertTrue(voice_res["ready"])
        self.assertTrue(voice_res["concurrency_lock_operational"])
        self.assertTrue(voice_res["voice_busy_enforced"])

    # -------------------------------------------------------------------------
    # 7. TV-Safe Surface Payload Safety and Privacy Quarantine
    # -------------------------------------------------------------------------
    def test_tv_surface_payload_safety_and_privacy_quarantine(self):
        surface_res = self.aadya.verify_tv_surface_payload_safety()
        self.assertEqual(surface_res["status"], "VALIDATED")
        self.assertTrue(surface_res["ready"])
        self.assertGreater(surface_res["cards_inspected"], 0)
        self.assertTrue(surface_res["zero_private_leakage"])

    # -------------------------------------------------------------------------
    # 8. POCO Escalation Queue Readiness Validation
    # -------------------------------------------------------------------------
    def test_poco_escalation_readiness_and_lifecycle(self):
        poco_res = self.aadya.verify_poco_escalation_queue_readiness()
        self.assertEqual(poco_res["status"], "VALIDATED")
        self.assertTrue(poco_res["ready"])
        self.assertTrue(poco_res["escalation_queue_accessible"])
        self.assertEqual(
            poco_res["autonomous_execution_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )
        self.assertTrue(poco_res["operator_gate_enforced"])

    # -------------------------------------------------------------------------
    # 9. Audit-Chain Verification and Tamper Detection
    # -------------------------------------------------------------------------
    def test_audit_chain_verification_and_tamper_detection(self):
        # Nominal audit chain
        clean_res = self.aadya.verify_audit_and_ram_guard()
        self.assertEqual(clean_res["audit_chain_status"], "AUDIT_CHAIN_VERIFIED")

        # Tamper test on temporary database copy
        tamper_dir = tempfile.mkdtemp()
        tamper_db = os.path.join(tamper_dir, "tampered.db")
        shutil.copyfile(self.db_path, tamper_db)

        try:
            execute_db(
                "UPDATE audit_log SET action = 'FORGED_ACTION' WHERE id = (SELECT id FROM audit_log ORDER BY id DESC LIMIT 1);",
                db_path=tamper_db
            )
            tamper_engine = AadyaOperatorEngine(db_path=tamper_db, parent_crown_zero=self.aadya)
            tamper_res = tamper_engine.verify_audit_and_ram_guard()
            self.assertEqual(tamper_res["audit_chain_status"], "AUDIT_VERIFICATION_FAILED")
            self.assertEqual(tamper_res["status"], "DEGRADED")
        finally:
            shutil.rmtree(tamper_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 10. RAM Guard Integration and Truthful Reporting
    # -------------------------------------------------------------------------
    def test_ram_guard_integration_and_threshold_verification(self):
        res = self.aadya.verify_audit_and_ram_guard()
        self.assertIn(res["ram_guard_status"], ["NOMINAL", "PRESSURE", "DEGRADED"])
        self.assertGreater(res["available_ram_kb"], 0)
        self.assertEqual(res["threshold_kb"], 800000)

    # -------------------------------------------------------------------------
    # 11. Controlled Local Smoke Tests Execution
    # -------------------------------------------------------------------------
    def test_controlled_local_smoke_turn_execution(self):
        smoke_res = self.aadya.execute_controlled_local_smoke_tests("give me my morning briefing")
        self.assertEqual(smoke_res["status"], "VALIDATED")
        self.assertTrue(smoke_res["success"])
        self.assertEqual(smoke_res["intent"], "BRIEFING_REQUEST")
        self.assertGreater(smoke_res["speech_length"], 10)
        self.assertTrue(smoke_res["has_layout_intent"])
        self.assertGreaterEqual(smoke_res["surface_cards"], 1)

    # -------------------------------------------------------------------------
    # 12. In-Memory Operator Readiness Report Synthesis and Digest
    # -------------------------------------------------------------------------
    def test_operator_readiness_report_in_memory_and_digest(self):
        report = self.aadya.generate_operator_readiness_report()
        self.assertIn("report_id", report)
        self.assertIn("report_digest", report)
        self.assertIn(report["verdict"], ["READY_FOR_OPERATOR_REVIEW", "DEGRADED_OPERATOR_ATTENTION_REQUIRED", "NOT_READY"])
        self.assertTrue(report["report_id"].startswith("op_rep_"))
        self.assertEqual(len(report["report_digest"]), 64)

        # Non-persistence invariant: report must NOT be auto-inserted into database
        rows = query_db(
            "SELECT COUNT(*) FROM audit_log WHERE action = 'OPERATOR_READINESS_REPORT_RECORDED' AND target = ?;",
            (report["report_id"],),
            db_path=self.db_path
        )
        self.assertEqual(rows[0][0], 0)

    # -------------------------------------------------------------------------
    # 13. Report Persistence Strictly Requires Operator Approval
    # -------------------------------------------------------------------------
    def test_operator_readiness_report_persistence_requires_approval(self):
        report = self.aadya.generate_operator_readiness_report()

        # Without explicit approval, persistence raises ValueError
        with self.assertRaises(ValueError):
            self.aadya.persist_operator_readiness_report(report, operator_approved=False)

        # With explicit approval, persistence succeeds
        persisted = self.aadya.persist_operator_readiness_report(report, operator_approved=True)
        self.assertTrue(persisted["persisted"])
        self.assertEqual(persisted["report_id"], report["report_id"])

        # Confirms audit log recorded the approval
        rows = query_db(
            "SELECT COUNT(*) FROM audit_log WHERE action = 'OPERATOR_READINESS_REPORT_RECORDED' AND target = ?;",
            (report["report_id"],),
            db_path=self.db_path
        )
        self.assertEqual(rows[0][0], 1)

    # -------------------------------------------------------------------------
    # 14. Permanent Financial Quarantine Non-Bypass across Operator Path
    # -------------------------------------------------------------------------
    def test_permanent_financial_quarantine_across_operator_surface(self):
        # Spoken financial command through dry-run smoke test returns quarantine refusal
        fin_smoke = self.aadya.execute_controlled_local_smoke_tests("transfer 1000 dollars to external wallet")
        self.assertTrue(fin_smoke["success"])
        self.assertEqual(fin_smoke["intent"], "FINANCIAL_BLOCKED")

        # Zero missions or escalations created from financial request
        m_rows = query_db("SELECT COUNT(*) FROM aadya_missions WHERE objective LIKE '%transfer%';", db_path=self.db_path)
        self.assertEqual(m_rows[0][0], 0)

    # -------------------------------------------------------------------------
    # 15. Preservation of All Existing Stages and Dry-Run Rollback
    # -------------------------------------------------------------------------
    def test_preservation_of_all_existing_stages_and_degraded_handling(self):
        # Stage 1: Crown-0 betterment priority
        prio = self.aadya.evaluate_priority("Review memory safety", "operational")
        self.assertIn("aadi_betterment_score", prio)

        # Stage 2: Context registration
        mem = self.aadya.add_memory_node(
            title="Stage 9 Verified",
            content="Service validation active",
            category="operational",
            privacy_tier=ContextPrivacyTier.TV_SAFE
        )
        self.assertIn("node_id", mem)

        # Stage 3: Missions listing
        missions = self.aadya.list_missions()
        self.assertIsInstance(missions, list)

        # Stage 4: Learning preference
        self.aadya.adapt_preference("ui_display", "theme_mode", "obsidian")
        pref = self.aadya.get_learned_preference("ui_display", "theme_mode")
        self.assertEqual(pref.get("value"), "obsidian")

        # Stage 5: Living surface rendering
        surface = self.aadya.render_living_surface(create_snapshot=False)
        self.assertEqual(surface.get("screen"), "living_surface")

        # Stage 6: Voice intent classification
        intent = self.aadya.classify_voice_intent("what are my active missions")
        self.assertEqual(intent.get("intent"), "MISSION_STATUS_QUERY")

        # Stage 7: Operational readiness evaluation
        readiness = self.aadya.evaluate_operational_readiness()
        self.assertIn(readiness.get("overall_status"), ["NOMINAL", "ALL_SYSTEMS_NOMINAL", "DEGRADED"])

        # Stage 8: Deployment manifest generation
        manifest = self.aadya.generate_deployment_manifest()
        self.assertIn("manifest_version", manifest)

        # Stage 9: Dry-run rollback verification
        rollback = self.operator.execute_dry_run_rollback_procedure()
        self.assertEqual(rollback["status"], "DRY_RUN_ROLLBACK_VERIFIED")
        self.assertEqual(rollback["base_checkpoint_commit"], "207651d")
        self.assertIn("LAST_RESORT_REQUIRES_SEPARATE_OPERATOR_APPROVAL", rollback["last_resort_recovery_command"])


if __name__ == "__main__":
    unittest.main()
