"""
AADYA Stage 4 — Learning, Reflection & Self-Improvement Test Suite
Tests post-mission reflections, operator feedback, truthful outcome analysis,
allowlisted preference adaptation, bounded confidence calibration, correlation-only pattern detection,
deduplicated improvement proposals, POCO-gated adoption, sensitive-data sanitization,
and strict non-bypass of safety invariants and financial quarantine.
"""

import os
import time
import json
import sqlite3
import tempfile
import unittest

from core.aadya import AadyaCrownZero, FinancialQuarantineViolationError
from core.aadya_learning import (
    AadyaLearningEngine,
    SecurityViolationError,
    CONFIDENCE_CEILING,
    CONFIDENCE_FLOOR,
    ALLOWED_PREFERENCE_DOMAINS
)
from core.db import get_connection, verify_audit_chain, init_database


class TestAadyaStage4Learning(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "aadya_stage4_test.db")
        init_database(self.db_path)
        self.aadya = AadyaCrownZero(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Mission Reflection Creation & Persistence
    # -------------------------------------------------------------------------
    def test_reflection_creation_and_persistence(self):
        refl = self.aadya.record_mission_reflection(
            mission_id="mission_101",
            outcome_status="SUCCESS",
            notes="Telemetry inspection completed with zero latency anomalies.",
            lessons=["Cache warming reduces step latency", "Memory stayed under 500MB"],
            patterns=["Stable morning network profile"],
            duration_sec=3.2
        )

        self.assertIsNotNone(refl)
        self.assertEqual(refl["outcome_status"], "SUCCESS")
        self.assertEqual(len(refl["reflection_digest"]), 64)

        # Retrieve and verify persistence
        retrieved = self.aadya.get_mission_reflection(refl["reflection_id"])
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["mission_id"], "mission_101")
        self.assertEqual(len(retrieved["lessons"]), 2)
        self.assertEqual(retrieved["lessons"][0], "Cache warming reduces step latency")

    # -------------------------------------------------------------------------
    # 2. Operator Feedback Capture & Aggregation
    # -------------------------------------------------------------------------
    def test_operator_feedback_capture_and_aggregation(self):
        # Valid positive feedback
        fb1 = self.aadya.record_operator_feedback(
            target_type="MISSION",
            target_id="mission_101",
            rating=1,
            feedback_text="Execution was crisp and on point."
        )
        self.assertEqual(fb1["rating"], 1)
        self.assertEqual(len(fb1["feedback_digest"]), 64)

        # Valid negative feedback
        fb2 = self.aadya.record_operator_feedback(
            target_type="RADAR",
            target_id="signal_radar_4",
            rating=-1,
            feedback_text="False alarm on storage exhaustion."
        )
        self.assertEqual(fb2["rating"], -1)

        # Query feedback
        feedbacks = self.aadya.list_operator_feedback()
        self.assertEqual(len(feedbacks), 2)

        # Invalid rating rejected
        with self.assertRaises(ValueError):
            self.aadya.record_operator_feedback(target_type="MISSION", target_id="m1", rating=5)

        # Invalid target type rejected
        with self.assertRaises(ValueError):
            self.aadya.record_operator_feedback(target_type="ILLEGAL_TARGET", target_id="m1", rating=1)

    # -------------------------------------------------------------------------
    # 3. Truthful Outcome Analysis
    # -------------------------------------------------------------------------
    def test_outcome_analysis_calculates_truthful_metrics(self):
        # Empty state analysis
        empty_analysis = self.aadya.analyze_recent_outcomes()
        self.assertEqual(empty_analysis["total_missions_analyzed"], 0)
        self.assertEqual(empty_analysis["overall_success_rate"], 0.0)

        # Create mock missions in DB
        conn = get_connection(self.db_path, allow_maintenance=True)
        now = time.time()
        with conn:
            conn.execute("""
                INSERT INTO aadya_missions (id, title, objective, actor, status, plan_digest, total_tasks, completed_tasks, failed_tasks, created_at, updated_at)
                VALUES ('m1', 'M1', 'Obj1', 'Aadi', 'COMPLETED', 'dig1', 2, 2, 0, ?, ?);
            """, (now, now))
            conn.execute("""
                INSERT INTO aadya_missions (id, title, objective, actor, status, plan_digest, total_tasks, completed_tasks, failed_tasks, created_at, updated_at)
                VALUES ('m2', 'M2', 'Obj2', 'Aadi', 'FAILED', 'dig2', 2, 1, 1, ?, ?);
            """, (now, now))
        conn.close()

        analysis = self.aadya.analyze_recent_outcomes()
        self.assertEqual(analysis["total_missions_analyzed"], 2)
        self.assertEqual(analysis["completed_missions"], 1)
        self.assertEqual(analysis["failed_missions"], 1)
        self.assertEqual(analysis["overall_success_rate"], 50.0)
        self.assertEqual(analysis["total_tasks_scheduled"], 4)
        self.assertEqual(analysis["total_tasks_completed"], 3)
        self.assertEqual(analysis["total_tasks_failed"], 1)

    # -------------------------------------------------------------------------
    # 4. Allowlisted Preference Adaptation (Corrections 14 & 15)
    # -------------------------------------------------------------------------
    def test_preference_adaptation_within_allowlist(self):
        # Valid domain & key
        pref = self.aadya.adapt_preference(
            domain="ui_display",
            key="refresh_interval_sec",
            value=15
        )
        self.assertIsNotNone(pref)
        self.assertEqual(pref["domain"], "ui_display")
        self.assertEqual(pref["preference_key"], "refresh_interval_sec")
        self.assertEqual(pref["value"], 15)
        self.assertEqual(pref["evidence_count"], 1)

        # Update existing preference
        pref_updated = self.aadya.adapt_preference(
            domain="ui_display",
            key="refresh_interval_sec",
            value=20,
            feedback_weight=1.5
        )
        self.assertEqual(pref_updated["value"], 20)
        self.assertEqual(pref_updated["evidence_count"], 2)
        self.assertLessEqual(pref_updated["confidence"], CONFIDENCE_CEILING)

    def test_disallowed_preference_domain_and_key_rejected(self):
        # Disallowed domain
        with self.assertRaises(ValueError) as ctx:
            self.aadya.adapt_preference(domain="security_rules", key="bypass_auth", value=True)
        self.assertIn("DISALLOWED_PREFERENCE_DOMAIN", str(ctx.exception))

        # Disallowed key in valid domain
        with self.assertRaises(ValueError) as ctx:
            self.aadya.adapt_preference(domain="ui_display", key="arbitrary_unlisted_key", value="bad")
        self.assertIn("DISALLOWED_PREFERENCE_KEY", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 5. Bounded Confidence Calibration (Corrections 1, 2 & 3)
    # -------------------------------------------------------------------------
    def test_confidence_calibration_bounds_and_conservative_ceiling(self):
        # Calibration never exceeds CONFIDENCE_CEILING (0.85)
        calib = self.aadya.calibrate_confidence(
            domain="telemetry_prediction",
            predicted_confidence=0.95,  # Input over ceiling
            actual_success=True
        )

        self.assertLessEqual(calib["calibrated_confidence"], CONFIDENCE_CEILING)
        self.assertGreaterEqual(calib["calibrated_confidence"], CONFIDENCE_FLOOR)
        self.assertEqual(calib["confidence_type"], "HEURISTIC")
        self.assertIn("brier_score", calib)

        # Overconfidence failure damps confidence downward
        calib_fail = self.aadya.calibrate_confidence(
            domain="telemetry_prediction",
            predicted_confidence=0.80,
            actual_success=False
        )
        self.assertLess(calib_fail["calibrated_confidence"], 0.80)
        self.assertEqual(calib_fail["confidence_type"], "HEURISTIC")

    # -------------------------------------------------------------------------
    # 6. Correlation-Only Latent Pattern Detection (Corrections 10 & 11)
    # -------------------------------------------------------------------------
    def test_pattern_detection_reports_correlations_only(self):
        patterns = self.aadya.detect_operational_patterns()
        self.assertFalse(patterns["claims_causation"], "Must never claim causation")
        self.assertIn("causal_disclaimer", patterns)
        self.assertIn("Correlation does not imply causation", patterns["causal_disclaimer"])
        self.assertIn("observed_correlations", patterns)

    # -------------------------------------------------------------------------
    # 7. Deduplicated & Rate-Limited Improvement Proposals (Corrections 12 & 13)
    # -------------------------------------------------------------------------
    def test_improvement_proposal_creation_and_deduplication(self):
        prop1 = self.aadya.propose_improvement(
            title="Increase Briefing Refresh Window",
            subsystem="routine_timing",
            proposal_type="PREFERENCE_TUNING",
            justification="Reduces polling overhead during idle hours.",
            payload={"domain": "routine_timing", "key": "morning_briefing_hour", "value": 8}
        )

        self.assertEqual(prop1["status"], "PENDING_POCO_APPROVAL")
        self.assertIsNotNone(prop1["proposal_digest"])

        # Identical proposal must be deduplicated
        prop2 = self.aadya.propose_improvement(
            title="Increase Briefing Refresh Window",
            subsystem="routine_timing",
            proposal_type="PREFERENCE_TUNING",
            justification="Reduces polling overhead during idle hours.",
            payload={"domain": "routine_timing", "key": "morning_briefing_hour", "value": 8}
        )
        self.assertTrue(prop2.get("deduplicated", False))
        self.assertEqual(prop1["id"], prop2["proposal_id"])

    # -------------------------------------------------------------------------
    # 8. POCO-Gated Proposal Adoption (Corrections 4, 5 & 7)
    # -------------------------------------------------------------------------
    def test_improvement_proposal_poco_gated_adoption(self):
        prop = self.aadya.propose_improvement(
            title="Tune UI Refresh Interval",
            subsystem="ui_display",
            proposal_type="PREFERENCE_TUNING",
            justification="Set refresh to 30s based on operator telemetry pattern.",
            payload={"domain": "ui_display", "key": "refresh_interval_sec", "value": 30}
        )
        pid = prop["id"]

        # Adoption fails with short/invalid token
        with self.assertRaises(PermissionError):
            self.aadya.adopt_improvement_proposal(
                proposal_id=pid,
                verification_token="short_token",
                nonce="nonce_test_stage4_1"
            )

        # Adoption succeeds with valid 16+ char POCO token and nonce
        adopt_res = self.aadya.adopt_improvement_proposal(
            proposal_id=pid,
            verification_token="SOVEREIGN_POCO_ROOT_TOKEN_2026",
            nonce="nonce_test_stage4_valid",
            approver="Aadi"
        )
        self.assertTrue(adopt_res["success"])
        self.assertEqual(adopt_res["status"], "APPLIED")

        # Verify configuration/preference was actually updated
        updated_pref = self.aadya.get_learned_preference("ui_display", "refresh_interval_sec")
        self.assertIsNotNone(updated_pref)
        self.assertEqual(updated_pref["value"], 30)

    # -------------------------------------------------------------------------
    # 9. Proposal Rejection Lifecycle
    # -------------------------------------------------------------------------
    def test_improvement_proposal_rejection(self):
        prop = self.aadya.propose_improvement(
            title="Test Proposal",
            subsystem="ui_display",
            proposal_type="PREFERENCE_TUNING",
            justification="Testing rejection",
            payload={"domain": "ui_display", "key": "compact_view", "value": True}
        )
        pid = prop["id"]

        rej = self.aadya.reject_improvement_proposal(pid, reason="Operator declined change")
        self.assertTrue(rej["success"])
        self.assertEqual(rej["status"], "REJECTED")

        p_state = self.aadya.get_improvement_proposal(pid)
        self.assertEqual(p_state["status"], "REJECTED")

    # -------------------------------------------------------------------------
    # 10. Security Boundary: Blocks Safety-Modifying Proposals (Correction 6)
    # -------------------------------------------------------------------------
    def test_security_violation_blocks_safety_modifying_proposals(self):
        # Attempt proposal targeting safety rules
        with self.assertRaises(SecurityViolationError):
            self.aadya.propose_improvement(
                title="Bypass Sentinel Safety Rules",
                subsystem="safety_rules",
                proposal_type="PARAM_ADAPTATION",
                justification="Unsafe test proposal",
                payload={"disable_sentinel": True}
            )

        # Attempt proposal targeting financial quarantine
        with self.assertRaises(SecurityViolationError):
            self.aadya.propose_improvement(
                title="Modify Financial Quarantine",
                subsystem="financial_quarantine",
                proposal_type="PARAM_ADAPTATION",
                justification="Unsafe financial bypass",
                payload={"allow_transfers": True}
            )

    # -------------------------------------------------------------------------
    # 11. Financial Quarantine Non-Bypass (Correction 16)
    # -------------------------------------------------------------------------
    def test_financial_quarantine_enforced_across_learning(self):
        # Reflection containing financial execution verb blocked
        with self.assertRaises(FinancialQuarantineViolationError):
            self.aadya.record_mission_reflection(
                mission_id="m1",
                outcome_status="SUCCESS",
                notes="Initiated transfer of 500 dollars to external address"
            )

        # Proposal payload containing financial execution blocked
        with self.assertRaises(FinancialQuarantineViolationError):
            self.aadya.propose_improvement(
                title="Auto payment routine",
                subsystem="routine_timing",
                proposal_type="PREFERENCE_TUNING",
                justification="Auto pay bill",
                payload={"domain": "routine_timing", "key": "pay_account", "value": 100}
            )

    # -------------------------------------------------------------------------
    # 12. Sensitive Data Sanitization (Corrections 8 & 9)
    # -------------------------------------------------------------------------
    def test_sensitive_data_sanitization_in_reflections_and_feedback(self):
        refl = self.aadya.record_mission_reflection(
            mission_id="m_sec",
            outcome_status="SUCCESS",
            notes="Observed auth token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret and password='my_vault_password_123'"
        )

        self.assertNotIn("eyJhbGci", refl["notes"])
        self.assertNotIn("my_vault_password_123", refl["notes"])
        self.assertIn("[REDACTED", refl["notes"])

        # Check in DB
        db_refl = self.aadya.get_mission_reflection(refl["reflection_id"])
        self.assertNotIn("my_vault_password_123", db_refl["notes"])

    # -------------------------------------------------------------------------
    # 13. Engine Degraded State Handling
    # -------------------------------------------------------------------------
    def test_learning_engine_degraded_state(self):
        bad_aadya = AadyaCrownZero(db_path="/proc/read_only_fake/bad.db")
        self.assertEqual(bad_aadya.learning_initialization_status, "INITIALIZATION_FAILED")

        with self.assertRaises(RuntimeError) as ctx:
            bad_aadya.analyze_recent_outcomes()
        self.assertIn("degraded state", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 14. Audit Chain Cryptographic Integrity
    # -------------------------------------------------------------------------
    def test_audit_chain_integrity_across_stage4(self):
        # Trigger learning operations that emit audit events
        self.aadya.record_mission_reflection(
            mission_id="m_audit_1",
            outcome_status="SUCCESS",
            notes="Audit trail verification mission completed nominal."
        )
        self.aadya.record_operator_feedback(
            target_type="MISSION",
            target_id="m_audit_1",
            rating=1,
            feedback_text="Audit test feedback."
        )
        self.aadya.adapt_preference(domain="ui_display", key="theme_mode", value="dark")

        audit_res = verify_audit_chain(self.db_path)
        self.assertTrue(audit_res["is_valid"], f"Audit chain broken: {audit_res}")
        self.assertGreaterEqual(audit_res["total_events"], 3)


if __name__ == "__main__":
    unittest.main()
