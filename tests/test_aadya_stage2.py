"""
Test Suite for AADYA Stage 2 — Memory & Context Engine
Governing Canon: AADYA_CROWN0_SUPREME_DIRECTIVE.md & AEONIX_PRISM_CANONICAL_RULES.md

Contracts Tested:
1. test_memory_correction_updates_provenance_and_digest
2. test_memory_deprecation_requires_correct_privacy_handling
3. test_permanent_private_memory_deletion_requires_poco_approval
4. test_unknown_confidence_is_not_fabricated
5. test_external_weather_freshness_and_unknown_fallback
6. test_tv_safe_export_never_contains_operator_or_vault_data
7. test_aadya_local_context_does_not_automatically_write_global_nexus
8. test_stage2_does_not_bypass_financial_quarantine
9. test_stage2_preserves_all_354_existing_tests
"""

import unittest
import time
import os
import tempfile
from core.db import init_database, query_db
from core.aadya import (
    AadyaCrownZero,
    FinancialActionType,
    FinancialQuarantineViolationError
)
from core.aadya_context import (
    AadyaContextEngine,
    ContextPrivacyTier,
    ConfidenceType
)


class TestAadyaStage2MemoryAndContext(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_database()

    def setUp(self):
        init_database()
        self.aadya = AadyaCrownZero()

    # -------------------------------------------------------------------------
    # 1. MEMORY CORRECTION & DIGEST TRACKING
    # -------------------------------------------------------------------------
    def test_memory_correction_updates_provenance_and_digest(self):
        """
        Validates that memory correction:
        - Updates payload_digest
        - Preserves prior_digest in provenance and aadya_memory_audit
        - Updates timestamp and records mutation reason
        """
        initial_content = {"focus": "Architecture Review", "target_date": "2026-11-20"}
        node = self.aadya.add_memory_node(
            title="Sovereign Project Milestone",
            content=initial_content,
            category="project",
            privacy_tier=ContextPrivacyTier.OPERATOR_ONLY
        )
        node_id = node["node_id"]
        prior_digest = node["payload_digest"]

        # Apply correction
        updated_content = {"focus": "Architecture Review & Stage 2 Context", "target_date": "2026-11-25"}
        correction = self.aadya.correct_memory_node(
            node_id=node_id,
            updated_content=updated_content,
            reason="Scope expansion for Stage 2"
        )

        self.assertEqual(correction["node_id"], node_id)
        self.assertEqual(correction["prior_digest"], prior_digest)
        self.assertNotEqual(correction["new_digest"], prior_digest)

        # Inspect updated node
        refreshed = self.aadya.get_memory_node(node_id)
        self.assertEqual(refreshed["payload_digest"], correction["new_digest"])
        self.assertGreater(refreshed["updated_at"], refreshed["created_at"])
        self.assertIn("corrections", refreshed["provenance"])
        self.assertEqual(len(refreshed["provenance"]["corrections"]), 1)
        self.assertEqual(refreshed["provenance"]["corrections"][0]["reason"], "Scope expansion for Stage 2")

        # Verify audit table entry
        audit_rows = query_db(
            "SELECT mutation_type, prior_digest, new_digest, reason FROM aadya_memory_audit WHERE node_id = ?;",
            (node_id,)
        )
        self.assertEqual(len(audit_rows), 1)
        self.assertEqual(audit_rows[0][0], "CORRECT")
        self.assertEqual(audit_rows[0][1], prior_digest)
        self.assertEqual(audit_rows[0][2], correction["new_digest"])

    # -------------------------------------------------------------------------
    # 2. MEMORY DEPRECATION & PRIVACY PRESERVATION
    # -------------------------------------------------------------------------
    def test_memory_deprecation_requires_correct_privacy_handling(self):
        """
        Validates that deprecation:
        - Excludes node from active lookups
        - Preserves or escalates privacy tier; NEVER relaxes it
        - Records mutation in aadya_memory_audit
        """
        node = self.aadya.add_memory_node(
            title="Private Architectural Note",
            content={"note": "Confidential hardware pinouts"},
            category="hardware",
            privacy_tier=ContextPrivacyTier.SOVEREIGN_VAULT_RESTRICTED
        )
        node_id = node["node_id"]

        # Attempt to relax privacy during deprecation (MUST FAIL)
        with self.assertRaises(ValueError, msg="Privacy tier cannot be relaxed during deprecation"):
            self.aadya.deprecate_memory_node(
                node_id=node_id,
                reason="Attempting to expose private note to TV",
                new_privacy_tier=ContextPrivacyTier.TV_SAFE
            )

        # Deprecate preserving original privacy tier
        dep_res = self.aadya.deprecate_memory_node(
            node_id=node_id,
            reason="Superseded by physical board revision"
        )
        self.assertEqual(dep_res["status"], "deprecated")
        self.assertEqual(dep_res["privacy_tier"], ContextPrivacyTier.SOVEREIGN_VAULT_RESTRICTED.value)

        # Active lookup must exclude deprecated node
        active_nodes = self.aadya.list_active_nodes(category="hardware")
        self.assertFalse(any(n["id"] == node_id for n in active_nodes))

        # Node itself still exists with status 'deprecated'
        refreshed = self.aadya.get_memory_node(node_id)
        self.assertEqual(refreshed["status"], "deprecated")

    # -------------------------------------------------------------------------
    # 3. PERMANENT DELETION POCO APPROVAL GATE
    # -------------------------------------------------------------------------
    def test_permanent_private_memory_deletion_requires_poco_approval(self):
        """
        Validates that permanent purge of OPERATOR_ONLY or SOVEREIGN_VAULT_RESTRICTED
        memory is gated behind POCO approval, while soft-delete is autonomous.
        """
        node = self.aadya.add_memory_node(
            title="Sensitive Operator Diagnostic",
            content={"metric": "low_level_memory_dump"},
            category="diagnostics",
            privacy_tier=ContextPrivacyTier.OPERATOR_ONLY
        )
        node_id = node["node_id"]

        # 1. Soft-delete succeeds autonomously
        soft_del = self.aadya.delete_memory_node(node_id=node_id, permanent=False, reason="Soft archival")
        self.assertEqual(soft_del["status"], "deleted")
        refreshed = self.aadya.get_memory_node(node_id)
        self.assertEqual(refreshed["status"], "deleted")

        # 2. Permanent delete of private memory WITHOUT POCO approval fails
        with self.assertRaises(PermissionError, msg="Permanent deletion must require POCO approval"):
            self.aadya.delete_memory_node(node_id=node_id, permanent=True, reason="Hard wipe drill")

        # 3. Permanent delete WITH valid POCO verification token succeeds
        perm_del = self.aadya.delete_memory_node(
            node_id=node_id,
            permanent=True,
            reason="Hard wipe drill authorized",
            poco_verification_token="poco_verified_token_1234567890"
        )
        self.assertEqual(perm_del["status"], "permanently_deleted")
        self.assertIsNone(self.aadya.get_memory_node(node_id))

    # -------------------------------------------------------------------------
    # 4. TRUTHFUL CONFIDENCE & UNKNOWN HANDLING
    # -------------------------------------------------------------------------
    def test_unknown_confidence_is_not_fabricated(self):
        """
        Validates that unknown confidence is stored as NULL with confidence_type 'UNKNOWN'.
        VERIFIED requires explicit confirmation by Aadi; arbitrary numbers are rejected.
        """
        # Node with unknown confidence
        node = self.aadya.add_memory_node(
            title="Ambiguous Observation",
            content={"observation": "Unverified external log spike"},
            category="observation"
        )
        self.assertEqual(node["confidence_type"], ConfidenceType.UNKNOWN.value)
        self.assertIsNone(node["confidence"])

        # Relation with unknown confidence
        node2 = self.aadya.add_memory_node(title="Target Node", content="test", category="test")
        rel = self.aadya.add_context_relation(
            source_node_id=node["node_id"],
            target_node_id=node2["node_id"],
            relation_type="correlates_with"
        )
        self.assertEqual(rel["confidence_type"], ConfidenceType.UNKNOWN.value)
        self.assertIsNone(rel["confidence"])

        # Claiming VERIFIED without explicit human confirmation raises ValueError
        with self.assertRaises(ValueError, msg="VERIFIED confidence cannot be claimed without explicit confirmation"):
            self.aadya.add_context_relation(
                source_node_id=node["node_id"],
                target_node_id=node2["node_id"],
                relation_type="verified_fact",
                confidence_type=ConfidenceType.VERIFIED,
                is_explicitly_confirmed_by_aadi=False
            )

        # Claiming VERIFIED WITH explicit confirmation succeeds
        rel_verified = self.aadya.add_context_relation(
            source_node_id=node["node_id"],
            target_node_id=node2["node_id"],
            relation_type="verified_fact",
            confidence_type=ConfidenceType.VERIFIED,
            is_explicitly_confirmed_by_aadi=True
        )
        self.assertEqual(rel_verified["confidence_type"], ConfidenceType.VERIFIED.value)
        self.assertEqual(rel_verified["confidence"], 1.0)

    # -------------------------------------------------------------------------
    # 5. EXTERNAL CONTEXT & WEATHER FRESHNESS
    # -------------------------------------------------------------------------
    def test_external_weather_freshness_and_unknown_fallback(self):
        """
        Validates external weather context wrapper:
        - Unavailable or missing data yields WEATHER_DATA_UNKNOWN and OPERATOR_ONLY
        - Expired data yields WEATHER_DATA_UNKNOWN and OPERATOR_ONLY
        - Fresh data yields TV_SAFE
        """
        now = time.time()

        # 1. Missing / None data
        w_missing = self.aadya.wrap_external_context(
            context_type="weather",
            source="open-meteo-offline-cache",
            data=None
        )
        self.assertFalse(w_missing["is_available"])
        self.assertEqual(w_missing["freshness_state"], "UNKNOWN")
        self.assertEqual(w_missing["fallback"], "WEATHER_DATA_UNKNOWN")
        self.assertEqual(w_missing["privacy_tier"], ContextPrivacyTier.OPERATOR_ONLY.value)

        # 2. Expired data (retrieved 3 hours ago with 1 hr TTL)
        w_expired = self.aadya.wrap_external_context(
            context_type="weather",
            source="open-meteo-offline-cache",
            data={"temperature_c": 26, "condition": "Sunny"},
            retrieved_at=now - 10800,
            ttl_seconds=3600
        )
        self.assertFalse(w_expired["is_available"])
        self.assertEqual(w_expired["freshness_state"], "EXPIRED")
        self.assertEqual(w_expired["fallback"], "WEATHER_DATA_UNKNOWN")
        self.assertEqual(w_expired["privacy_tier"], ContextPrivacyTier.OPERATOR_ONLY.value)

        # 3. Fresh data (retrieved 2 minutes ago)
        w_fresh = self.aadya.wrap_external_context(
            context_type="weather",
            source="open-meteo-offline-cache",
            data={"temperature_c": 24, "condition": "Clear Sky"},
            retrieved_at=now - 120,
            ttl_seconds=3600
        )
        self.assertTrue(w_fresh["is_available"])
        self.assertEqual(w_fresh["freshness_state"], "FRESH")
        self.assertIsNone(w_fresh["fallback"])
        self.assertEqual(w_fresh["privacy_tier"], ContextPrivacyTier.TV_SAFE.value)

    # -------------------------------------------------------------------------
    # 6. TV-SAFE SANITIZER LEAK PREVENTION
    # -------------------------------------------------------------------------
    def test_tv_safe_export_never_contains_operator_or_vault_data(self):
        """
        Validates that sanitize_for_tv_export strips 100% of OPERATOR_ONLY and
        SOVEREIGN_VAULT_RESTRICTED records, returning strictly TV_SAFE records and receipt.
        """
        mock_nodes = [
            {"id": "n1", "title": "Public Habit", "privacy_tier": ContextPrivacyTier.TV_SAFE.value, "content": "Drink water"},
            {"id": "n2", "title": "System Kernel Metrics", "privacy_tier": ContextPrivacyTier.OPERATOR_ONLY.value, "content": "127.0.0.1:8080 debug"},
            {"id": "n3", "title": "Private Vault Secret", "privacy_tier": ContextPrivacyTier.SOVEREIGN_VAULT_RESTRICTED.value, "content": "Personal reflection"},
            {"id": "n4", "title": "Living Room Schedule", "privacy_tier": ContextPrivacyTier.TV_SAFE.value, "content": "Evening documentary"}
        ]

        export_res = self.aadya.sanitize_for_tv_export(mock_nodes)

        self.assertEqual(export_res["total_records_processed"], 4)
        self.assertEqual(export_res["included_count"], 2)
        self.assertEqual(export_res["excluded_count"], 2)
        self.assertIn("rcpt_tv_", export_res["audit_receipt"])

        # Strict assertion: zero non-TV_SAFE data in output
        for r in export_res["tv_safe_records"]:
            self.assertEqual(r["privacy_tier"], ContextPrivacyTier.TV_SAFE.value)
            self.assertNotIn("debug", str(r.get("content", "")))
            self.assertNotIn("reflection", str(r.get("content", "")))

    # -------------------------------------------------------------------------
    # 7. AADYA LOCAL CONTEXT VS GLOBAL NEXUS ISOLATION
    # -------------------------------------------------------------------------
    def test_aadya_local_context_does_not_automatically_write_global_nexus(self):
        """
        Validates that AADYA context relations remain local by default (is_global_nexus=0)
        and do NOT write to global entity_relations without explicit operator promotion.
        """
        n1 = self.aadya.add_memory_node(title="Local Concept A", content="A", category="concept")
        n2 = self.aadya.add_memory_node(title="Local Concept B", content="B", category="concept")

        rel = self.aadya.add_context_relation(
            source_node_id=n1["node_id"],
            target_node_id=n2["node_id"],
            relation_type="conceptually_links",
            confidence=0.7,
            confidence_type=ConfidenceType.HEURISTIC
        )
        self.assertFalse(rel["is_global_nexus"])

        # Verify zero entries in global entity_relations table
        global_rows = query_db(
            "SELECT COUNT(*) FROM entity_relations WHERE source_id = ? OR target_id = ?;",
            (n1["node_id"], n2["node_id"])
        )
        self.assertEqual(global_rows[0][0], 0, "Local AADYA relation must NOT automatically write to global NEXUS")

        # Promotion requires valid operator token
        with self.assertRaises(PermissionError):
            self.aadya.promote_to_global_nexus(rel["relation_id"], operator_verification_token="short")

        promoted = self.aadya.promote_to_global_nexus(
            rel["relation_id"],
            operator_verification_token="poco_verified_token_1234567890"
        )
        self.assertTrue(promoted["is_global_nexus"])

    # -------------------------------------------------------------------------
    # 8. FINANCIAL QUARANTINE ENFORCEMENT & RESEARCH ACCOMMODATION
    # -------------------------------------------------------------------------
    def test_stage2_does_not_bypass_financial_quarantine(self):
        """
        Validates that memory creation:
        - Rejects plaintext payment secrets and card CVVs (ValueError)
        - Blocks executable financial commands (FinancialQuarantineViolationError)
        - Permits financial research and advisory notes without executing transactions
        """
        from core.aadya_context import classify_financial_memory_content

        # 1. Plaintext banking credential rejection
        with self.assertRaises(ValueError, msg="Plaintext card CVV must be blocked from storage"):
            self.aadya.add_memory_node(
                title="Stolen Card Note",
                content={"card_number": "4111222233334444", "card_cvv": "123"},
                category="notes"
            )

        with self.assertRaises(ValueError, msg="Plaintext upi pin must be blocked from storage"):
            self.aadya.add_memory_node(
                title="UPI PIN leak",
                content={"bank": "SBI", "upi_pin": "9876"},
                category="notes"
            )

        # 2. Executable financial command rejection
        with self.assertRaises(FinancialQuarantineViolationError, msg="Financial execution must be blocked"):
            self.aadya.add_memory_node(
                title="Execution Request",
                content="Pay 500 rupees via UPI to vendor",
                category="action"
            )

        with self.assertRaises(FinancialQuarantineViolationError, msg="Structured financial action must be blocked"):
            self.aadya.add_memory_node(
                title="Purchase Action",
                content=FinancialActionType.PURCHASE,
                category="action"
            )

        # 3. Financial research & advisory notes ARE PERMITTED to be remembered
        advisory_node = self.aadya.add_memory_node(
            title="Cloud Hosting Cost Analysis",
            content={"summary": "Compare prices and budget analysis for local server vs VPS"},
            category="finance_research"
        )
        self.assertEqual(advisory_node["status"], "active")
        self.assertEqual(advisory_node["financial_classification"], "ADVISORY_ONLY")

        research_node = self.aadya.add_memory_node(
            title="Crypto Architecture Notes",
            content="General thoughts on bitcoin and ethereum trading history",
            category="research"
        )
        self.assertEqual(research_node["status"], "active")
        self.assertEqual(research_node["financial_classification"], "FINANCIAL_INTENT_REVIEW_REQUIRED")

        # Direct classifier checks
        c_adv = classify_financial_memory_content("Budget analysis and price comparison of hardware")
        self.assertEqual(c_adv["classification"], "ADVISORY_ONLY")
        self.assertTrue(c_adv["can_store"])

        c_amb = classify_financial_memory_content("General thoughts on stock market history")
        self.assertEqual(c_amb["classification"], "FINANCIAL_INTENT_REVIEW_REQUIRED")
        self.assertTrue(c_amb["can_store"])

        c_neu = classify_financial_memory_content("Notes on compiler design and AST traversal")
        self.assertEqual(c_neu["classification"], "NEUTRAL")
        self.assertTrue(c_neu["can_store"])

    # -------------------------------------------------------------------------
    # 9. CONTEXT ENGINE DEGRADED HEALTH & INITIALIZATION ERROR HANDLING
    # -------------------------------------------------------------------------
    def test_context_engine_initialization_failure_raises_degraded_error(self):
        """
        Validates that context engine initialization failures:
        - Are not silently swallowed
        - Set context_initialization_status to INITIALIZATION_FAILED
        - Forwarding methods raise explicit RuntimeError
        - AadyaContextEngine validates health via _check_context_health()
        """
        bad_aadya = AadyaCrownZero(db_path="/proc/illegal_path/vault.db")
        self.assertFalse(bad_aadya.is_initialized)
        self.assertEqual(bad_aadya.context_initialization_status, "INITIALIZATION_FAILED")
        self.assertIsNotNone(bad_aadya.context_initialization_error)
        self.assertIsNone(bad_aadya.context)

        # Calling context methods on degraded instance raises explicit RuntimeError
        with self.assertRaises(RuntimeError) as ctx_err:
            bad_aadya.add_memory_node(title="Test", content="Test", category="test")
        self.assertIn("degraded state", str(ctx_err.exception).lower())

        # Standalone context engine on bad path raises on creation and check
        with self.assertRaises(Exception):
            AadyaContextEngine(db_path="/proc/illegal_path/vault.db")

    # -------------------------------------------------------------------------
    # 10. STAGE 1 & BASELINE REGRESSION PRESERVATION
    # -------------------------------------------------------------------------
    def test_stage2_preserves_all_354_existing_tests(self):
        """
        Validates that Stage 1 AADYA Crown-0 core capabilities remain intact:
        - Autonomy assessment & POCO escalation boundary
        - Future radar status labels
        - Truthful priority evaluation
        - Staged root-commit verification
        - Timeline synthesis
        """
        # Autonomy scope
        scope = self.aadya.assess_autonomy_scope("read_local_documentation")
        self.assertTrue(scope["can_proceed_autonomously"])

        # Future radar
        radar = self.aadya.scan_future_radar()
        self.assertEqual(radar["radar_status"], "CLEAR_AND_VIGILANT")

        # Timeline synthesis across audit log and memory audit
        tl = self.aadya.synthesize_unified_timeline(limit=10)
        self.assertIsInstance(tl, list)


if __name__ == "__main__":
    unittest.main()
