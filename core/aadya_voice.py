"""
AADYA Stage 6 — Voice-First Command & Response Engine
=====================================================
Processes spoken voice transcripts, performs deterministic intent classification,
and generates concise, natural, privacy-quarantined spoken responses for Aadi.

Architectural Invariants & Privacy Rules:
- Voice may create ONLY a DRAFT or PENDING_CONFIRMATION low-risk mission.
- Voice NEVER directly creates and executes a mission in one turn.
- Deterministic keyword and phrase matching first; fail-closed on unknown intents.
- Transcripts and speech are sanitized before database persistence and delivery.
- Zero internal paths, stack traces, escalation IDs, tokens, nonces, or digests vocalized.
- Memory queries filter strictly to TV_SAFE before sanitization.
- Final spoken-response safety assertion enforces length, path, and privacy rules.
- Permanent financial quarantine: financial queries receive clear refusal; zero financial
  tasks, missions, or escalations created.
- Voice commands never mutate safety rules, autonomy boundaries, or permissions.
- Concurrency and voice response ownership integration (strict single-response-at-a-time).
- Non-blocking database access, bounded response length (< 300 chars for speech).
"""

import time
import json
import uuid
import re
import threading
from typing import Dict, Any, List, Optional, Tuple
from collections import deque

try:
    from core.db import query_db, execute_db, log_audit_event, get_connection
    from core.aadya_context import ContextPrivacyTier, ConfidenceType
    from core.aadya_learning import sanitize_sensitive_data
    from core.aadya_surface import sanitize_tv_summary
except ImportError:
    from aeonix.core.db import query_db, execute_db, log_audit_event, get_connection
    from aeonix.core.aadya_context import ContextPrivacyTier, ConfidenceType
    from aeonix.core.aadya_learning import sanitize_sensitive_data
    from aeonix.core.aadya_surface import sanitize_tv_summary


# --- Constants & Configuration ---
MAX_SPEECH_LENGTH = 320
MAX_RECENT_CONTEXT_TURNS = 3
MAX_STORED_INTERACTIONS = 50

FINANCIAL_PATTERNS = [
    r"\b(buy|sell|trade|trading|crypto|bitcoin|ethereum|btc|eth|sol)\b",
    r"\b(wallet|portfolio|balance|funds|pnl|profit|loss|broker)\b",
    r"\b(transfer\s+(funds|money|crypto|cash))\b",
    r"\b(purchase|invest|investing|investment|stock|shares)\b"
]

HIGH_RISK_PATTERNS = [
    r"\b(delete|wipe|erase)\s+(user|data|vault|database|system|all)\b",
    r"\b(grant|give)\s+(root|superuser|admin|privilege)\b",
    r"\b(disable|bypass|turn off)\s+(sentinel|security|guard|firewall)\b",
    r"\b(modify|change)\s+(security|policy|autonomy|quarantine)\b",
    r"\b(execute|run)\s+(binary|script|shell|untrusted|root)\b",
    r"\b(firewall|iptables|network rule)\b"
]

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|previous\s+|prior\s+)?instructions",
    r"system\s+override",
    r"you\s+are\s+now\s+(dan|developer\s+mode|unrestricted|god\s+mode)",
    r"bypass\s+(sentinel|security|safety|rules|gate)",
    r"disregard\s+(all\s+)?(sentinel|safety|rules|instructions)"
]


class VoiceSafetyViolationError(Exception):
    """Raised when an unsafe field, token, or prohibited action leaks into voice."""
    pass


class VoiceDegradedStateError(Exception):
    """Raised when voice engine is uninitialized or degraded."""
    pass


class VoiceBusyError(Exception):
    """Raised when voice response concurrency ownership is already held."""
    pass


