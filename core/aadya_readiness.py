"""
AADYA Stage 7 — End-to-End Integration & Operational Readiness Engine
=====================================================================
Integrates AADYA subsystems into a unified operational readiness model:
- Read-only readiness evaluations aggregating Core, Context, Missions,
  Learning, Surface, Voice, RAM Guard, and Cryptographic Audit-Chain Integrity.
- Truthful degradation detection: Any uninitialized subsystem, RAM pressure,
  or audit failure marks readiness as DEGRADED or NOT_READY.
- Bounded, rate-limited persistence of readiness assessments into SQLite
  (aadya_readiness_assessments) with immutable audit events.
- Multi-channel end-to-end voice pipeline execution forwarding to AADYA
  voice engine with safety assertions and TV surface intent pairing.
- Safe read-only queries are NEVER blocked by operational degradation.
"""

import os
import sys
import time
import json
import uuid
import hashlib
import sqlite3
import re
from typing import Dict, Any, List, Optional, Union

try:
    from core.db import query_db, execute_db, log_audit_event, get_connection, verify_audit_chain
    from core.ram_guard import check_ram_guard
    from core.aadya_context import ContextPrivacyTier
    from core.aadya_voice import assert_spoken_response_safety, VoiceSafetyViolationError
    from core.aadya_surface import sanitize_tv_summary
except ImportError:
    from aeonix.core.db import query_db, execute_db, log_audit_event, get_connection, verify_audit_chain
    from aeonix.core.ram_guard import check_ram_guard
    from aeonix.core.aadya_context import ContextPrivacyTier
    from aeonix.core.aadya_voice import assert_spoken_response_safety, VoiceSafetyViolationError
    from aeonix.core.aadya_surface import sanitize_tv_summary


READINESS_MIN_INTERVAL_SECONDS = 1.0  # Rate-limit between persisted assessments
MAX_ASSESSMENTS_LIMIT = 50


class ReadinessDegradedError(Exception):
    """Raised when an operation requiring nominal readiness is attempted in degraded state."""
    pass


