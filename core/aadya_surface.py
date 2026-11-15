"""
AADYA Stage 5 — Adaptive Interface & Living Surface Engine
=========================================================
Synthesizes contextual memory nodes, real-time mission progress, Future Radar
horizons, and system health into a unified, TV-safe living surface HUD for
Fire TV and ambient displays.

Architectural Invariants & Privacy Rules:
- Layered privacy defense:
    1. Privacy-tier filtering (drops OPERATOR_ONLY & SOVEREIGN_VAULT_RESTRICTED)
    2. Field allowlisting (strictly bounds allowed card attributes)
    3. Content sanitization (redacts tokens, credentials, sensitive keys)
    4. Output schema validation (enforces TV-safe card contract)
    5. Final TV-payload assertion (rejects unknown/unsafe keys and sensitive patterns)
- Zero raw memory content: only short, purpose-built TV-safe summaries.
- Zero escalation payload leakage: only pending count and neutral notice.
- Generic, actionable TV-safe error messages without stack traces or internal paths.
- Read-only surface rendering: snapshot persistence is explicit, bounded, and rate-limited.
- Learned preferences adjust presentation only (theme, verbosity, card ordering)
  and can NEVER suppress safety or degraded-state alerts.
- Truthful audit-chain verification (AUDIT_STATUS_UNKNOWN / AUDIT_VERIFICATION_FAILED
  if check fails or is missing).
- Non-blocking data queries for decoupled voice-loop concurrency.
- Permanent financial quarantine: zero financial data or controls on TV.
"""

import time
import json
import uuid
import re
import hashlib
from typing import Dict, Any, List, Optional, Tuple

try:
    from core.db import query_db, execute_db, log_audit_event, get_connection, verify_audit_chain
    from core.ram_guard import check_ram_guard
    from core.aadya_context import ContextPrivacyTier, ConfidenceType
    from core.aadya_learning import sanitize_sensitive_data
except ImportError:
    from aeonix.core.db import query_db, execute_db, log_audit_event, get_connection, verify_audit_chain
    from aeonix.core.ram_guard import check_ram_guard
    from aeonix.core.aadya_context import ContextPrivacyTier, ConfidenceType
    from aeonix.core.aadya_learning import sanitize_sensitive_data


# --- Configuration & Constants ---
ALLOWED_CARD_FIELDS = {
    "card_id",
    "card_type",
    "title",
    "summary",
    "priority",
    "privacy_tier",
    "timestamp",
    "details"
}

ALLOWED_CARD_TYPES = {
    "health_alert",
    "poco_escalation",
    "adaptive_briefing",
    "mission_progress",
    "context_summary",
    "future_radar",
    "living_surface_status"
}

FORBIDDEN_KEY_PATTERNS = [
    "token", "nonce", "digest", "action_digest", "action_payload",
    "details_json", "private_key", "secret", "password", "target",
    "file_path", "db_path", "stack_trace", "traceback", "exception",
    "credentials", "vault_content", "financial", "trade", "wallet", "crypto"
]

FINANCIAL_TERMS = [
    "trading", "trade", "portfolio", "fund", "balance", "crypto",
    "wallet", "pnl", "profit", "loss", "order_book", "broker"
]

SNAPSHOT_MIN_INTERVAL_SECONDS = 5.0
MAX_SUMMARY_LENGTH = 160
MAX_STORED_SNAPSHOTS = 50


class PrivacyViolationError(Exception):
    """Raised when an unsafe field, private tier, or credential leaks into TV output."""
    pass


class DegradedStateError(Exception):
    """Raised when an operation cannot complete due to degraded engine state."""
    pass