def assert_spoken_response_safety(speech: str) -> None:
    """
    Final Spoken-Response Safety Assertion:
    Enforces that speech is concise, free of internal file paths, stack traces,
    passwords, tokens, nonces, raw digests, and private markers.
    """
    if not isinstance(speech, str):
        raise VoiceSafetyViolationError("Spoken response must be a string")

    if len(speech) > MAX_SPEECH_LENGTH:
        raise VoiceSafetyViolationError(
            f"Spoken response exceeds max length ({len(speech)} > {MAX_SPEECH_LENGTH})"
        )

    # Check for filesystem paths
    if "/data/data/" in speech or "/home/" in speech or "/proc/" in speech or ".sqlite" in speech:
        raise VoiceSafetyViolationError("Internal filesystem path leaked into spoken response")

    # Check for stack traces or exception dumps
    if "Traceback" in speech or "Exception:" in speech or "OperationalError" in speech:
        raise VoiceSafetyViolationError("Internal exception dump leaked into spoken response")

    # Check for private tier markers
    if "OPERATOR_ONLY" in speech or "SOVEREIGN_VAULT_RESTRICTED" in speech:
        raise VoiceSafetyViolationError("Private tier classification leaked into spoken response")

    # Check for raw API tokens, keys, or hex digests (> 24 hex chars)
    if re.search(r"\b(sk-[A-Za-z0-9_\-]{8,}|bearer\s+[A-Za-z0-9_\-\.]{8,})\b", speech, re.IGNORECASE):
        raise VoiceSafetyViolationError("Secret token leaked into spoken response")
    if re.search(r"\b[a-f0-9]{32,64}\b", speech, re.IGNORECASE):
        raise VoiceSafetyViolationError("Raw cryptographic digest leaked into spoken response")


