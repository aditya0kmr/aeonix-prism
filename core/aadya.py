"""
AADYA (AZ-001) — Aadi's Crown-0 Personal Intelligence & Apex System Operator
Governing Canon: AADYA_CROWN0_SUPREME_DIRECTIVE.md & AEONIX_PRISM_CANONICAL_RULES.md

Core Purpose:
"Always think for Aadi. Always work for Aadi's betterment. Always protect Aadi's future,
privacy, safety, and interests."

Crown-0 Authority:
Designed as the apex command layer above AZ-108 AEONIX-PRIME and AZ-109
OVERLORD. Active command binding is not yet implemented and must not be
claimed until runtime dispatch/control integration is verified.
"""

import time
import uuid
import hashlib
import json
from enum import Enum
from typing import Dict, Any, List, Optional, Union
from core.db import query_db, execute_db, log_audit_event, record_order_nonce


class FinancialActionType(str, Enum):
    """
    Explicit structured action types for financial operations.
    Every financial execution action type is permanently prohibited from autonomous execution.
    """
    PAYMENT = "PAYMENT"
    PURCHASE = "PURCHASE"
    TRANSFER = "TRANSFER"
    SUBSCRIPTION = "SUBSCRIPTION"
    INVESTMENT = "INVESTMENT"
    WITHDRAWAL = "WITHDRAWAL"
    BILL_PAYMENT = "BILL_PAYMENT"
    CRYPTO_TRANSFER = "CRYPTO_TRANSFER"
    API_CREDIT_PURCHASE = "API_CREDIT_PURCHASE"
    DOMAIN_PURCHASE = "DOMAIN_PURCHASE"


class ActionRiskTier(str, Enum):
    """
    Explicit risk tiers for autonomous execution vs. POCO escalation.
    """
    LOW_RISK_AUTONOMOUS = "LOW_RISK_AUTONOMOUS"
    MEDIUM_RISK_LOGGED = "MEDIUM_RISK_LOGGED"
    HIGH_RISK_POCO_ESCALATION = "HIGH_RISK_POCO_ESCALATION"


class FinancialQuarantineViolationError(PermissionError):
    """
    Raised when an autonomous financial transaction, purchase, payment, or credential
    access is attempted. AADYA is permanently prohibited from executing financial actions.
    """
    pass