class AadyaReadinessEngine:
    """
    Stage 7 Operational Readiness and Health Aggregation Engine for AADYA Crown-0.
    """

    def __init__(self, db_path: Optional[str] = None, parent_crown_zero: Optional[Any] = None):
        self.db_path = db_path
        self.parent = parent_crown_zero
        self.initialization_status = "PENDING"
        self.init_error = None
        self._last_assessment_time = 0.0

        self._ensure_readiness_tables()

    def _ensure_readiness_tables(self) -> None:
        """Creates aadya_readiness_assessments table if not exists."""
        try:
            conn = get_connection(self.db_path)
            try:
                with conn:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS aadya_readiness_assessments (
                            id TEXT PRIMARY KEY,
                            readiness_status TEXT NOT NULL,
                            subsystem_health_json TEXT NOT NULL,
                            audit_chain_status TEXT NOT NULL,
                            ram_guard_status TEXT NOT NULL,
                            degraded_reasons_json TEXT NOT NULL,
                            assessment_digest TEXT NOT NULL,
                            created_at REAL NOT NULL
                        );
                    """)
                    conn.execute("""
                        CREATE INDEX IF NOT EXISTS idx_aadya_readiness_created
                        ON aadya_readiness_assessments(created_at);
                    """)
                self.initialization_status = "INITIALIZED"
                self.init_error = None
            finally:
                conn.close()

            # Record initialization audit event
            try:
                log_audit_event(
                    actor="AZ-001_AADYA",
                    action="READINESS_ENGINE_INITIALIZED",
                    target="aadya_readiness_engine",
                    result="SUCCESS",
                    details={"table": "aadya_readiness_assessments"},
                    db_path=self.db_path
                )
            except Exception:
                pass
        except Exception as e:
            self.initialization_status = "INITIALIZATION_FAILED"
            self.init_error = str(e)
            try:
                log_audit_event(
                    actor="AZ-001_AADYA",
                    action="READINESS_ENGINE_INITIALIZATION_FAILED",
                    target="aadya_readiness_engine",
                    result="DEGRADED",
                    details={"error": str(e)},
                    db_path=self.db_path
                )
            except Exception:
                pass

    @property
    def is_initialized(self) -> bool:
        return self.initialization_status == "INITIALIZED"

    def _check_engine_health(self) -> None:
        if not self.is_initialized:
            raise ReadinessDegradedError(
                f"AADYA Readiness Engine is in degraded state: {self.initialization_status}. Root cause: {self.init_error}"
            )

    # =========================================================================
    # 1. READ-ONLY OPERATIONAL READINESS EVALUATION
    # =========================================================================

    def evaluate_operational_readiness(self) -> Dict[str, Any]:
        """
        Pure read-only operational readiness assessment.
        NEVER persists records or mutates database state.
        
        Evaluates:
        1. Subsystem statuses: Core, Context, Missions, Learning, Surface, Voice, Readiness.
        2. Cryptographic audit chain integrity via verify_audit_chain().
        3. RAM guard via check_ram_guard().
        4. Active POCO escalations and active missions.
        
        Returns:
            Dict containing:
            - overall_status: "NOMINAL", "DEGRADED", or "NOT_READY"
            - is_operational: bool (True even in DEGRADED for safe read-only queries)
            - subsystems: Dict of subsystem statuses
            - audit_chain: Dict with status and total_events
            - ram_guard: Dict with safe flag and available_mb
            - degraded_reasons: List of generic human-readable strings
            - summary: Actionable status message
        """
        try:
            return self._evaluate_operational_readiness_internal()
        except Exception as e:
            # Mandatory Correction 12: Fail closed to explicit degraded/not_ready without crashing
            return {
                "overall_status": "NOT_READY",
                "is_operational": False,
                "subsystems": {},
                "audit_chain": {"status": "AUDIT_STATUS_UNKNOWN", "is_valid": False},
                "ram_guard": {"status": "UNKNOWN", "is_safe": False},
                "degraded_reasons": ["Operational readiness evaluation error"],
                "summary": "System status evaluation encountered an internal error. Consult POCO console.",
                "evaluated_at": time.time()
            }

    def _evaluate_operational_readiness_internal(self) -> Dict[str, Any]:
        degraded_reasons: List[str] = []
        subsystems: Dict[str, str] = {}

        # 1. Evaluate Core Mind and Subsystems
        if self.parent:
            core_st = getattr(self.parent, "initialization_status", "UNKNOWN")
            subsystems["core"] = core_st
            if core_st != "INITIALIZED":
                degraded_reasons.append("Crown-0 Core")

            ctx_st = getattr(self.parent, "context_initialization_status", "UNKNOWN")
            subsystems["context"] = ctx_st
            if ctx_st != "INITIALIZED":
                degraded_reasons.append("Context Engine")

            mis_st = getattr(self.parent, "missions_initialization_status", "UNKNOWN")
            subsystems["missions"] = mis_st
            if mis_st != "INITIALIZED":
                degraded_reasons.append("Mission Engine")

            lrn_st = getattr(self.parent, "learning_initialization_status", "UNKNOWN")
            subsystems["learning"] = lrn_st
            if lrn_st != "INITIALIZED":
                degraded_reasons.append("Learning Engine")

            srf_st = getattr(self.parent, "surface_initialization_status", "UNKNOWN")
            subsystems["surface"] = srf_st
            if srf_st != "INITIALIZED":
                degraded_reasons.append("Surface Engine")

            vox_st = getattr(self.parent, "voice_initialization_status", "UNKNOWN")
            subsystems["voice"] = vox_st
            if vox_st != "INITIALIZED":
                degraded_reasons.append("Voice Engine")
        else:
            subsystems["core"] = "UNLINKED"
            degraded_reasons.append("Crown-0 Core Unlinked")

        subsystems["readiness"] = self.initialization_status
        if not self.is_initialized:
            degraded_reasons.append("Readiness Engine")

        # 2. Cryptographic Audit Chain Verification
        audit_chain_status = "AUDIT_STATUS_UNKNOWN"
        audit_valid = False
        audit_total = 0
        try:
            audit_res = verify_audit_chain(self.db_path)
            audit_valid = bool(audit_res.get("is_valid", False))
            audit_total = int(audit_res.get("total_events", 0))

            if audit_valid:
                if audit_total > 0:
                    audit_chain_status = "AUDIT_CHAIN_VERIFIED"
                else:
                    audit_chain_status = "AUDIT_STATUS_EMPTY"
            else:
                audit_chain_status = "AUDIT_VERIFICATION_FAILED"
                degraded_reasons.append("Audit Verification")
        except Exception:
            audit_chain_status = "AUDIT_STATUS_UNKNOWN"
            degraded_reasons.append("Audit Verification Check")

        # 3. RAM Guard Assessment
        ram_status = "NOMINAL"
        ram_safe = True
        available_mb = 0.0
        try:
            ram_res = check_ram_guard()
            ram_safe = bool(ram_res.get("can_proceed", ram_res.get("is_safe", True)))
            available_mb = float(ram_res.get("available_mb", 0.0))
            if not ram_safe:
                ram_status = "PRESSURE_WARNING"
                degraded_reasons.append("System Memory Pressure")
        except Exception:
            ram_status = "UNKNOWN"
            ram_safe = False
            degraded_reasons.append("Memory Telemetry")

        # 4. Synthesize Overall Status
        # Mandatory Correction 5 & 6:
        # ALL SYSTEMS NOMINAL ONLY if every subsystem is INITIALIZED, audit verification succeeds, and RAM is nominal.
        if len(degraded_reasons) == 0 and audit_valid and ram_safe:
            overall_status = "NOMINAL"
            summary = "All local core subsystems operational. Storage and audit logs verified."
        else:
            overall_status = "DEGRADED"
            # Sanitize reason names
            safe_reasons = [re.sub(r'[^a-zA-Z0-9_\s]', '', r).strip() for r in degraded_reasons]
            summary = f"Operating in degraded mode ({', '.join(safe_reasons)}). Consult POCO operator console."

        return {
            "overall_status": overall_status,
            "is_operational": True,  # Safe read-only operations remain permitted
            "subsystems": subsystems,
            "audit_chain": {
                "status": audit_chain_status,
                "is_valid": audit_valid,
                "total_events": audit_total
            },
            "ram_guard": {
                "status": ram_status,
                "is_safe": ram_safe,
                "available_mb": available_mb
            },
            "degraded_reasons": degraded_reasons,
            "summary": summary,
            "evaluated_at": time.time()
        }

    # =========================================================================
    # 2. BOUNDED & RATE-LIMITED READINESS PERSISTENCE
    # =========================================================================

    def record_readiness_assessment(self, actor: str = "AZ-001_AADYA") -> Dict[str, Any]:
        """
        Explicitly evaluates and commits an operational readiness assessment into SQLite.
        Enforces a minimum interval rate limit between persisted assessments.
        Logs an immutable audit event.
        """
        self._check_engine_health()
        now = time.time()

        if (now - self._last_assessment_time) < READINESS_MIN_INTERVAL_SECONDS:
            raise ReadinessDegradedError(
                f"Readiness assessment rate-limited. Please wait {READINESS_MIN_INTERVAL_SECONDS}s between assessments."
            )

        eval_result = self.evaluate_operational_readiness()
        assessment_id = f"readiness_{uuid.uuid4().hex[:12]}"

        subsystems_json = json.dumps(eval_result["subsystems"], sort_keys=True)
        degraded_reasons_json = json.dumps(eval_result["degraded_reasons"])
        audit_status = eval_result["audit_chain"]["status"]
        ram_status = eval_result["ram_guard"]["status"]
        overall_status = eval_result["overall_status"]

        digest_payload = f"{assessment_id}|{overall_status}|{subsystems_json}|{audit_status}|{ram_status}|{now}"
        assessment_digest = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()

        conn = get_connection(self.db_path)
        try:
            with conn:
                conn.execute("""
                    INSERT INTO aadya_readiness_assessments (
                        id, readiness_status, subsystem_health_json, audit_chain_status,
                        ram_guard_status, degraded_reasons_json, assessment_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    assessment_id,
                    overall_status,
                    subsystems_json,
                    audit_status,
                    ram_status,
                    degraded_reasons_json,
                    assessment_digest,
                    now
                ))

                log_audit_event(
                    actor=actor,
                    action="READINESS_ASSESSMENT_RECORDED",
                    target=assessment_id,
                    result="SUCCESS",
                    details={
                        "overall_status": overall_status,
                        "degraded_count": len(eval_result["degraded_reasons"]),
                        "audit_chain_status": audit_status
                    },
                    conn=conn
                )
        finally:
            conn.close()

        self._last_assessment_time = now

        return {
            "assessment_id": assessment_id,
            "overall_status": overall_status,
            "subsystems": eval_result["subsystems"],
            "audit_chain_status": audit_status,
            "ram_guard_status": ram_status,
            "degraded_reasons": eval_result["degraded_reasons"],
            "assessment_digest": assessment_digest,
            "created_at": now
        }

    def list_readiness_assessments(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Lists recent persisted operational readiness assessments."""
        self._check_engine_health()
        bounded_limit = min(max(1, limit), MAX_ASSESSMENTS_LIMIT)
        rows = query_db(
            "SELECT id, readiness_status, subsystem_health_json, audit_chain_status, ram_guard_status, "
            "degraded_reasons_json, assessment_digest, created_at FROM aadya_readiness_assessments "
            "ORDER BY created_at DESC LIMIT ?;",
            (bounded_limit,),
            db_path=self.db_path
        )
        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "readiness_status": r[1],
                "subsystems": json.loads(r[2]),
                "audit_chain_status": r[3],
                "ram_guard_status": r[4],
                "degraded_reasons": json.loads(r[5]),
                "assessment_digest": r[6],
                "created_at": r[7]
            })
        return results

    # =========================================================================
    # 3. END-TO-END PIPELINE ORCHESTRATION & COMPLIANCE
    # =========================================================================

    def run_end_to_end_voice_turn(
        self,
        transcript: str,
        session_id: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Coordinates full end-to-end voice turn with operational health verification:
        1. Checks readiness non-intrusively (does not block safe queries on degraded).
        2. Routes through parent Crown-0 process_voice_command().
        3. Enforces output safety assertions for both spoken response and TV surface payload.
        4. Injects readiness metadata into the response bundle.
        """
        if not self.parent:
            raise ReadinessDegradedError("Crown-0 parent instance is unlinked.")

        # Non-blocking readiness check
        readiness_eval = self.evaluate_operational_readiness()

        # Execute voice processing through Crown-0
        voice_result = self.parent.process_voice_command(
            transcript=transcript,
            session_id=session_id,
            dry_run=dry_run
        )

        speech = voice_result.get("speech", "")
        # Validate final spoken output safety
        assert_spoken_response_safety(speech)

        # Build paired Living Surface HUD payload for the turn
        surface_payload = {}
        if getattr(self.parent, "surface", None) and self.parent.surface_initialization_status == "INITIALIZED":
            try:
                surface_payload = self.parent.render_living_surface(create_snapshot=False)
                # Ensure TV payload adheres to strict safety invariants
                self.parent.surface.assert_tv_payload_safety(surface_payload)
            except Exception:
                surface_payload = {"error": "Surface payload unavailable in fallback mode"}

        return {
            "success": voice_result.get("success", False),
            "intent": voice_result.get("intent", "UNKNOWN"),
            "speech": speech,
            "transcript": voice_result.get("transcript", ""),
            "layout_intent": voice_result.get("layout_intent", {}),
            "is_escalated": voice_result.get("is_escalated", False),
            "escalation_id": voice_result.get("escalation_id"),
            "readiness_state": readiness_eval.get("overall_status", "UNKNOWN"),
            "surface_payload": surface_payload,
            "latency_ms": voice_result.get("latency_ms", 0.0)
        }
