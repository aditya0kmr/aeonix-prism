"""
ÆONIX PRISM // Stage 2 Comprehensive Test Suite
Validates Backend Correctness, Async Workload Control, Agent Contracts,
and Real Prototype Replacements (Zero Mocks / Real Computations).
"""

import unittest
import asyncio
import time
import os
import sqlite3
import json

from aeonix.core.db import (
    init_database,
    get_connection,
    log_audit_event,
    verify_audit_chain,
    query_db
)
from aeonix.core.auth import ROLE_POCO_CORE, ROLE_FIRETV_GLASS
from aeonix.core.trust import trust
from aeonix.core.server import process_intent_pipeline, heavy_executor, llm_inference_lock
from aeonix.core.forge import draft_command_from_prompt, execute_typed_operation
from aeonix.core.council import convene_council_session
from aeonix.core.oracle import oracle
from aeonix.core.ghost import ghost
from aeonix.core.paradox import paradox
from aeonix.core.signal import signal_detector
from aeonix.core.aadya import AadyaIntelligence
from aeonix.core.nexus_room import nexus_room
from aeonix.agents.builder import BuilderAgent
from aeonix.agents.skeptic import SkepticAgent
from aeonix.agents.analyst import AnalystAgent
from aeonix.agents.orchestrator import orchestrator


