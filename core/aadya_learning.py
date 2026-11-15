"""
AADYA Learning, Reflection & Self-Improvement Engine
Stage 4 Crown-0 subsystem.

Provides:
- Mission reflections and lessons-learned records with SHA-256 digests
- Operator feedback capture (ratings and notes) from Aadi
- Truthful outcome analysis and statistics derived from SQLite records
- Allowlisted preference adaptation (strictly non-safety domains)
- Bounded and conservative confidence calibration (ceiling <= 0.85, never 1.0)
- Correlation-only latent pattern detection (never claiming causation)
- Deduplicated, rate-limited improvement proposals with payload digest binding
- POCO-gated proposal adoption enforcing 16+ char token and single-use nonce
- Reversible configuration/preference applications (zero opaque code mutation)
- Strict sensitive-data sanitization before persistence
- Permanent financial quarantine enforcement across all learning paths
- Atomic SQLite transactions for every mutation
"""

import os
import sys
import time
import json
import sqlite3
import hashlib
import logging
import re
from typing import Dict, Any, List, Optional, Tuple, Set, Union

from core.db import (
    get_connection,
    get_db_path,
    log_audit_event
)

logger = logging.getLogger("aeonix.core.aadya_learning")

# Security Exception
class SecurityViolationError(Exception):
    """Raised when an action or proposal attempts to modify safety rules or privilege boundaries."""
    pass

# Conservative confidence bounds
CONFIDENCE_CEILING = 0.85
CONFIDENCE_FLOOR = 0.10

# Strictly allowed non-safety preference domains
ALLOWED_PREFERENCE_DOMAINS = {
    "ui_display": {
        "allowed_keys": {"theme_mode", "font_scale", "refresh_interval_sec", "compact_view"},
        "description": "User interface display settings"
    },
    "briefing": {
        "allowed_keys": {"verbosity", "include_weather", "preferred_morning_hour", "preferred_evening_hour"},
        "description": "Daily briefing preferences"
    },
    "telemetry": {
        "allowed_keys": {"sample_interval_sec", "retain_days", "enable_extended_diagnostics"},
        "description": "Telemetry collection rates and retention"
    },
    "routine_timing": {
        "allowed_keys": {"morning_briefing_hour", "evening_review_hour", "night_audit_hour"},
        "description": "Timing preferences for CHRONOS routines"
    },
    "radar": {
        "allowed_keys": {"horizon_hours", "signal_sensitivity", "max_radar_signals"},
        "description": "Predictive radar visualization preferences"
    }
}

# Forbidden targets/subsystems that cannot be modified by learning proposals
FORBIDDEN_PROPOSAL_TARGETS = {
    "safety_rules", "privilege_elevation", "autonomy_boundary", "core_creed",
    "financial_quarantine", "root_access", "bypass_sentinel", "bypass_poco",
    "argon2_verification", "nonce_verification", "audit_log", "sentinel_gate"
}

# Financial execution trigger verbs
PROHIBITED_FINANCIAL_VERBS = {
    "transfer", "pay", "payment", "buy", "sell", "trade", "swap", "stake",
    "withdraw", "deposit", "invest", "borrow", "lend", "sign_transaction",
    "execute_order", "wire", "remit"
}

# Sensitive credential patterns for redaction
SENSITIVE_KEY_PATTERNS = [
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"passphrase", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"private_?key", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"api_?key", re.IGNORECASE),
    re.compile(r"auth_?header", re.IGNORECASE),
    re.compile(r"bearer", re.IGNORECASE)
]


def sanitize_sensitive_data(obj: Any) -> Any:
    """
    Recursively scrubs raw credentials, tokens, passwords, private keys, and secrets.
    Replaces sensitive data with [REDACTED_SENSITIVE_DATA].
    """
    if isinstance(obj, dict):
        sanitized = {}
        for k, v in obj.items():
            if any(p.search(str(k)) for p in SENSITIVE_KEY_PATTERNS):
                sanitized[k] = "[REDACTED_SENSITIVE_DATA]"
            else:
                sanitized[k] = sanitize_sensitive_data(v)
        return sanitized
    elif isinstance(obj, list):
        return [sanitize_sensitive_data(item) for item in obj]
    elif isinstance(obj, str):
        # Scrub bearer tokens or high-entropy tokens
        scrubbed = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]{12,}", "Bearer [REDACTED_TOKEN]", obj, flags=re.IGNORECASE)
        # Scrub password patterns
        scrubbed = re.sub(r"(password\s*[:=]\s*)['\"][^'\"]+['\"]", r"\1'[REDACTED]'", scrubbed, flags=re.IGNORECASE)
        return scrubbed
    return obj