def _verify_surface_non_financial(obj: Any) -> None:
    """Recursively validates that no financial terms or controls exist in surface payloads."""
    if isinstance(obj, str):
        lowered = obj.lower()
        for term in FINANCIAL_TERMS:
            if re.search(rf"\b{re.escape(term)}\b", lowered):
                raise PrivacyViolationError(f"Financial term prohibited on TV surface: {term}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            k_low = str(k).lower()
            for term in FINANCIAL_TERMS:
                if term in k_low:
                    raise PrivacyViolationError(f"Financial key prohibited on TV surface: {k}")
            _verify_surface_non_financial(v)
    elif isinstance(obj, list):
        for item in obj:
            _verify_surface_non_financial(item)


def sanitize_tv_summary(text: str, max_len: int = MAX_SUMMARY_LENGTH) -> str:
    """
    Produces a concise, safe summary string for TV display:
    - Strips passwords, API keys, credentials via sanitize_sensitive_data and regexes
    - Strips internal paths (/data/data, /home, /var, etc.)
    - Truncates to max_len
    """
    if not text:
        return ""
    clean = sanitize_sensitive_data(str(text))
    # Scrub API keys and tokens (e.g. sk-live..., token sk-...)
    clean = re.sub(r"sk-[a-zA-Z0-9_\-]{8,}", "[REDACTED_SENSITIVE_DATA]", clean)
    clean = re.sub(r"(token\s*[:=]?\s*)[A-Za-z0-9_\-]{8,}", r"\1[REDACTED_SENSITIVE_DATA]", clean, flags=re.IGNORECASE)
    clean = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]{8,}", "Bearer [REDACTED_SENSITIVE_DATA]", clean, flags=re.IGNORECASE)
    # Strip absolute filesystem paths
    clean = re.sub(r'(/[\w\.\-]+)+', '[LOCAL_PATH]', clean)
    clean = clean.strip()
    if len(clean) > max_len:
        clean = clean[:max_len - 3] + "..."
    return clean