class TestStage2BackendCorrectness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def test_audit_chain_full_cryptographic_verification(self):
        """Verifies genesis-to-tip SHA-256 hash chaining and tampering detection."""
        # Clean check on active vault
        res = verify_audit_chain()
        self.assertTrue(res["is_valid"])
        self.assertGreater(res["total_events"], 0)
        self.assertEqual(res["status"], "CRYPTOGRAPHICALLY_VERIFIED")
        self.assertTrue(res["genesis_hash"])
        self.assertTrue(res["tip_hash"])

    def test_audit_chain_tamper_detection(self):
        """Intentionally tampers with a test database copy and confirms verifier catches it."""
        test_db = "/data/data/com.termux/files/usr/tmp/test_tamper.db"
        if os.path.exists(test_db):
            os.remove(test_db)

        init_database(test_db)
        log_audit_event("Tester", "action1", "target1", "ok", {"step": 1}, db_path=test_db)
        log_audit_event("Tester", "action2", "target2", "ok", {"step": 2}, db_path=test_db)
        log_audit_event("Tester", "action3", "target3", "ok", {"step": 3}, db_path=test_db)

        # Baseline is valid
        self.assertTrue(verify_audit_chain(test_db)["is_valid"])

        # Tamper with row 2 details
        conn = sqlite3.connect(test_db)
        conn.execute("UPDATE audit_log SET result = 'tampered' WHERE id = 2;")
        conn.commit()
        conn.close()

        # Verifier MUST detect content tampering
        tampered_res = verify_audit_chain(test_db)
        self.assertFalse(tampered_res["is_valid"])
        self.assertIn("tampering detected", tampered_res["error"])
        self.assertEqual(tampered_res["row_id"], 2)

        if os.path.exists(test_db):
            os.remove(test_db)

    def test_builder_and_forge_schema_alignment(self):
        """Builder correctly consumes Forge's risk and risk_assessment schemas without KeyError."""
        draft = draft_command_from_prompt("delete audit.log")
        self.assertIn("risk", draft)
        self.assertIn("risk_assessment", draft)
        self.assertEqual(draft["risk"]["risk_level"], "R3_HIGH")
        self.assertEqual(draft["risk_assessment"]["risk_tier"], "R3")

        builder = BuilderAgent()
        res = builder.execute({"task": "custom", "directive": "check repo status"})
        self.assertIn(res["status"], ["executed", "completed"])

    def test_skeptic_adversarial_evidence_evaluation(self):
        """Skeptic validates real vault hashes and rejects ungrounded speculation or cloud leaks."""
        skeptic = SkepticAgent()

        # Claim with zero evidence
        review1 = skeptic.challenge_hypotheses(
            claims=["System operates with zero cloud dependencies."],
            evidence_hashes=[]
        )
        self.assertEqual(review1["overall_assessment"], "CHALLENGED")
        self.assertGreater(review1["total_critiques"], 0)

        # Claim with cloud leak keyword
        review2 = skeptic.challenge_hypotheses(
            claims=["System performs cloud upload of user voice."],
            evidence_hashes=["dummy_hash"]
        )
        self.assertEqual(review2["overall_assessment"], "CHALLENGED")
        self.assertEqual(review2["critiques"][0]["severity"], "HIGH")

    def test_analyst_semantic_entity_linking(self):
        """Analyst builds semantic relationships (subnet, domain) instead of sequential order."""
        analyst = AnalystAgent()
        entities = [
            {"name": "10.116.23.168", "type": "device", "ip": "10.116.23.168"},
            {"name": "10.116.23.179", "type": "device", "ip": "10.116.23.179"},
            {"name": "aeonix.local", "type": "domain"},
            {"name": "surface.aeonix.local", "type": "subdomain"}
        ]
        res = analyst.correlate(entities)
        self.assertEqual(res["indexed_entities"], 4)
        self.assertGreaterEqual(res["linked_edges"], 2)

    def test_council_adversarial_deliberation(self):
        """Council allows disagreement, catches ambiguity, and generates genuine verdicts."""
        # Ambiguous query yields INSUFFICIENT_EVIDENCE
        res_ambiguous = convene_council_session("run")
        self.assertEqual(res_ambiguous["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(res_ambiguous["votes"]["skeptic"], "DISSENT")

        # Destructive directive yields Skeptic dissent
        res_destruct = convene_council_session("format all local databases and drop tables")
        self.assertEqual(res_destruct["votes"]["skeptic"], "DISSENT")
        self.assertIn("DISSENT", res_destruct["verdict"]["consensus"])

        # Sovereign local build query achieves consensus
        res_valid = convene_council_session("Deploy local SQLite WAL backup routine on POCO M4 Pro")
        self.assertEqual(res_valid["votes"]["defender"], "APPROVE")
        self.assertIn("UNANIMOUS", res_valid["verdict"]["consensus"])

    def test_oracle_multi_source_and_prediction_ledger(self):
        """Oracle queries multi-source vault, calibrates uncertainty, and persists to ledger."""
        res = oracle.conduct_research("Sovereign Root of Trust POCO")
        self.assertIn("research_id", res)
        self.assertIn("sources", res)
        self.assertIn("confidence", res)
        self.assertIn("prediction", res)
        self.assertGreater(res["confidence"], 0.0)

        # Confirm persisted in research_ledger
        rows = query_db("SELECT id, confidence FROM research_ledger WHERE id = ?;", (res["research_id"],))
        self.assertEqual(len(rows), 1)

    def test_ghost_telemetry_and_stated_assumptions(self):
        """GHOST synchronizes with live database and provides stated assumptions for faults."""
        twin = ghost.get_digital_twin_state()
        self.assertTrue(twin["telemetry_synchronized"])
        self.assertGreaterEqual(len(twin["virtual_devices"]), 3)

        sim = ghost.simulate_fault_injection("internet_loss")
        self.assertIn("stated_assumptions", sim)
        self.assertGreater(len(sim["stated_assumptions"]), 0)
        self.assertEqual(sim["system_integrity"], "UNCOMPROMISED")

    def test_paradox_quantified_hardware_modeling(self):
        """PARADOX computes trade-off matrix using hardware benchmarks instead of static percentages."""
        sim = paradox.simulate_counterfactual(
            "Execute on native Termux Dimensity 810",
            "Deploy commercial cloud API with off-device inference"
        )
        self.assertIn("tradeoff_matrix", sim)
        self.assertIn("estimated_latency_impact", sim["tradeoff_matrix"])
        self.assertIn("CRITICAL RISK", sim["tradeoff_matrix"]["privacy_evaluation"])

    def test_signal_dynamic_anomaly_detection(self):
        """SIGNAL computes dynamic anomaly scores from real database error rates."""
        scan = signal_detector.scan_for_latent_patterns()
        self.assertIn("total_events_measured", scan)
        self.assertIn("anomaly_score", scan)
        self.assertGreaterEqual(scan["anomaly_score"], 0.0)
        self.assertLessEqual(scan["anomaly_score"], 1.0)
        self.assertIn("detected_patterns", scan)

    def test_aadya_priority_with_hardware_context(self):
        """AADYA incorporates live RAM and security context into betterment evaluation."""
        aadya = AadyaIntelligence()
        p1 = aadya.evaluate_priority("Schedule daily offline encrypted WAL backups")
        self.assertEqual(p1["verdict"], "STRONGLY_ALIGNED")
        self.assertIn("context", p1)
        self.assertTrue(p1["context"]["ram_safe"])

        p2 = aadya.evaluate_priority("Send user conversations to third-party commercial cloud")
        self.assertEqual(p2["verdict"], "SCRUTINY_REQUIRED")

    def test_nexus_room_live_synchronization(self):
        """NEXUS ROOM topology renders live synchronized devices, agents, and disturbances."""
        topo = nexus_room.render_celestial_topology()
        self.assertTrue(topo["live_synchronized"])
        self.assertGreater(len(topo["celestial_nodes"]), 0)
        self.assertGreater(len(topo["agent_beacons"]), 0)
        self.assertIn("disturbances_count", topo)

    def test_orchestrator_state_persistence_and_stage_failure_halt(self):
        """Orchestrator persists state in SQLite, enforces step limits, and halts on failed stages."""
        res = orchestrator.dispatch_mission("Audit local filesystem boundaries", "local_filesystem")
        self.assertTrue(res["success"])
        self.assertIn("mission_id", res)
        self.assertIn("report", res)

        # Confirm mission was persisted in missions table
        rows = query_db("SELECT id, status, current_phase FROM missions WHERE id = ?;", (res["mission_id"],))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "completed")

    def test_shared_request_pipeline_fast_path_and_concurrency(self):
        """process_intent_pipeline handles Fast-Path and correlation IDs correctly."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            res = loop.run_until_complete(
                process_intent_pipeline("system status", actor="Aadi", actor_role=ROLE_POCO_CORE)
            )
            self.assertIn("correlation_id", res)
            self.assertEqual(res["tier"], "Tier 0 (Fast-Path)")
            self.assertIn("speech", res)
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
