"""
Gate G9: Forensic & Telemetry Expansion Unit & Verification Test Suite
Master Specification Reference: Section 19 (Forensics & Intelligence) & Section 22 (Gate G9)

Verifies:
1. Bounded network topology telemetry with rate limiting and exponential backoff (zero continuous battery drain).
2. Deterministic SHA-256 evidence digests and durable event journal emission (events table, 1.0.0 schema).
3. Source-linked Markdown note parsing (frontmatter, headings, tags, citations).
4. Immutable evidence vault recording with cryptographic chain-of-custody.
5. PANOPTES Entity-Relation Graph population (document, topic, citation, author entities).
6. Topic monitoring queries and evidence integrity verification.
7. LUMEN Living Surface HUD context integration with active research topic cards.
8. Guardian and Panoptes REST API endpoints.
"""

import os
import sys
import tempfile
import time
import json
import unittest

_TMP = tempfile.mkdtemp(prefix="aeonix_test_g9_")
os.environ["AEONIX_TEST_MODE"] = "1"
if "AEONIX_SECRETS_DIR" not in os.environ:
    os.environ["AEONIX_SECRETS_DIR"] = os.path.join(_TMP, "secrets")
if "AEONIX_DB_PATH" not in os.environ:
    os.environ["AEONIX_DB_PATH"] = os.path.join(_TMP, "test_aeonix.db")
os.environ["AEONIX_DATA_DIR"] = _TMP
os.environ["AEONIX_VAULT_DIR"] = os.path.join(_TMP, "vault")
os.environ["AEONIX_TEST_SKIP_PORT_CHECKS"] = "1"
os.makedirs(os.environ["AEONIX_SECRETS_DIR"], exist_ok=True)
os.makedirs(os.environ["AEONIX_VAULT_DIR"], exist_ok=True)
_sec_file = os.path.join(os.environ["AEONIX_SECRETS_DIR"], "master_passphrase")
if not os.path.exists(_sec_file):
    with open(_sec_file, "w") as f:
        f.write("SovereignTestPassphrase123!")

from aeonix.core.db import (
    init_database, get_connection, replay_event_journal, log_audit_event
)
from aeonix.core.guardian import (
    read_passive_arp_table,
    get_passive_network_topology,
    get_bounded_network_telemetry,
    compute_inventory_digest,
    WHITELISTED_DEVICES
)
from aeonix.core.panoptes import (
    parse_markdown_document,
    ingest_markdown_note,
    query_notes_by_topic,
    list_monitored_topics,
    verify_note_evidence
)
from aeonix.core.lumen import lumen
from aeonix.core.auth import issue_device_token, ROLE_POCO_CORE, ROLE_AGENT_EXECUTOR
from starlette.testclient import TestClient
from aeonix.core.server import app