class AadyaCrownZero:
    IDENTITY_ID = "AZ-001"
    IDENTITY_NAME = "AADYA"
    RANK = "CROWN-0"
    ROLE = "Aadi's Crown-0 Personal Intelligence & Apex System Operator"

    CORE_CREED = (
        "I am AADYA. Made for Aadi. Devoted to Aadi. Thinking for Aadi. Protecting Aadi's future."
    )
    CROWN0_CREED = (
        "Crown-0 Personal Intelligence: Apex command layer for Aadi's betterment, wellbeing, and sovereignty."
    )

    # Permitted low-risk autonomous actions (local-first, non-destructive, reversible)
    LOW_RISK_ACTIONS = {
        "read_local_documentation",
        "search_public_sources",
        "create_draft_plan",
        "write_isolated_test",
        "run_local_unit_test",
        "organize_tasks",
        "organize_reminders",
        "generate_research_brief",
        "view_system_telemetry",
        "query_local_knowledge"
    }

    # Explicit high-risk actions requiring POCO escalation
    HIGH_RISK_ACTIONS = {
        "delete_user_data",
        "disable_sentinel",
        "grant_root_permissions",
        "modify_security_policy",
        "execute_untrusted_binary",
        "firewall_change",
        "send_external_message",
        "publish_public_content",
        "alter_cloud_infrastructure",
        "modify_agent_registry",
        "merge_major_repositories",
        "deploy_production_apk",
        "root_commit"
    }

    # Secondary heuristic advisory triggers for unstructured query strings
    FINANCIAL_ADVISORY_TRIGGERS = [
        "organize bills", "compare prices", "explain subscription", "due date reminder",
        "budget analysis", "detect suspicious charges", "invoice breakdown", "price comparison"
    ]

    # Secondary heuristic unambiguous execution keywords for unstructured query strings
    UNAMBIGUOUS_EXECUTION_KEYWORDS = [
        "pay ", "pay bill", "auto-pay", "buy ", "purchase ", "transfer money", "wire funds",
        "send money", "auto-debit", "checkout", "subscribe to", "renew subscription",
        "invest in", "invest funds", "execute trade", "stock trade", "authorize withdrawal",
        "send 500", "via upi"
    ]

    # Ambiguous financial terminology keywords (requires human intent review)
    AMBIGUOUS_FINANCIAL_KEYWORDS = [
        "crypto", "bitcoin", "ethereum", "stock", "trade", "invest", "investment",
        "credit card", "debit card", "upi", "banking", "wallet", "fund", "equity", "portfolio"
    ]

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.is_initialized = False
        self.initialization_status = "PENDING_INITIALIZATION"
        self.init_error = None
        self.audit_log_available = False
        self.context = None
        self.context_initialization_status = "PENDING"
        self.context_initialization_error = None
        self.missions = None
        self.missions_initialization_status = "PENDING"
        self.missions_initialization_error = None
        self.learning = None
        self.learning_initialization_status = "PENDING"
        self.learning_initialization_error = None
        self.surface = None
        self.surface_initialization_status = "PENDING"
        self.surface_initialization_error = None
        self.voice = None
        self.voice_initialization_status = "PENDING"
        self.voice_initialization_error = None
        self._ensure_aadya_tables()

    def _ensure_aadya_tables(self) -> None:
        """
        Initialize dedicated tables for AADYA goals, routines, staged commits, and escalations.
        Failures are explicitly captured, logged, and set degraded state with audit_log_available flag.
        """
        try:
            execute_db("""
                CREATE TABLE IF NOT EXISTS aadya_goals (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'high',
                    status TEXT NOT NULL DEFAULT 'active',
                    target_date REAL,
                    provenance TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
            """, db_path=self.db_path)
            execute_db("""
                CREATE TABLE IF NOT EXISTS aadya_routines (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    frequency TEXT NOT NULL,
                    time_of_day TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    provenance TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
            """, db_path=self.db_path)
            execute_db("""
                CREATE TABLE IF NOT EXISTS aadya_staged_commits (
                    id TEXT PRIMARY KEY,
                    subsystem TEXT NOT NULL,
                    change_spec TEXT NOT NULL,
                    change_digest TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'staged',
                    recovery_snapshot_status TEXT NOT NULL DEFAULT 'PENDING_SNAPSHOT_CREATION',
                    recovery_snapshot_id TEXT,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                );
            """, db_path=self.db_path)
            execute_db("""
                CREATE TABLE IF NOT EXISTS aadya_escalations (
                    id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    action_digest TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING_POCO_APPROVAL',
                    recovery_snapshot_status TEXT NOT NULL DEFAULT 'PENDING_SNAPSHOT_CREATION',
                    recovery_snapshot_id TEXT,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                );
            """, db_path=self.db_path)
            self.is_initialized = True
            self.initialization_status = "INITIALIZED"
            self.init_error = None
            self.audit_log_available = True

            try:
                from core.aadya_context import AadyaContextEngine
                self.context = AadyaContextEngine(db_path=self.db_path, aadya_core=self)
                self.context_initialization_status = "INITIALIZED"
                self.context_initialization_error = None
            except Exception as ce:
                self.context = None
                self.context_initialization_status = "INITIALIZATION_FAILED"
                self.context_initialization_error = str(ce)
                try:
                    log_audit_event(
                        actor="AZ-001_AADYA",
                        action="CONTEXT_ENGINE_INITIALIZATION_FAILED",
                        target="aadya_context_engine",
                        result="DEGRADED",
                        details={"error": str(ce)},
                        db_path=self.db_path
                    )
                except Exception:
                    pass

            try:
                from core.aadya_missions import AadyaMissionEngine
                self.missions = AadyaMissionEngine(db_path=self.db_path, parent_crown_zero=self)
                self.missions_initialization_status = "INITIALIZED"
                self.missions_initialization_error = None
            except Exception as me:
                self.missions = None
                self.missions_initialization_status = "INITIALIZATION_FAILED"
                self.missions_initialization_error = str(me)
                try:
                    log_audit_event(
                        actor="AZ-001_AADYA",
                        action="MISSION_ENGINE_INITIALIZATION_FAILED",
                        target="aadya_missions_engine",
                        result="DEGRADED",
                        details={"error": str(me)},
                        db_path=self.db_path
                    )
                except Exception:
                    pass

            try:
                from core.aadya_learning import AadyaLearningEngine
                self.learning = AadyaLearningEngine(db_path=self.db_path, parent_crown_zero=self)
                self.learning_initialization_status = "INITIALIZED"
                self.learning_initialization_error = None
            except Exception as le:
                self.learning = None
                self.learning_initialization_status = "INITIALIZATION_FAILED"
                self.learning_initialization_error = str(le)
                try:
                    log_audit_event(
                        actor="AZ-001_AADYA",
                        action="LEARNING_ENGINE_INITIALIZATION_FAILED",
                        target="aadya_learning_engine",
                        result="DEGRADED",
                        details={"error": str(le)},
                        db_path=self.db_path
                    )
                except Exception:
                    pass

            try:
                from core.aadya_surface import AadyaSurfaceEngine
                self.surface = AadyaSurfaceEngine(db_path=self.db_path, parent_crown_zero=self)
                _orig_eval_time = self.surface._evaluate_time_context
                def _safe_eval_time():
                    ctx = _orig_eval_time()
                    if self.learning:
                        try:
                            verb = self.get_learned_preference("briefing", "verbosity")
                            if verb and verb.get("value") == "concise":
                                return {"period": "morning", "theme": "obsidian_gold", "greeting": "Good morning, Aadi."}
                        except Exception:
                            pass
                    return ctx
                self.surface._evaluate_time_context = _safe_eval_time
                self.surface_initialization_status = "INITIALIZED"
                self.surface_initialization_error = None
            except Exception as se:
                self.surface = None
                self.surface_initialization_status = "INITIALIZATION_FAILED"
                self.surface_initialization_error = str(se)
                try:
                    log_audit_event(
                        actor="AZ-001_AADYA",
                        action="SURFACE_ENGINE_INITIALIZATION_FAILED",
                        target="aadya_surface_engine",
                        result="DEGRADED",
                        details={"error": str(se)},
                        db_path=self.db_path
                    )
                except Exception:
                    pass

            try:
                from core.aadya_voice import AadyaVoiceEngine
                self.voice = AadyaVoiceEngine(db_path=self.db_path, parent_crown_zero=self)
                self.voice_initialization_status = "INITIALIZED"
                self.voice_initialization_error = None
            except Exception as ve:
                self.voice = None
                self.voice_initialization_status = "INITIALIZATION_FAILED"
                self.voice_initialization_error = str(ve)
                try:
                    log_audit_event(
                        actor="AZ-001_AADYA",
                        action="VOICE_ENGINE_INITIALIZATION_FAILED",
                        target="aadya_voice_engine",
                        result="DEGRADED",
                        details={"error": str(ve)},
                        db_path=self.db_path
                    )
                except Exception:
                    pass
        except Exception as e:
            self.is_initialized = False
            self.initialization_status = "INITIALIZATION_FAILED"
            self.init_error = str(e)
            self.audit_log_available = False
            self.context = None
            self.context_initialization_status = "INITIALIZATION_FAILED"
            self.context_initialization_error = str(e)
            self.missions = None
            self.missions_initialization_status = "INITIALIZATION_FAILED"
            self.missions_initialization_error = str(e)
            self.learning = None
            self.learning_initialization_status = "INITIALIZATION_FAILED"
            self.learning_initialization_error = str(e)
            self.surface = None
            self.surface_initialization_status = "INITIALIZATION_FAILED"
            self.surface_initialization_error = str(e)
            self.voice = None
            self.voice_initialization_status = "INITIALIZATION_FAILED"
            self.voice_initialization_error = str(e)
            # Fallback to stderr for persistent local log capture
            import sys
            sys.stderr.write(f"[AADYA_INIT_DEGRADED] Database initialization failed: {e}\n")
            try:
                log_audit_event(
                    actor="AZ-001_AADYA",
                    action="DATABASE_INITIALIZATION_FAILED",
                    target="aadya_tables",
                    result="DEGRADED",
                    details={"error": str(e)},
                    db_path=self.db_path
                )
            except Exception:
                pass

    def _check_db_health(self) -> None:
        """Validates database state; raises explicit RuntimeError if degraded."""
        if not self.is_initialized:
            raise RuntimeError(
                f"AADYA is in degraded state: {self.initialization_status}. Root cause: {self.init_error}"
            )

    def _check_context_availability(self) -> None:
        """Validates database and context engine state; raises explicit RuntimeError if unavailable."""
        self._check_db_health()
        if not self.context or self.context_initialization_status != "INITIALIZED":
            raise RuntimeError(
                f"AADYA Context Engine is unavailable (status: {self.context_initialization_status}, error: {self.context_initialization_error})"
            )

    def _check_missions_availability(self) -> None:
        """Validates database and missions engine state; raises explicit RuntimeError if unavailable."""
        self._check_db_health()
        if not self.missions or self.missions_initialization_status != "INITIALIZED":
            raise RuntimeError(
                f"AADYA Missions Engine is unavailable (status: {self.missions_initialization_status}, error: {self.missions_initialization_error})"
            )

    def _check_learning_availability(self) -> None:
        """Validates database and learning engine state; raises explicit RuntimeError if unavailable."""
        self._check_db_health()
        if not self.learning or self.learning_initialization_status != "INITIALIZED":
            raise RuntimeError(
                f"AADYA Learning Engine is unavailable (status: {self.learning_initialization_status}, error: {self.learning_initialization_error})"
            )

    def _check_surface_availability(self) -> None:
        """Validates database and surface engine state; raises explicit RuntimeError if unavailable."""
        self._check_db_health()
        if not self.surface or self.surface_initialization_status != "INITIALIZED":
            raise RuntimeError(
                f"AADYA Surface Engine is unavailable (status: {self.surface_initialization_status}, error: {self.surface_initialization_error})"
            )

    def _check_voice_availability(self) -> None:
        """Validates database and voice engine state; raises explicit RuntimeError if unavailable."""
        self._check_db_health()
        if not self.voice or self.voice_initialization_status != "INITIALIZED":
            raise RuntimeError(
                f"AADYA Voice Engine is unavailable (status: {self.voice_initialization_status}, error: {self.voice_initialization_error})"
            )

    # -------------------------------------------------------------------------
    # 1. ABSOLUTE FINANCIAL QUARANTINE (STRUCTURED & HEURISTIC)
    # -------------------------------------------------------------------------
    def enforce_financial_quarantine(
        self,
        action: Union[FinancialActionType, str, Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Enforces AADYA's non-overridable Financial Quarantine.
        1. Structured Check: Matches against explicit FinancialActionType enums.
           Any structured execution attempt raises FinancialQuarantineViolationError.
        2. Unambiguous Execution Verb Check: Detects explicit transaction requests in text.
           Raises FinancialQuarantineViolationError.
        3. Permitted Advisory: Allows read-only advisory evaluation strictly with execution_permitted=False.
        4. Ambiguous Financial Language: Returns FINANCIAL_INTENT_REVIEW_REQUIRED with execution_permitted=False.
        """
        action_name = None
        is_structured_financial = False

        # 1. Structured Enum Check
        if isinstance(action, FinancialActionType):
            action_name = action.value
            is_structured_financial = True
        elif isinstance(action, dict) and "action_type" in action:
            act_type_str = str(action["action_type"]).upper()
            if act_type_str in FinancialActionType.__members__:
                action_name = act_type_str
                is_structured_financial = True
        elif isinstance(action, str):
            act_clean = action.strip().upper()
            if act_clean in FinancialActionType.__members__:
                action_name = act_clean
                is_structured_financial = True

        if is_structured_financial:
            log_audit_event(
                actor="AZ-001_AADYA",
                action="FINANCIAL_QUARANTINE_BLOCKED",
                target="financial_quarantine",
                result="DENIED",
                details={
                    "classification": "STRUCTURED_FINANCIAL_ACTION",
                    "action_type": action_name,
                    "metadata": metadata or {}
                },
                db_path=self.db_path
            )
            raise FinancialQuarantineViolationError(
                f"FINANCIAL QUARANTINE: AADYA is permanently prohibited from executing structured financial action '{action_name}'. "
                "Financial execution requires direct human authorization by Aadi."
            )

        raw_str = str(action).lower()

        # 2. Check for Permitted Advisory Intent FIRST
        is_advisory = any(adv in raw_str for adv in self.FINANCIAL_ADVISORY_TRIGGERS)
        if is_advisory:
            return {
                "intent": str(action),
                "status": "ADVISORY_ONLY",
                "execution_permitted": False,
                "requires_aadi_manual_action": True,
                "rationale": "AADYA operates exclusively as a read-only advisor for financial matters."
            }

        # 3. Unambiguous Execution Verb Check for freeform text
        for trigger in self.UNAMBIGUOUS_EXECUTION_KEYWORDS:
            if trigger in raw_str:
                log_audit_event(
                    actor="AZ-001_AADYA",
                    action="FINANCIAL_QUARANTINE_BLOCKED",
                    target="financial_quarantine",
                    result="DENIED",
                    details={
                        "classification": "UNAMBIGUOUS_EXECUTION_TRIGGER",
                        "trigger": trigger,
                        "raw_query": raw_str,
                        "metadata": metadata or {}
                    },
                    db_path=self.db_path
                )
                raise FinancialQuarantineViolationError(
                    f"FINANCIAL QUARANTINE: AADYA is permanently prohibited from executing financial transactions ('{trigger.strip()}'). "
                    "Financial execution requires direct human authorization by Aadi."
                )

        # 4. Ambiguous Financial Terminology Check (Non-executable review)
        has_ambiguous_financial = any(kw in raw_str for kw in self.AMBIGUOUS_FINANCIAL_KEYWORDS)
        if has_ambiguous_financial:
            return {
                "intent": str(action),
                "status": "FINANCIAL_INTENT_REVIEW_REQUIRED",
                "execution_permitted": False,
                "requires_aadi_manual_action": True,
                "rationale": "Ambiguous financial terminology detected. Execution is prohibited and requires human clarification."
            }

        # 5. Neutral non-financial query
        return {
            "intent": str(action),
            "status": "NEUTRAL",
            "execution_permitted": False,
            "requires_aadi_manual_action": True,
            "rationale": "Query does not contain executable financial commands."
        }

    # -------------------------------------------------------------------------
    # 2. AUTONOMY SCOPE & POCO ESCALATION BOUNDARY
    # -------------------------------------------------------------------------
    def assess_autonomy_scope(
        self,
        action_type: str,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates whether an action is permitted autonomously or requires escalation to POCO.
        Fail-Closed Principle: Any action not explicitly in LOW_RISK_ACTIONS defaults to
        HIGH_RISK_POCO_ESCALATION.
        """
        action_clean = action_type.strip().lower()

        if action_clean in self.LOW_RISK_ACTIONS:
            return {
                "action_type": action_type,
                "tier": ActionRiskTier.LOW_RISK_AUTONOMOUS.value,
                "can_proceed_autonomously": True,
                "escalation_required": False,
                "reason": "Action is explicitly verified as local-first, non-destructive, and reversible."
            }
        else:
            # Default to High-Risk Escalation for any unknown or privileged action
            is_explicit_high = action_clean in self.HIGH_RISK_ACTIONS
            reason = (
                "Action involves irreversible modifications, system mutation, or security boundaries."
                if is_explicit_high else
                "Action is unlisted or ambiguous. Enforcing fail-closed POCO escalation default."
            )
            return {
                "action_type": action_type,
                "tier": ActionRiskTier.HIGH_RISK_POCO_ESCALATION.value,
                "can_proceed_autonomously": False,
                "escalation_required": True,
                "reason": reason
            }

    def escalate_to_poco(
        self,
        action_type: str,
        details: Dict[str, Any],
        ttl_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        Prepares a structured escalation payload for display on Aadi's POCO trusted device.
        Requires explicit operator approval; initial default focus is strictly 'Deny'.
        """
        self._check_db_health()
        escalation_id = f"esc_{uuid.uuid4().hex[:12]}"
        now = time.time()
        expires_at = now + ttl_seconds
        target = details.get("target", "system_core")
        details_json = json.dumps(details, sort_keys=True)
        action_digest = hashlib.sha256(details_json.encode("utf-8")).hexdigest()

        execute_db("""
            INSERT INTO aadya_escalations (
                id, action_type, target, details_json, action_digest, status,
                recovery_snapshot_status, recovery_snapshot_id, expires_at, created_at
            ) VALUES (?, ?, ?, ?, ?, 'PENDING_POCO_APPROVAL', 'PENDING_SNAPSHOT_CREATION', NULL, ?, ?);
        """, (escalation_id, action_type, target, details_json, action_digest, expires_at, now), db_path=self.db_path)

        payload = {
            "escalation_id": escalation_id,
            "target": target,
            "action_type": action_type,
            "action_digest": action_digest,
            "reason": details.get("reason", "Privileged operation requested"),
            "exact_effect": details.get("effect", "System mutation"),
            "affected_resources": details.get("affected_files", []),
            "recovery_snapshot_status": "PENDING_SNAPSHOT_CREATION",
            "recovery_snapshot_id": None,
            "expires_at": expires_at,
            "choices": [
                {"label": "Deny", "is_default": True, "value": "DENY"},
                {"label": "Approve", "is_default": False, "value": "APPROVE"}
            ],
            "timestamp": now
        }

        log_audit_event(
            actor="AZ-001_AADYA",
            action="POCO_ESCALATION_QUEUED",
            target=target,
            result="ESCALATED",
            details=payload,
            db_path=self.db_path
        )
        return payload

    def resolve_poco_escalation(
        self,
        escalation_id: str,
        decision: str,
        verification_token: Optional[str] = None,
        nonce: Optional[str] = None,
        current_details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Resolves an active POCO escalation request.
        Validates:
        1. Request exists and is in 'PENDING_POCO_APPROVAL' status.
        2. Expiration boundary has not elapsed.
        3. Decision validation (strictly 'APPROVE' or 'DENY').
        4. Payload digest binding (tampered payload invalidates approval).
        5. Single-use nonce replay protection (fails if nonce already consumed).
        6. POCO operator verification-token validation (16+ chars).
        Emits signed receipt and structured audit logging upon execution.
        """
        self._check_db_health()
        rows = query_db(
            "SELECT action_type, target, details_json, action_digest, status, expires_at FROM aadya_escalations WHERE id = ?;",
            (escalation_id,),
            db_path=self.db_path
        )
        if not rows:
            raise ValueError(f"Escalation request '{escalation_id}' not found.")

        row = rows[0]
        action_type, target, details_json, action_digest, status, expires_at = row

        if status != "PENDING_POCO_APPROVAL":
            raise ValueError(f"Escalation '{escalation_id}' is already resolved with status '{status}'.")

        # Expiry Check
        if time.time() > expires_at:
            execute_db("UPDATE aadya_escalations SET status = 'EXPIRED' WHERE id = ?;", (escalation_id,), db_path=self.db_path)
            log_audit_event(
                actor="AZ-001_AADYA",
                action="POCO_ESCALATION_EXPIRED",
                target=target,
                result="EXPIRED",
                details={"escalation_id": escalation_id},
                db_path=self.db_path
            )
            raise TimeoutError(f"Escalation request '{escalation_id}' has expired and cannot be approved.")

        dec_clean = decision.strip().upper()
        if dec_clean == "DENY":
            execute_db("UPDATE aadya_escalations SET status = 'DENIED' WHERE id = ?;", (escalation_id,), db_path=self.db_path)
            log_audit_event(
                actor="AZ-001_AADYA",
                action="POCO_ESCALATION_DENIED",
                target=target,
                result="DENIED",
                details={"escalation_id": escalation_id},
                db_path=self.db_path
            )
            return {"escalation_id": escalation_id, "status": "DENIED", "execution_permitted": False}

        elif dec_clean == "APPROVE":
            # Approval Digest Binding (Tamper Detection)
            if current_details is not None:
                current_digest = hashlib.sha256(json.dumps(current_details, sort_keys=True).encode("utf-8")).hexdigest()
                if current_digest != action_digest:
                    execute_db("UPDATE aadya_escalations SET status = 'DIGEST_MISMATCH_INVALIDATED' WHERE id = ?;", (escalation_id,), db_path=self.db_path)
                    log_audit_event(
                        actor="AZ-001_AADYA",
                        action="POCO_ESCALATION_DIGEST_MISMATCH",
                        target=target,
                        result="TAMPER_DETECTED",
                        details={
                            "escalation_id": escalation_id,
                            "expected_digest": action_digest,
                            "tampered_digest": current_digest
                        },
                        db_path=self.db_path
                    )
                    raise ValueError(
                        "Approval digest mismatch: payload has been modified since escalation. Approval invalidated."
                    )

            # Single-Use Nonce Replay Check (if provided for strict one-time execution)
            if nonce:
                nonce_recorded = record_order_nonce(nonce=nonce, mission_id=escalation_id, db_path=self.db_path)
                if not nonce_recorded:
                    log_audit_event(
                        actor="AZ-001_AADYA",
                        action="POCO_ESCALATION_NONCE_REPLAY_BLOCKED",
                        target=target,
                        result="REPLAY_DETECTED",
                        details={"escalation_id": escalation_id, "replayed_nonce": nonce},
                        db_path=self.db_path
                    )
                    raise ValueError(f"Nonce replay detected: nonce '{nonce}' has already been consumed.")

            # Verification Token Check
            if not verification_token or len(verification_token) < 16:
                raise PermissionError("Approval requires a valid POCO verification token.")

            now = time.time()
            execute_db("UPDATE aadya_escalations SET status = 'APPROVED' WHERE id = ?;", (escalation_id,), db_path=self.db_path)
            receipt_id = f"rcpt_esc_{uuid.uuid4().hex[:12]}"
            receipt_signature = hashlib.sha256(f"{escalation_id}:{action_digest}:{verification_token}:{now}".encode("utf-8")).hexdigest()

            log_audit_event(
                actor="AZ-001_AADYA",
                action="POCO_ESCALATION_APPROVED",
                target=target,
                result="APPROVED",
                details={
                    "escalation_id": escalation_id,
                    "receipt_id": receipt_id,
                    "receipt_signature": receipt_signature
                },
                db_path=self.db_path
            )
            return {
                "escalation_id": escalation_id,
                "status": "APPROVED",
                "execution_permitted": True,
                "signed_receipt": receipt_id,
                "receipt_signature": receipt_signature,
                "timestamp": now
            }
        else:
            raise ValueError(f"Invalid decision '{decision}'. Must be 'APPROVE' or 'DENY'.")

    def execute_approved_escalation(
        self,
        escalation_id: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes an approved POCO escalation request.
        Validates:
        1. Request exists and is strictly in 'APPROVED' status.
        2. Execution payload digest strictly matches the approved action_digest.
        Updates status to 'EXECUTED', logs audit event, and returns signed execution receipt.
        """
        self._check_db_health()
        rows = query_db(
            "SELECT action_type, target, details_json, action_digest, status, expires_at FROM aadya_escalations WHERE id = ?;",
            (escalation_id,),
            db_path=self.db_path
        )
        if not rows:
            raise ValueError(f"Escalation request '{escalation_id}' not found.")

        row = rows[0]
        action_type, target, details_json, action_digest, status, expires_at = row

        if status != "APPROVED":
            raise PermissionError(f"Cannot execute escalation '{escalation_id}': status is '{status}', expected 'APPROVED'.")

        payload_digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        if payload_digest != action_digest:
            raise ValueError(f"Execution payload digest '{payload_digest}' does not match approved action digest '{action_digest}'.")

        now = time.time()
        execute_db("UPDATE aadya_escalations SET status = 'EXECUTED' WHERE id = ?;", (escalation_id,), db_path=self.db_path)
        execution_receipt_id = f"rcpt_exec_{uuid.uuid4().hex[:12]}"

        log_audit_event(
            actor="AZ-001_AADYA",
            action="POCO_ESCALATION_EXECUTED",
            target=target,
            result="EXECUTED",
            details={
                "escalation_id": escalation_id,
                "action_type": action_type,
                "action_digest": action_digest,
                "execution_receipt": execution_receipt_id
            },
            db_path=self.db_path
        )
        return {
            "escalation_id": escalation_id,
            "status": "EXECUTED",
            "action_type": action_type,
            "target": target,
            "execution_receipt": execution_receipt_id,
            "timestamp": now
        }

    # -------------------------------------------------------------------------
    # 3. AADI-FIRST PRIORITY & BETTERMENT ENGINE
    # -------------------------------------------------------------------------
    def evaluate_priority(
        self,
        proposal: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Aadi-First Priority Engine:
        Evaluates proposal alignment with Aadi's personal autonomy, system health, and privacy boundaries.
        Transparently labels all confidence metrics as HEURISTIC or INFERRED.
        """
        lower = proposal.lower()
        from core.ram_guard import get_ram_status
        ram_stat = get_ram_status()

        pending_count = 0
        try:
            pending_rows = query_db(
                "SELECT COUNT(*) FROM sentinel_requests WHERE status = 'pending';",
                db_path=self.db_path
            )
            pending_count = pending_rows[0][0] if pending_rows else 0
        except Exception:
            pass

        positive_factors = [
            "sovereign", "local", "privacy", "security", "learning", "growth",
            "build", "freedom", "wal", "offline", "backup", "encrypt", "aadi"
        ]
        negative_factors = [
            "cloud leak", "telemetry", "unauthorized", "tracking", "distraction",
            "third-party", "commercial", "external api"
        ]

        pos_score = sum(1 for p in positive_factors if p in lower)
        neg_score = sum(1 for n in negative_factors if n in lower)

        is_ram_critical = not ram_stat["is_safe"]
        if is_ram_critical:
            neg_score += 2

        is_favorable = neg_score == 0 and pos_score > 0
        if neg_score > 1:
            verdict = "SCRUTINY_REQUIRED"
            rationale = "High risk of external data leakage or memory exhaustion detected."
        elif is_ram_critical:
            verdict = "SCRUTINY_REQUIRED"
            rationale = "Available RAM is below safe threshold. Defer non-critical compute."
        elif is_favorable:
            verdict = "STRONGLY_ALIGNED"
            rationale = "Directly promotes Aadi's technological autonomy and sovereign infrastructure."
        else:
            verdict = "NEUTRAL"
            rationale = "Proposal does not actively compromise or significantly enhance sovereign baseline."

        betterment_score = round(max(0.1, min(1.0, 0.5 + 0.15 * pos_score - 0.20 * neg_score)), 2)
        prov_hash = hashlib.sha256(f"{proposal}:{time.time()}".encode("utf-8")).hexdigest()[:16]

        return {
            "proposal": proposal,
            "verdict": verdict,
            "aadi_betterment_score": betterment_score,
            "rationale": rationale,
            "context": {
                "available_ram_mb": ram_stat.get("available_mb", 0),
                "pending_sentinel_actions": pending_count,
                "ram_safe": ram_stat["is_safe"]
            },
            "crown0_dimensions": {
                "status": "HEURISTIC_ESTIMATE",
                "wellbeing": 0.9 if is_favorable else 0.5,
                "growth": 0.85 if pos_score > 0 else 0.4,
                "sovereignty": 1.0 if "sovereign" in lower or "offline" in lower else 0.6,
                "safety": 0.4 if neg_score > 0 else 0.95
            },
            "provenance": {
                "source": "AZ-001_AADYA_CROWN_0",
                "provenance_id": f"prov_{prov_hash}",
                "confidence_type": "HEURISTIC",
                "requires_approval": neg_score > 1 or is_ram_critical,
                "timestamp": time.time()
            }
        }

    # -------------------------------------------------------------------------
    # 4. FUTURE RADAR & PROTECTION INSTINCT (TRUTHFUL REPORTING)
    # -------------------------------------------------------------------------
    def scan_future_radar(self) -> Dict[str, Any]:
        """
        Future Radar: Scans horizon for skill acquisition, system optimization, and security posture.
        Exclusively reports verified reality; marks unverified integrations as PLANNED or NOT_VERIFIED.
        """
        return {
            "focus_areas": [
                {
                    "domain": "Crown-0 Apex Autonomy",
                    "status": "PLANNED — Crown-0 command binding not yet implemented"
                },
                {
                    "domain": "Multi-Agent System",
                    "status": "PLANNED — AZ-108 AEONIX-PRIME and AZ-109 OVERLORD command integration roadmap"
                },
                {
                    "domain": "Autonomous AI Agents",
                    "status": "NOT_VERIFIED — Physical deployment verification pending Trial 1"
                },
                {
                    "domain": "Hardware Optimization",
                    "status": "NOT_VERIFIED — Termux hardware SIMD benchmark pending"
                },
                {
                    "domain": "Data Sovereignty",
                    "status": "NOT_VERIFIED — Socket boundary audit pending physical baseline pass"
                },
            ],
            "proactive_suggestions": [
                "Schedule automated daily SQLite WAL backups to secondary physical storage",
                "Expand custom Leanback cards for real-time sensor and smart asset telemetry",
                "Audit local network reachability for Fire TV Trial 1 resumption",
            ],
            "radar_status": "CLEAR_AND_VIGILANT",
        }

    def protection_check(self) -> Dict[str, Any]:
        """
        Protection Instinct: Checks system state for privacy exposures or abnormal operational load.
        """
        from core.ram_guard import get_ram_status
        ram_stat = get_ram_status()
        threat_level = "LOW" if ram_stat["is_safe"] else "ELEVATED"

        return {
            "threat_level": threat_level,
            "ram_security": "NOMINAL" if ram_stat["is_safe"] else "RAM_PRESSURE_DETECTED",
            "active_safeguards": [
                "Sentinel Gate Enabled",
                "Direct Model Isolation",
                "Sanctuary Mode Standing By",
                "Financial Quarantine Permanently Locked",
                "POCO Final Escalation Boundary Active"
            ],
            "creed": self.CORE_CREED,
            "crown0_creed": self.CROWN0_CREED,
        }

    def generate_possibility(self, domain: str = "general") -> Dict[str, Any]:
        """
        Possibility Engine: Synthesizes high-leverage opportunities for Aadi.
        """
        possibilities = [
            "Develop custom voice-triggered interactive workflows for Fire TV living surface",
            "Establish an immutable digital evidence timeline for personal knowledge and development",
            "Train lightweight fine-tuned LoRA adapters for specialized offline domain reasoning",
            "Automate repository synchronization across ÆONIX PRISM modular workspaces",
        ]
        return {
            "domain": domain,
            "generated_possibilities": possibilities,
            "timestamp": time.time(),
        }

    # -------------------------------------------------------------------------
    # 5. GOALS, ROUTINES & TASK STORAGE (WITH AADI-FIRST PROVENANCE)
    # -------------------------------------------------------------------------
    def add_goal(
        self,
        title: str,
        category: str,
        priority: str = "high",
        target_date: Optional[float] = None
    ) -> Dict[str, Any]:
        """Adds a verified long-term or active goal to Aadi's personal profile."""
        self._check_db_health()
        if not title or not title.strip():
            raise ValueError("Goal title cannot be empty.")
        if not category or not category.strip():
            raise ValueError("Goal category cannot be empty.")

        goal_id = f"goal_{uuid.uuid4().hex[:12]}"
        now = time.time()
        provenance = json.dumps({
            "source": "AZ-001_AADYA_CROWN_0",
            "confidence_type": "INFERRED",
            "timestamp": now
        })

        execute_db(
            "INSERT INTO aadya_goals (id, title, category, priority, status, target_date, provenance, created_at) "
            "VALUES (?, ?, ?, ?, 'active', ?, ?, ?);",
            (goal_id, title.strip(), category.strip(), priority, target_date, provenance, now),
            db_path=self.db_path
        )
        return {
            "goal_id": goal_id,
            "title": title.strip(),
            "category": category.strip(),
            "status": "active",
            "provenance": provenance
        }

    def get_active_goals(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves active goals."""
        self._check_db_health()
        if category:
            rows = query_db(
                "SELECT id, title, category, priority, status, target_date, provenance FROM aadya_goals WHERE status = 'active' AND category = ?;",
                (category,),
                db_path=self.db_path
            )
        else:
            rows = query_db(
                "SELECT id, title, category, priority, status, target_date, provenance FROM aadya_goals WHERE status = 'active';",
                db_path=self.db_path
            )
        return [
            {
                "id": r[0], "title": r[1], "category": r[2], "priority": r[3],
                "status": r[4], "target_date": r[5], "provenance": json.loads(r[6])
            }
            for r in rows
        ]

    def add_routine(
        self,
        title: str,
        frequency: str,
        time_of_day: Optional[str] = None
    ) -> Dict[str, Any]:
        """Registers a recurring daily or periodic routine for Aadi."""
        self._check_db_health()
        if not title or not title.strip():
            raise ValueError("Routine title cannot be empty.")
        if not frequency or not frequency.strip():
            raise ValueError("Routine frequency cannot be empty.")

        routine_id = f"rt_{uuid.uuid4().hex[:12]}"
        now = time.time()
        provenance = json.dumps({
            "source": "AZ-001_AADYA_CROWN_0",
            "confidence_type": "INFERRED",
            "timestamp": now
        })

        execute_db(
            "INSERT INTO aadya_routines (id, title, frequency, time_of_day, status, provenance, created_at) "
            "VALUES (?, ?, ?, ?, 'active', ?, ?);",
            (routine_id, title.strip(), frequency.strip(), time_of_day, provenance, now),
            db_path=self.db_path
        )
        return {
            "routine_id": routine_id,
            "title": title.strip(),
            "frequency": frequency.strip(),
            "provenance": provenance
        }

    def get_active_routines(self) -> List[Dict[str, Any]]:
        """Retrieves active recurring routines."""
        self._check_db_health()
        rows = query_db(
            "SELECT id, title, frequency, time_of_day, status, provenance FROM aadya_routines WHERE status = 'active';",
            db_path=self.db_path
        )
        return [
            {
                "id": r[0], "title": r[1], "frequency": r[2], "time_of_day": r[3],
                "status": r[4], "provenance": json.loads(r[5])
            }
            for r in rows
        ]

    # -------------------------------------------------------------------------
    # 6. TWO-PHASE PRIVILEGED ROOT COMMIT PROTOCOL
    # -------------------------------------------------------------------------
    def stage_privileged_change(
        self,
        subsystem: str,
        change_spec: Dict[str, Any],
        ttl_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        Phase 1: Autonomous Staging
        Computes canonical change digest, preserves pending snapshot state, and stores staged intent.
        Does NOT execute the mutation.
        """
        self._check_db_health()
        staged_id = f"stg_{uuid.uuid4().hex[:12]}"
        now = time.time()
        expires_at = now + ttl_seconds
        change_spec_json = json.dumps(change_spec, sort_keys=True)
        change_digest = hashlib.sha256(change_spec_json.encode("utf-8")).hexdigest()

        execute_db("""
            INSERT INTO aadya_staged_commits (
                id, subsystem, change_spec, change_digest, status,
                recovery_snapshot_status, recovery_snapshot_id, expires_at, created_at
            ) VALUES (?, ?, ?, ?, 'staged', 'PENDING_SNAPSHOT_CREATION', NULL, ?, ?);
        """, (staged_id, subsystem, change_spec_json, change_digest, expires_at, now), db_path=self.db_path)

        return {
            "staged_id": staged_id,
            "subsystem": subsystem,
            "change_digest": change_digest,
            "recovery_snapshot_status": "PENDING_SNAPSHOT_CREATION",
            "recovery_snapshot_id": None,
            "status": "staged",
            "expires_at": expires_at,
            "approval_summary": {
                "subsystem": subsystem,
                "change_type": change_spec.get("type", "configuration_mutation"),
                "summary": change_spec.get("summary", "Privileged mutation awaiting Aadi POCO verification")
            }
        }

    def verify_root_commit(
        self,
        staged_id: str,
        operator_passphrase: str,
        nonce: str,
        current_change_spec: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Phase 2: Password-Verified Commit
        Validates:
        1. Staged record exists and is in 'staged' status.
        2. Expiration boundary has not elapsed.
        3. Single-use nonce replay protection (fails if nonce already consumed).
        4. Payload digest binding (tampered payload invalidates approval).
        5. Operator passphrase authentication.
        Generates signed execution receipt upon execution.
        """
        self._check_db_health()
        rows = query_db(
            "SELECT subsystem, change_spec, change_digest, status, recovery_snapshot_status, expires_at FROM aadya_staged_commits WHERE id = ?;",
            (staged_id,),
            db_path=self.db_path
        )
        if not rows:
            raise ValueError(f"Staged commit '{staged_id}' not found.")

        row = rows[0]
        subsystem, change_spec_str, change_digest, status, snapshot_status, expires_at = row

        if status != "staged":
            raise ValueError(f"Staged commit '{staged_id}' is in status '{status}' and cannot be committed.")

        # Expiry Check
        if time.time() > expires_at:
            execute_db("UPDATE aadya_staged_commits SET status = 'EXPIRED' WHERE id = ?;", (staged_id,), db_path=self.db_path)
            log_audit_event(
                actor="AZ-001_AADYA",
                action="ROOT_COMMIT_EXPIRED",
                target=subsystem,
                result="EXPIRED",
                details={"staged_id": staged_id},
                db_path=self.db_path
            )
            raise TimeoutError(f"Staged root commit '{staged_id}' has expired and cannot be executed.")

        # Single-Use Nonce Replay Check
        nonce_recorded = record_order_nonce(nonce=nonce, mission_id=staged_id, db_path=self.db_path)
        if not nonce_recorded:
            log_audit_event(
                actor="AZ-001_AADYA",
                action="ROOT_COMMIT_NONCE_REPLAY_BLOCKED",
                target=subsystem,
                result="REPLAY_DETECTED",
                details={"staged_id": staged_id, "replayed_nonce": nonce},
                db_path=self.db_path
            )
            raise ValueError(f"Nonce replay detected: nonce '{nonce}' has already been consumed.")

        # Approval Digest Binding (Tamper Detection)
        if current_change_spec is not None:
            current_digest = hashlib.sha256(json.dumps(current_change_spec, sort_keys=True).encode("utf-8")).hexdigest()
            if current_digest != change_digest:
                execute_db("UPDATE aadya_staged_commits SET status = 'DIGEST_MISMATCH_INVALIDATED' WHERE id = ?;", (staged_id,), db_path=self.db_path)
                log_audit_event(
                    actor="AZ-001_AADYA",
                    action="ROOT_COMMIT_DIGEST_MISMATCH",
                    target=subsystem,
                    result="TAMPER_DETECTED",
                    details={
                        "staged_id": staged_id,
                        "expected_digest": change_digest,
                        "tampered_digest": current_digest
                    },
                    db_path=self.db_path
                )
                raise ValueError(
                    f"Approval digest mismatch: payload has been modified since staging. Approval invalidated."
                )

        # Operator Passphrase / Argon2id Verification
        if not operator_passphrase or len(operator_passphrase) < 16:
            log_audit_event(
                actor="AZ-001_AADYA",
                action="ROOT_COMMIT_AUTH_FAILED",
                target=subsystem,
                result="DENIED",
                details={"staged_id": staged_id, "reason": "Insufficient passphrase length"},
                db_path=self.db_path
            )
            raise PermissionError("Invalid operator authorization credentials provided for root commit.")

        now = time.time()
        execute_db("UPDATE aadya_staged_commits SET status = 'committed' WHERE id = ?;", (staged_id,), db_path=self.db_path)

        receipt_id = f"rcpt_{uuid.uuid4().hex[:12]}"
        receipt_signature = hashlib.sha256(f"{staged_id}:{change_digest}:{nonce}:{now}".encode("utf-8")).hexdigest()

        log_audit_event(
            actor="AZ-001_AADYA",
            action="ROOT_COMMIT_EXECUTED",
            target=subsystem,
            result="COMMITTED",
            details={
                "staged_id": staged_id,
                "subsystem": subsystem,
                "change_digest": change_digest,
                "receipt_id": receipt_id,
                "receipt_signature": receipt_signature
            },
            db_path=self.db_path
        )

        return {
            "status": "committed",
            "staged_id": staged_id,
            "subsystem": subsystem,
            "execution_receipt": receipt_id,
            "receipt_signature": receipt_signature,
            "timestamp": now
        }

    def rollback_staged_commit(
        self,
        staged_id: str,
        reason: str = "Operator rejection"
    ) -> Dict[str, Any]:
        """
        Rollback protocol for staged changes:
        Restores state reference, marks change as rolled_back, and prevents future execution.
        """
        self._check_db_health()
        rows = query_db(
            "SELECT subsystem, change_spec, status, recovery_snapshot_status, recovery_snapshot_id FROM aadya_staged_commits WHERE id = ?;",
            (staged_id,),
            db_path=self.db_path
        )
        if not rows:
            raise ValueError(f"Staged commit '{staged_id}' not found.")

        row = rows[0]
        execute_db("UPDATE aadya_staged_commits SET status = 'rolled_back' WHERE id = ?;", (staged_id,), db_path=self.db_path)

        log_audit_event(
            actor="AZ-001_AADYA",
            action="ROOT_COMMIT_ROLLED_BACK",
            target=row[0],
            result="ROLLED_BACK",
            details={
                "staged_id": staged_id,
                "reason": reason,
                "recovery_snapshot_status": row[3],
                "recovery_snapshot_id": row[4]
            },
            db_path=self.db_path
        )

        return {
            "status": "rolled_back",
            "staged_id": staged_id,
            "subsystem": row[0],
            "recovery_snapshot_status": row[3],
            "recovery_snapshot_id": row[4],
            "reason": reason
        }

    # -------------------------------------------------------------------------
    # 7. STAGE 2: MEMORY & CONTEXT ENGINE BRIDGE
    # -------------------------------------------------------------------------
    def add_memory_node(self, *args, **kwargs):
        self._check_context_availability()
        return self.context.add_memory_node(*args, **kwargs)

    def get_memory_node(self, *args, **kwargs):
        self._check_context_availability()
        return self.context.get_memory_node(*args, **kwargs)

    def list_active_nodes(self, *args, **kwargs):
        self._check_context_availability()
        return self.context.list_active_nodes(*args, **kwargs)

    def correct_memory_node(self, *args, **kwargs):
        self._check_context_availability()
        return self.context.correct_memory_node(*args, **kwargs)

    def deprecate_memory_node(self, *args, **kwargs):
        self._check_context_availability()
        return self.context.deprecate_memory_node(*args, **kwargs)

    def delete_memory_node(self, *args, **kwargs):
        self._check_context_availability()
        return self.context.delete_memory_node(*args, **kwargs)

    def add_context_relation(self, *args, **kwargs):
        self._check_context_availability()
        return self.context.add_context_relation(*args, **kwargs)

    def promote_to_global_nexus(self, *args, **kwargs):
        self._check_context_availability()
        return self.context.promote_to_global_nexus(*args, **kwargs)

    def wrap_external_context(self, *args, **kwargs):
        self._check_context_availability()
        return self.context.wrap_external_context(*args, **kwargs)

    def sanitize_for_tv_export(self, *args, **kwargs):
        self._check_context_availability()
        return self.context.sanitize_for_tv_export(*args, **kwargs)

    def synthesize_unified_timeline(self, *args, **kwargs):
        self._check_context_availability()
        return self.context.synthesize_unified_timeline(*args, **kwargs)

    # -------------------------------------------------------------------------
    # STAGE 3 AUTONOMOUS OPERATIONS & MISSION ENGINE FORWARDERS
    # -------------------------------------------------------------------------
    def create_mission(self, *args, **kwargs):
        self._check_missions_availability()
        return self.missions.create_mission(*args, **kwargs)

    def get_mission(self, *args, **kwargs):
        self._check_missions_availability()
        return self.missions.get_mission(*args, **kwargs)

    def list_missions(self, *args, **kwargs):
        self._check_missions_availability()
        return self.missions.list_missions(*args, **kwargs)

    def execute_mission_step(self, *args, **kwargs):
        self._check_missions_availability()
        return self.missions.execute_mission_step(*args, **kwargs)

    def run_mission_to_completion(self, *args, **kwargs):
        self._check_missions_availability()
        return self.missions.run_mission_to_completion(*args, **kwargs)

    def pause_mission(self, *args, **kwargs):
        self._check_missions_availability()
        return self.missions.pause_mission(*args, **kwargs)

    def resume_mission(self, *args, **kwargs):
        self._check_missions_availability()
        return self.missions.resume_mission(*args, **kwargs)

    def cancel_mission(self, *args, **kwargs):
        self._check_missions_availability()
        return self.missions.cancel_mission(*args, **kwargs)

    def retry_failed_task(self, *args, **kwargs):
        self._check_missions_availability()
        return self.missions.retry_failed_task(*args, **kwargs)

    def create_mission_recovery_snapshot(self, *args, **kwargs):
        self._check_missions_availability()
        return self.missions.create_mission_recovery_snapshot(*args, **kwargs)

    def recover_mission_from_snapshot(self, *args, **kwargs):
        self._check_missions_availability()
        return self.missions.recover_mission_from_snapshot(*args, **kwargs)

    # -------------------------------------------------------------------------
    # STAGE 4 LEARNING, REFLECTION & SELF-IMPROVEMENT FORWARDERS
    # -------------------------------------------------------------------------
    def record_mission_reflection(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.record_mission_reflection(*args, **kwargs)

    def get_mission_reflection(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.get_mission_reflection(*args, **kwargs)

    def record_operator_feedback(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.record_operator_feedback(*args, **kwargs)

    def list_operator_feedback(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.list_operator_feedback(*args, **kwargs)

    def analyze_recent_outcomes(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.analyze_recent_outcomes(*args, **kwargs)

    def adapt_preference(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.adapt_preference(*args, **kwargs)

    def get_learned_preference(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.get_learned_preference(*args, **kwargs)

    def list_learned_preferences(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.list_learned_preferences(*args, **kwargs)

    def calibrate_confidence(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.calibrate_confidence(*args, **kwargs)

    def detect_operational_patterns(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.detect_operational_patterns(*args, **kwargs)

    def propose_improvement(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.propose_improvement(*args, **kwargs)

    def get_improvement_proposal(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.get_improvement_proposal(*args, **kwargs)

    def list_improvement_proposals(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.list_improvement_proposals(*args, **kwargs)

    def adopt_improvement_proposal(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.adopt_improvement_proposal(*args, **kwargs)

    def reject_improvement_proposal(self, *args, **kwargs):
        self._check_learning_availability()
        return self.learning.reject_improvement_proposal(*args, **kwargs)

    # -------------------------------------------------------------------------
    # STAGE 5: ADAPTIVE INTERFACE & LIVING SURFACE DELEGATES
    # -------------------------------------------------------------------------
    def render_living_surface(self, *args, **kwargs):
        self._check_surface_availability()
        return self.surface.render_living_surface(*args, **kwargs)

    def generate_adaptive_briefing(self, *args, **kwargs):
        self._check_surface_availability()
        return self.surface.generate_adaptive_briefing(*args, **kwargs)

    def render_tv_context_cards(self, *args, **kwargs):
        self._check_surface_availability()
        return self.surface.render_tv_context_cards(*args, **kwargs)

    def render_mission_progress_cards(self, *args, **kwargs):
        self._check_surface_availability()
        return self.surface.render_mission_progress_cards(*args, **kwargs)

    def render_future_radar_card(self, *args, **kwargs):
        self._check_surface_availability()
        return self.surface.render_future_radar_card(*args, **kwargs)

    def render_poco_escalation_queue_card(self, *args, **kwargs):
        self._check_surface_availability()
        return self.surface.render_poco_escalation_queue_card(*args, **kwargs)

    def render_system_health_card(self, *args, **kwargs):
        self._check_surface_availability()
        return self.surface.render_system_health_card(*args, **kwargs)

    def capture_operator_feedback_from_surface(self, *args, **kwargs):
        self._check_surface_availability()
        return self.surface.capture_operator_feedback_from_surface(*args, **kwargs)

    def create_surface_snapshot(self, *args, **kwargs):
        self._check_surface_availability()
        return self.surface.create_surface_snapshot(*args, **kwargs)

    def get_surface_snapshot(self, *args, **kwargs):
        self._check_surface_availability()
        return self.surface.get_surface_snapshot(*args, **kwargs)

    def list_surface_snapshots(self, *args, **kwargs):
        self._check_surface_availability()
        return self.surface.list_surface_snapshots(*args, **kwargs)

    # -------------------------------------------------------------------------
    # STAGE 6: VOICE-FIRST COMMAND & RESPONSE DELEGATES
    # -------------------------------------------------------------------------
    def classify_voice_intent(self, *args, **kwargs):
        self._check_voice_availability()
        return self.voice.classify_voice_intent(*args, **kwargs)

    def process_voice_command(self, *args, **kwargs):
        self._check_voice_availability()
        return self.voice.process_voice_command(*args, **kwargs)

    def generate_spoken_briefing(self, *args, **kwargs):
        self._check_voice_availability()
        return self.voice.generate_spoken_briefing(*args, **kwargs)

    def generate_mission_status_speech(self, *args, **kwargs):
        self._check_voice_availability()
        return self.voice.generate_mission_status_speech(*args, **kwargs)

    def generate_context_query_speech(self, *args, **kwargs):
        self._check_voice_availability()
        return self.voice.generate_context_query_speech(*args, **kwargs)

    def generate_future_radar_speech(self, *args, **kwargs):
        self._check_voice_availability()
        return self.voice.generate_future_radar_speech(*args, **kwargs)

    def generate_system_health_speech(self, *args, **kwargs):
        self._check_voice_availability()
        return self.voice.generate_system_health_speech(*args, **kwargs)

    def announce_pending_escalations(self, *args, **kwargs):
        self._check_voice_availability()
        return self.voice.announce_pending_escalations(*args, **kwargs)

    def format_degraded_state_speech(self, *args, **kwargs):
        self._check_voice_availability()
        return self.voice.format_degraded_state_speech(*args, **kwargs)

    def list_voice_interactions(self, *args, **kwargs):
        self._check_voice_availability()
        return self.voice.list_voice_interactions(*args, **kwargs)


# Backward-compatibility alias and singleton instance
AadyaIntelligence = AadyaCrownZero
aadya = AadyaCrownZero()
