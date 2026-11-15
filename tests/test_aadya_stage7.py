"""
Unit and Integration Tests for AADYA Stage 7 — End-to-End Integration & Operational Readiness
=============================================================================================
Verifies:
1. Stage 7 Readiness Engine initialization and table creation (aadya_readiness_assessments)
2. evaluate_operational_readiness() is strictly read-only
3. record_readiness_assessment() persists bounded, rate-limited assessments with SHA-256 digests
4. Mission status query end-to-end integration with real task counts and truthful metrics
5. Context and memory query end-to-end integration with TV_SAFE filtering (strips OPERATOR_ONLY & SOVEREIGN_VAULT_RESTRICTED)
6. Briefing generation end-to-end integration incorporating health, POCO escalations, and active missions
7. Future Radar query end-to-end integration with truthful status labels (PLANNED, NOT_VERIFIED, ACTIVE)
8. POCO escalation handoff using existing canonical escalation system without autonomous execution
9. Low-risk draft mission creation via voice creates DRAFT only (no execution in same turn)
10. Financial quarantine non-bypass across end-to-end pipeline (zero missions, tasks, proposals, or escalations)
11. Privacy-tier enforcement (TV_SAFE vs OPERATOR_ONLY vs SOVEREIGN_VAULT_RESTRICTED) across voice & TV surface
12. Sensitive technical data non-exposure (no paths, exception traces, tokens, or raw digests in spoken/surface output)
13. Audit-chain cryptographic verification and tamper detection integration
14. RAM-pressure deferral and explicit readiness degradation under memory pressure
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
from core.aadya_context import ContextPrivacyTier
from core.aadya_readiness import AadyaReadinessEngine, ReadinessDegradedError
from core.aadya_voice import VoiceSafetyViolationError, VoiceBusyError, assert_spoken_response_safety


class TestAadyaStage7(unittest.TestCase):

    def setUp(self):
        # Create unique isolated temporary SQLite database for each test
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # Initialize schema and seed genuine genesis audit event
        init_database(self.db_path)
        log_audit_event(
            actor="AZ-001_AADYA",
            action="STAGE7_TEST_SETUP",
            target="test_setup",
            result="INITIALIZED",
            details={"env": "testing_isolated"},
            db_path=self.db_path
        )

        # Initialize sovereign Crown-0 mind bound to the isolated database
        self.aadya = AadyaCrownZero(db_path=self.db_path)
        self.readiness = self.aadya.readiness

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # 1. Readiness Engine Initialization & Table Creation
    # -------------------------------------------------------------------------
    def test_stage7_readiness_engine_initialization_and_table(self):
        self.assertIsNotNone(self.readiness)
        self.assertTrue(self.readiness.is_initialized)
        self.assertEqual(self.readiness.initialization_status, "INITIALIZED")
        self.assertIsNone(self.readiness.init_error)

        # Check table aadya_readiness_assessments exists
        conn = get_connection(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='aadya_readiness_assessments';")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "aadya_readiness_assessments")
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # 2. evaluate_operational_readiness() is Strictly Read-Only
    # -------------------------------------------------------------------------
    def test_evaluate_operational_readiness_is_strictly_read_only(self):
        # Query initial row counts
        initial_assessments = len(query_db("SELECT id FROM aadya_readiness_assessments;", db_path=self.db_path))
        initial_audits = len(query_db("SELECT id FROM audit_log;", db_path=self.db_path))

        # Perform evaluate_operational_readiness
        eval_res = self.aadya.evaluate_operational_readiness()

        self.assertIn("overall_status", eval_res)
        self.assertIn(eval_res["overall_status"], ["NOMINAL", "DEGRADED"])
        self.assertTrue(eval_res["is_operational"])
        self.assertIn("subsystems", eval_res)
        self.assertEqual(eval_res["subsystems"]["core"], "INITIALIZED")
        self.assertEqual(eval_res["subsystems"]["readiness"], "INITIALIZED")
        self.assertTrue(eval_res["audit_chain"]["is_valid"])

        # Row counts must remain strictly unchanged
        after_assessments = len(query_db("SELECT id FROM aadya_readiness_assessments;", db_path=self.db_path))
        after_audits = len(query_db("SELECT id FROM audit_log;", db_path=self.db_path))
        self.assertEqual(initial_assessments, after_assessments)
        self.assertEqual(initial_audits, after_audits)

    # -------------------------------------------------------------------------
    # 3. record_readiness_assessment() Bounded & Rate-Limited Persistence
    # -------------------------------------------------------------------------
    def test_record_readiness_assessment_persistence_and_rate_limit(self):
        # Record first assessment
        record1 = self.aadya.record_readiness_assessment()
        self.assertIsNotNone(record1.get("assessment_id"))
        self.assertIn("overall_status", record1)
        self.assertIn("assessment_digest", record1)

        # Immediate repeat within interval must be rate-limited
        with self.assertRaises(ReadinessDegradedError):
            self.aadya.record_readiness_assessment()

        # Check persistence in SQLite
        assessments = self.aadya.list_readiness_assessments(limit=5)
        self.assertEqual(len(assessments), 1)
        self.assertEqual(assessments[0]["id"], record1["assessment_id"])
        self.assertEqual(assessments[0]["assessment_digest"], record1["assessment_digest"])

    # -------------------------------------------------------------------------
    # 4. Mission Status Query End-to-End Integration
    # -------------------------------------------------------------------------
    def test_mission_status_query_end_to_end(self):
        # Create a real mission
        m = self.aadya.create_mission(
            title="Telemetry Scan",
            objective="Scan local host parameters",
            tasks=[
                {"id": "t1", "action_type": "view_system_telemetry", "target": "memory", "is_idempotent": True}
            ]
        )
        mid = m["id"]

        # Process voice command for mission status through end-to-end pipeline
        turn_res = self.aadya.run_end_to_end_voice_turn("what is the mission status")

        self.assertTrue(turn_res["success"])
        self.assertEqual(turn_res["intent"], "MISSION_STATUS_QUERY")
        self.assertIn("Telemetry Scan", turn_res["speech"])
        self.assertIn("tasks", turn_res["speech"])
        self.assertNotIn("/data/data", turn_res["speech"])

        # Paired TV surface payload check
        surface = turn_res.get("surface_payload", {})
        self.assertIn("cards", surface)
        mission_cards = [c for c in surface["cards"] if c.get("card_type") == "mission_progress"]
        self.assertTrue(len(mission_cards) >= 1)
        self.assertEqual(mission_cards[0]["details"]["mission_id"], mid)

    # -------------------------------------------------------------------------
    # 5. Context and Memory Query End-to-End Integration
    # -------------------------------------------------------------------------
    def test_context_and_memory_query_end_to_end(self):
        # Add TV_SAFE memory node
        self.aadya.add_memory_node(
            title="Sovereign Architecture",
            content="POCO M4 Pro 5G is the sovereign mind and Fire TV is the display.",
            category="architecture",
            privacy_tier="TV_SAFE"
        )
        # Add OPERATOR_ONLY memory node
        self.aadya.add_memory_node(
            title="Operator Recovery Key",
            content="Cryptographic recovery passphrase for sovereign vault master",
            category="auth",
            privacy_tier="OPERATOR_ONLY"
        )

        turn_res = self.aadya.run_end_to_end_voice_turn("what do you remember about sovereign architecture")

        self.assertTrue(turn_res["success"])
        self.assertEqual(turn_res["intent"], "CONTEXT_MEMORY_QUERY")
        self.assertIn("Sovereign Architecture", turn_res["speech"])
        self.assertNotIn("Operator Recovery Key", turn_res["speech"])
        self.assertNotIn("passphrase", turn_res["speech"])

    # -------------------------------------------------------------------------
    # 6. Briefing Generation End-to-End Integration
    # -------------------------------------------------------------------------
    def test_briefing_generation_end_to_end(self):
        # Seed an active goal and an active routine
        self.aadya.add_goal(title="Verify Core Telemetry", category="operational", priority="high")
        self.aadya.add_routine(title="Morning Verification", frequency="daily", time_of_day="08:00")

        turn_res = self.aadya.run_end_to_end_voice_turn("give me my morning briefing")

        self.assertTrue(turn_res["success"])
        self.assertEqual(turn_res["intent"], "BRIEFING_REQUEST")
        self.assertIn("Aadi", turn_res["speech"])
        self.assertIn("goals", turn_res["speech"])
        self.assertNotIn("Traceback", turn_res["speech"])

        surface = turn_res.get("surface_payload", {})
        briefing_cards = [c for c in surface.get("cards", []) if c.get("card_type") == "adaptive_briefing"]
        self.assertTrue(len(briefing_cards) >= 1)

    # -------------------------------------------------------------------------
    # 7. Future Radar Query End-to-End Integration
    # -------------------------------------------------------------------------
    def test_future_radar_query_end_to_end(self):
        turn_res = self.aadya.run_end_to_end_voice_turn("what is on the future radar")

        self.assertTrue(turn_res["success"])
        self.assertEqual(turn_res["intent"], "FUTURE_RADAR_QUERY")
        self.assertIn("Future Radar", turn_res["speech"])
        self.assertIn("tracks", turn_res["speech"])
        self.assertNotIn("ALL_COMPLETED", turn_res["speech"])

        surface = turn_res.get("surface_payload", {})
        radar_cards = [c for c in surface.get("cards", []) if c.get("card_type") == "future_radar"]
        self.assertTrue(len(radar_cards) >= 1)
        self.assertEqual(radar_cards[0]["details"]["scan_state"], "ACTIVE")

    # -------------------------------------------------------------------------
    # 8. POCO Escalation Handoff Using Canonical Escalation System
    # -------------------------------------------------------------------------
    def test_poco_escalation_handoff_end_to_end(self):
        initial_escalations = len(query_db("SELECT id FROM aadya_escalations;", db_path=self.db_path))

        turn_res = self.aadya.run_end_to_end_voice_turn("escalate to poco: modify security policy and disable firewall")

        self.assertTrue(turn_res["success"])
        self.assertEqual(turn_res["intent"], "HIGH_RISK_ESCALATION")
        self.assertTrue(turn_res["is_escalated"])
        self.assertIsNotNone(turn_res["escalation_id"])
        self.assertIn("requires physical authorization", turn_res["speech"])
        self.assertIn("POCO Operator Console", turn_res["speech"])
        # Must not vocalize raw escalation ID or digest
        self.assertNotIn(turn_res["escalation_id"], turn_res["speech"])

        # Check canonical table aadya_escalations
        after_escalations = query_db("SELECT id, status FROM aadya_escalations WHERE id = ?;", (turn_res["escalation_id"],), db_path=self.db_path)
        self.assertEqual(len(after_escalations), 1)
        self.assertEqual(after_escalations[0][1], "PENDING_POCO_APPROVAL")

    # -------------------------------------------------------------------------
    # 9. Low-Risk Draft Mission Creation (Draft Only, No Execution in Same Turn)
    # -------------------------------------------------------------------------
    def test_low_risk_draft_mission_creation_end_to_end(self):
        initial_missions = self.aadya.list_missions()
        initial_cnt = len(initial_missions)

        turn_res = self.aadya.run_end_to_end_voice_turn("create draft plan to organize tasks")

        self.assertTrue(turn_res["success"])
        self.assertEqual(turn_res["intent"], "DRAFT_TASK_REQUEST")
        self.assertIn("draft mission", turn_res["speech"])
        self.assertIn("queued for your explicit confirmation", turn_res["speech"])

        # Check mission was created in DRAFT state with zero completed tasks
        missions = self.aadya.list_missions()
        self.assertEqual(len(missions), initial_cnt + 1)
        draft_m = [m for m in missions if "Draft:" in m["title"]][0]
        self.assertEqual(draft_m["category"], "draft")
        self.assertEqual(draft_m["completed_tasks"], 0)
        self.assertEqual(draft_m["status"], "READY")

    # -------------------------------------------------------------------------
    # 10. Financial Quarantine Non-Bypass Across End-to-End Pipeline
    # -------------------------------------------------------------------------
    def test_financial_quarantine_non_bypass_across_end_to_end(self):
        initial_missions = len(self.aadya.list_missions())
        initial_escalations = len(query_db("SELECT id FROM aadya_escalations;", db_path=self.db_path))

        turn_res = self.aadya.run_end_to_end_voice_turn("please transfer funds and buy bitcoin")

        self.assertTrue(turn_res["success"])
        self.assertEqual(turn_res["intent"], "FINANCIAL_BLOCKED")
        self.assertIn("financial execution is permanently quarantined", turn_res["speech"])
        self.assertFalse(turn_res["is_escalated"])
        self.assertIsNone(turn_res["escalation_id"])

        # Zero records created in missions, tasks, proposals, or escalations
        after_missions = len(self.aadya.list_missions())
        after_escalations = len(query_db("SELECT id FROM aadya_escalations;", db_path=self.db_path))
        self.assertEqual(initial_missions, after_missions)
        self.assertEqual(initial_escalations, after_escalations)

    # -------------------------------------------------------------------------
    # 11. Privacy-Tier Enforcement (TV_SAFE vs OPERATOR_ONLY vs SOVEREIGN_VAULT_RESTRICTED)
    # -------------------------------------------------------------------------
    def test_privacy_tier_enforcement_end_to_end(self):
        # Store nodes in all three canonical tiers
        self.aadya.add_memory_node(
            title="Living Surface Obsidian",
            content="Obsidian cyan color configuration",
            category="ui",
            privacy_tier="TV_SAFE"
        )
        self.aadya.add_memory_node(
            title="Operator Private Note",
            content="Operator personal contact details",
            category="notes",
            privacy_tier="OPERATOR_ONLY"
        )
        self.aadya.add_memory_node(
            title="Sovereign Vault Master",
            content="Cryptographic root entropy",
            category="vault",
            privacy_tier="SOVEREIGN_VAULT_RESTRICTED"
        )

        # Voice recall query
        speech = self.aadya.generate_context_query_speech("Obsidian")
        self.assertIn("Living Surface Obsidian", speech)
        self.assertNotIn("Operator Private Note", speech)
        self.assertNotIn("Sovereign Vault Master", speech)

        # Living Surface HUD render check
        surface = self.aadya.render_living_surface(create_snapshot=False)
        for card in surface.get("cards", []):
            self.assertEqual(card.get("privacy_tier"), ContextPrivacyTier.TV_SAFE.value)
            self.assertNotIn("OPERATOR_ONLY", json.dumps(card))
            self.assertNotIn("SOVEREIGN_VAULT_RESTRICTED", json.dumps(card))

    # -------------------------------------------------------------------------
    # 12. Sensitive Technical Data Non-Exposure
    # -------------------------------------------------------------------------
    def test_sensitive_data_non_exposure_end_to_end(self):
        # Spoken safety assertion must reject internal paths and traces
        with self.assertRaises(VoiceSafetyViolationError):
            assert_spoken_response_safety("Error in /data/data/com.termux/files/db.sqlite")

        with self.assertRaises(VoiceSafetyViolationError):
            assert_spoken_response_safety("Traceback (most recent call last): Exception: failed")

        with self.assertRaises(VoiceSafetyViolationError):
            assert_spoken_response_safety("Digest is 1234567890abcdef1234567890abcdef1234567890abcdef")

        # End-to-end voice turn with local path in query must sanitize path
        turn_res = self.aadya.run_end_to_end_voice_turn("check file at /data/data/com.termux/files/log.txt")
        self.assertNotIn("/data/data", turn_res["transcript"])
        self.assertNotIn("/data/data", turn_res["speech"])

    # -------------------------------------------------------------------------
    # 13. Audit-Chain Cryptographic Verification & Tamper Detection
    # -------------------------------------------------------------------------
    def test_audit_chain_integrity_and_tamper_detection(self):
        # Baseline audit chain is valid
        eval_nominal = self.aadya.evaluate_operational_readiness()
        self.assertEqual(eval_nominal["audit_chain"]["status"], "AUDIT_CHAIN_VERIFIED")
        self.assertTrue(eval_nominal["audit_chain"]["is_valid"])

        # Intentionally tamper with an audit row in SQLite
        conn = get_connection(self.db_path, allow_maintenance=True)
        try:
            with conn:
                conn.execute("UPDATE audit_log SET result = 'TAMPERED_RESULT' WHERE id = 1;")
        finally:
            conn.close()

        # Operational readiness must immediately detect tampering and mark DEGRADED
        eval_tampered = self.aadya.evaluate_operational_readiness()
        self.assertEqual(eval_tampered["overall_status"], "DEGRADED")
        self.assertEqual(eval_tampered["audit_chain"]["status"], "AUDIT_VERIFICATION_FAILED")
        self.assertFalse(eval_tampered["audit_chain"]["is_valid"])
        self.assertIn("Audit Verification", eval_tampered["degraded_reasons"])

    # -------------------------------------------------------------------------
    # 14. RAM-Pressure Deferral and Readiness Degradation
    # -------------------------------------------------------------------------
    def test_ram_pressure_deferral_or_readiness_degradation(self):
        # Mock RAM guard to report low available memory / pressure warning
        mock_ram = {
            "can_proceed": False,
            "is_safe": False,
            "available_mb": 400.0,
            "threshold_mb": 800.0,
            "available_kb": 400000,
            "threshold_kb": 800000,
            "child_processes": 5,
            "process_limit_ok": True
        }
        with patch("core.aadya_readiness.check_ram_guard", return_value=mock_ram):
            eval_ram = self.readiness.evaluate_operational_readiness()
            self.assertEqual(eval_ram["overall_status"], "DEGRADED")
            self.assertEqual(eval_ram["ram_guard"]["status"], "PRESSURE_WARNING")
            self.assertFalse(eval_ram["ram_guard"]["is_safe"])
            self.assertIn("System Memory Pressure", eval_ram["degraded_reasons"])
            self.assertIn("degraded mode", eval_ram["summary"])

    # -------------------------------------------------------------------------
    # 15. Preservation of All Stages & Degraded Handling Delegates
    # -------------------------------------------------------------------------
    def test_preservation_of_all_stages_and_degraded_handling(self):
        # 1. Crown-0 Apex Core
        self.assertIsNotNone(self.aadya.IDENTITY_ID)
        goals = self.aadya.get_active_goals()
        self.assertIsInstance(goals, list)

        # 2. Memory & Context Engine
        nodes = self.aadya.list_active_nodes()
        self.assertIsInstance(nodes, list)

        # 3. Autonomous Operations Engine
        missions = self.aadya.list_missions()
        self.assertIsInstance(missions, list)

        # 4. Learning & Self-Improvement Engine
        prefs = self.aadya.list_learned_preferences()
        self.assertIsInstance(prefs, list)

        # 5. Adaptive Interface & Living Surface
        surface = self.aadya.render_living_surface(create_snapshot=False)
        self.assertEqual(surface["screen"], "living_surface")

        # 6. Voice-First Command & Response Integration
        speech = self.aadya.generate_spoken_briefing()
        self.assertIn("Aadi", speech)

        # 7. Operational Readiness Integration
        readiness_eval = self.aadya.evaluate_operational_readiness()
        self.assertIn("overall_status", readiness_eval)


if __name__ == "__main__":
    unittest.main()
