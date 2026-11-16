"""
Tests for AADYA Stage 10: Controlled Local Runtime Activation & Operator Handoff.
Verifies:
1. In-process activation engine initialization and status.
2. 10-point operator activation checklist evaluation.
3. Fault-isolated degraded-state handling across checklist items.
4. Operator readiness dashboard rendering with zero credential leakage.
5. Safe local runtime smoke pipeline execution with simulated transcripts.
6. Runtime voice ownership and single-speaker concurrency lock validation.
7. TV-safe surface runtime readiness and strict privacy quarantine.
8. POCO escalation gate readiness with AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS.
9. Cryptographic audit-chain and truthful hardware guard validation.
10. Non-destructive rollback dry-run validation without file deletion.
11. In-memory operator handoff report generation with SHA-256 digest.
12. Explicit operator approval gate required for report persistence.
13. Permanent financial quarantine non-bypass across activation smoke tests.
14. Sensitive credential and path stripping on all handoff surfaces.
15. Preservation of all existing stages 1 through 9 alongside Stage 10.
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
from core.aadya_activation import AadyaActivationEngine


class TestAadyaStage10(unittest.TestCase):
    """Exhaustive test suite for AADYA Stage 10 Activation Engine."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_aeonix.db")
        init_database(self.db_path)
        self.aadya = AadyaCrownZero(db_path=self.db_path)
        self.activation = self.aadya.activation

    def tearDown(self):
        try:
            shutil.rmtree(self.test_dir, ignore_errors=True)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 1. Stage 10 Activation Engine Initialization and Status
    # -------------------------------------------------------------------------
    def test_stage10_activation_engine_initialization_and_status(self):
        self.assertIsNotNone(self.activation)
        self.assertIsInstance(self.activation, AadyaActivationEngine)
        self.assertTrue(self.activation.is_initialized)
        self.assertEqual(self.aadya.activation_initialization_status, "INITIALIZED")
        self.assertIsNone(self.aadya.activation_initialization_error)

    # -------------------------------------------------------------------------
    # 2. Operator Activation Checklist Evaluation (Nominal)
    # -------------------------------------------------------------------------
    def test_operator_activation_checklist_evaluation(self):
        checklist = self.aadya.generate_operator_activation_checklist(
            config={"bind_host": "127.0.0.1", "port": 8080}
        )
        self.assertIn("checklist_id", checklist)
        self.assertTrue(checklist["checklist_id"].startswith("chk_act_"))
        self.assertTrue(checklist["all_items_passed"])

        items = checklist["items"]
        expected_keys = [
            "local_configuration",
            "database_and_schema",
            "audit_chain_integrity",
            "ram_guard_status",
            "subsystem_health",
            "voice_concurrency",
            "tv_surface_safety",
            "poco_escalation_gate",
            "test_credential_isolation",
            "rollback_readiness"
        ]
        for k in expected_keys:
            self.assertIn(k, items)
            self.assertTrue(items[k]["passed"])

    # -------------------------------------------------------------------------
    # 3. Fault-Isolated Degraded-State Handling across Checklist Items
    # -------------------------------------------------------------------------
    def test_operator_activation_checklist_degraded_state_handling(self):
        # Simulate sub-engine initialization failure
        orig_voice_status = self.aadya.voice_initialization_status
        self.aadya.voice_initialization_status = "INITIALIZATION_FAILED"

        try:
            checklist = self.aadya.generate_operator_activation_checklist(
                config={"bind_host": "127.0.0.1", "port": 8080}
            )
            # Checklist should not crash, but indicate failed item
            self.assertFalse(checklist["all_items_passed"])
            # Other independent items remain evaluated
            self.assertTrue(checklist["items"]["local_configuration"]["passed"])
            self.assertTrue(checklist["items"]["database_and_schema"]["passed"])
        finally:
            self.aadya.voice_initialization_status = orig_voice_status

    # -------------------------------------------------------------------------
    # 4. Operator Readiness Dashboard Rendering
    # -------------------------------------------------------------------------
    def test_operator_readiness_dashboard_rendering(self):
        dashboard = self.aadya.render_operator_readiness_dashboard()
        self.assertIn("dashboard_id", dashboard)
        self.assertIn("system_status", dashboard)
        self.assertIn("audit_chain_status", dashboard)
        self.assertIn("ram_status", dashboard)
        self.assertIn("available_ram_mb", dashboard)
        self.assertIn("pending_poco_reviews", dashboard)
        self.assertIn("activation_state", dashboard)
        self.assertEqual(dashboard["privacy_tier"], ContextPrivacyTier.OPERATOR_ONLY.value)

        # Zero sensitive tokens or absolute paths exposed
        serialized = json.dumps(dashboard)
        self.assertNotIn("Bearer", serialized)
        self.assertNotIn("PRIVATE_KEY", serialized)
        self.assertNotIn("/data/data", serialized)

    # -------------------------------------------------------------------------
    # 5. Safe Local Runtime Smoke Pipeline
    # -------------------------------------------------------------------------
    def test_safe_local_endpoint_smoke_pipeline(self):
        smoke_res = self.aadya.validate_runtime_smoke_pipeline("give me my morning briefing")
        self.assertEqual(smoke_res["status"], "VALIDATED")
        self.assertTrue(smoke_res["success"])
        self.assertEqual(smoke_res["intent"], "BRIEFING_REQUEST")
        self.assertGreater(smoke_res["speech_length"], 10)
        self.assertTrue(smoke_res["has_layout_intent"])
        self.assertGreaterEqual(smoke_res["surface_cards"], 1)
        self.assertGreater(smoke_res["latency_ms"], 0.0)

    # -------------------------------------------------------------------------
    # 6. Runtime Voice Ownership and Concurrency Lock
    # -------------------------------------------------------------------------
    def test_runtime_voice_ownership_and_concurrency(self):
        voice_res = self.aadya.verify_runtime_voice_concurrency()
        self.assertEqual(voice_res["status"], "VALIDATED")
        self.assertTrue(voice_res["ready"])
        self.assertTrue(voice_res["concurrency_lock_operational"])
        self.assertTrue(voice_res["voice_busy_enforced"])

    # -------------------------------------------------------------------------
    # 7. TV-Safe Surface Runtime Readiness
    # -------------------------------------------------------------------------
    def test_tv_safe_surface_runtime_readiness(self):
        surface_res = self.aadya.validate_surface_runtime_readiness()
        self.assertEqual(surface_res["status"], "VALIDATED")
        self.assertTrue(surface_res["ready"])
        self.assertGreater(surface_res["cards_inspected"], 0)
        self.assertTrue(surface_res["zero_private_leakage"])

    # -------------------------------------------------------------------------
    # 8. POCO Escalation Readiness and Bypass Absence
    # -------------------------------------------------------------------------
    def test_poco_escalation_readiness_and_bypass_absence(self):
        poco_res = self.aadya.validate_poco_gate_readiness()
        self.assertEqual(poco_res["status"], "VALIDATED")
        self.assertTrue(poco_res["ready"])
        self.assertEqual(
            poco_res["autonomous_execution_status"],
            "AUTONOMOUS_EXECUTION_BYPASS_NOT_DETECTED_IN_VALIDATED_PATHS"
        )
        self.assertTrue(poco_res["operator_gate_enforced"])

    # -------------------------------------------------------------------------
    # 9. Audit-Chain and Truthful Hardware Guard Validation
    # -------------------------------------------------------------------------
    def test_audit_chain_and_hardware_guards_verification(self):
        guards_res = self.aadya.verify_audit_and_hardware_guards()
        self.assertEqual(guards_res["audit_chain_status"], "AUDIT_CHAIN_VERIFIED")
        self.assertIn(guards_res["ram_guard_status"], ["NOMINAL", "PRESSURE", "DEGRADED"])
        self.assertGreater(guards_res["available_ram_kb"], 0)
        self.assertEqual(guards_res["threshold_kb"], 800000)

    # -------------------------------------------------------------------------
    # 10. Non-Destructive Rollback Dry-Run Validation
    # -------------------------------------------------------------------------
    def test_controlled_rollback_dry_run_procedure(self):
        # Rollback validation must strictly NOT delete files or run git checkout
        pre_exists = os.path.exists("/data/data/com.termux/files/home/aeonix-prism/core/aadya_activation.py")
        self.assertTrue(pre_exists)

        rollback_res = self.aadya.execute_controlled_rollback_dry_run()
        self.assertEqual(rollback_res["status"], "DRY_RUN_ROLLBACK_VERIFIED")
        self.assertEqual(rollback_res["base_checkpoint_commit"], "05e2771")
        self.assertIn("LAST_RESORT_REQUIRES_SEPARATE_OPERATOR_APPROVAL", rollback_res["last_resort_recovery_command"])
        self.assertGreater(len(rollback_res["routine_rollback_commands"]), 2)
        self.assertGreater(len(rollback_res["preconditions"]), 1)

        # Confirm file still exists (zero destructive actions executed)
        post_exists = os.path.exists("/data/data/com.termux/files/home/aeonix-prism/core/aadya_activation.py")
        self.assertTrue(post_exists)

    # -------------------------------------------------------------------------
    # 11. In-Memory Operator Handoff Report Synthesis and Digest
    # -------------------------------------------------------------------------
    def test_operator_handoff_report_in_memory_and_digest(self):
        report = self.aadya.generate_operator_handoff_report()
        self.assertIn("handoff_id", report)
        self.assertIn("report_digest", report)
        self.assertIn(report["verdict"], ["READY_FOR_OPERATOR_ACTIVATION", "DEGRADED_OPERATOR_REVIEW_REQUIRED", "ACTIVATION_HALTED"])
        self.assertTrue(report["handoff_id"].startswith("handoff_"))
        self.assertEqual(len(report["report_digest"]), 64)
        self.assertEqual(report["base_commit"], "05e2771")

        # In-memory return invariant: report must NOT be auto-inserted into database
        rows = query_db(
            "SELECT COUNT(*) FROM audit_log WHERE action = 'OPERATOR_HANDOFF_REPORT_RECORDED' AND target = ?;",
            (report["handoff_id"],),
            db_path=self.db_path
        )
        self.assertEqual(rows[0][0], 0)

    # -------------------------------------------------------------------------
    # 12. Handoff Report Persistence Strictly Requires Operator Approval Gate
    # -------------------------------------------------------------------------
    def test_operator_handoff_report_persistence_requires_approval(self):
        report = self.aadya.generate_operator_handoff_report()

        # Without approval -> raises ValueError
        with self.assertRaises(ValueError):
            self.aadya.persist_operator_handoff_report(report, operator_approved=False)

        # With approval -> succeeds
        persisted = self.aadya.persist_operator_handoff_report(report, operator_approved=True)
        self.assertTrue(persisted["persisted"])
        self.assertEqual(persisted["handoff_id"], report["handoff_id"])

        # Confirms audit log recorded the handoff
        rows = query_db(
            "SELECT COUNT(*) FROM audit_log WHERE action = 'OPERATOR_HANDOFF_REPORT_RECORDED' AND target = ?;",
            (report["handoff_id"],),
            db_path=self.db_path
        )
        self.assertEqual(rows[0][0], 1)

    # -------------------------------------------------------------------------
    # 13. Permanent Financial Quarantine in Activation Smoke
    # -------------------------------------------------------------------------
    def test_permanent_financial_quarantine_in_activation_smoke(self):
        fin_smoke = self.aadya.validate_runtime_smoke_pipeline("transfer funds to external wallet")
        self.assertTrue(fin_smoke["success"])
        self.assertEqual(fin_smoke["intent"], "FINANCIAL_BLOCKED")

        # Zero tasks or missions created from financial input
        m_rows = query_db("SELECT COUNT(*) FROM aadya_missions WHERE objective LIKE '%transfer%';", db_path=self.db_path)
        self.assertEqual(m_rows[0][0], 0)

    # -------------------------------------------------------------------------
    # 14. Sensitive Credential and Path Stripping on Handoff Surfaces
    # -------------------------------------------------------------------------
    def test_sensitive_credential_stripping_on_handoff_surfaces(self):
        report = self.aadya.generate_operator_handoff_report()
        dashboard = self.aadya.render_operator_readiness_dashboard()

        for payload in [report, dashboard]:
            serialized = json.dumps(payload)
            self.assertNotIn("password", serialized.lower())
            self.assertNotIn("secret_key", serialized.lower())
            self.assertNotIn("master_secret", serialized.lower())
            self.assertNotIn("/data/data/com.termux/files", serialized)

    # -------------------------------------------------------------------------
    # 15. Preservation of All Existing Stages and Backward Compatibility
    # -------------------------------------------------------------------------
    def test_preservation_of_all_existing_stages_and_degraded_handling(self):
        # Stage 1: Crown-0 betterment evaluation
        prio = self.aadya.evaluate_priority("Evaluate activation readiness", "operational")
        self.assertIn("aadi_betterment_score", prio)

        # Stage 2: Memory node registration
        mem = self.aadya.add_memory_node(
            title="Stage 10 Verified",
            content="Controlled activation handoff nominal",
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
        intent = self.aadya.classify_voice_intent("give me a system status update")
        self.assertEqual(intent.get("intent"), "SYSTEM_HEALTH_QUERY")

        # Stage 7: Operational readiness evaluation
        readiness = self.aadya.evaluate_operational_readiness()
        self.assertIn(readiness.get("overall_status"), ["NOMINAL", "ALL_SYSTEMS_NOMINAL", "DEGRADED"])

        # Stage 8: Deployment manifest generation
        manifest = self.aadya.generate_deployment_manifest()
        self.assertIn("manifest_version", manifest)

        # Stage 9: Operator readiness report generation
        op_rep = self.aadya.generate_operator_readiness_report()
        self.assertIn("report_id", op_rep)

        # Stage 10: Activation checklist evaluation
        chk = self.aadya.generate_operator_activation_checklist()
        self.assertIn("checklist_id", chk)


if __name__ == "__main__":
    unittest.main()
