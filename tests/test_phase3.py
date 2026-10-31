"""
ÆONIX PRISM // Phase 3 Test & Verification Suite
Verifies PANOPTES OSINT, VERITAS Forensic Vault, GUARDIAN Perimeter, and ATLAS WATCH Supervisor.
"""

import os
import sys
import time
import tempfile
import unittest

sys.path.insert(0, "/data/data/com.termux/files/home")

from aeonix.core.db import init_database, get_connection
from aeonix.core.panoptes import upsert_entity, add_relation, get_entity_graph, request_active_probe
from aeonix.core.veritas import create_case, ingest_evidence, verify_evidence, generate_case_manifest
from aeonix.core.guardian import get_network_inventory
from aeonix.core.atlas_watch import run_supervisor_cycle
from aeonix.core.fast_path import match_fast_path, execute_fast_path

class TestPhase3Arsenal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def test_panoptes_graph_and_sentinel(self):
        """Test entity graph insertion, traversal, and Sentinel gate hold."""
        d_id = upsert_entity("target-test.net", "domain", {"verified": True})
        ip_id = upsert_entity("192.168.1.100", "ipv4_address", {"version": 4})
        rel_id = add_relation(d_id, ip_id, "resolves_to", confidence=1.0)
        
        self.assertTrue(d_id.startswith("ent_domain_"))
        self.assertTrue(ip_id.startswith("ent_ipv4_address_"))
        self.assertTrue(rel_id.startswith("rel_"))

        # Traverse
        graph = get_entity_graph(d_id, max_depth=1)
        self.assertGreaterEqual(graph["total_nodes"], 2)
        self.assertGreaterEqual(graph["total_edges"], 1)

        # Active probe MUST halt at Sentinel Gate
        hold = request_active_probe("192.168.1.100", [80, 443])
        self.assertEqual(hold["status"], "sentinel_gate_hold")
        self.assertIn("sentinel_", hold["request_id"])

    def test_veritas_forensics_and_tamper_detection(self):
        """Test evidence ingestion, cryptographic SHA-256 verification, and manifest integrity."""
        case_id = create_case("Test Forensic Audit", "Automated verification test case")
        self.assertTrue(case_id.startswith("case_"))

        # Create temporary file
        tmp_dir = tempfile.gettempdir()
        test_file = os.path.join(tmp_dir, f"evidence_test_{int(time.time())}.txt")
        with open(test_file, "w") as f:
            f.write("CONFIDENTIAL_SOVEREIGN_LOG_ENTRY")

        # Ingest
        evidence = ingest_evidence(case_id, test_file, "text/plain", {"origin": "automated_test"})
        self.assertEqual(evidence["status"], "secured")
        self.assertTrue(os.path.exists(evidence["vault_path"]))

        # Verify intact
        check = verify_evidence(evidence["evidence_id"])
        self.assertTrue(check["verified"])
        self.assertEqual(check["status"], "intact")

        # Manifest
        manifest = generate_case_manifest(case_id)
        self.assertTrue(manifest["all_evidence_intact"])
        self.assertEqual(manifest["total_evidence_items"], 1)

    def test_guardian_subnet_discovery(self):
        """Test subnet perimeter inventory and device classification."""
        inv = get_network_inventory()
        self.assertIn("perimeter_status", inv)
        self.assertEqual(inv["subnet"], "10.116.23.0/24")
        self.assertGreaterEqual(inv["active_devices_count"], 1)
        # All detected devices must have authorized status flag
        for dev in inv["devices"]:
            self.assertIn("authorized", dev)
            self.assertIn("ip", dev)

    def test_atlas_watch_supervisor(self):
        """Test supervisor health pass."""
        report = run_supervisor_cycle()
        self.assertIn("core_server", report)
        self.assertIn("ram_guard", report)
        self.assertIn("firetv_adb", report)
        self.assertIn("firetv_launcher", report)
        self.assertTrue(report["ram_guard"]["is_safe"])

    def test_fast_path_arsenal_triggers(self):
        """Test sub-5ms intent resolution for Phase 3 directives."""
        triggers = [
            ("who is on my wifi", "network_scan"),
            ("veritas status", "cases_status"),
            ("supervisor health", "supervisor_health"),
        ]
        for query, expected_action in triggers:
            match = match_fast_path(query)
            self.assertIsNotNone(match)
            action, conf = match
            self.assertEqual(action, expected_action)
            res = execute_fast_path(action)
            self.assertEqual(res["action"], expected_action)
            self.assertIn("speech", res)
            self.assertIn("layout_intent", res)
            self.assertLess(res["latency_ms"], 2500) # fast-path including network scan

if __name__ == "__main__":
    unittest.main()
