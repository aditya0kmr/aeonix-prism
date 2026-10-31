"""
Unit Tests for ÆONIX PRISM Autonomous Agent System
Tests all 11 specialized agents and the multi-agent orchestrator:
- Navigator (Plan decomposition)
- Collector (Passive collection & active probe Sentinel hold)
- Analyst (Nexus graph correlation & confidence scoring)
- Skeptic (Claim validation & counter-hypotheses)
- LegalGuard (Scope, consent, Black-class hard-blocks)
- Forensicator (Evidence hashing & VERITAS integration)
- Defender (Subnet assessment & isolation holds)
- Reporter (Briefing compilation & layout intent)
- Builder (Git telemetry & sandboxed execution)
- Archivist (Unified timeline reconstruction)
- Orchestrator (Multi-agent coordination & stateful pause)
"""

import sys
import os
sys.path.insert(0, "/data/data/com.termux/files/home/aeonix")
sys.path.insert(0, "/data/data/com.termux/files/home")
import unittest
from agents.navigator import NavigatorAgent
from agents.collector import CollectorAgent
from agents.analyst import AnalystAgent
from agents.skeptic import SkepticAgent
from agents.legal_guard import LegalGuardAgent
from agents.forensicator import ForensicatorAgent
from agents.defender import DefenderAgent
from agents.reporter import ReporterAgent
from agents.builder import BuilderAgent
from agents.archivist import ArchivistAgent
from agents.orchestrator import orchestrator


class TestAgentSystem(unittest.TestCase):
    def test_navigator_plan_decomposition(self):
        nav = NavigatorAgent()
        plan = nav.execute({"objective": "Investigate public OSINT posture of example.com"})
        self.assertEqual(plan["status"], "planned")
        self.assertGreaterEqual(len(plan["phases"]), 3)
        self.assertEqual(plan["recommended_lead_agent"], "LegalGuard")

    def test_legal_guard_boundaries(self):
        lg = LegalGuardAgent()
        # Test lawful directive
        res_lawful = lg.execute({"target": "example.com", "objective": "analyze public DNS"})
        self.assertEqual(res_lawful["status"], "cleared")

        # Test prohibited directive (Black Class)
        res_prohibited = lg.execute({"target": "victim", "objective": "stalk and steal credentials"})
        self.assertEqual(res_prohibited["status"], "blocked")
        self.assertIn("Black", res_prohibited["action_class"])

    def test_collector_and_sentinel_hold(self):
        collector = CollectorAgent()
        # Passive mode
        res_passive = collector.execute({"target": "local_project", "mode": "passive"})
        self.assertEqual(res_passive["status"], "collected")

        # Active mode should hit Sentinel Gate hold
        res_active = collector.execute({"target": "10.116.23.1", "mode": "active"})
        self.assertEqual(res_active["status"], "sentinel_gate_hold")
        self.assertIn("request_id", res_active)

    def test_analyst_correlation(self):
        analyst = AnalystAgent()
        entities = [
            {"name": "Domain Node", "type": "domain"},
            {"name": "IP Node", "type": "ip"},
        ]
        res = analyst.execute({"entities": entities})
        self.assertEqual(res["status"], "analyzed")
        self.assertGreater(res["confidence_score"], 0.7)

    def test_skeptic_validation(self):
        skeptic = SkepticAgent()
        # Without evidence
        res_no_ev = skeptic.execute({"claims": ["Unverified assertion"]})
        self.assertEqual(res_no_ev["skeptic_review"]["overall_assessment"], "CHALLENGED")

        # With evidence
        res_with_ev = skeptic.execute({"claims": ["Ground truth assertion"], "evidence_hashes": ["sha256_mock"]})
        self.assertEqual(res_with_ev["skeptic_review"]["overall_assessment"], "CONDITIONALLY_VALIDATED")

    def test_forensicator_manifest(self):
        forensicator = ForensicatorAgent()
        res = forensicator.execute({"case_id": "test_case"})
        self.assertEqual(res["status"], "manifest_only")

    def test_defender_assessment(self):
        defender = DefenderAgent()
        res = defender.execute({"action": "assess"})
        self.assertEqual(res["status"], "assessed")
        self.assertIn("threat_assessment", res)

    def test_reporter_briefing(self):
        reporter = ReporterAgent()
        res = reporter.execute({"title": "Daily Summary", "sections": [{"title": "Status", "content": "Nominal"}]})
        self.assertEqual(res["status"], "reported")
        self.assertIn("layout_intent", res["report"])

    def test_builder_git(self):
        builder = BuilderAgent()
        res = builder.execute({"task": "git_status"})
        self.assertEqual(res["status"], "completed")
        self.assertIn("git_telemetry", res)

    def test_archivist_timeline(self):
        archivist = ArchivistAgent()
        res = archivist.execute({"task": "timeline", "limit": 5})
        self.assertEqual(res["status"], "timeline_curated")
        self.assertIsInstance(res["timeline"], list)

    def test_orchestrator_roster_and_dispatch(self):
        roster = orchestrator.list_roster()
        self.assertEqual(len(roster), 10)
        # Dispatch standard mission
        mission_res = orchestrator.dispatch_mission(objective="Investigate public DNS records of sovereign.local")
        self.assertTrue(mission_res["success"])
        self.assertEqual(len(mission_res["execution_log"]), 5)


if __name__ == "__main__":
    unittest.main()
