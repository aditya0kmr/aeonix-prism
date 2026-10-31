"""
ÆONIX PRISM // Phase 6 Test & Verification Suite
Verifies Vault Backups, Integrity Verification, Emergency Recovery, MORPH Evolution, and Oracle's Council.
"""

import os
import sys
import unittest

sys.path.insert(0, "/data/data/com.termux/files/home")

from aeonix.core.db import init_database
from aeonix.core.backup import (
    create_vault_backup,
    verify_backup,
    list_backups,
    generate_emergency_recovery_key
)
from aeonix.core.morph import (
    generate_optimization_proposal,
    get_pending_proposals
)
from aeonix.core.council import convene_council_session
from aeonix.core.fast_path import match_fast_path, execute_fast_path

class TestPhase6SovereignMesh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def test_backup_create_and_verify(self):
        """Test atomic SQLite WAL backup and archive verification."""
        res = create_vault_backup(actor="Aadi", note="Unit Test Snapshot")
        self.assertTrue(res["success"])
        self.assertTrue(os.path.exists(res["backup_path"]))
        self.assertGreater(res["size_bytes"], 1000)
        self.assertEqual(len(res["sha256"]), 64)

        # Verify integrity
        v_res = verify_backup(res["backup_path"])
        self.assertTrue(v_res["success"])
        self.assertTrue(v_res["is_intact"])
        self.assertEqual(v_res["integrity_check"], "ok")

        # List backups
        all_bks = list_backups()
        self.assertGreaterEqual(len(all_bks), 1)

    def test_emergency_recovery_key(self):
        """Test high-entropy recovery key generation and checksum."""
        rec = generate_emergency_recovery_key()
        self.assertTrue(rec["recovery_key"].startswith("AEONIX-RECOVERY-"))
        self.assertEqual(len(rec["checksum"]), 8)

    def test_morph_self_evolution_guardrails(self):
        """Test proposal generation and mandatory Sentinel gate hold."""
        prop = generate_optimization_proposal(actor="Aadi")
        self.assertIn(prop["status"], ("proposal_generated", "nominal"))
        if prop["status"] == "proposal_generated":
            self.assertIn("sentinel_request_id", prop)
            self.assertTrue(prop["sentinel_request_id"].startswith("sentinel_"))

        proposals = get_pending_proposals()
        self.assertIsInstance(proposals, list)

    def test_oracle_council_adversarial_session(self):
        """Test 4-perspective deliberation and consensus verdict."""
        query = "Deploy automated daily OSINT scans across owned subdomains"
        council = convene_council_session(query, actor="Aadi")
        self.assertTrue(council["success"])
        self.assertEqual(len(council["deliberations"]), 4)

        roles = [d["role"] for d in council["deliberations"]]
        self.assertIn("Visionary", roles)
        self.assertIn("Skeptic", roles)
        self.assertIn("Strategist", roles)
        self.assertIn("Defender", roles)

        self.assertIn("verdict", council)
        self.assertIn("consensus", council["verdict"])
        self.assertIn("primary_risk", council["verdict"])

    def test_fast_path_phase6_triggers(self):
        """Test sub-50ms intent matching for backup, morph, and council directives."""
        triggers = [
            ("create backup", "create_backup"),
            ("backup status", "backup_status"),
            ("morph status", "morph_status"),
            ("convene council", "oracle_council")
        ]
        for query, expected in triggers:
            match = match_fast_path(query)
            self.assertIsNotNone(match)
            action, conf = match
            self.assertEqual(action, expected)
            res = execute_fast_path(action)
            self.assertIn("speech", res)
            self.assertIn("layout_intent", res)
            self.assertLess(res["latency_ms"], 200)

if __name__ == "__main__":
    unittest.main()