class TestGate9ForensicsAndTelemetry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = os.environ["AEONIX_DB_PATH"]
        init_database(cls.db_path)
        cls.core_token = issue_device_token("test_poco_g9", ROLE_POCO_CORE)
        cls.client = TestClient(app, base_url="http://testserver")

    def test_01_passive_arp_table_and_bounded_network_telemetry(self):
        """Test passive ARP table parsing and bounded network topology discovery without active network probes."""
        # 1. Passive ARP inspection must execute safely without raising exceptions even under Android SELinux
        arp_entries = read_passive_arp_table()
        self.assertIsInstance(arp_entries, list)

        # 2. Passive network topology must identify whitelisted sovereign hardware
        topo = get_passive_network_topology()
        self.assertIn("devices", topo)
        self.assertIn("inventory_digest", topo)
        self.assertTrue(topo["passive_mode"])
        self.assertGreaterEqual(topo["active_devices_count"], 2)

        # Whitelisted POCO M4 Pro and Fire TV Lite must be present
        ip_map = {d["ip"]: d for d in topo["devices"]}
        self.assertIn("10.116.23.168", ip_map)
        self.assertIn("10.116.23.179", ip_map)
        self.assertEqual(ip_map["10.116.23.168"]["trust_level"], "SOVEREIGN_CORE")
        self.assertEqual(ip_map["10.116.23.179"]["trust_level"], "DUMB_GLASS")

        # 3. Deterministic SHA-256 evidence digest
        digest = compute_inventory_digest(topo["devices"])
        self.assertEqual(digest, topo["inventory_digest"])
        self.assertEqual(len(digest), 64)

    def test_02_bounded_telemetry_exponential_backoff_and_cache(self):
        """Test rate limiting and exponential backoff to ensure zero continuous battery drain."""
        # Initial scan: fresh sample
        t1 = get_bounded_network_telemetry(force_refresh=True, db_path=self.db_path)
        self.assertFalse(t1["cache_hit"])
        self.assertIn("inventory_digest", t1)
        initial_backoff = t1["backoff_interval"]
        self.assertEqual(initial_backoff, 60.0)

        # Immediate follow-up call within backoff window must hit cache with 0 background overhead
        t2 = get_bounded_network_telemetry(force_refresh=False, db_path=self.db_path)
        self.assertTrue(t2["cache_hit"])
        self.assertEqual(t2["inventory_digest"], t1["inventory_digest"])

        # Forced refresh with unchanged inventory triggers exponential backoff doubling
        t3 = get_bounded_network_telemetry(force_refresh=True, max_backoff=480.0, db_path=self.db_path)
        self.assertFalse(t3["cache_hit"])
        self.assertEqual(t3["backoff_interval"], 120.0)  # Doubled from 60 to 120

        # Another forced refresh with unchanged inventory doubles again
        t4 = get_bounded_network_telemetry(force_refresh=True, max_backoff=480.0, db_path=self.db_path)
        self.assertEqual(t4["backoff_interval"], 240.0)

    def test_03_network_telemetry_durable_event_emission(self):
        """Verify durable event envelope recorded into events table on telemetry capture."""
        # Replay event journal to verify durable recording
        replay = replay_event_journal(start_sequence=1, limit=50, db_path=self.db_path)
        self.assertTrue(replay["is_valid"])

        event_types = [e["event_type"] for e in replay["events"]]
        self.assertIn("network_topology_snapshot", event_types)

        # Verify envelope structure of the network snapshot event
        net_events = [e for e in replay["events"] if e["event_type"] == "network_topology_snapshot"]
        latest_net = net_events[-1]
        self.assertEqual(latest_net["schema_version"], "1.0.0")
        self.assertEqual(latest_net["device_id"], "poco_m4_pro_5g")
        self.assertEqual(latest_net["source"], "GUARDIAN")
        self.assertEqual(latest_net["classification"], "R1")
        self.assertIn("inventory_digest", latest_net["payload"])

    def test_04_markdown_note_parsing_and_extraction(self):
        """Test Markdown document parsing: frontmatter, headings, hashtags, and citations."""
        sample_md = """---
title: "PRISM Sovereign Perimeter Analysis"
author: "Aadi"
tags: ["security", "network", "firetv"]
---

# Sovereign Architecture Overview

This document specifies the lawful telemetry boundary for ÆONIX PRISM.
Observations are passive and zero-cloud.

## Perimeter Defense
We monitor rogue devices via #guardian and #arp inspection.
All consequential missions require operator approval.

### References & Citations
- Protocol standard: [RFC 8446 TLS 1.3](https://tools.ietf.org/html/rfc8446)
- Local Spec: [Master Blueprint](file:///home/aeonix-prism/docs/blueprint.md)
"""
        parsed = parse_markdown_document(sample_md)
        self.assertEqual(parsed["title"], "PRISM Sovereign Perimeter Analysis")
        self.assertEqual(parsed["frontmatter"]["author"], "Aadi")
        self.assertIn("security", parsed["topics"])
        self.assertIn("guardian", parsed["topics"])
        self.assertIn("perimeter defense", parsed["topics"])

        # Check citations
        citations = parsed["citations"]
        self.assertEqual(len(citations), 2)
        urls = [c["url"] for c in citations]
        self.assertIn("https://tools.ietf.org/html/rfc8446", urls)
        self.assertIn("file:///home/aeonix-prism/docs/blueprint.md", urls)

    def test_05_markdown_note_ingestion_and_evidence_vault(self):
        """Test Markdown note ingestion with immutable SHA-256 evidence record and chain-of-custody."""
        note_content = """# Hardware Isolation Guidelines
#hardware #isolation
All high-risk R3/R4 authority remains pinned to POCO Dimensity 810 ARM NEON.
Living glass terminal acts strictly as dumb display.
Citation: [ARM Architecture Reference](https://developer.arm.com/documentation)
"""
        ingest_res = ingest_markdown_note(
            content=note_content,
            source_path="/tmp/hardware_isolation.md",
            author="Aadi",
            db_path=self.db_path
        )

        self.assertEqual(ingest_res["status"], "ingested")
        self.assertEqual(ingest_res["title"], "Hardware Isolation Guidelines")
        self.assertIn("hardware", ingest_res["topics"])
        self.assertIn("isolation", ingest_res["topics"])

        # Verify cryptographic evidence vault record
        evidence_id = ingest_res["evidence_id"]
        check = verify_note_evidence(evidence_id, db_path=self.db_path)
        self.assertTrue(check["is_valid"])
        self.assertEqual(check["sha256"], ingest_res["sha256"])
        self.assertEqual(check["title"], "Hardware Isolation Guidelines")

    def test_06_panoptes_entity_graph_population_and_topic_linking(self):
        """Test PANOPTES Entity Graph linking documents, topics, citations, and authors."""
        topics = list_monitored_topics(db_path=self.db_path)
        self.assertIsInstance(topics, list)
        topic_names = [t["name"] for t in topics]
        self.assertIn("hardware", topic_names)

        # Query notes by topic
        notes = query_notes_by_topic("hardware", db_path=self.db_path)
        self.assertGreaterEqual(len(notes), 1)
        self.assertEqual(notes[0]["title"], "Hardware Isolation Guidelines")
        self.assertTrue(notes[0]["evidence_valid"])

    def test_07_lumen_living_surface_topic_integration(self):
        """Test LUMEN synthesizes Knowledge Vault HUD card when monitored topics exist."""
        surface = lumen.compute_living_surface_state()
        self.assertEqual(surface["screen"], "living_surface")
        card_types = [c["type"] for c in surface["cards"]]
        self.assertIn("knowledge_topics", card_types)

        topic_card = next(c for c in surface["cards"] if c["type"] == "knowledge_topics")
        self.assertEqual(topic_card["title"], "Knowledge Vault & Monitored Topics")
        self.assertIn("active research topics", topic_card["content"])

    def test_08_rest_api_endpoints_telemetry_and_notes(self):
        """Test Guardian telemetry and Panoptes note ingestion REST API endpoints."""
        headers = {"Authorization": f"Bearer {self.core_token}"}

        # 1. GET /api/guardian/telemetry
        r_tel = self.client.get("/api/guardian/telemetry?force=true", headers=headers)
        self.assertEqual(r_tel.status_code, 200)
        tel_data = r_tel.json()
        self.assertTrue(tel_data["success"])
        self.assertIn("telemetry", tel_data)
        self.assertIn("inventory_digest", tel_data["telemetry"])

        # 2. POST /api/panoptes/ingest-note
        sample_post = {
            "content": "# Sentinel Safety Gate Contract\n#sentinel #contracts\nOperator passphrase physically required.\n[Docs](https://aeonix.local/docs)",
            "author": "Aadi"
        }
        r_ingest = self.client.post("/api/panoptes/ingest-note", json=sample_post, headers=headers)
        self.assertEqual(r_ingest.status_code, 200)
        ing_data = r_ingest.json()
        self.assertTrue(ing_data["success"])
        self.assertEqual(ing_data["note"]["title"], "Sentinel Safety Gate Contract")

        # 3. GET /api/panoptes/topics
        r_topics = self.client.get("/api/panoptes/topics", headers=headers)
        self.assertEqual(r_topics.status_code, 200)
        topics_data = r_topics.json()
        self.assertTrue(topics_data["success"])
        names = [t["name"] for t in topics_data["topics"]]
        self.assertIn("sentinel", names)

        # 4. GET /api/panoptes/topics/notes?topic=sentinel
        r_q = self.client.get("/api/panoptes/topics/notes?topic=sentinel", headers=headers)
        self.assertEqual(r_q.status_code, 200)
        q_data = r_q.json()
        self.assertTrue(q_data["success"])
        self.assertEqual(len(q_data["notes"]), 1)
        self.assertEqual(q_data["notes"][0]["title"], "Sentinel Safety Gate Contract")


if __name__ == "__main__":
    unittest.main()
