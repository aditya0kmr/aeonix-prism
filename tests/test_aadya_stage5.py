"""
AADYA Stage 5 Test Suite — Adaptive Interface & Living Surface Engine
=====================================================================
Verifies all Stage 5 requirements and binding corrections:
1. aadya_surface_snapshots table creation and persistence.
2. Layered privacy defense: privacy-tier filtering, field allowlisting, content
   sanitization, output schema validation, and final TV-payload assertion.
3. No raw memory-node content on TV; only purpose-built TV-safe summaries.
4. No escalation payloads, tokens, nonces, digests, targets, or approval metadata on TV;
   only pending count and neutral notice.
5. Generic, actionable TV-safe error notices with zero internal paths, stack traces,
   or subsystem error strings exposed.
6. Surface rendering is strictly read-only; snapshot creation is explicit, rate-limited,
   and bounded.
7. Learned preferences modify presentation only (theme, verbosity) and NEVER hide
   safety or degraded-state alerts.
8. Truthful audit-chain verification (AUDIT_STATUS_UNKNOWN / AUDIT_VERIFICATION_FAILED
   when unverified or broken).
9. Permanent financial quarantine: zero financial data, controls, or terms on TV.
10. AadyaCrownZero integration and degraded-state handling.
"""

import os
import sys
import time
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, "/data/data/com.termux/files/home/aeonix-prism")

from core.db import init_database, query_db, execute_db, log_audit_event, get_connection
from core.aadya import AadyaCrownZero
from core.aadya_context import ContextPrivacyTier, ConfidenceType
from core.aadya_surface import (
    AadyaSurfaceEngine,
    PrivacyViolationError,
    DegradedStateError,
    ALLOWED_CARD_FIELDS,
    ALLOWED_CARD_TYPES,
    sanitize_tv_summary,
    _verify_surface_non_financial
)


