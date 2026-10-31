"""
ÆONIX PRISM // Phase 4 Verification Suite: PANOPTES & GUARDIAN
Verifies OSINT reconnaissance, certificate transparency, entity graph traversal,
investigation reporting, subnet perimeter defense, and active probe gating.
Zero cloud API dependencies.
"""

import sys
import unittest
import time
from typing import Dict, Any

sys.path.insert(0, "/data/data/com.termux/files/home/aeonix")
sys.path.insert(0, "/data/data/com.termux/files/home")

from aeonix.core.db import init_database, get_connection
from aeonix.core.panoptes import (
    upsert_entity,
    add_relation,
    get_entity_graph,
    passive_dns_recon,
    http_fingerprint,
    run_passive_osint,
    generate_osint_report,
    request_active_probe
)
from aeonix.core.guardian import (
    scan_host,
    scan_local_subnet,
    get_network_inventory,
    async_get_network_inventory,
    WHITELISTED_DEVICES
)

class TestPhase4PanoptesAndGuardian(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def test_entity_graph_upsert_and_traversal(self):
        """Test entity node deduplication, directed relations, and BFS traversal."""
        ent1 = upsert_entity("target.corp", "domain", {"verified": True})
        ent2 = upsert_entity("192.168.1.100", "ipv4_address", {"version": 4})
        ent3 = upsert_entity("api.target.corp", "subdomain", {"parent": "target.corp"})

        rel1 = add_relation(ent1, ent2, "resolves_to", confidence=1.0)
        rel2 = add_relation(ent1, ent3, "has_subdomain", confidence=0.95)

        self.assertTrue(ent1.startswith("ent_domain_"))
        self.assertTrue(rel1.startswith("rel_"))

        graph = get_entity_graph(ent1, max_depth=2)
        self.assertGreaterEqual(graph["total_nodes"], 3)
        self.assertGreaterEqual(graph["total_edges"], 2)

        node_names = [n["name"] for n in graph["nodes"]]
        self.assertIn("target.corp", node_names)
        self.assertIn("192.168.1.100", node_names)
        self.assertIn("api.target.corp", node_names)

    def test_passive_dns_and_http_fingerprint(self):
        """Test non-intrusive DNS resolution and HTTP security header inspection."""
        dns = passive_dns_recon("127.0.0.1")
        self.assertEqual(dns["domain"], "127.0.0.1")

        # Test HTTP fingerprint against Core Mind server
        fp = http_fingerprint("http://127.0.0.1:8080/api/status", timeout=2.0)
        self.assertEqual(fp["status_code"], 200)
        self.assertIn("server", fp)
        self.assertIn("uvicorn", fp["server"].lower())

    def test_panoptes_osint_report_generator(self):
        """Test automated OSINT dossier generation, security finding calculation, and audit logging."""
        report = generate_osint_report("127.0.0.1", generated_by="Aadi")
        self.assertTrue(isinstance(report, dict))
        self.assertEqual(report["domain"], "127.0.0.1")
        self.assertIn("dossier_markdown", report)
        self.assertIn("# PANOPTES Intelligence Dossier", report["dossier_markdown"])
        self.assertIn("total_entities", report)
        self.assertIn("findings", report)
        self.assertLess(report["latency_seconds"], 10.0)

    def test_sentinel_gate_holds_active_network_probes(self):
        """Verify active TCP probes CANNOT execute without Sentinel Gate authorization."""
        res = request_active_probe("10.116.23.1", [80, 443, 8080])
        self.assertEqual(res["status"], "sentinel_gate_hold")
        self.assertTrue(res["request_id"].startswith("sentinel_"))
        self.assertIn("POCO Core Mind", res["message"])

    def test_guardian_subnet_inventory_and_classification(self):
        """Test local perimeter inventory and rogue vs authorized classification."""
        inv = get_network_inventory()
        self.assertIn("perimeter_status", inv)
        self.assertIn("active_devices_count", inv)
        self.assertIn("authorized_count", inv)
        self.assertGreaterEqual(inv["authorized_count"], 1)

        # Check POCO Core Mind is recognized as sovereign core
        poco_entry = next((d for d in inv["devices"] if d["ip"] == "10.116.23.168"), None)
        self.assertIsNotNone(poco_entry)
        self.assertTrue(poco_entry["authorized"])
        self.assertEqual(poco_entry["trust_level"], "SOVEREIGN_CORE")

        # Check Fire TV Glass is recognized as dumb glass
        glass_entry = next((d for d in inv["devices"] if d["ip"] == "10.116.23.179"), None)
        self.assertIsNotNone(glass_entry)
        self.assertTrue(glass_entry["authorized"])
        self.assertEqual(glass_entry["trust_level"], "DUMB_GLASS")

    def test_guardian_single_host_probe(self):
        """Test scanning localhost open ports via non-blocking TCP connect."""
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(scan_host("127.0.0.1"))
            self.assertTrue(res["is_online"])
            # Core Mind is on 8080
            self.assertIn(8080, res["open_ports"])
        finally:
            loop.close()

if __name__ == "__main__":
    unittest.main()