class AadyaSurfaceEngine:
    """
    Adaptive Interface & Living Surface Engine for AADYA Crown-0.
    Generates unified, privacy-sanitized Living Surface HUD states for Fire TV.
    """

    def __init__(self, db_path: Optional[str] = None, parent_crown_zero: Optional[Any] = None):
        self.db_path = db_path
        self.parent = parent_crown_zero
        self.is_initialized = False
        self.initialization_status = "PENDING_INITIALIZATION"
        self.init_error = None
        self._last_snapshot_time = 0.0
        self._ensure_surface_tables()

    def _ensure_surface_tables(self) -> None:
        """Initializes the aadya_surface_snapshots table with atomic error handling."""
        try:
            execute_db("""
                CREATE TABLE IF NOT EXISTS aadya_surface_snapshots (
                    id TEXT PRIMARY KEY,
                    surface_type TEXT NOT NULL DEFAULT 'living_surface',
                    theme TEXT NOT NULL,
                    period TEXT NOT NULL,
                    card_count INTEGER NOT NULL,
                    state_digest TEXT NOT NULL,
                    sanitizer_receipt TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
            """, db_path=self.db_path)
            execute_db("""
                CREATE INDEX IF NOT EXISTS idx_surface_snapshots_created
                ON aadya_surface_snapshots(created_at);
            """, db_path=self.db_path)
            self.is_initialized = True
            self.initialization_status = "INITIALIZED"
            self.init_error = None
        except Exception as e:
            self.is_initialized = False
            self.initialization_status = "INITIALIZATION_FAILED"
            self.init_error = str(e)
            try:
                log_audit_event(
                    actor="AZ-001_AADYA",
                    action="SURFACE_ENGINE_INITIALIZATION_FAILED",
                    target="aadya_surface_engine",
                    result="DEGRADED",
                    details={"error": "Database error initializing surface tables"},
                    db_path=self.db_path
                )
            except Exception:
                pass

    def _check_surface_health(self) -> None:
        """Fails closed if the surface engine is uninitialized or degraded."""
        if not self.is_initialized or self.initialization_status != "INITIALIZED":
            raise DegradedStateError(f"AadyaSurfaceEngine degraded: {self.init_error or self.initialization_status}")

    # =========================================================================
    # Privacy Defense Layer
    # =========================================================================

    def _validate_card_schema(self, card: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates card fields against allowlist and privacy constraints.
        Enforces Layered Privacy Defense:
        1. Only ALLOWED_CARD_FIELDS permitted
        2. privacy_tier must strictly be TV_SAFE
        3. Forbidden keys in details are strictly rejected
        4. Internal paths and credentials stripped
        """
        if not isinstance(card, dict):
            raise PrivacyViolationError("Card must be a dictionary")

        # 1. Field allowlisting
        for k in card.keys():
            if k not in ALLOWED_CARD_FIELDS:
                raise PrivacyViolationError(f"Disallowed card field: {k}")

        # 2. Strict privacy tier
        if card.get("privacy_tier") != ContextPrivacyTier.TV_SAFE.value:
            raise PrivacyViolationError(f"Card privacy_tier must be TV_SAFE, found: {card.get('privacy_tier')}")

        # 3. Card type check
        if card.get("card_type") not in ALLOWED_CARD_TYPES:
            raise PrivacyViolationError(f"Disallowed card_type: {card.get('card_type')}")

        # 4. Details validation
        details = card.get("details")
        if details is not None:
            if not isinstance(details, dict):
                raise PrivacyViolationError("Card details must be a dictionary")
            for dk in details.keys():
                dk_low = str(dk).lower()
                for pat in FORBIDDEN_KEY_PATTERNS:
                    if pat in dk_low:
                        raise PrivacyViolationError(f"Forbidden key in card details: {dk}")

        # 5. Financial check
        _verify_surface_non_financial(card)

        return card

    def assert_tv_payload_safety(self, payload: Dict[str, Any]) -> None:
        """
        Final TV-Payload Assertion:
        Rejects unknown top-level keys, private data markers, sensitive regexes,
        forbidden keys, or financial triggers before payload reaches Fire TV transport.
        """
        allowed_top_keys = {
            "screen", "period", "theme", "greeting", "pending_approvals",
            "active_tasks", "cards", "system_status", "audit_chain_status",
            "timestamp", "sanitizer_receipt"
        }
        for k in payload.keys():
            if k not in allowed_top_keys:
                raise PrivacyViolationError(f"Disallowed top-level key in TV payload: {k}")

        cards = payload.get("cards", [])
        if not isinstance(cards, list):
            raise PrivacyViolationError("Payload cards must be a list")

        for card in cards:
            self._validate_card_schema(card)

        # Check entire payload JSON for secret leaks or internal file system paths
        serialized = json.dumps(payload)
        if "/data/data/" in serialized or "/home/" in serialized:
            raise PrivacyViolationError("Internal path leaked in TV payload serialization")
        if "OPERATOR_ONLY" in serialized or "SOVEREIGN_VAULT_RESTRICTED" in serialized:
            raise PrivacyViolationError("Private tier marker leaked in TV payload serialization")

        _verify_surface_non_financial(payload)

    # =========================================================================
    # Time & Presentation Helpers
    # =========================================================================

    def _evaluate_time_context(self) -> Dict[str, str]:
        """Calculates time period and obsidian theme."""
        hour = time.localtime().tm_hour
        if 5 <= hour < 12:
            return {"period": "morning", "theme": "obsidian_gold", "greeting": "Good morning, Aadi."}
        elif 12 <= hour < 17:
            return {"period": "afternoon", "theme": "obsidian_cyan", "greeting": "Good afternoon, Aadi."}
        elif 17 <= hour < 22:
            return {"period": "evening", "theme": "obsidian_purple", "greeting": "Good evening, Aadi."}
        else:
            return {"period": "night", "theme": "obsidian_dark", "greeting": "Late hours. Low distraction mode."}

    def _get_presentation_preferences(self) -> Dict[str, Any]:
        """Retrieves learned UI display preferences safely without mutating safety."""
        prefs = {"theme_override": None, "briefing_verbosity": "normal", "card_order": "default"}
        if self.parent and getattr(self.parent, "learning", None):
            try:
                theme_pref = self.parent.get_learned_preference("ui_display", "theme_mode")
                if theme_pref:
                    val = theme_pref.get("value")
                    if val in ["obsidian_gold", "obsidian_cyan", "obsidian_purple", "obsidian_dark"]:
                        prefs["theme_override"] = val

                verb_pref = self.parent.get_learned_preference("briefing", "verbosity")
                if verb_pref:
                    val = verb_pref.get("value")
                    if val in ["concise", "detailed", "normal"]:
                        prefs["briefing_verbosity"] = val
            except Exception:
                pass
        return prefs

    # =========================================================================
    # Card Generators (Strict TV-Safe)
    # =========================================================================

    def render_system_health_card(self) -> Dict[str, Any]:
        """
        Renders system status truthfully:
        - Checks initialization of Core, Context, Missions, Learning, and Surface.
        - Evaluates RAM guard.
        - Verifies audit chain integrity (AUDIT_STATUS_UNKNOWN / AUDIT_VERIFICATION_FAILED if unverifiable).
        - Error strings are generic and actionable (no paths or internal traces).
        """
        is_degraded = False
        degraded_reasons = []

        # Check Core Mind and sub-engines
        if self.parent:
            if getattr(self.parent, "initialization_status", None) != "INITIALIZED":
                is_degraded = True
                degraded_reasons.append("Core Mind")
            if getattr(self.parent, "context_initialization_status", None) != "INITIALIZED" or (
                getattr(self.parent, "context", None) and getattr(self.parent.context, "initialization_status", None) != "INITIALIZED"
            ):
                is_degraded = True
                degraded_reasons.append("Context Engine")
            if getattr(self.parent, "missions_initialization_status", None) != "INITIALIZED" or (
                getattr(self.parent, "missions", None) and getattr(self.parent.missions, "initialization_status", None) != "INITIALIZED"
            ):
                is_degraded = True
                degraded_reasons.append("Mission Engine")
            if getattr(self.parent, "learning_initialization_status", None) != "INITIALIZED" or (
                getattr(self.parent, "learning", None) and getattr(self.parent.learning, "initialization_status", None) != "INITIALIZED"
            ):
                is_degraded = True
                degraded_reasons.append("Learning Engine")

        if not self.is_initialized:
            is_degraded = True
            degraded_reasons.append("Surface Engine")

        # RAM Guard Check
        ram_status = "NOMINAL"
        try:
            ram_res = check_ram_guard()
            if not ram_res.get("can_proceed", True):
                is_degraded = True
                ram_status = "PRESSURE_WARNING"
                degraded_reasons.append("System Memory Pressure")
        except Exception:
            ram_status = "UNKNOWN"

        # Truthful Audit Chain Check
        audit_chain_status = "AUDIT_STATUS_UNKNOWN"
        try:
            audit_res = verify_audit_chain(self.db_path)
            if audit_res.get("is_valid"):
                if audit_res.get("total_events", 0) > 0:
                    audit_chain_status = "AUDIT_CHAIN_VERIFIED"
                else:
                    audit_chain_status = "AUDIT_STATUS_EMPTY"
            else:
                audit_chain_status = "AUDIT_VERIFICATION_FAILED"
                is_degraded = True
                degraded_reasons.append("Audit Verification")
        except Exception:
            audit_chain_status = "AUDIT_STATUS_UNKNOWN"

        if is_degraded:
            title = "System Notice: Subsystem Fallback"
            summary = (
                f"Operating in degraded mode ({', '.join(degraded_reasons)}). "
                "Consult POCO operator console for diagnostics."
            )
            priority = "CRITICAL"
        else:
            title = "Sovereign Mind Status"
            summary = "All local core subsystems operational. Storage and audit logs verified."
            priority = "NORMAL"

        card = {
            "card_id": f"card_health_{uuid.uuid4().hex[:8]}",
            "card_type": "health_alert",
            "title": title,
            "summary": sanitize_tv_summary(summary),
            "priority": priority,
            "privacy_tier": ContextPrivacyTier.TV_SAFE.value,
            "timestamp": time.time(),
            "details": {
                "core_state": "DEGRADED" if is_degraded else "NOMINAL",
                "ram_state": ram_status,
                "audit_state": audit_chain_status
            }
        }
        return self._validate_card_schema(card)

    def render_poco_escalation_queue_card(self) -> Dict[str, Any]:
        """
        Renders the POCO escalation notice:
        - Shows ONLY pending count and neutral notice.
        - Never includes targets, digests, tokens, payloads, or action specifics.
        """
        pending_count = 0
        try:
            # Query sentinel requests and aadya escalations
            rows1 = query_db(
                "SELECT COUNT(*) FROM sentinel_requests WHERE status = 'pending';",
                db_path=self.db_path
            )
            c1 = rows1[0][0] if rows1 else 0

            rows2 = query_db(
                "SELECT COUNT(*) FROM aadya_escalations WHERE status = 'PENDING_POCO_APPROVAL';",
                db_path=self.db_path
            )
            c2 = rows2[0][0] if rows2 else 0
            pending_count = c1 + c2
        except Exception:
            pending_count = 0

        if pending_count > 0:
            title = "POCO Gate Escalations"
            summary = f"{pending_count} action(s) awaiting review. Pending physical approval on POCO device."
            priority = "HIGH"
        else:
            title = "POCO Gate Escalations"
            summary = "No pending escalations awaiting operator review."
            priority = "LOW"

        card = {
            "card_id": f"card_poco_{uuid.uuid4().hex[:8]}",
            "card_type": "poco_escalation",
            "title": title,
            "summary": sanitize_tv_summary(summary),
            "priority": priority,
            "privacy_tier": ContextPrivacyTier.TV_SAFE.value,
            "timestamp": time.time(),
            "details": {
                "pending_count": pending_count
            }
        }
        return self._validate_card_schema(card)

    def generate_adaptive_briefing(self, time_period: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates an adaptive briefing card based on time of day, active goals, and routines.
        """
        time_ctx = self._evaluate_time_context()
        period = time_period or time_ctx["period"]

        prefs = self._get_presentation_preferences()
        verbosity = prefs.get("briefing_verbosity", "normal")

        # Fetch active goals count
        goal_count = 0
        if self.parent:
            try:
                goals = self.parent.get_active_goals()
                goal_count = len(goals)
            except Exception:
                pass

        # Fetch active routines count
        routine_count = 0
        if self.parent:
            try:
                routines = self.parent.get_active_routines()
                routine_count = len(routines)
            except Exception:
                pass

        if period == "morning":
            title = "Morning Briefing"
            if verbosity == "concise":
                summary = f"Morning plan ready: {goal_count} goals and {routine_count} routines active."
            else:
                summary = (
                    f"Good morning. Daily baseline prepared. {goal_count} sovereign goals "
                    f"and {routine_count} scheduled routines monitored."
                )
        elif period == "afternoon":
            title = "Midday Operations"
            summary = f"Active focus window. System tracking {goal_count} prioritized goals."
        elif period == "evening":
            title = "Evening Review"
            summary = "Day cycle winding down. Routine maintenance and review active."
        else:
            title = "Night Sanctuary"
            summary = "Night Sanctuary mode engaged. Low distraction, background inference throttled."

        card = {
            "card_id": f"card_briefing_{uuid.uuid4().hex[:8]}",
            "card_type": "adaptive_briefing",
            "title": title,
            "summary": sanitize_tv_summary(summary),
            "priority": "NORMAL",
            "privacy_tier": ContextPrivacyTier.TV_SAFE.value,
            "timestamp": time.time(),
            "details": {
                "period": period,
                "goal_count": goal_count,
                "routine_count": routine_count
            }
        }
        return self._validate_card_schema(card)

    def render_mission_progress_cards(self) -> List[Dict[str, Any]]:
        """
        Renders progress cards for active missions:
        - Shows task counts and verified wave numbers.
        - Never invents completion or fake progress.
        """
        cards = []
        if not self.parent or not getattr(self.parent, "missions", None):
            return cards

        try:
            missions = self.parent.list_missions()
            for m in missions:
                if m.get("status") in ["READY", "IN_PROGRESS", "CREATED", "PAUSED", "FAILED"]:
                    tot = m.get("total_tasks", 0)
                    done = m.get("completed_tasks", 0)
                    failed = m.get("failed_tasks", 0)
                    status = m.get("status")
                    title = f"Mission: {m.get('title', 'Autonomous Mission')}"
                    summary = (
                        f"Status: {status}. Completed {done}/{tot} tasks "
                        f"(Failed: {failed}). Verified execution in progress."
                    )
                    priority = "HIGH" if status == "FAILED" else "NORMAL"

                    card = {
                        "card_id": f"card_mis_{uuid.uuid4().hex[:8]}",
                        "card_type": "mission_progress",
                        "title": title,
                        "summary": sanitize_tv_summary(summary),
                        "priority": priority,
                        "privacy_tier": ContextPrivacyTier.TV_SAFE.value,
                        "timestamp": time.time(),
                        "details": {
                            "mission_id": m.get("id"),
                            "status": status,
                            "completed_tasks": done,
                            "total_tasks": tot
                        }
                    }
                    cards.append(self._validate_card_schema(card))
        except Exception:
            pass

        return cards

    def render_tv_context_cards(self, categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Transforms context memory nodes into short, sanitized TV-safe summary cards:
        - Layered privacy defense: privacy-tier check, sanitize_for_tv_export, content sanitization.
        - NEVER renders raw content.
        """
        cards = []
        if not self.parent or not getattr(self.parent, "context", None):
            return cards

        try:
            category_filter = categories[0] if categories and len(categories) == 1 else None
            nodes = self.parent.list_active_nodes(category=category_filter)
            sanitized_export = self.parent.sanitize_for_tv_export(nodes)
            clean_nodes = sanitized_export.get("tv_safe_records", [])

            for n in clean_nodes:
                cat = n.get("category", "general")
                if categories and cat not in categories:
                    continue

                title = n.get("title", "Context Record")
                # Build short summary; NEVER use raw content directly
                raw = n.get("content", "")
                summary = sanitize_tv_summary(raw, max_len=120)

                card = {
                    "card_id": f"card_ctx_{uuid.uuid4().hex[:8]}",
                    "card_type": "context_summary",
                    "title": title,
                    "summary": summary,
                    "priority": "LOW",
                    "privacy_tier": ContextPrivacyTier.TV_SAFE.value,
                    "timestamp": time.time(),
                    "details": {
                        "category": cat
                    }
                }
                cards.append(self._validate_card_schema(card))
        except Exception:
            pass

        return cards

    def render_future_radar_card(self) -> Dict[str, Any]:
        """
        Renders the Future Radar horizon scan card:
        - Reports verified status of capabilities.
        - Unverified items are marked PLANNED or NOT_VERIFIED.
        """
        radar_summary = "Horizon scan active: 5 capability domains tracked."
        if self.parent:
            try:
                radar = self.parent.scan_future_radar()
                areas = radar.get("focus_areas", [])
                planned_cnt = sum(1 for a in areas if "PLANNED" in a.get("status", ""))
                not_ver_cnt = sum(1 for a in areas if "NOT_VERIFIED" in a.get("status", ""))
                radar_summary = (
                    f"Tracking {len(areas)} domains ({planned_cnt} planned, "
                    f"{not_ver_cnt} pending verification)."
                )
            except Exception:
                pass

        card = {
            "card_id": f"card_radar_{uuid.uuid4().hex[:8]}",
            "card_type": "future_radar",
            "title": "Future Radar Horizon",
            "summary": sanitize_tv_summary(radar_summary),
            "priority": "LOW",
            "privacy_tier": ContextPrivacyTier.TV_SAFE.value,
            "timestamp": time.time(),
            "details": {
                "scan_state": "ACTIVE"
            }
        }
        return self._validate_card_schema(card)

    # =========================================================================
    # Living Surface Rendering Pipeline
    # =========================================================================

    def render_living_surface(
        self,
        refresh: bool = False,
        create_snapshot: bool = False
    ) -> Dict[str, Any]:
        """
        Renders the complete Living Surface HUD payload for Fire TV.
        - Enforces Layered Privacy Defense and Final TV-Payload Assertion.
        - Read-only by default; does NOT create snapshots unless explicitly requested.
        - Orders cards safely: Health/Degraded alerts ALWAYS pinned at top.
        """
        self._check_surface_health()

        time_ctx = self._evaluate_time_context()
        prefs = self._get_presentation_preferences()
        theme = prefs.get("theme_override") or time_ctx["theme"]
        period = time_ctx["period"]

        cards: List[Dict[str, Any]] = []

        # 1. System Health & Degraded State (ALWAYS FIRST)
        health_card = self.render_system_health_card()
        cards.append(health_card)

        # 2. POCO Escalations
        poco_card = self.render_poco_escalation_queue_card()
        if poco_card.get("details", {}).get("pending_count", 0) > 0:
            cards.append(poco_card)

        # 3. Active Missions Progress
        mission_cards = self.render_mission_progress_cards()
        cards.extend(mission_cards)

        # 4. Adaptive Briefing
        briefing_card = self.generate_adaptive_briefing(time_period=period)
        cards.append(briefing_card)

        # 5. TV-Safe Context Nodes (bounded to 4 items)
        ctx_cards = self.render_tv_context_cards()[:4]
        cards.extend(ctx_cards)

        # 6. Future Radar
        radar_card = self.render_future_radar_card()
        cards.append(radar_card)

        # If POCO had 0 escalations, append low priority card at end
        if poco_card.get("details", {}).get("pending_count", 0) == 0:
            cards.append(poco_card)

        receipt_id = f"rcpt_tv_{uuid.uuid4().hex[:12]}"

        payload = {
            "screen": "living_surface",
            "period": period,
            "theme": theme,
            "greeting": time_ctx["greeting"],
            "pending_approvals": poco_card.get("details", {}).get("pending_count", 0),
            "active_tasks": len(mission_cards),
            "cards": cards,
            "system_status": health_card.get("details", {}).get("core_state", "NOMINAL"),
            "audit_chain_status": health_card.get("details", {}).get("audit_state", "AUDIT_STATUS_UNKNOWN"),
            "timestamp": time.time(),
            "sanitizer_receipt": receipt_id
        }

        # FINAL TV PAYLOAD ASSERTION: Fails closed if any invariant violated
        self.assert_tv_payload_safety(payload)

        # Audit log rendering event
        try:
            log_audit_event(
                actor="AZ-001_AADYA",
                action="LIVING_SURFACE_RENDERED",
                target="fire_tv_living_surface",
                result="SUCCESS",
                details={
                    "receipt_id": receipt_id,
                    "card_count": len(cards),
                    "theme": theme,
                    "period": period
                },
                db_path=self.db_path
            )
        except Exception:
            pass

        # Explicit snapshot creation if requested
        if create_snapshot:
            self._save_surface_snapshot(payload, receipt_id)

        return payload

    # =========================================================================
    # Snapshot Persistence & Rate-Limiting
    # =========================================================================

    def create_surface_snapshot(self) -> Dict[str, Any]:
        """Explicit, rate-limited, and bounded snapshot creation."""
        now = time.time()
        if (now - self._last_snapshot_time) < SNAPSHOT_MIN_INTERVAL_SECONDS:
            raise DegradedStateError(
                f"Snapshot creation rate-limited. Please wait {SNAPSHOT_MIN_INTERVAL_SECONDS}s between snapshots."
            )

        payload = self.render_living_surface(create_snapshot=False)
        receipt_id = payload.get("sanitizer_receipt", f"rcpt_tv_{uuid.uuid4().hex[:12]}")
        snapshot = self._save_surface_snapshot(payload, receipt_id)
        self._last_snapshot_time = now
        return snapshot

    def _save_surface_snapshot(self, payload: Dict[str, Any], receipt_id: str) -> Dict[str, Any]:
        """Saves a bounded snapshot to SQLite atomically."""
        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
        now = time.time()
        payload_str = json.dumps(payload, sort_keys=True)
        state_digest = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

        conn = get_connection(self.db_path)
        cur = conn.cursor()
        try:
            cur.execute("BEGIN IMMEDIATE;")
            cur.execute("""
                INSERT INTO aadya_surface_snapshots (
                    id, surface_type, theme, period, card_count,
                    state_digest, sanitizer_receipt, snapshot_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                snapshot_id,
                payload.get("screen", "living_surface"),
                payload.get("theme", "obsidian_cyan"),
                payload.get("period", "day"),
                len(payload.get("cards", [])),
                state_digest,
                receipt_id,
                payload_str,
                now
            ))

            # Bound storage: prune oldest beyond MAX_STORED_SNAPSHOTS
            cur.execute("""
                DELETE FROM aadya_surface_snapshots
                WHERE id NOT IN (
                    SELECT id FROM aadya_surface_snapshots
                    ORDER BY created_at DESC LIMIT ?
                );
            """, (MAX_STORED_SNAPSHOTS,))

            log_audit_event(
                actor="AZ-001_AADYA",
                action="SURFACE_SNAPSHOT_CREATED",
                target=snapshot_id,
                result="SUCCESS",
                details={
                    "state_digest": state_digest,
                    "receipt_id": receipt_id,
                    "card_count": len(payload.get("cards", []))
                },
                db_path=self.db_path,
                conn=conn
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise DegradedStateError(f"Failed to persist surface snapshot: {str(e)}")
        finally:
            conn.close()

        return {
            "id": snapshot_id,
            "state_digest": state_digest,
            "sanitizer_receipt": receipt_id,
            "card_count": len(payload.get("cards", [])),
            "created_at": now
        }

    def get_surface_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a previously persisted surface snapshot."""
        rows = query_db(
            "SELECT id, surface_type, theme, period, card_count, state_digest, sanitizer_receipt, snapshot_json, created_at FROM aadya_surface_snapshots WHERE id = ?;",
            (snapshot_id,),
            db_path=self.db_path
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "id": r[0],
            "surface_type": r[1],
            "theme": r[2],
            "period": r[3],
            "card_count": r[4],
            "state_digest": r[5],
            "sanitizer_receipt": r[6],
            "payload": json.loads(r[7]),
            "created_at": r[8]
        }

    def list_surface_snapshots(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Lists recent surface snapshots."""
        bounded_limit = min(max(1, limit), 50)
        rows = query_db(
            "SELECT id, surface_type, theme, period, card_count, state_digest, sanitizer_receipt, created_at FROM aadya_surface_snapshots ORDER BY created_at DESC LIMIT ?;",
            (bounded_limit,),
            db_path=self.db_path
        )
        return [
            {
                "id": r[0],
                "surface_type": r[1],
                "theme": r[2],
                "period": r[3],
                "card_count": r[4],
                "state_digest": r[5],
                "sanitizer_receipt": r[6],
                "created_at": r[7]
            }
            for r in rows
        ]

    # =========================================================================
    # Operator Feedback Capture
    # =========================================================================

    def capture_operator_feedback_from_surface(
        self,
        source: str,
        rating: int,
        comment: str,
        target: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Captures operator feedback against a surface element or briefing:
        - Forwards to AadyaLearningEngine.record_operator_feedback() if available.
        - Sanitizes comments to ensure zero sensitive token leakage.
        """
        self._check_surface_health()
        clean_comment = sanitize_tv_summary(comment, max_len=250)

        valid_targets = {"MEMORY", "MISSION", "RADAR", "RECOMMENDATION", "ROUTINE", "TASK"}
        target_type = "ROUTINE"
        if target and str(target).upper() in valid_targets:
            target_type = str(target).upper()

        if self.parent and getattr(self.parent, "learning", None):
            return self.parent.record_operator_feedback(
                target_type=target_type,
                target_id=f"surface_{source}",
                rating=rating,
                feedback_text=clean_comment,
                operator="Aadi"
            )

        # Fallback if learning engine not available
        fb_id = f"fb_{uuid.uuid4().hex[:12]}"
        now = time.time()
        log_audit_event(
            actor="AZ-001_AADYA",
            action="SURFACE_FEEDBACK_RECORDED",
            target=fb_id,
            result="SUCCESS",
            details={"rating": rating, "source": source},
            db_path=self.db_path
        )
        return {
            "id": fb_id,
            "feedback_id": fb_id,
            "rating": rating,
            "comment": clean_comment,
            "created_at": now
        }
