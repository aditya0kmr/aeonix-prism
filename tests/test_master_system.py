"""
Unit Tests for ÆONIX PRISM Master System & Advanced Engines
Tests:
- LUMEN (Living surface context engine)
- CHRONOS (Time & routine automation engine)
- ORACLE (Deep research engine)
- AADYA (Eternal intelligence & personal advocate)
- IDENTITY (Lawful subject intelligence & exposure)
- ATLAS (Geospatial awareness & weather)
- TRUST (Signed orders & emergency kill switch)
- PARADOX (Decision replay engine)
- GHOST (Digital twin & fault injection)
- CHRONOSCOPE (Time machine & audit replay)
- DREAMCATCHER (Idea incubator)
- MIMIC (Workflow cloning)
- BLACKBOX (Mission flight recorder)
- SIGNAL (Hidden pattern detector)
- FORGE MIND (Self-extending tool proposals)
- NEXUS ROOM (Celestial living interface universe)
"""

import unittest
from core.lumen import lumen
from core.chronos import chronos
from core.oracle import oracle
from core.aadya import aadya
from core.identity import identity_engine
from core.atlas import atlas
from core.trust import trust
from core.paradox import paradox
from core.ghost import ghost
from core.chronoscope import chronoscope
from core.dreamcatcher import dreamcatcher
from core.mimic import mimic
from core.blackbox import blackbox
from core.signal import signal_detector
from core.forge_mind import forge_mind
from core.nexus_room import nexus_room


class TestMasterSystemEngines(unittest.TestCase):
    def test_lumen_living_surface(self):
        state = lumen.compute_living_surface_state()
        self.assertEqual(state["screen"], "living_surface")
        self.assertIn("theme", state)
        self.assertIsInstance(state["cards"], list)

    def test_chronos_routines(self):
        routines = chronos.list_routines()
        self.assertGreaterEqual(len(routines), 3)
        res = chronos.trigger_routine("routine_morning")
        self.assertTrue(res["success"])

    def test_oracle_research(self):
        res = oracle.conduct_research("Autonomous Operating Systems")
        self.assertIn("key_findings", res)
        self.assertGreaterEqual(res["confidence"], 0.5)

    def test_aadya_priority_and_radar(self):
        eval_res = aadya.evaluate_priority("Build local sovereign memory vault")
        self.assertEqual(eval_res["verdict"], "STRONGLY_ALIGNED")
        radar = aadya.scan_future_radar()
        self.assertEqual(radar["radar_status"], "CLEAR_AND_VIGILANT")
        protection = aadya.protection_check()
        self.assertIn("Aadi", protection["creed"])

    def test_identity_exposure(self):
        res = identity_engine.analyze_public_exposure("sovereign.local")
        self.assertTrue(res["success"])
        self.assertIn("compliance_attestation", res["data"])

    def test_atlas_situational_summary(self):
        summary = atlas.get_situational_summary()
        self.assertEqual(summary["spatial_zone"], "Sovereign Home Perimeter")
        self.assertEqual(summary["status"], "SECURE")

    def test_trust_signed_orders_and_kill_switch(self):
        order = trust.generate_signed_order("deploy_guardrails", ["vault", "stt"])
        self.assertTrue(trust.verify_order(order))
        self.assertTrue(order["signature"].startswith("POCO_SIGNED_"))

        # Test kill switch
        ks_res = trust.trigger_kill_switch()
        self.assertEqual(ks_res["kill_switch"], "ENGAGED")
        reset_res = trust.reset_kill_switch()
        self.assertEqual(reset_res["kill_switch"], "DISENGAGED")

    def test_paradox_decision_replay(self):
        sim = paradox.simulate_counterfactual("Deploy Termux on POCO", "Deploy heavy cloud VM")
        self.assertIn("projected_differences", sim)
        self.assertIn("baseline", sim["verdict"])

    def test_ghost_digital_twin_and_fault(self):
        twin = ghost.get_digital_twin_state()
        self.assertEqual(len(twin["virtual_devices"]), 3)
        fault = ghost.simulate_fault_injection("internet_loss")
        self.assertEqual(fault["system_integrity"], "UNCOMPROMISED")

    def test_chronoscope_audit_replay(self):
        events = chronoscope.replay_audit_chain(limit=5)
        self.assertIsInstance(events, list)

    def test_dreamcatcher_incubate(self):
        res = dreamcatcher.incubate_thought("Autonomous Fire TV ambient widget", "ui_feature")
        self.assertIn("thought_id", res)
        self.assertGreaterEqual(len(res["developing_questions"]), 2)

    def test_mimic_workflow_clone(self):
        steps = [{"action": "check_ram"}, {"action": "seal_vault"}]
        res = mimic.clone_workflow("emergency_prep", steps)
        self.assertTrue(res["success"])
        self.assertIn("emergency_prep", mimic.list_clones())

    def test_blackbox_flight_recorder(self):
        flight = blackbox.record_mission_flight(
            mission_id="m_101",
            goal="Subnet Discovery",
            agents_involved=["Navigator", "Defender"],
            tool_calls=[{"tool": "arp_scan"}],
            outcome="COMPLETED",
            total_latency_ms=12.5,
        )
        self.assertEqual(flight["outcome"], "COMPLETED")
        self.assertGreaterEqual(len(blackbox.get_recent_flights()), 1)

    def test_signal_pattern_detector(self):
        sig = signal_detector.scan_for_latent_patterns()
        self.assertEqual(sig["signal_status"], "PATTERNS_NOMINAL")
        self.assertIsInstance(sig["detected_patterns"], list)

    def test_forge_mind_propose_tool(self):
        res = forge_mind.propose_new_tool("packet_parser", "Parse local UDP broadcast", "def parse(pkt): pass")
        self.assertEqual(res["status"], "sentinel_gate_hold")
        self.assertIn("sentinel_request_id", res)

    def test_nexus_room_celestial_universe(self):
        univ = nexus_room.render_celestial_topology()
        self.assertEqual(univ["view"], "nexus_room_celestial_universe")
        self.assertEqual(len(univ["celestial_nodes"]), 3)


if __name__ == "__main__":
    unittest.main()