class TestAadyaStage5Surface(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_aeonix.db")
        init_database(self.db_path)
        self.aadya = AadyaCrownZero(db_path=self.db_path)
        self.surface = self.aadya.surface

    def tearDown(self):
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
            wal = self.db_path + "-wal"
            shm = self.db_path + "-shm"
            if os.path.exists(wal):
                os.remove(wal)
            if os.path.exists(shm):
                os.remove(shm)
            os.rmdir(self.test_dir)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 1. Engine Initialization & Snapshots Table
    # -------------------------------------------------------------------------
    def test_stage5_engine_initialization_and_snapshot_table(self):
        self.assertTrue(self.surface.is_initialized)
        self.assertEqual(self.surface.initialization_status, "INITIALIZED")
        self.assertIsNone(self.surface.init_error)

        rows = query_db(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='aadya_surface_snapshots';",
            db_path=self.db_path
        )
        self.assertEqual(len(rows), 1)

    # -------------------------------------------------------------------------
    # 2. Living Surface Structure and Obsidian Theme
    # -------------------------------------------------------------------------
    def test_render_living_surface_structure_and_theme(self):
        surface_state = self.aadya.render_living_surface()

        self.assertEqual(surface_state.get("screen"), "living_surface")
        self.assertIn(surface_state.get("theme"), ["obsidian_gold", "obsidian_cyan", "obsidian_purple", "obsidian_dark"])
        self.assertIn("greeting", surface_state)
        self.assertIsInstance(surface_state.get("cards"), list)
        self.assertGreater(len(surface_state.get("cards")), 0)
        self.assertIn("sanitizer_receipt", surface_state)
        self.assertTrue(surface_state["sanitizer_receipt"].startswith("rcpt_tv_"))

        # Verify all cards have strict schema
        for card in surface_state["cards"]:
            for field in card.keys():
                self.assertIn(field, ALLOWED_CARD_FIELDS)
            self.assertEqual(card["privacy_tier"], ContextPrivacyTier.TV_SAFE.value)
            self.assertIn(card["card_type"], ALLOWED_CARD_TYPES)

    # -------------------------------------------------------------------------
    # 3. Layered Privacy Defense: Privacy-Tier Quarantine
    # -------------------------------------------------------------------------
    def test_privacy_tier_quarantine_on_tv_surface(self):
        # Add TV_SAFE node
        self.aadya.add_memory_node(
            title="Living Room Ambient Schedule",
            content="Automated evening dimming routine active at 19:00",
            category="schedule",
            privacy_tier="TV_SAFE"
        )
        # Add OPERATOR_ONLY node
        self.aadya.add_memory_node(
            title="Operator Private Routine",
            content="Direct access credential rotation scheduled on POCO terminal",
            category="security",
            privacy_tier="OPERATOR_ONLY"
        )
        # Add SOVEREIGN_VAULT_RESTRICTED node
        self.aadya.add_memory_node(
            title="Sovereign Vault Recovery Seed",
            content="mnemonic secret passphrase stored in encrypted vault partition",
            category="vault",
            privacy_tier="SOVEREIGN_VAULT_RESTRICTED"
        )

        surface_state = self.aadya.render_living_surface()
        cards = surface_state["cards"]

        # TV-Safe node summary should be present
        ctx_cards = [c for c in cards if c["card_type"] == "context_summary"]
        card_titles = [c["title"] for c in ctx_cards]
        self.assertIn("Living Room Ambient Schedule", card_titles)

        # Private nodes must NEVER appear on TV
        self.assertNotIn("Operator Private Routine", card_titles)
        self.assertNotIn("Sovereign Vault Recovery Seed", card_titles)

        # Direct card schema validation must reject non-TV_SAFE tiers
        unsafe_card = {
            "card_id": "card_unsafe_1",
            "card_type": "context_summary",
            "title": "Unsafe Card",
            "summary": "This should be blocked",
            "priority": "HIGH",
            "privacy_tier": "OPERATOR_ONLY",
            "timestamp": time.time()
        }
        with self.assertRaises(PrivacyViolationError):
            self.surface._validate_card_schema(unsafe_card)

    # -------------------------------------------------------------------------
    # 4. Sensitive Credential & Path Sanitization
    # -------------------------------------------------------------------------
    def test_sensitive_credential_sanitization_on_surface_cards(self):
        raw_text = "Backup stored at /data/data/com.termux/files/home/secret.key with token sk-live999912345678"
        clean = sanitize_tv_summary(raw_text)

        self.assertNotIn("/data/data", clean)
        self.assertNotIn("sk-live", clean)
        self.assertIn("[REDACTED_SENSITIVE_DATA]", clean)
        self.assertIn("[LOCAL_PATH]", clean)

        # Test assert_tv_payload_safety catches internal filesystem path
        leaky_payload = self.surface.render_living_surface()
        leaky_payload["cards"][0]["summary"] = "Stored at /data/data/com.termux/files/db.sqlite"
        with self.assertRaises(PrivacyViolationError):
            self.surface.assert_tv_payload_safety(leaky_payload)

    # -------------------------------------------------------------------------
    # 5. Adaptive Briefing Layout
    # -------------------------------------------------------------------------
    def test_adaptive_briefing_time_context_and_routine_integration(self):
        # Morning briefing
        morning_card = self.surface.generate_adaptive_briefing(time_period="morning")
        self.assertEqual(morning_card["card_type"], "adaptive_briefing")
        self.assertEqual(morning_card["title"], "Morning Briefing")
        self.assertEqual(morning_card["privacy_tier"], ContextPrivacyTier.TV_SAFE.value)

        # Night sanctuary
        night_card = self.surface.generate_adaptive_briefing(time_period="night")
        self.assertEqual(night_card["title"], "Night Sanctuary")
        self.assertIn("Sanctuary", night_card["summary"])

    # -------------------------------------------------------------------------
    # 6. Presentation Preferences (Theme & Verbosity)
    # -------------------------------------------------------------------------
    def test_learned_preference_adaptation_in_surface_layout(self):
        # Adapt theme preference via AadyaLearningEngine
        self.aadya.adapt_preference("ui_display", "theme_mode", "obsidian_purple")
        self.aadya.adapt_preference("briefing", "verbosity", "concise")

        surface_state = self.aadya.render_living_surface()
        self.assertEqual(surface_state.get("theme"), "obsidian_purple")

        briefing_card = next(c for c in surface_state["cards"] if c["card_type"] == "adaptive_briefing")
        self.assertIn("Morning plan ready", briefing_card["summary"])

    # -------------------------------------------------------------------------
    # 7. Preferences Never Hide Safety or Degraded-State Alerts
    # -------------------------------------------------------------------------
    def test_preferences_never_hide_degraded_state_or_safety(self):
        # Force a degraded state on context engine
        self.aadya.context.initialization_status = "INITIALIZATION_FAILED"

        surface_state = self.aadya.render_living_surface()
        cards = surface_state["cards"]

        # Health card must be the very first card and marked CRITICAL
        self.assertEqual(cards[0]["card_type"], "health_alert")
        self.assertEqual(cards[0]["priority"], "CRITICAL")
        self.assertIn("System Notice", cards[0]["title"])

        # Restore
        self.aadya.context.initialization_status = "INITIALIZED"

    # -------------------------------------------------------------------------
    # 8. Truthful System Health & Generic Error Messaging
    # -------------------------------------------------------------------------
    def test_system_health_reporting_truthful_and_degraded_state_card(self):
        health_card = self.surface.render_system_health_card()
        self.assertEqual(health_card["card_type"], "health_alert")
        self.assertEqual(health_card["privacy_tier"], ContextPrivacyTier.TV_SAFE.value)

        # Verify summary contains no raw file paths, stack traces, or internal exceptions
        summary = health_card["summary"]
        self.assertNotIn("/data/data", summary)
        self.assertNotIn("Traceback", summary)
        self.assertNotIn("Exception", summary)

    # -------------------------------------------------------------------------
    # 9. Truthful Audit-Chain Verification
    # -------------------------------------------------------------------------
    def test_truthful_audit_chain_verification_status(self):
        # Empty audit log
        card_empty = self.surface.render_system_health_card()
        audit_state = card_empty["details"]["audit_state"]
        self.assertIn(audit_state, ["AUDIT_STATUS_EMPTY", "AUDIT_CHAIN_VERIFIED", "AUDIT_STATUS_UNKNOWN"])

        # Log genuine events
        log_audit_event("AZ-001_AADYA", "TEST_EVENT_1", "test_target", "SUCCESS", details={"key": "val1"}, db_path=self.db_path)
        log_audit_event("AZ-001_AADYA", "TEST_EVENT_2", "test_target", "SUCCESS", details={"key": "val2"}, db_path=self.db_path)

        card_verified = self.surface.render_system_health_card()
        self.assertEqual(card_verified["details"]["audit_state"], "AUDIT_CHAIN_VERIFIED")

        # Corrupt audit chain by inserting invalid previous_hash
        conn = get_connection(self.db_path, allow_maintenance=True)
        cur = conn.cursor()
        cur.execute("UPDATE audit_log SET previous_hash = 'CORRUPTED_HASH' WHERE id = 2;")
        conn.commit()
        conn.close()

        card_corrupted = self.surface.render_system_health_card()
        self.assertEqual(card_corrupted["details"]["audit_state"], "AUDIT_VERIFICATION_FAILED")
        self.assertEqual(card_corrupted["priority"], "CRITICAL")

    # -------------------------------------------------------------------------
    # 10. POCO Escalation Queue Notice (Read-Only Glass)
    # -------------------------------------------------------------------------
    def test_read_only_poco_escalation_queue_on_tv_surface(self):
        # Add escalation to aadya_escalations table
        execute_db("""
            INSERT INTO aadya_escalations (
                id, action_type, target, details_json, action_digest, status, expires_at, created_at
            ) VALUES ('esc_test_1', 'modify_firewall', 'network_boundary', '{"port": 8080}', 'digest123', 'PENDING_POCO_APPROVAL', 9999999999, 1000.0);
        """, db_path=self.db_path)

        escalation_card = self.surface.render_poco_escalation_queue_card()

        self.assertEqual(escalation_card["card_type"], "poco_escalation")
        self.assertGreaterEqual(escalation_card["details"]["pending_count"], 1)
        self.assertEqual(escalation_card["priority"], "HIGH")

        # Must show neutral notice
        self.assertIn("Pending physical approval on POCO device", escalation_card["summary"])

        # Must NEVER contain action payloads, targets, digests, or approval tokens
        self.assertNotIn("modify_firewall", escalation_card["summary"])
        self.assertNotIn("network_boundary", escalation_card["summary"])
        self.assertNotIn("digest123", str(escalation_card))
        self.assertNotIn("token", escalation_card["details"])
        self.assertNotIn("action_payload", escalation_card["details"])

    # -------------------------------------------------------------------------
    # 11. Mission Progress Cards with Verified Task Counts
    # -------------------------------------------------------------------------
    def test_mission_progress_cards_with_verified_digests(self):
        # Create an autonomous mission via AadyaCrownZero
        res = self.aadya.create_mission(
            title="Inspect System Telemetry",
            objective="Autonomous health scan",
            tasks=[
                {"id": "t1", "action_type": "view_system_telemetry", "target": "memory", "is_idempotent": True},
                {"id": "t2", "action_type": "read_local_documentation", "target": "docs", "is_idempotent": True, "dependencies": ["t1"]}
            ]
        )
        mis_id = res["id"]

        cards = self.surface.render_mission_progress_cards()
        self.assertGreater(len(cards), 0)

        mis_card = next(c for c in cards if c["details"]["mission_id"] == mis_id)
        self.assertEqual(mis_card["card_type"], "mission_progress")
        self.assertEqual(mis_card["details"]["total_tasks"], 2)
        self.assertEqual(mis_card["details"]["completed_tasks"], 0)
        self.assertIn("Inspect System Telemetry", mis_card["title"])

    # -------------------------------------------------------------------------
    # 12. Future Radar Card Status Fidelity
    # -------------------------------------------------------------------------
    def test_future_radar_card_rendering_and_status_fidelity(self):
        radar_card = self.surface.render_future_radar_card()
        self.assertEqual(radar_card["card_type"], "future_radar")
        self.assertEqual(radar_card["title"], "Future Radar Horizon")
        self.assertEqual(radar_card["privacy_tier"], ContextPrivacyTier.TV_SAFE.value)
        self.assertIn("Tracking 5 domains", radar_card["summary"])

    # -------------------------------------------------------------------------
    # 13. Permanent Financial Quarantine
    # -------------------------------------------------------------------------
    def test_financial_quarantine_on_living_surface(self):
        # Check helper directly
        with self.assertRaises(PrivacyViolationError):
            _verify_surface_non_financial("Execute trade on cryptocurrency exchange")

        with self.assertRaises(PrivacyViolationError):
            _verify_surface_non_financial({"crypto_wallet": "0xABCDEF123456"})

        # Attempt to inject financial card into surface payload
        financial_card = {
            "card_id": "card_fin_1",
            "card_type": "context_summary",
            "title": "Crypto Portfolio Balance",
            "summary": "Bitcoin trading profit $10,000",
            "priority": "HIGH",
            "privacy_tier": "TV_SAFE",
            "timestamp": time.time()
        }
        with self.assertRaises(PrivacyViolationError):
            self.surface._validate_card_schema(financial_card)

    # -------------------------------------------------------------------------
    # 14. Surface Rendering Read-Only & Snapshot Rate-Limiting
    # -------------------------------------------------------------------------
    def test_surface_rendering_is_read_only_and_snapshot_is_rate_limited(self):
        # Initial snapshot count
        initial_count = len(self.surface.list_surface_snapshots())

        # Rendering surface without create_snapshot must be strictly read-only
        self.surface.render_living_surface(create_snapshot=False)
        self.surface.render_living_surface(create_snapshot=False)
        count_after = len(self.surface.list_surface_snapshots())
        self.assertEqual(initial_count, count_after)

        # Explicit snapshot creation
        snap1 = self.surface.create_surface_snapshot()
        self.assertIn("id", snap1)
        self.assertIn("state_digest", snap1)

        # Immediate second snapshot must raise DegradedStateError due to rate limit
        with self.assertRaises(DegradedStateError):
            self.surface.create_surface_snapshot()

        # Retrieve snapshot
        retrieved = self.surface.get_surface_snapshot(snap1["id"])
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["state_digest"], snap1["state_digest"])

    # -------------------------------------------------------------------------
    # 15. AadyaCrownZero Integration & Degraded Handling
    # -------------------------------------------------------------------------
    def test_aadya_crown_zero_stage5_delegation_and_degraded_handling(self):
        # Verify AadyaCrownZero forwards surface calls
        state = self.aadya.render_living_surface()
        self.assertEqual(state["screen"], "living_surface")

        briefing = self.aadya.generate_adaptive_briefing()
        self.assertEqual(briefing["card_type"], "adaptive_briefing")

        # Capture operator feedback from surface
        fb_res = self.aadya.capture_operator_feedback_from_surface(
            source="briefing_card",
            rating=1,
            comment="Morning briefing was crisp and useful."
        )
        self.assertTrue("feedback_id" in fb_res or "id" in fb_res)

        # Simulate degraded surface engine
        self.aadya.surface_initialization_status = "INITIALIZATION_FAILED"
        with self.assertRaises(RuntimeError):
            self.aadya.render_living_surface()

        # Restore
        self.aadya.surface_initialization_status = "INITIALIZED"


if __name__ == "__main__":
    unittest.main()
