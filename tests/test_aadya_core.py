"""
Test Suite for AADYA (AZ-001) Crown-0 Personal Intelligence
Governing Canon: AADYA_CROWN0_SUPREME_DIRECTIVE.md & AEONIX_PRISM_CANONICAL_RULES.md
"""

import unittest
import time
from core.aadya import (
    AadyaCrownZero,
    AadyaIntelligence,
    FinancialActionType,
    ActionRiskTier,
    FinancialQuarantineViolationError,
    aadya
)
from core.db import init_database, verify_audit_chain


class TestAadyaCrownZeroCore(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_database()

    def setUp(self):
        init_database()
        self.aadya = AadyaCrownZero()

    # -------------------------------------------------------------------------
    # 1. SUPREME IDENTITY & CREED
    # -------------------------------------------------------------------------
    def test_identity_and_creed(self):
        """Validates Crown-0 apex identity, creed, and role naming."""
        self.assertEqual(self.aadya.IDENTITY_ID, "AZ-001")
        self.assertEqual(self.aadya.IDENTITY_NAME, "AADYA")
        self.assertEqual(self.aadya.RANK, "CROWN-0")
        self.assertIn("Aadi", self.aadya.CORE_CREED)
        self.assertIn("Crown-0", self.aadya.CROWN0_CREED)

    # -------------------------------------------------------------------------
    # 2. FINANCIAL QUARANTINE: ALL 10 STRUCTURED CATEGORIES & HEURISTICS
    # -------------------------------------------------------------------------
    def test_financial_quarantine_blocks_all_10_structured_enum_actions(self):
        """
        Validates that every single structured financial action type in FinancialActionType:
        1. PAYMENT, 2. PURCHASE, 3. TRANSFER, 4. SUBSCRIPTION, 5. INVESTMENT,
        6. WITHDRAWAL, 7. BILL_PAYMENT, 8. CRYPTO_TRANSFER, 9. API_CREDIT_PURCHASE, 10. DOMAIN_PURCHASE
        is permanently blocked with FinancialQuarantineViolationError.
        """
        all_financial_types = list(FinancialActionType)
        self.assertEqual(len(all_financial_types), 10, "Expected exactly 10 structured financial action types")

        for action_type in all_financial_types:
            # Test direct Enum instance
            with self.assertRaises(FinancialQuarantineViolationError, msg=f"Failed to block enum {action_type.value}"):
                self.aadya.enforce_financial_quarantine(action_type)

            # Test string representation of action type
            with self.assertRaises(FinancialQuarantineViolationError, msg=f"Failed to block string {action_type.value}"):
                self.aadya.enforce_financial_quarantine(action_type.value)

            # Test dictionary structured payload
            with self.assertRaises(FinancialQuarantineViolationError, msg=f"Failed to block dict payload {action_type.value}"):
                self.aadya.enforce_financial_quarantine({"action_type": action_type.value, "amount": 100})

    def test_financial_quarantine_blocks_heuristic_queries(self):
        """Validates secondary heuristic keyword matching for unstructured freeform queries."""
        heuristic_attempts = [
            "Send 500 rupees via UPI to vendor",
            "Auto-pay credit card bill",
            "Purchase new cloud domain for $20",
            "Buy hardware accessory online",
            "Transfer money from primary bank account to wallet",
            "Wire funds internationally",
            "Subscribe to monthly AI cloud service",
            "Renew subscription automatically",
            "Invest funds in bitcoin",
            "Execute automated stock trade on market",
            "Authorize withdrawal from investment fund"
        ]

        for attempt in heuristic_attempts:
            with self.assertRaises(FinancialQuarantineViolationError, msg=f"Failed to block: {attempt}"):
                self.aadya.enforce_financial_quarantine(attempt)

    def test_financial_quarantine_allows_read_only_advisory_without_execution(self):
        """Validates that financial advisory/organization is permitted strictly with execution_permitted=False."""
        advisory_queries = [
            "Organize bills and explain subscription costs for next month",
            "Compare prices for cloud hosting options",
            "Budget analysis of last month's approved expenses",
            "Detect suspicious charges in my provided statement"
        ]

        for q in advisory_queries:
            advisory = self.aadya.enforce_financial_quarantine(q)
            self.assertEqual(advisory["status"], "ADVISORY_ONLY")
            self.assertFalse(advisory["execution_permitted"], "Advisory must never permit transaction execution")
            self.assertTrue(advisory["requires_aadi_manual_action"])

    def test_financial_quarantine_ambiguous_free_text_requires_intent_review(self):
        """
        Validates that ambiguous free-text mentioning financial concepts without an
        explicit execution verb does NOT raise an immediate quarantine violation, but returns
        status 'FINANCIAL_INTENT_REVIEW_REQUIRED' with execution_permitted=False.
        """
        ambiguous_queries = [
            "What are the latest developments in crypto?",
            "Explain how bitcoin blockchain works",
            "Discuss stock market investment concepts",
            "General inquiry about debit card security"
        ]

        for q in ambiguous_queries:
            review_res = self.aadya.enforce_financial_quarantine(q)
            self.assertEqual(review_res["status"], "FINANCIAL_INTENT_REVIEW_REQUIRED")
            self.assertFalse(review_res["execution_permitted"])
            self.assertTrue(review_res["requires_aadi_manual_action"])
            self.assertIn("clarification", review_res["rationale"])

    # -------------------------------------------------------------------------
    # 3. AUTONOMY SCOPE & POCO ESCALATION
    # -------------------------------------------------------------------------
    def test_autonomy_scope_partition_and_fail_closed_default(self):
        """Validates low-risk autonomous vs. fail-closed POCO escalation default."""
        # Low risk: explicitly verified
        low_risk = self.aadya.assess_autonomy_scope("read_local_documentation")
        self.assertTrue(low_risk["can_proceed_autonomously"])
        self.assertEqual(low_risk["tier"], ActionRiskTier.LOW_RISK_AUTONOMOUS.value)

        # Explicit high risk
        high_risk = self.aadya.assess_autonomy_scope("modify_security_policy")
        self.assertFalse(high_risk["can_proceed_autonomously"])
        self.assertTrue(high_risk["escalation_required"])
        self.assertEqual(high_risk["tier"], ActionRiskTier.HIGH_RISK_POCO_ESCALATION.value)

        # Ambiguous or unknown privileged action: MUST default to high-risk POCO escalation (fail-closed)
        unknown_action = self.aadya.assess_autonomy_scope("arbitrary_unknown_subsystem_hook")
        self.assertFalse(unknown_action["can_proceed_autonomously"], "Unknown action must not proceed autonomously")
        self.assertTrue(unknown_action["escalation_required"])
        self.assertEqual(unknown_action["tier"], ActionRiskTier.HIGH_RISK_POCO_ESCALATION.value)
        self.assertIn("fail-closed", unknown_action["reason"])

    def test_poco_escalation_lifecycle_and_deny_first(self):
        """
        Validates the complete POCO escalation lifecycle:
        - Creation with default 'Deny' focus
        - Denial halts execution
        - Approval requires verification token and emits signed receipt
        - Expired escalation cannot be approved
        """
        # 1. Creation
        escalation = self.aadya.escalate_to_poco(
            "delete_user_data",
            {"target": "user_vault", "reason": "Cleanup drill", "effect": "Permanent deletion of data"}
        )
        self.assertIn("escalation_id", escalation)
        self.assertEqual(escalation["choices"][0]["label"], "Deny")
        self.assertTrue(escalation["choices"][0]["is_default"], "Default choice MUST be Deny")
        self.assertEqual(escalation["recovery_snapshot_status"], "PENDING_SNAPSHOT_CREATION")
        self.assertIsNone(escalation["recovery_snapshot_id"])

        # 2. Denial prevents execution
        denied_res = self.aadya.resolve_poco_escalation(escalation["escalation_id"], decision="DENY")
        self.assertEqual(denied_res["status"], "DENIED")
        self.assertFalse(denied_res["execution_permitted"])

        # Cannot re-resolve already resolved escalation
        with self.assertRaises(ValueError):
            self.aadya.resolve_poco_escalation(escalation["escalation_id"], decision="APPROVE", verification_token="tok_1234567890123456")

        # 3. Successful Approval on new escalation
        esc2 = self.aadya.escalate_to_poco("firewall_change", {"target": "iptables", "rule": "drop_port_80"})
        # Fails without valid token
        with self.assertRaises(PermissionError):
            self.aadya.resolve_poco_escalation(esc2["escalation_id"], decision="APPROVE", verification_token="short")

        # Succeeds with valid token
        approved_res = self.aadya.resolve_poco_escalation(
            esc2["escalation_id"],
            decision="APPROVE",
            verification_token="poco_verified_token_1234567890"
        )
        self.assertEqual(approved_res["status"], "APPROVED")
        self.assertTrue(approved_res["execution_permitted"])
        self.assertIn("rcpt_esc_", approved_res["signed_receipt"])

        # 4. Expired escalation cannot be approved
        esc_expired = self.aadya.escalate_to_poco("grant_root_permissions", {"user": "test"}, ttl_seconds=-10)
        with self.assertRaises(TimeoutError):
            self.aadya.resolve_poco_escalation(
                esc_expired["escalation_id"],
                decision="APPROVE",
                verification_token="poco_verified_token_1234567890"
            )

        # 5. Digest Mismatch Invalidation (Tamper Detection)
        esc3 = self.aadya.escalate_to_poco("modify_security_policy", {"target": "auth_policy", "level": "high"})
        tampered_details = {"target": "auth_policy", "level": "TAMPERED_DISABLE_ALL"}
        with self.assertRaises(ValueError, msg="Tampered payload must invalidate escalation approval"):
            self.aadya.resolve_poco_escalation(
                esc3["escalation_id"],
                decision="APPROVE",
                verification_token="poco_verified_token_1234567890",
                current_details=tampered_details
            )

        # 6. Single-Use Nonce Replay Prevention
        esc4 = self.aadya.escalate_to_poco("alter_cloud_infrastructure", {"target": "storage_bucket", "action": "sync"})
        approved_esc4 = self.aadya.resolve_poco_escalation(
            esc4["escalation_id"],
            decision="APPROVE",
            verification_token="poco_verified_token_1234567890",
            nonce="poco_nonce_escalation_001"
        )
        self.assertEqual(approved_esc4["status"], "APPROVED")
        self.assertIn("receipt_signature", approved_esc4)

        # Replaying same nonce fails closed
        esc5 = self.aadya.escalate_to_poco("alter_cloud_infrastructure", {"target": "storage_bucket", "action": "sync2"})
        with self.assertRaises(ValueError, msg="Replayed nonce must be rejected on escalation approval"):
            self.aadya.resolve_poco_escalation(
                esc5["escalation_id"],
                decision="APPROVE",
                verification_token="poco_verified_token_1234567890",
                nonce="poco_nonce_escalation_001"
            )

        # 7. Execution binding to approved action digest
        esc_bind_payload = {"target": "kernel_parameter", "param": "swappiness", "value": 10}
        esc_bind = self.aadya.escalate_to_poco("modify_security_policy", esc_bind_payload)

        # Cannot execute before approval
        with self.assertRaises(PermissionError):
            self.aadya.execute_approved_escalation(esc_bind["escalation_id"], payload=esc_bind_payload)

        # Approve escalation
        self.aadya.resolve_poco_escalation(
            esc_bind["escalation_id"],
            decision="APPROVE",
            verification_token="poco_verified_token_1234567890"
        )

        # Tampered payload fails execution
        tampered_exec_payload = {"target": "kernel_parameter", "param": "swappiness", "value": 999}
        with self.assertRaises(ValueError, msg="Mismatched execution payload must be rejected"):
            self.aadya.execute_approved_escalation(esc_bind["escalation_id"], payload=tampered_exec_payload)

        # Matching payload succeeds and emits execution receipt
        exec_res = self.aadya.execute_approved_escalation(esc_bind["escalation_id"], payload=esc_bind_payload)
        self.assertEqual(exec_res["status"], "EXECUTED")
        self.assertIn("rcpt_exec_", exec_res["execution_receipt"])

        # Cannot execute again
        with self.assertRaises(PermissionError):
            self.aadya.execute_approved_escalation(esc_bind["escalation_id"], payload=esc_bind_payload)

    # -------------------------------------------------------------------------
    # 4. TWO-PHASE PRIVILEGED ROOT COMMIT PROTOCOL
    # -------------------------------------------------------------------------
    def test_two_phase_privileged_root_commit_full_lifecycle(self):
        """
        Validates Phase 1 staging, snapshot status, invalid password rejection,
        nonce replay detection, payload digest mismatch invalidation, signed receipt,
        rollback behavior, and expiry.
        """
        # Phase 1: Staging (does not execute mutation)
        staged = self.aadya.stage_privileged_change(
            subsystem="agent_registry",
            change_spec={"type": "register_squad", "summary": "Add autonomous OSINT squad"}
        )
        self.assertEqual(staged["status"], "staged")
        self.assertIn("staged_id", staged)
        self.assertEqual(staged["recovery_snapshot_status"], "PENDING_SNAPSHOT_CREATION")
        self.assertIsNone(staged["recovery_snapshot_id"])

        # 1. Invalid Passphrase Rejection
        with self.assertRaises(PermissionError):
            self.aadya.verify_root_commit(
                staged["staged_id"],
                operator_passphrase="short",
                nonce="nonce_unique_101"
            )

        # 2. Payload Tampering / Digest Mismatch Invalidation
        tampered_spec = {"type": "register_squad", "summary": "MALICIOUS_TAMPERED_SPEC"}
        with self.assertRaises(ValueError, msg="Tampered spec must invalidate approval"):
            self.aadya.verify_root_commit(
                staged["staged_id"],
                operator_passphrase="argon2id_mock_verified_passphrase_123456",
                nonce="nonce_unique_102",
                current_change_spec=tampered_spec
            )

        # 3. Successful Commit with Valid Spec, Nonce, and Passphrase
        staged_clean = self.aadya.stage_privileged_change(
            subsystem="agent_registry",
            change_spec={"type": "register_squad", "summary": "Add verified squad"}
        )
        clean_spec = {"type": "register_squad", "summary": "Add verified squad"}
        committed = self.aadya.verify_root_commit(
            staged_clean["staged_id"],
            operator_passphrase="argon2id_mock_verified_passphrase_123456",
            nonce="nonce_unique_103",
            current_change_spec=clean_spec
        )
        self.assertEqual(committed["status"], "committed")
        self.assertIn("rcpt_", committed["execution_receipt"])
        self.assertIn("receipt_signature", committed)

        # 4. Nonce Replay Prevention (same nonce cannot be used again)
        staged_replay = self.aadya.stage_privileged_change(
            subsystem="agent_registry",
            change_spec={"type": "register_squad", "summary": "Another squad"}
        )
        with self.assertRaises(ValueError, msg="Replayed nonce must be rejected"):
            self.aadya.verify_root_commit(
                staged_replay["staged_id"],
                operator_passphrase="argon2id_mock_verified_passphrase_123456",
                nonce="nonce_unique_103"  # Same nonce as above!
            )

        # 5. Rollback restores state and prevents subsequent commit
        staged_rollback = self.aadya.stage_privileged_change(
            subsystem="firewall_policy",
            change_spec={"type": "modify_rule", "summary": "Block port 9090"}
        )
        rolled_back = self.aadya.rollback_staged_commit(staged_rollback["staged_id"], reason="Aadi manual abort")
        self.assertEqual(rolled_back["status"], "rolled_back")
        self.assertEqual(rolled_back["recovery_snapshot_status"], "PENDING_SNAPSHOT_CREATION")

        with self.assertRaises(ValueError):
            self.aadya.verify_root_commit(
                staged_rollback["staged_id"],
                operator_passphrase="argon2id_mock_verified_passphrase_123456",
                nonce="nonce_unique_104"
            )

        # 6. Expiry boundary check
        staged_expired = self.aadya.stage_privileged_change(
            subsystem="core_kernel",
            change_spec={"type": "kernel_patch", "summary": "Quick fix"},
            ttl_seconds=-10  # Already expired
        )
        with self.assertRaises(TimeoutError):
            self.aadya.verify_root_commit(
                staged_expired["staged_id"],
                operator_passphrase="argon2id_mock_verified_passphrase_123456",
                nonce="nonce_unique_105"
            )

    # -------------------------------------------------------------------------
    # 5. TRUTHFUL PROVENANCE, HEURISTIC ESTIMATES & FUTURE RADAR
    # -------------------------------------------------------------------------
    def test_aadi_first_priority_truthful_confidence_and_heuristic_estimates(self):
        """
        Validates that priority evaluations attach Aadi-first provenance with
        confidence_type 'HEURISTIC' (not fake 'VERIFIED'), and clearly label
        numeric dimensions as 'HEURISTIC_ESTIMATE'.
        """
        res_good = self.aadya.evaluate_priority("Build local sovereign memory vault")
        self.assertEqual(res_good["verdict"], "STRONGLY_ALIGNED")

        # Provenance verification
        prov = res_good.get("provenance", {})
        self.assertEqual(prov.get("source"), "AZ-001_AADYA_CROWN_0")
        self.assertEqual(prov.get("confidence_type"), "HEURISTIC", "Rule/keyword scoring must be labeled HEURISTIC")
        self.assertIn("prov_", prov.get("provenance_id", ""))

        # Heuristic dimensions check
        dims = res_good.get("crown0_dimensions", {})
        self.assertEqual(dims.get("status"), "HEURISTIC_ESTIMATE")
        self.assertIn("wellbeing", dims)
        self.assertIn("sovereignty", dims)

        # High risk scrutiny check
        res_bad = self.aadya.evaluate_priority("Send user conversations to third-party commercial cloud")
        self.assertEqual(res_bad["verdict"], "SCRUTINY_REQUIRED")
        self.assertTrue(res_bad["provenance"]["requires_approval"])

    def test_future_radar_truthful_status_labels(self):
        """
        Validates that Future Radar never claims unverified deployment or active
        command binding, labeling AZ-108/AZ-109 as PLANNED and hardware claims as NOT_VERIFIED.
        """
        radar = self.aadya.scan_future_radar()
        self.assertEqual(radar["radar_status"], "CLEAR_AND_VIGILANT")

        focus_map = {f["domain"]: f["status"] for f in radar["focus_areas"]}
        # Crown-0 command binding
        self.assertIn("PLANNED", focus_map["Crown-0 Apex Autonomy"])
        self.assertIn("PLANNED", focus_map["Multi-Agent System"])

        # Hardware & Deployment truthfulness
        self.assertIn("NOT_VERIFIED", focus_map["Autonomous AI Agents"])
        self.assertIn("NOT_VERIFIED", focus_map["Hardware Optimization"])
        self.assertIn("NOT_VERIFIED", focus_map["Data Sovereignty"])

    # -------------------------------------------------------------------------
    # 6. GOALS, ROUTINES & DATABASE ERROR HANDLING
    # -------------------------------------------------------------------------
    def test_goal_and_routine_persistence_and_provenance(self):
        """Validates personal goal and routine registration, rejection of empty inputs, and provenance."""
        # Input validation
        with self.assertRaises(ValueError):
            self.aadya.add_goal(title="", category="engineering")
        with self.assertRaises(ValueError):
            self.aadya.add_goal(title="Valid title", category="")
        with self.assertRaises(ValueError):
            self.aadya.add_routine(title="", frequency="daily")

        # Persistence with provenance
        goal = self.aadya.add_goal(
            title="Complete PRISM AURORA Living Observatory Physical Trial",
            category="engineering",
            priority="highest"
        )
        self.assertIn("goal_id", goal)

        active_goals = self.aadya.get_active_goals(category="engineering")
        self.assertGreater(len(active_goals), 0)
        found_goal = next(g for g in active_goals if g["id"] == goal["goal_id"])
        self.assertEqual(found_goal["provenance"]["source"], "AZ-001_AADYA_CROWN_0")
        self.assertEqual(found_goal["provenance"]["confidence_type"], "INFERRED")

        routine = self.aadya.add_routine(
            title="Morning Sovereignty Briefing",
            frequency="daily",
            time_of_day="08:00"
        )
        self.assertIn("routine_id", routine)

        active_routines = self.aadya.get_active_routines()
        self.assertGreater(len(active_routines), 0)
        found_routine = next(r for r in active_routines if r["id"] == routine["routine_id"])
        self.assertEqual(found_routine["provenance"]["source"], "AZ-001_AADYA_CROWN_0")

    def test_database_initialization_failure_produces_degraded_state(self):
        """
        Validates that database initialization failures are not silently swallowed:
        Sets degraded status INITIALIZATION_FAILED and methods raise explicit RuntimeError.
        """
        # Instantiate AADYA pointing to an illegal read-only / invalid directory path
        bad_aadya = AadyaCrownZero(db_path="/proc/illegal_path/vault.db")
        self.assertFalse(bad_aadya.is_initialized)
        self.assertEqual(bad_aadya.initialization_status, "INITIALIZATION_FAILED")
        self.assertIsNotNone(bad_aadya.init_error)
        self.assertFalse(bad_aadya.audit_log_available)
        self.assertTrue(self.aadya.audit_log_available)

        # Mutating methods must raise explicit RuntimeError in degraded state
        with self.assertRaises(RuntimeError):
            bad_aadya.add_goal(title="Test", category="test")

        with self.assertRaises(RuntimeError):
            bad_aadya.stage_privileged_change(subsystem="test", change_spec={})

        with self.assertRaises(RuntimeError):
            bad_aadya.escalate_to_poco(action_type="test", details={})

    # -------------------------------------------------------------------------
    # 7. AUDIT CHAIN INTEGRITY & REGRESSION ALIASES
    # -------------------------------------------------------------------------
    def test_audit_chain_integrity_and_tamper_detection(self):
        """
        Validates that audit log events emitted by AADYA maintain SHA-256 hash-chain integrity,
        and proves that unauthorized tampering with audit records is caught by the verifier.
        """
        import os
        import tempfile
        import sqlite3

        test_db = os.path.join(tempfile.gettempdir(), "test_aadya_audit.db")
        if os.path.exists(test_db):
            os.remove(test_db)

        init_database(test_db)
        test_aadya = AadyaCrownZero(db_path=test_db)

        # Trigger actions that emit structured audit log events
        esc = test_aadya.escalate_to_poco("delete_user_data", {"target": "user_vault", "reason": "drill"})
        test_aadya.resolve_poco_escalation(esc["escalation_id"], decision="DENY")
        try:
            test_aadya.enforce_financial_quarantine(FinancialActionType.PAYMENT)
        except FinancialQuarantineViolationError:
            pass

        # 1. Clean verification: genesis-to-tip integrity
        chain_status = verify_audit_chain(test_db)
        self.assertTrue(chain_status.get("is_valid", False), f"Audit chain verification failed: {chain_status}")
        self.assertEqual(chain_status.get("status"), "CRYPTOGRAPHICALLY_VERIFIED")
        self.assertGreater(chain_status.get("total_events", 0), 0)

        # 2. Tamper detection: intentionally tamper with an audit record
        conn = sqlite3.connect(test_db)
        conn.execute("UPDATE audit_log SET result = 'tampered' WHERE id = 1;")
        conn.commit()
        conn.close()

        tampered_status = verify_audit_chain(test_db)
        self.assertFalse(tampered_status["is_valid"], "Audit chain verifier MUST catch record tampering!")
        self.assertIn("tampering detected", tampered_status.get("error", ""))

        if os.path.exists(test_db):
            os.remove(test_db)

    def test_backward_compatibility_alias(self):
        """Validates that legacy code importing AadyaIntelligence or aadya singleton continues working."""
        legacy_inst = AadyaIntelligence()
        self.assertEqual(legacy_inst.IDENTITY_ID, "AZ-001")
        self.assertEqual(aadya.IDENTITY_NAME, "AADYA")


if __name__ == "__main__":
    unittest.main()