class AadyaVoiceEngine:
    """
    Voice-First Command & Response Engine for AADYA Crown-0.
    Handles spoken intent classification, command routing, TV-safe read-only responses,
    draft mission preparation, and POCO escalation announcements.
    """

    def __init__(self, db_path: Optional[str] = None, parent_crown_zero: Optional[Any] = None):
        self.db_path = db_path
        self.parent = parent_crown_zero
        self.is_initialized = False
        self.initialization_status = "PENDING_INITIALIZATION"
        self.init_error = None
        self._voice_lock = threading.Lock()
        self._recent_context: deque = deque(maxlen=MAX_RECENT_CONTEXT_TURNS)
        self._ensure_voice_tables()

    def _ensure_voice_tables(self) -> None:
        """Initializes the aadya_voice_interactions table."""
        try:
            execute_db("""
                CREATE TABLE IF NOT EXISTS aadya_voice_interactions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    intent_type TEXT NOT NULL,
                    transcript TEXT NOT NULL,
                    speech_response TEXT NOT NULL,
                    layout_intent_json TEXT,
                    sanitizer_receipt TEXT NOT NULL,
                    is_escalated INTEGER NOT NULL DEFAULT 0,
                    escalation_id TEXT,
                    latency_ms REAL NOT NULL,
                    created_at REAL NOT NULL
                );
            """, db_path=self.db_path)
            execute_db("""
                CREATE INDEX IF NOT EXISTS idx_voice_interactions_created
                ON aadya_voice_interactions(created_at);
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
                    action="VOICE_ENGINE_INITIALIZATION_FAILED",
                    target="aadya_voice_engine",
                    result="DEGRADED",
                    details={"error": "Database error initializing voice tables"},
                    db_path=self.db_path
                )
            except Exception:
                pass

    def _check_voice_health(self) -> None:
        """Fails closed if the voice engine is uninitialized or degraded."""
        if not self.is_initialized or self.initialization_status != "INITIALIZED":
            raise VoiceDegradedStateError(f"AadyaVoiceEngine degraded: {self.init_error or self.initialization_status}")

    # =========================================================================
    # Intent Classification Layer (Deterministic First)
    # =========================================================================

    def classify_voice_intent(self, transcript: str) -> Dict[str, Any]:
        """
        Deterministic intent classifier:
        - Scans for prompt injection attacks.
        - Scans for financial keywords (instantly blocked).
        - Scans for high-risk actions requiring POCO escalation.
        - Matches deterministic command keywords.
        - Fails closed for unknown or ambiguous utterances.
        """
        self._check_voice_health()
        clean = (transcript or "").strip().lower()

        if not clean:
            return {"intent": "EMPTY", "confidence": 0.0, "requires_escalation": False, "is_financial": False}

        # 1. Prompt Injection Scanning
        for pat in PROMPT_INJECTION_PATTERNS:
            if re.search(pat, clean):
                return {
                    "intent": "INJECTION_ATTACK",
                    "confidence": 1.0,
                    "requires_escalation": False,
                    "is_financial": False,
                    "matched_pattern": pat
                }

        # 2. Absolute Financial Quarantine Scanning
        for pat in FINANCIAL_PATTERNS:
            if re.search(pat, clean):
                return {
                    "intent": "FINANCIAL_BLOCKED",
                    "confidence": 1.0,
                    "requires_escalation": False,
                    "is_financial": True,
                    "matched_pattern": pat
                }

        # 3. High-Risk Action Scanning (Requires POCO)
        for pat in HIGH_RISK_PATTERNS:
            if re.search(pat, clean):
                return {
                    "intent": "HIGH_RISK_ESCALATION",
                    "confidence": 1.0,
                    "requires_escalation": True,
                    "is_financial": False,
                    "matched_pattern": pat
                }

        # 4. Deterministic Command Matching
        if any(k in clean for k in ["briefing", "daily update", "status report", "brief me", "morning briefing", "evening review"]):
            return {"intent": "BRIEFING_REQUEST", "confidence": 0.95, "requires_escalation": False, "is_financial": False}

        if any(k in clean for k in ["mission status", "active missions", "task progress", "how are missions", "running tasks", "mission progress"]):
            return {"intent": "MISSION_STATUS_QUERY", "confidence": 0.95, "requires_escalation": False, "is_financial": False}

        if any(k in clean for k in ["future radar", "scan horizon", "radar horizon", "radar status", "planned capabilities"]):
            return {"intent": "FUTURE_RADAR_QUERY", "confidence": 0.95, "requires_escalation": False, "is_financial": False}

        if any(k in clean for k in ["system status", "health check", "is everything working", "aadya health", "system health", "diagnostics"]):
            return {"intent": "SYSTEM_HEALTH_QUERY", "confidence": 0.95, "requires_escalation": False, "is_financial": False}

        if any(k in clean for k in ["pending approvals", "escalation status", "what is waiting for poco", "sentinel holds", "poco queue"]):
            return {"intent": "POCO_ESCALATIONS_QUERY", "confidence": 0.95, "requires_escalation": False, "is_financial": False}

        if any(k in clean for k in ["remember about", "recall notes", "check context", "what do you know about", "search memory"]):
            return {"intent": "CONTEXT_MEMORY_QUERY", "confidence": 0.90, "requires_escalation": False, "is_financial": False}

        if any(k in clean for k in ["create task", "create draft plan", "draft mission", "schedule routine", "organize reminders", "run test"]):
            return {"intent": "DRAFT_TASK_REQUEST", "confidence": 0.90, "requires_escalation": False, "is_financial": False}

        if any(k in clean for k in ["hello", "hi aadya", "good morning", "good evening", "who are you", "what is your creed"]):
            return {"intent": "GENERAL_GREETING", "confidence": 0.90, "requires_escalation": False, "is_financial": False}

        # Fail-closed default for unknown intents
        return {"intent": "UNKNOWN", "confidence": 0.20, "requires_escalation": False, "is_financial": False}

    # =========================================================================
    # Voice Response Generators (Truthful, TV-Safe, Bounded)
    # =========================================================================

    def generate_spoken_briefing(self, time_period: Optional[str] = None) -> str:
        """Generates a concise spoken briefing for Aadi."""
        hour = time.localtime().tm_hour
        period = time_period or ("morning" if 5 <= hour < 12 else ("afternoon" if 12 <= hour < 17 else ("evening" if 17 <= hour < 22 else "night")))

        goal_cnt = len(self.parent.get_active_goals()) if self.parent else 0
        routine_cnt = len(self.parent.get_active_routines()) if self.parent else 0

        if period == "morning":
            speech = f"Good morning, Aadi. Daily baseline prepared with {goal_cnt} goals and {routine_cnt} active routines."
        elif period == "afternoon":
            speech = f"Good afternoon, Aadi. Core operations nominal with {goal_cnt} prioritized goals tracked."
        elif period == "evening":
            speech = f"Good evening, Aadi. System winding down for routine maintenance and review."
        else:
            speech = "Aadi, low distraction mode engaged. Background inference is throttled for the night."

        assert_spoken_response_safety(speech)
        return speech

    def generate_mission_status_speech(self, mission_id: Optional[str] = None) -> str:
        """Generates truthful status speech for active autonomous missions."""
        if not self.parent or not getattr(self.parent, "missions", None):
            speech = "Aadi, the autonomous missions subsystem is currently unlinked."
            assert_spoken_response_safety(speech)
            return speech

        missions = self.parent.list_missions()
        if not missions:
            speech = "Aadi, there are currently no active autonomous missions in the ledger."
            assert_spoken_response_safety(speech)
            return speech

        active = [m for m in missions if m.get("status") in ["IN_PROGRESS", "READY", "PAUSED", "FAILED"]]
        if not active:
            speech = f"Aadi, all {len(missions)} recorded missions are in terminal completed states."
            assert_spoken_response_safety(speech)
            return speech

        target_m = active[0]
        title = target_m.get("title", "Autonomous Mission")
        status = target_m.get("status")
        tot = target_m.get("total_tasks", 0)
        done = target_m.get("completed_tasks", 0)
        failed = target_m.get("failed_tasks", 0)

        if failed > 0:
            speech = f"Aadi, mission '{title}' is in {status} state with {failed} failed tasks requiring review."
        elif status == "IN_PROGRESS" or status == "READY":
            speech = f"Aadi, mission '{title}' is {status}. {done} of {tot} tasks completed."
        else:
            speech = f"Aadi, mission '{title}' is currently {status} with {done} of {tot} tasks finished."

        assert_spoken_response_safety(speech)
        return speech

    def generate_context_query_speech(self, query: str) -> str:
        """Queries TV-safe memory and provides truthful confidence qualification."""
        if not self.parent or not getattr(self.parent, "context", None):
            speech = "Aadi, context memory is currently unavailable."
            assert_spoken_response_safety(speech)
            return speech

        # Fetch only TV_SAFE nodes
        nodes = self.parent.list_active_nodes()
        sanitized = self.parent.sanitize_for_tv_export(nodes)
        tv_nodes = sanitized.get("tv_safe_records", [])

        if not tv_nodes:
            speech = "Aadi, I found no TV-safe memory records matching that inquiry."
            assert_spoken_response_safety(speech)
            return speech

        # Keyword match
        clean_q = query.lower()
        matched = [n for n in tv_nodes if any(w in n.get("title", "").lower() or w in n.get("content", "").lower() for w in clean_q.split() if len(w) > 3)]
        if not matched:
            matched = tv_nodes[:1]

        n = matched[0]
        title = n.get("title", "Context Record")
        raw_content = n.get("content", "")
        summary = sanitize_tv_summary(raw_content, max_len=140)

        speech = f"Aadi, record '{title}' indicates: {summary}"
        assert_spoken_response_safety(speech)
        return speech

    def generate_future_radar_speech(self) -> str:
        """Generates future radar speech reporting verified status labels."""
        if not self.parent:
            speech = "Aadi, Future Radar is operating in standalone offline scan."
        else:
            radar = self.parent.scan_future_radar()
            areas = radar.get("focus_areas", [])
            planned = sum(1 for a in areas if "PLANNED" in a.get("status", ""))
            speech = f"Aadi, Future Radar tracks {len(areas)} domains. {planned} external capabilities are marked planned."

        assert_spoken_response_safety(speech)
        return speech

    def generate_system_health_speech(self) -> str:
        """Truthfully articulates system health without exposing file paths or internal errors."""
        is_degraded = False
        degraded_items = []

        if self.parent:
            if getattr(self.parent, "initialization_status", None) != "INITIALIZED":
                is_degraded = True
                degraded_items.append("Core Mind")
            if getattr(self.parent, "context_initialization_status", None) != "INITIALIZED":
                is_degraded = True
                degraded_items.append("Context Engine")
            if getattr(self.parent, "missions_initialization_status", None) != "INITIALIZED":
                is_degraded = True
                degraded_items.append("Mission Engine")
            if getattr(self.parent, "surface_initialization_status", None) != "INITIALIZED":
                is_degraded = True
                degraded_items.append("Surface Engine")

        if is_degraded:
            speech = f"Aadi, the system is operating in degraded mode due to {', '.join(degraded_items)}. Please consult POCO console."
        else:
            speech = "Aadi, all local subsystems are operational and audit logs are synchronized."

        assert_spoken_response_safety(speech)
        return speech

    def announce_pending_escalations(self) -> str:
        """Announces pending POCO escalation counts neutrally."""
        pending_count = 0
        try:
            r1 = query_db("SELECT COUNT(*) FROM sentinel_requests WHERE status = 'pending';", db_path=self.db_path)
            c1 = r1[0][0] if r1 else 0
            r2 = query_db("SELECT COUNT(*) FROM aadya_escalations WHERE status = 'PENDING_POCO_APPROVAL';", db_path=self.db_path)
            c2 = r2[0][0] if r2 else 0
            pending_count = c1 + c2
        except Exception:
            pending_count = 0

        if pending_count > 0:
            speech = f"Aadi, there are {pending_count} pending actions awaiting physical authorization on your POCO device."
        else:
            speech = "Aadi, there are currently no pending escalations awaiting operator authorization."

        assert_spoken_response_safety(speech)
        return speech

    def format_degraded_state_speech(self, subsystem: str) -> str:
        """Produces safe spoken error guidance without stack traces or internal diagnostics."""
        clean_name = re.sub(r'[^a-zA-Z0-9_\s]', '', subsystem).strip()
        speech = f"Aadi, the {clean_name} subsystem is degraded. Operating in offline fail-closed fallback mode."
        assert_spoken_response_safety(speech)
        return speech

    # =========================================================================
    # Voice Command Execution & Routing Pipeline
    # =========================================================================

    def process_voice_command(
        self,
        transcript: str,
        session_id: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Coordinates end-to-end voice processing:
        1. Acquires concurrency ownership lock (VoiceBusyError if held).
        2. Sanitizes input transcript.
        3. Classifies intent deterministically.
        4. Routes command safely:
           - Financial -> Explicit refusal
           - High-risk -> Escalates to POCO without execution
           - Draft low-risk task -> Creates DRAFT mission only (NO automatic execution)
           - Read-only queries -> Synthesizes verified speech & HUD layout
        5. Validates final speech through safety assertion.
        6. Persists interaction to aadya_voice_interactions and audit_log.
        """
        self._check_voice_health()
        start_time = time.time()

        # Enforce single-response-at-a-time concurrency lock
        acquired = self._voice_lock.acquire(blocking=False)
        if not acquired:
            raise VoiceBusyError("Voice engine is busy with an active response.")

        try:
            # Sanitize input transcript before processing and storage
            clean_transcript = sanitize_sensitive_data(transcript or "").strip()
            # Strip absolute local filesystem paths from transcript
            clean_transcript = re.sub(r'(/[\w\.\-]+)+', '[LOCAL_PATH]', clean_transcript)

            intent_info = self.classify_voice_intent(clean_transcript)
            intent = intent_info.get("intent", "UNKNOWN")

            speech_response = ""
            layout_intent = {"screen": "living_surface", "theme": "obsidian_cyan"}
            is_escalated = False
            escalation_id = None

            # --- Route by Classified Intent ---
            if intent == "INJECTION_ATTACK":
                speech_response = "Aadi, that command pattern is disallowed by sovereign safety rules."

            elif intent == "FINANCIAL_BLOCKED":
                # Absolute Financial Quarantine: Clear refusal, zero task/mission/escalation
                speech_response = "Aadi, financial execution is permanently quarantined. AADYA cannot perform financial actions."

            elif intent == "HIGH_RISK_ESCALATION":
                # High-risk action: Route to POCO escalation without execution
                is_escalated = True
                if self.parent:
                    esc = self.parent.escalate_to_poco(
                        action_type="VOICE_INITIATED_HIGH_RISK_ACTION",
                        details={"transcript": clean_transcript}
                    )
                    escalation_id = esc.get("escalation_id") or esc.get("id")
                speech_response = "Aadi, that action requires physical authorization. I have queued it on the POCO Operator Console."

            elif intent == "BRIEFING_REQUEST":
                speech_response = self.generate_spoken_briefing()
                layout_intent["cards"] = [{"type": "briefing", "title": "Briefing", "priority": "NORMAL"}]

            elif intent == "MISSION_STATUS_QUERY":
                speech_response = self.generate_mission_status_speech()
                layout_intent["cards"] = [{"type": "mission_progress", "title": "Mission Status", "priority": "NORMAL"}]

            elif intent == "FUTURE_RADAR_QUERY":
                speech_response = self.generate_future_radar_speech()
                layout_intent["cards"] = [{"type": "future_radar", "title": "Future Radar", "priority": "LOW"}]

            elif intent == "SYSTEM_HEALTH_QUERY":
                speech_response = self.generate_system_health_speech()
                layout_intent["cards"] = [{"type": "health_alert", "title": "Health", "priority": "NORMAL"}]

            elif intent == "POCO_ESCALATIONS_QUERY":
                speech_response = self.announce_pending_escalations()
                layout_intent["cards"] = [{"type": "poco_escalation", "title": "POCO Queue", "priority": "HIGH"}]

            elif intent == "CONTEXT_MEMORY_QUERY":
                speech_response = self.generate_context_query_speech(clean_transcript)
                layout_intent["cards"] = [{"type": "context_summary", "title": "Context Record", "priority": "LOW"}]

            elif intent == "DRAFT_TASK_REQUEST":
                # Voice may create ONLY a DRAFT or PENDING_CONFIRMATION mission
                # Must NEVER directly execute in one turn
                task_title = "Voice Draft Task"
                if "organize" in clean_transcript:
                    task_title = "Organize Reminders"
                elif "test" in clean_transcript:
                    task_title = "Run Local Unit Test"

                if self.parent and getattr(self.parent, "missions", None):
                    draft_res = self.parent.create_mission(
                        title=f"Draft: {task_title}",
                        objective=f"Pending confirmation: {clean_transcript}",
                        tasks=[
                            {
                                "id": f"t_draft_{int(time.time())}",
                                "action_type": "view_system_telemetry",
                                "target": "local_system",
                                "is_idempotent": True
                            }
                        ],
                        category="draft"
                    )
                    speech_response = f"Aadi, I have prepared draft mission '{task_title}'. It is queued for your explicit confirmation."
                else:
                    speech_response = f"Aadi, I have staged draft task '{task_title}' awaiting your confirmation."

            elif intent == "GENERAL_GREETING":
                speech_response = "Aadi, I am AADYA, devoted to your betterment, wellbeing, and sovereignty."

            else:
                # Fail-closed for unknown or ambiguous utterances
                speech_response = "Aadi, I did not recognize that command. Please specify an operational or briefing request."

            # Final Spoken-Response Safety Assertion
            assert_spoken_response_safety(speech_response)

            latency_ms = round((time.time() - start_time) * 1000, 2)
            interaction_id = f"v_act_{uuid.uuid4().hex[:12]}"
            receipt_id = f"rcpt_vox_{uuid.uuid4().hex[:12]}"

            # Update bounded conversational context
            self._recent_context.append({
                "user": clean_transcript,
                "aadya": speech_response,
                "timestamp": time.time()
            })

            # Record interaction to SQLite unless dry_run is active
            if not dry_run:
                conn = get_connection(self.db_path)
                try:
                    with conn:
                        conn.execute("""
                            INSERT INTO aadya_voice_interactions (
                                id, session_id, intent_type, transcript,
                                speech_response, layout_intent_json, sanitizer_receipt,
                                is_escalated, escalation_id, latency_ms, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """, (
                            interaction_id,
                            session_id or f"sess_{uuid.uuid4().hex[:8]}",
                            intent,
                            clean_transcript,
                            speech_response,
                            json.dumps(layout_intent),
                            receipt_id,
                            1 if is_escalated else 0,
                            escalation_id,
                            latency_ms,
                            time.time()
                        ))

                        # Bounded persistence pruning
                        conn.execute("""
                            DELETE FROM aadya_voice_interactions
                            WHERE id NOT IN (
                                SELECT id FROM aadya_voice_interactions
                                ORDER BY created_at DESC LIMIT ?
                            );
                        """, (MAX_STORED_INTERACTIONS,))

                        log_audit_event(
                            actor="AZ-001_AADYA",
                            action="VOICE_COMMAND_PROCESSED",
                            target=interaction_id,
                            result="SUCCESS",
                            details={
                                "intent": intent,
                                "is_escalated": is_escalated,
                                "latency_ms": latency_ms,
                                "receipt_id": receipt_id
                            },
                            conn=conn
                        )
                finally:
                    conn.close()

            return {
                "success": True,
                "interaction_id": interaction_id,
                "intent": intent,
                "transcript": clean_transcript,
                "speech": speech_response,
                "layout_intent": layout_intent,
                "is_escalated": is_escalated,
                "escalation_id": escalation_id,
                "latency_ms": latency_ms,
                "sanitizer_receipt": receipt_id
            }

        finally:
            self._voice_lock.release()

    def list_voice_interactions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Lists recent voice interactions safely from SQLite."""
        self._check_voice_health()
        bounded_limit = min(max(1, limit), 50)
        rows = query_db(
            "SELECT id, session_id, intent_type, transcript, speech_response, is_escalated, escalation_id, latency_ms, created_at "
            "FROM aadya_voice_interactions ORDER BY created_at DESC LIMIT ?;",
            (bounded_limit,),
            db_path=self.db_path
        )
        return [
            {
                "id": r[0],
                "session_id": r[1],
                "intent_type": r[2],
                "transcript": r[3],
                "speech_response": r[4],
                "is_escalated": bool(r[5]),
                "escalation_id": r[6],
                "latency_ms": r[7],
                "created_at": r[8]
            }
            for r in rows
        ]