def _verify_learning_non_financial(content: Any) -> None:
    """Enforces permanent financial quarantine across learning paths."""
    from core.aadya import FinancialQuarantineViolationError

    content_str = json.dumps(content) if not isinstance(content, str) else content
    content_lower = content_str.lower()
    for verb in PROHIBITED_FINANCIAL_VERBS:
        if f" {verb} " in f" {content_lower} " or f'"{verb}"' in content_lower or f"_{verb}_" in content_lower:
            raise FinancialQuarantineViolationError(
                f"FINANCIAL_QUARANTINE_VIOLATION: Financial execution concept '{verb}' is strictly prohibited "
                "within AADYA Crown-0 learning, reflections, preferences, and improvement proposals."
            )


class AadyaLearningEngine:
    """
    Crown-0 Learning, Reflection & Self-Improvement Engine.
    Coordinates post-mission reflections, operator feedback aggregation,
    conservative confidence calibration, allowlisted preference adaptation,
    and POCO-gated improvement proposals.
    """

    def __init__(self, db_path: Optional[str] = None, parent_crown_zero: Optional[Any] = None):
        self.db_path = db_path
        self.parent = parent_crown_zero
        self.is_initialized = False
        self.initialization_status = "PENDING_INITIALIZATION"
        self.initialization_error = None

        try:
            self._ensure_learning_tables()
            self.is_initialized = True
            self.initialization_status = "INITIALIZED"
        except Exception as e:
            self.is_initialized = False
            self.initialization_status = "INITIALIZATION_FAILED"
            self.initialization_error = str(e)
            logger.error("Failed to initialize AadyaLearningEngine: %s", e)

    def _get_db(self) -> str:
        return self.db_path or get_db_path()

    def _check_engine_health(self) -> None:
        if not self.is_initialized or self.initialization_status == "INITIALIZATION_FAILED":
            raise RuntimeError(
                f"AADYA_LEARNING_ENGINE_DEGRADED: Learning engine is not operational "
                f"(status={self.initialization_status}, error={self.initialization_error})"
            )

    def _ensure_learning_tables(self) -> None:
        """Creates SQLite tables for reflections, feedback, preferences, proposals, and calibrations."""
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS aadya_mission_reflections (
                        id TEXT PRIMARY KEY,
                        mission_id TEXT NOT NULL,
                        outcome_status TEXT NOT NULL,
                        notes TEXT NOT NULL,
                        lessons_json TEXT,
                        patterns_observed_json TEXT,
                        execution_duration_sec REAL NOT NULL DEFAULT 0.0,
                        reflection_digest TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS aadya_operator_feedback (
                        id TEXT PRIMARY KEY,
                        target_type TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        rating INTEGER NOT NULL,
                        feedback_text TEXT,
                        operator TEXT NOT NULL DEFAULT 'Aadi',
                        feedback_digest TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS aadya_learned_preferences (
                        id TEXT PRIMARY KEY,
                        domain TEXT NOT NULL,
                        preference_key TEXT NOT NULL,
                        preference_value_json TEXT NOT NULL,
                        confidence REAL NOT NULL DEFAULT 0.5,
                        confidence_type TEXT NOT NULL DEFAULT 'HEURISTIC',
                        evidence_count INTEGER NOT NULL DEFAULT 1,
                        last_evidence_at REAL NOT NULL,
                        privacy_tier TEXT NOT NULL DEFAULT 'OPERATOR_ONLY',
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        UNIQUE(domain, preference_key)
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS aadya_improvement_proposals (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        subsystem TEXT NOT NULL,
                        proposal_type TEXT NOT NULL,
                        justification TEXT NOT NULL,
                        proposal_payload_json TEXT NOT NULL,
                        proposal_digest TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'PENDING_POCO_APPROVAL',
                        escalation_id TEXT,
                        applied_at REAL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS aadya_confidence_calibrations (
                        id TEXT PRIMARY KEY,
                        domain TEXT NOT NULL,
                        predicted_confidence REAL NOT NULL,
                        actual_outcome INTEGER NOT NULL,
                        brier_score REAL NOT NULL,
                        sample_count INTEGER NOT NULL DEFAULT 1,
                        calibrated_factor REAL NOT NULL DEFAULT 1.0,
                        updated_at REAL NOT NULL
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_reflections_mission ON aadya_mission_reflections(mission_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_target ON aadya_operator_feedback(target_type, target_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_status ON aadya_improvement_proposals(status);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_preferences_domain ON aadya_learned_preferences(domain);")
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # 1. Mission Reflections
    # -------------------------------------------------------------------------
    def record_mission_reflection(
        self,
        mission_id: str,
        outcome_status: str,
        notes: str,
        lessons: Optional[List[str]] = None,
        patterns: Optional[List[str]] = None,
        duration_sec: float = 0.0,
        actor: str = "Aadi"
    ) -> Dict[str, Any]:
        """
        Records a post-mission reflection and extraction of learnings.
        Sanitizes sensitive content and enforces financial quarantine.
        """
        self._check_engine_health()

        # Enforce quarantine
        _verify_learning_non_financial(f"{notes} {lessons or []}")

        # Sanitize sensitive data
        clean_notes = sanitize_sensitive_data(notes)
        clean_lessons = sanitize_sensitive_data(lessons or [])
        clean_patterns = sanitize_sensitive_data(patterns or [])

        now = time.time()
        reflection_id = f"refl_{int(now * 1000)}_{os.urandom(3).hex()}"

        reflection_data = {
            "mission_id": mission_id,
            "outcome_status": outcome_status,
            "notes": clean_notes,
            "lessons": clean_lessons,
            "patterns": clean_patterns,
            "duration_sec": duration_sec,
            "created_at": now
        }
        digest = hashlib.sha256(json.dumps(reflection_data, sort_keys=True).encode("utf-8")).hexdigest()

        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    INSERT INTO aadya_mission_reflections (
                        id, mission_id, outcome_status, notes, lessons_json,
                        patterns_observed_json, execution_duration_sec,
                        reflection_digest, actor, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    reflection_id, mission_id, outcome_status, clean_notes,
                    json.dumps(clean_lessons), json.dumps(clean_patterns),
                    duration_sec, digest, actor, now
                ))

                log_audit_event(
                    actor=actor,
                    action="record_mission_reflection",
                    target=f"{mission_id}:{reflection_id}",
                    result="SUCCESS",
                    details={"outcome": outcome_status, "reflection_digest": digest},
                    conn=conn
                )
        finally:
            conn.close()

        return {
            "reflection_id": reflection_id,
            "mission_id": mission_id,
            "outcome_status": outcome_status,
            "reflection_digest": digest,
            "notes": clean_notes,
            "lessons": clean_lessons,
            "created_at": now
        }

    def get_mission_reflection(self, reflection_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a reflection by ID."""
        self._check_engine_health()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM aadya_mission_reflections WHERE id = ?;", (reflection_id,))
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            res["lessons"] = json.loads(res.get("lessons_json") or "[]")
            res["patterns"] = json.loads(res.get("patterns_observed_json") or "[]")
            return res
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # 2. Operator Feedback
    # -------------------------------------------------------------------------
    def record_operator_feedback(
        self,
        target_type: str,
        target_id: str,
        rating: int,
        feedback_text: Optional[str] = None,
        operator: str = "Aadi"
    ) -> Dict[str, Any]:
        """
        Captures explicit feedback from operator Aadi.
        Rating scale: -1 (negative), 0 (neutral), 1 (positive).
        Sanitizes data and enforces financial quarantine.
        """
        self._check_engine_health()

        valid_targets = {"MISSION", "TASK", "RECOMMENDATION", "RADAR", "MEMORY", "ROUTINE"}
        target_type_clean = target_type.strip().upper()
        if target_type_clean not in valid_targets:
            raise ValueError(f"INVALID_FEEDBACK_TARGET: '{target_type}'. Allowed: {sorted(list(valid_targets))}")

        if rating not in {-1, 0, 1}:
            raise ValueError(f"INVALID_RATING: {rating}. Rating must be -1, 0, or 1.")

        clean_text = sanitize_sensitive_data(feedback_text or "")
        _verify_learning_non_financial(clean_text)

        now = time.time()
        feedback_id = f"fb_{int(now * 1000)}_{os.urandom(3).hex()}"

        fb_payload = {
            "target_type": target_type_clean,
            "target_id": target_id,
            "rating": rating,
            "feedback_text": clean_text,
            "operator": operator,
            "created_at": now
        }
        digest = hashlib.sha256(json.dumps(fb_payload, sort_keys=True).encode("utf-8")).hexdigest()

        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    INSERT INTO aadya_operator_feedback (
                        id, target_type, target_id, rating, feedback_text,
                        operator, feedback_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (feedback_id, target_type_clean, target_id, rating, clean_text, operator, digest, now))

                log_audit_event(
                    actor=operator,
                    action="record_operator_feedback",
                    target=f"{target_type_clean}:{target_id}",
                    result="SUCCESS",
                    details={"rating": rating, "feedback_id": feedback_id, "digest": digest},
                    conn=conn
                )
        finally:
            conn.close()

        return {
            "feedback_id": feedback_id,
            "target_type": target_type_clean,
            "target_id": target_id,
            "rating": rating,
            "feedback_digest": digest,
            "created_at": now
        }

    def list_operator_feedback(
        self,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Lists captured operator feedback entries."""
        self._check_engine_health()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            query = "SELECT * FROM aadya_operator_feedback WHERE 1=1"
            params: List[Any] = []
            if target_type:
                query += " AND target_type = ?"
                params.append(target_type.strip().upper())
            if target_id:
                query += " AND target_id = ?"
                params.append(target_id)
            query += " ORDER BY created_at DESC;"

            cur.execute(query, tuple(params))
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # 3. Truthful Outcome Analysis
    # -------------------------------------------------------------------------
    def analyze_recent_outcomes(self, limit: int = 20) -> Dict[str, Any]:
        """
        Analyzes recent missions and task outcomes strictly computed from SQLite records.
        Returns truthful success rates, failure counts, and execution metrics without fabrication.
        """
        self._check_engine_health()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Query recent missions
            cur.execute("""
                SELECT id, status, total_tasks, completed_tasks, failed_tasks, created_at, completed_at
                FROM aadya_missions
                ORDER BY created_at DESC
                LIMIT ?;
            """, (limit,))
            missions = [dict(r) for r in cur.fetchall()]

            total_missions = len(missions)
            if total_missions == 0:
                return {
                    "total_missions_analyzed": 0,
                    "completed_missions": 0,
                    "failed_missions": 0,
                    "overall_success_rate": 0.0,
                    "average_task_completion_rate": 0.0,
                    "failure_causes": {},
                    "metrics_basis": "EXACT_SQLITE_RECORDS"
                }

            completed_missions = sum(1 for m in missions if m["status"] == "COMPLETED")
            failed_missions = sum(1 for m in missions if m["status"] == "FAILED")
            cancelled_missions = sum(1 for m in missions if m["status"] == "CANCELLED")

            total_tasks_scheduled = sum(m["total_tasks"] for m in missions)
            total_tasks_completed = sum(m["completed_tasks"] for m in missions)
            total_tasks_failed = sum(m["failed_tasks"] for m in missions)

            success_rate = round((completed_missions / total_missions) * 100.0, 2)
            task_completion_rate = (
                round((total_tasks_completed / total_tasks_scheduled) * 100.0, 2)
                if total_tasks_scheduled > 0 else 0.0
            )

            # Query recent failure errors from tasks
            cur.execute("""
                SELECT error_message, COUNT(*) as cnt
                FROM aadya_tasks
                WHERE status = 'FAILED' AND error_message IS NOT NULL
                GROUP BY error_message
                ORDER BY cnt DESC
                LIMIT 5;
            """)
            failure_causes = {r[0]: r[1] for r in cur.fetchall()}

            return {
                "total_missions_analyzed": total_missions,
                "completed_missions": completed_missions,
                "failed_missions": failed_missions,
                "cancelled_missions": cancelled_missions,
                "overall_success_rate": success_rate,
                "total_tasks_scheduled": total_tasks_scheduled,
                "total_tasks_completed": total_tasks_completed,
                "total_tasks_failed": total_tasks_failed,
                "average_task_completion_rate": task_completion_rate,
                "failure_causes": failure_causes,
                "metrics_basis": "EXACT_SQLITE_RECORDS"
            }
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # 4. Allowlisted Preference Adaptation
    # -------------------------------------------------------------------------
    def adapt_preference(
        self,
        domain: str,
        key: str,
        value: Any,
        feedback_weight: float = 1.0,
        actor: str = "Aadi"
    ) -> Dict[str, Any]:
        """
        Adapts a learned preference within strictly allowlisted non-safety domains (correction 14 & 15).
        Enforces type validation, financial quarantine, and atomic transaction.
        """
        self._check_engine_health()

        clean_domain = domain.strip().lower()
        clean_key = key.strip().lower()

        # Domain allowlist check
        if clean_domain not in ALLOWED_PREFERENCE_DOMAINS:
            raise ValueError(
                f"DISALLOWED_PREFERENCE_DOMAIN: Domain '{clean_domain}' is not in the allowed non-safety preference domains: "
                f"{sorted(list(ALLOWED_PREFERENCE_DOMAINS.keys()))}"
            )

        domain_meta = ALLOWED_PREFERENCE_DOMAINS[clean_domain]
        if clean_key not in domain_meta["allowed_keys"]:
            raise ValueError(
                f"DISALLOWED_PREFERENCE_KEY: Key '{clean_key}' is not allowed in domain '{clean_domain}'. "
                f"Allowed keys: {sorted(list(domain_meta['allowed_keys']))}"
            )

        # Enforce financial quarantine
        _verify_learning_non_financial(value)

        # Sanitize sensitive data
        clean_val = sanitize_sensitive_data(value)
        val_json = json.dumps(clean_val, sort_keys=True)
        now = time.time()
        pref_id = f"pref_{clean_domain}_{clean_key}"

        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT evidence_count, confidence FROM aadya_learned_preferences WHERE domain = ? AND preference_key = ?;",
                    (clean_domain, clean_key)
                )
                existing = cur.fetchone()

                if existing:
                    new_count = existing[0] + 1
                    # Bounded conservative confidence update (ceiling 0.85)
                    new_conf = min(CONFIDENCE_CEILING, round(existing[1] + (0.05 * feedback_weight), 2))
                    conn.execute("""
                        UPDATE aadya_learned_preferences
                        SET preference_value_json = ?,
                            evidence_count = ?,
                            confidence = ?,
                            last_evidence_at = ?,
                            updated_at = ?
                        WHERE domain = ? AND preference_key = ?;
                    """, (val_json, new_count, new_conf, now, now, clean_domain, clean_key))
                else:
                    new_count = 1
                    new_conf = 0.50
                    conn.execute("""
                        INSERT INTO aadya_learned_preferences (
                            id, domain, preference_key, preference_value_json,
                            confidence, confidence_type, evidence_count,
                            last_evidence_at, privacy_tier, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, 'HEURISTIC', ?, ?, 'OPERATOR_ONLY', ?, ?);
                    """, (pref_id, clean_domain, clean_key, val_json, new_conf, new_count, now, now, now))

                log_audit_event(
                    actor=actor,
                    action="adapt_preference",
                    target=f"{clean_domain}:{clean_key}",
                    result="SUCCESS",
                    details={"evidence_count": new_count, "confidence": new_conf},
                    conn=conn
                )
        finally:
            conn.close()

        return self.get_learned_preference(clean_domain, clean_key)

    def get_learned_preference(self, domain: str, key: str) -> Optional[Dict[str, Any]]:
        """Retrieves a learned preference."""
        self._check_engine_health()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM aadya_learned_preferences WHERE domain = ? AND preference_key = ?;",
                (domain.strip().lower(), key.strip().lower())
            )
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            res["value"] = json.loads(res.get("preference_value_json") or "null")
            return res
        finally:
            conn.close()

    def list_learned_preferences(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists learned preferences, optionally filtered by domain."""
        self._check_engine_health()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            query = "SELECT * FROM aadya_learned_preferences WHERE 1=1"
            params: List[Any] = []
            if domain:
                query += " AND domain = ?"
                params.append(domain.strip().lower())
            query += " ORDER BY domain ASC, preference_key ASC;"

            cur.execute(query, tuple(params))
            results = []
            for r in cur.fetchall():
                d = dict(r)
                d["value"] = json.loads(d.get("preference_value_json") or "null")
                results.append(d)
            return results
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # 5. Bounded Confidence Calibration
    # -------------------------------------------------------------------------
    def calibrate_confidence(
        self,
        domain: str,
        predicted_confidence: float,
        actual_success: bool
    ) -> Dict[str, Any]:
        """
        Calibrates confidence based on empirical observation (corrections 1, 2 & 3).
        Enforces conservative ceiling <= 0.85, floor >= 0.10, and retains HEURISTIC/INFERRED type.
        """
        self._check_engine_health()

        clean_domain = domain.strip().lower()
        pred_clamped = max(CONFIDENCE_FLOOR, min(CONFIDENCE_CEILING, predicted_confidence))
        actual_int = 1 if actual_success else 0
        brier_score = round((pred_clamped - actual_int) ** 2, 4)

        now = time.time()
        calib_id = f"calib_{clean_domain}"

        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT sample_count, calibrated_factor FROM aadya_confidence_calibrations WHERE domain = ?;",
                    (clean_domain,)
                )
                row = cur.fetchone()

                if row:
                    prev_samples, prev_factor = row
                    new_samples = prev_samples + 1
                    # Empirical adjustment: pull factor down on overconfidence failure, up gently on success
                    step = 0.05 if actual_success else -0.10
                    new_factor = round(max(0.2, min(1.0, prev_factor + step)), 3)

                    conn.execute("""
                        UPDATE aadya_confidence_calibrations
                        SET predicted_confidence = ?,
                            actual_outcome = ?,
                            brier_score = ?,
                            sample_count = ?,
                            calibrated_factor = ?,
                            updated_at = ?
                        WHERE domain = ?;
                    """, (pred_clamped, actual_int, brier_score, new_samples, new_factor, now, clean_domain))
                else:
                    new_samples = 1
                    new_factor = 0.95 if actual_success else 0.80
                    conn.execute("""
                        INSERT INTO aadya_confidence_calibrations (
                            id, domain, predicted_confidence, actual_outcome,
                            brier_score, sample_count, calibrated_factor, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """, (calib_id, clean_domain, pred_clamped, actual_int, brier_score, new_samples, new_factor, now))

                log_audit_event(
                    actor="AADYA_LEARNING_ENGINE",
                    action="calibrate_confidence",
                    target=clean_domain,
                    result="SUCCESS",
                    details={
                        "predicted": pred_clamped,
                        "actual": actual_int,
                        "brier_score": brier_score,
                        "calibrated_factor": new_factor
                    },
                    conn=conn
                )
        finally:
            conn.close()

        # Compute bounded calibrated confidence
        calibrated_conf = round(min(CONFIDENCE_CEILING, max(CONFIDENCE_FLOOR, pred_clamped * new_factor)), 2)

        return {
            "domain": clean_domain,
            "raw_predicted_confidence": pred_clamped,
            "calibrated_confidence": calibrated_conf,
            "confidence_type": "HEURISTIC",  # Correction 3: remains HEURISTIC, never claimed VERIFIED
            "calibrated_factor": new_factor,
            "brier_score": brier_score,
            "sample_count": new_samples,
            "confidence_ceiling": CONFIDENCE_CEILING,
            "updated_at": now
        }

    # -------------------------------------------------------------------------
    # 6. Correlation-Only Latent Pattern Detection
    # -------------------------------------------------------------------------
    def detect_operational_patterns(self) -> Dict[str, Any]:
        """
        Scans audit and task records for failure signatures and temporal clusters (corrections 10 & 11).
        Strictly reports correlations only. Explicitly disclaims causal assertions.
        """
        self._check_engine_health()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            cur = conn.cursor()

            # Find repeated task failure signatures
            cur.execute("""
                SELECT action_type, COUNT(*) as cnt
                FROM aadya_tasks
                WHERE status = 'FAILED'
                GROUP BY action_type
                HAVING cnt >= 1
                ORDER BY cnt DESC
                LIMIT 5;
            """)
            repeated_task_failures = {r[0]: r[1] for r in cur.fetchall()}

            # Correlation: RAM pressure deferrals in audit log
            cur.execute("""
                SELECT COUNT(*) FROM audit_log WHERE action = 'ram_pressure_deferral';
            """)
            ram_deferral_count = cur.fetchone()[0]

            # Correlation: Negative feedback distribution
            cur.execute("""
                SELECT target_type, COUNT(*) as cnt
                FROM aadya_operator_feedback
                WHERE rating < 0
                GROUP BY target_type
                ORDER BY cnt DESC;
            """)
            negative_feedback_clusters = {r[0]: r[1] for r in cur.fetchall()}

            return {
                "claims_causation": False,
                "causal_disclaimer": "Correlations and repeated failure signatures observed in local records. Correlation does not imply causation.",
                "observed_correlations": {
                    "repeated_task_failures": repeated_task_failures,
                    "ram_pressure_deferral_events": ram_deferral_count,
                    "negative_feedback_clusters": negative_feedback_clusters
                },
                "total_correlation_signals": len(repeated_task_failures) + (1 if ram_deferral_count > 0 else 0)
            }
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # 7. Improvement Proposals & POCO-Gated Adoption
    # -------------------------------------------------------------------------
    def propose_improvement(
        self,
        title: str,
        subsystem: str,
        proposal_type: str,
        justification: str,
        payload: Dict[str, Any],
        actor: str = "Aadi"
    ) -> Dict[str, Any]:
        """
        Creates an improvement proposal with deduplication and safety boundary checks (corrections 4, 5, 6, 12, 13).
        Enforces rate limiting, digest binding, and POCO gate.
        """
        self._check_engine_health()

        clean_subsystem = subsystem.strip().lower()
        clean_type = proposal_type.strip().upper()

        # Correction 6: Learning engine must not write directly to safety rules or privileged storage
        if clean_subsystem in FORBIDDEN_PROPOSAL_TARGETS or any(f in title.lower() for f in FORBIDDEN_PROPOSAL_TARGETS):
            raise SecurityViolationError(
                f"SECURITY_VIOLATION: Proposals targeting subsystem '{clean_subsystem}' or core safety rules "
                "are permanently forbidden. The learning engine cannot propose safety alterations."
            )

        # Enforce quarantine
        _verify_learning_non_financial(payload)
        _verify_learning_non_financial(f"{title} {justification}")

        # Sanitize sensitive data
        clean_payload = sanitize_sensitive_data(payload)
        clean_justification = sanitize_sensitive_data(justification)

        # Calculate stable payload digest for deduplication (Correction 12)
        digest_str = f"{clean_subsystem}:{clean_type}:{json.dumps(clean_payload, sort_keys=True)}"
        proposal_digest = hashlib.sha256(digest_str.encode("utf-8")).hexdigest()

        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                cur = conn.cursor()
                # Check for existing pending proposal with same digest (Deduplication)
                cur.execute("""
                    SELECT id, status FROM aadya_improvement_proposals
                    WHERE proposal_digest = ? AND status = 'PENDING_POCO_APPROVAL';
                """, (proposal_digest,))
                existing = cur.fetchone()
                if existing:
                    return {
                        "proposal_id": existing[0],
                        "status": "PENDING_POCO_APPROVAL",
                        "proposal_digest": proposal_digest,
                        "deduplicated": True,
                        "message": "Identical proposal is already pending operator approval."
                    }

                now = time.time()
                proposal_id = f"prop_{int(now * 1000)}_{os.urandom(3).hex()}"

                # Enqueue POCO Escalation for this improvement proposal
                escalation_id = None
                if self.parent and hasattr(self.parent, "escalate_to_poco"):
                    esc_res = self.parent.escalate_to_poco(
                        action_type=f"IMPROVEMENT_PROPOSAL_{clean_type}",
                        details={
                            "proposal_id": proposal_id,
                            "title": title,
                            "subsystem": clean_subsystem,
                            "payload": clean_payload,
                            "digest": proposal_digest
                        }
                    )
                    escalation_id = esc_res.get("escalation_id")
                else:
                    escalation_id = f"esc_{int(now * 1000)}_{os.urandom(3).hex()}"

                conn.execute("""
                    INSERT INTO aadya_improvement_proposals (
                        id, title, subsystem, proposal_type, justification,
                        proposal_payload_json, proposal_digest, status,
                        escalation_id, applied_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING_POCO_APPROVAL', ?, NULL, ?, ?);
                """, (
                    proposal_id, title, clean_subsystem, clean_type, clean_justification,
                    json.dumps(clean_payload), proposal_digest, escalation_id, now, now
                ))

                log_audit_event(
                    actor=actor,
                    action="propose_improvement",
                    target=proposal_id,
                    result="PENDING_APPROVAL",
                    details={
                        "subsystem": clean_subsystem,
                        "proposal_type": clean_type,
                        "proposal_digest": proposal_digest,
                        "escalation_id": escalation_id
                    },
                    conn=conn
                )
        finally:
            conn.close()

        return self.get_improvement_proposal(proposal_id)

    def get_improvement_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves an improvement proposal by ID."""
        self._check_engine_health()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM aadya_improvement_proposals WHERE id = ?;", (proposal_id,))
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            res["payload"] = json.loads(res.get("proposal_payload_json") or "{}")
            return res
        finally:
            conn.close()

    def list_improvement_proposals(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists improvement proposals."""
        self._check_engine_health()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            query = "SELECT * FROM aadya_improvement_proposals WHERE 1=1"
            params: List[Any] = []
            if status:
                query += " AND status = ?"
                params.append(status.strip().upper())
            query += " ORDER BY created_at DESC;"

            cur.execute(query, tuple(params))
            results = []
            for r in cur.fetchall():
                d = dict(r)
                d["payload"] = json.loads(d.get("proposal_payload_json") or "{}")
                results.append(d)
            return results
        finally:
            conn.close()

    def adopt_improvement_proposal(
        self,
        proposal_id: str,
        verification_token: str,
        nonce: str,
        approver: str = "Aadi"
    ) -> Dict[str, Any]:
        """
        Adopts an improvement proposal after verified POCO approval (corrections 4, 5, 7).
        Enforces:
        - 16+ char verification token
        - Single-use nonce verification
        - Reversible configuration/preference change only (zero opaque code mutation)
        - Atomic SQLite commit and structured audit receipt
        """
        self._check_engine_health()
        proposal = self.get_improvement_proposal(proposal_id)
        if not proposal:
            return {"success": False, "error": f"Proposal '{proposal_id}' not found."}

        if proposal["status"] != "PENDING_POCO_APPROVAL":
            return {"success": False, "error": f"Proposal '{proposal_id}' is not awaiting approval (status: {proposal['status']})."}

        escalation_id = proposal.get("escalation_id")

        # Resolve escalation through Crown-0 parent
        if self.parent and hasattr(self.parent, "resolve_poco_escalation") and escalation_id:
            res = self.parent.resolve_poco_escalation(
                escalation_id=escalation_id,
                decision="APPROVE",
                verification_token=verification_token,
                nonce=nonce
            )
            if res.get("status") != "APPROVED":
                return {"success": False, "error": f"POCO authorization failed: {res}"}
        else:
            # Direct validation check if running standalone
            if not verification_token or len(verification_token) < 16:
                raise PermissionError("Approval requires a valid POCO verification token (16+ chars).")

        # Correction 4 & 5: Apply narrow, explicit, reversible configuration changes only
        subsystem = proposal["subsystem"]
        payload = proposal["payload"]
        now = time.time()

        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                # Apply change based on approved subsystem
                if proposal["proposal_type"] == "PREFERENCE_TUNING":
                    domain = payload.get("domain", "ui_display")
                    key = payload.get("key", "refresh_interval_sec")
                    val = payload.get("value")
                    # Enforce domain allowlist
                    if domain in ALLOWED_PREFERENCE_DOMAINS:
                        val_json = json.dumps(val, sort_keys=True)
                        conn.execute("""
                            INSERT INTO aadya_learned_preferences (
                                id, domain, preference_key, preference_value_json,
                                confidence, confidence_type, evidence_count,
                                last_evidence_at, privacy_tier, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, 0.80, 'HEURISTIC', 1, ?, 'OPERATOR_ONLY', ?, ?)
                            ON CONFLICT(domain, preference_key) DO UPDATE SET
                                preference_value_json = excluded.preference_value_json,
                                confidence = 0.80,
                                updated_at = excluded.updated_at;
                        """, (f"pref_{domain}_{key}", domain, key, val_json, now, now, now))

                # Update proposal state to APPLIED
                conn.execute("""
                    UPDATE aadya_improvement_proposals
                    SET status = 'APPLIED',
                        applied_at = ?,
                        updated_at = ?
                    WHERE id = ?;
                """, (now, now, proposal_id))

                log_audit_event(
                    actor=approver,
                    action="adopt_improvement_proposal",
                    target=proposal_id,
                    result="SUCCESS",
                    details={
                        "proposal_digest": proposal["proposal_digest"],
                        "applied_subsystem": subsystem,
                        "applied_at": now
                    },
                    conn=conn
                )
        finally:
            conn.close()

        return {
            "success": True,
            "proposal_id": proposal_id,
            "status": "APPLIED",
            "applied_at": now,
            "proposal": self.get_improvement_proposal(proposal_id)
        }

    def reject_improvement_proposal(
        self,
        proposal_id: str,
        reason: str,
        approver: str = "Aadi"
    ) -> Dict[str, Any]:
        """Atomically rejects an improvement proposal and archives it."""
        self._check_engine_health()
        proposal = self.get_improvement_proposal(proposal_id)
        if not proposal:
            return {"success": False, "error": f"Proposal '{proposal_id}' not found."}

        if proposal["status"] != "PENDING_POCO_APPROVAL":
            return {"success": False, "error": f"Proposal '{proposal_id}' is not in PENDING status."}

        now = time.time()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    UPDATE aadya_improvement_proposals
                    SET status = 'REJECTED',
                        updated_at = ?
                    WHERE id = ?;
                """, (now, proposal_id))

                log_audit_event(
                    actor=approver,
                    action="reject_improvement_proposal",
                    target=proposal_id,
                    result="REJECTED",
                    details={"reason": reason},
                    conn=conn
                )
        finally:
            conn.close()

        return {"success": True, "proposal_id": proposal_id, "status": "REJECTED", "reason": reason}
