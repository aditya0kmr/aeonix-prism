import sys
import os
sys.path.insert(0, "/data/data/com.termux/files/home/aeonix")
sys.path.insert(0, "/data/data/com.termux/files/home")
import json
import time
import asyncio
import base64
from typing import List, Set, Tuple, Dict, Any, Optional
from starlette.applications import Starlette
from starlette.responses import JSONResponse, HTMLResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from aeonix.core.db import (
    init_database,
    get_connection,
    log_audit_event,
    queue_sentinel_request,
    resolve_sentinel_request,
    compute_action_digest
)
from aeonix.core.operator_console import verify_operator_secret
from aeonix.core.auth import (
    verify_token,
    issue_device_token,
    ROLE_POCO_CORE,
    ROLE_FIRETV_GLASS,
    ROLE_AGENT_EXECUTOR,
    ROLE_PTT_OPERATOR,
    exchange_bootstrap_secret,
    generate_bootstrap_secret,
    POCO_CORE_TOKEN,
    FIRETV_GLASS_TOKEN
)
from aeonix.core.trust import trust
from aeonix.core.ram_guard import check_ram_guard
from aeonix.core.discovery import AeonixDiscoveryService
from aeonix.core.llama_runner import llama_runner
from aeonix.core.fast_path import match_fast_path, execute_fast_path
from aeonix.core.memory import store_memory, recall_memories, generate_daily_briefing
from aeonix.core.stt import transcribe_pcm
from aeonix.core.panoptes import (
    run_passive_osint, get_entity_graph, request_active_probe,
    ingest_markdown_note, query_notes_by_topic, list_monitored_topics, verify_note_evidence
)
from aeonix.core.veritas import create_case, ingest_evidence, verify_evidence, generate_case_manifest
from aeonix.core.guardian import get_network_inventory, async_get_network_inventory, get_bounded_network_telemetry
from aeonix.core.atlas_watch import run_supervisor_cycle
from aeonix.core.spectra import get_channel_catalog, get_current_playback, set_playback_state, find_channel_by_query
from aeonix.core.sanctuary import engage_sanctuary, release_sanctuary, get_sanctuary_status, is_sanctuary_active
from aeonix.core.forge import draft_command_from_prompt, execute_sandboxed_command, execute_typed_operation, get_git_telemetry
from aeonix.core.visia import analyze_visual_artifact
from aeonix.core.backup import create_vault_backup, list_backups, verify_backup, generate_emergency_recovery_key
from aeonix.core.morph import get_pending_proposals, generate_optimization_proposal
from aeonix.core.council import convene_council_session
from aeonix.core.ptt import PocoPttController
from aeonix.ui.ptt_console import get_ptt_console_html
from aeonix.core.voice_pipeline import process_voice_pipeline, get_queue_manager
from aeonix.core.llama_runner import llama_runner

_ptt_controller = PocoPttController(db_path=os.environ.get("AEONIX_DB_PATH"))
_ptt_start_history: List[float] = []

def get_request_identity(request) -> Tuple[str, str]:
    """
    Derives identity from cryptographically verified bearer token.
    Returns (role: str, device_id: str).
    """
    if hasattr(request, "state"):
        role = getattr(request.state, "auth_role", None)
        device_id = getattr(request.state, "device_id", None)
        if role and device_id:
            return role, device_id

    auth_header = request.headers.get("Authorization", "") or request.headers.get("authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    if token:
        payload = verify_token(token)
        if payload:
            return payload.get("role", "UNKNOWN"), payload.get("device_id", "anonymous")

    return "UNAUTHENTICATED", "untrusted"

# Connected Fire TV and client WebSockets with authenticated identity metadata
active_connections: Set[WebSocket] = set()
active_terminals: Dict[WebSocket, Dict[str, Any]] = {}

# PTT Voice Response concurrency and ownership manager (enforces strict one-response-at-a-time execution)
from aeonix.core.voice_pipeline import VoiceResponseOwnership, VoiceResponseSession
_voice_response_ownership = VoiceResponseOwnership()

def get_voice_response_ownership() -> VoiceResponseOwnership:
    return _voice_response_ownership

def get_ptt_voice_response_lock() -> VoiceResponseOwnership:
    """Compatibility interface returning the ownership manager which provides .locked()."""
    return _voice_response_ownership

def get_authorized_firetv_websocket() -> Tuple[Optional[WebSocket], Optional[Dict[str, Any]]]:
    """
    Returns the active WebSocket and metadata for an authenticated Fire TV Glass device.
    Reconciles configured device identities ('firetv_glass', 'firetv_stick_glass')
    with verified role ROLE_FIRETV_GLASS.
    """
    for ws, meta in list(active_terminals.items()):
        if meta.get("role") == ROLE_FIRETV_GLASS and meta.get("device_id") in ("firetv_glass", "firetv_stick_glass"):
            return ws, meta
    return None, None

def get_configured_port() -> int:
    raw = os.getenv("AEONIX_PORT", "8080").strip()
    try:
        val = int(raw)
        if not (1 <= val <= 65535):
            raise ValueError(f"Port {val} is outside valid range [1, 65535]")
        return val
    except ValueError as e:
        raise ValueError(f"Invalid AEONIX_PORT '{raw}': {e}") from None

AEONIX_PORT = get_configured_port()
discovery_service = AeonixDiscoveryService(port=AEONIX_PORT)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: Starlette):
    init_database()
    log_audit_event("SYSTEM", "daemon_start", "aeonix_core", "ok", {"port": AEONIX_PORT})
    try:
        from aeonix.core.governed_mission import governor
        reconciled = governor.reconcile_interrupted_missions()
        if reconciled:
            print(f"[MISSION RECONCILER]: Recovered {len(reconciled)} interrupted missions into NEEDS_RECONCILIATION")
    except Exception as re:
        print(f"[MISSION RECONCILER ERROR]: {re}")
    discovery_service.start()
    yield
    discovery_service.stop()
    log_audit_event("SYSTEM", "daemon_stop", "aeonix_core", "ok", {})

async def get_status(request):
    """
    Public minimal liveness endpoint.
    Strictly leaks zero usernames, device counts, or resources/RAM.
    """
    return JSONResponse({
        "status": "online",
        "system": "ÆONIX PRISM Core Mind v2.0",
        "timestamp": time.time()
    })

async def get_system_status(request):
    """
    Authenticated system telemetry and operational status.
    Requires ROLE_POCO_CORE.
    """
    ram = check_ram_guard()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT count(*) as count FROM sentinel_requests WHERE status = 'pending';")
    pending_count = cur.fetchone()["count"]
    conn.close()

    return JSONResponse({
        "status": "online",
        "system": "ÆONIX PRISM Core Mind v2.0",
        "sovereign_user": "Aadi",
        "timestamp": time.time(),
        "ram": ram,
        "sentinel_pending": pending_count,
        "connected_glass_clients": len(active_connections)
    })

async def list_sentinel_pending(request):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM sentinel_requests 
        WHERE status = 'pending' AND expires_at > ?
        ORDER BY created_at ASC;
    """, (time.time(),))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse({"pending": rows, "requests": rows})

async def resolve_sentinel(request):
    try:
        body = await request.json()
        req_id = body.get("request_id")
        approved = body.get("approved")
        
        if not req_id:
            return JSONResponse({"error": "Missing request_id"}, status_code=400)

        if not isinstance(approved, bool):
            return JSONResponse({"error": "Field 'approved' must be a strict boolean (true/false)"}, status_code=400)

        auth_role, actor = get_request_identity(request)
        if auth_role == "UNAUTHENTICATED":
            return JSONResponse({"error": "Missing or invalid authorization header"}, status_code=401)

        passphrase_verified = False
        expected_action_digest = body.get("action_digest")

        if approved is True:
            if auth_role != ROLE_POCO_CORE:
                return JSONResponse({
                    "error": "POCO_AUTHORITY_REQUIRED: Approval of consequential actions is restricted strictly to POCO Core Mind"
                }, status_code=403)

            operator_passphrase = body.get("operator_passphrase") or request.headers.get("X-Operator-Passphrase")
            if not operator_passphrase:
                return JSONResponse({
                    "error": "OPERATOR_PASSPHRASE_REQUIRED: Approval of consequential actions strictly requires operator passphrase verification"
                }, status_code=403)

            is_valid, msg = verify_operator_secret(operator_passphrase)
            if not is_valid:
                return JSONResponse({
                    "error": f"OPERATOR_AUTH_FAILED: {msg}"
                }, status_code=403)

            if not expected_action_digest or not str(expected_action_digest).strip():
                return JSONResponse({
                    "error": "ACTION_DIGEST_REQUIRED: Approval of consequential actions strictly requires reviewed action_digest in request payload"
                }, status_code=400)

            passphrase_verified = True

        ok, status_reason = resolve_sentinel_request(
            req_id, 
            approved, 
            resolver=actor, 
            resolver_role=auth_role,
            passphrase_verified=passphrase_verified,
            expected_action_digest=expected_action_digest
        )
        if ok:
            # Broadcast resolution event to TV over WebSocket
            await broadcast_message({
                "type": "sentinel_resolved",
                "request_id": req_id,
                "status": status_reason
            })
            return JSONResponse({"success": True, "request_id": req_id, "status": status_reason})
        else:
            return JSONResponse({"error": status_reason}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def create_sentinel(request):
    """Generates a Sentinel Request and broadcasts the approval card to Fire TV."""
    try:
        body = await request.json()
        agent = body.get("agent", "SYSTEM")
        action_class = body.get("action_class", "consequential")
        action_type = body.get("action_type", "unspecified")
        target = body.get("target", "system")
        scope = body.get("scope", {})
        risk_level = body.get("risk_level", "R3")
        ttl = int(body.get("ttl_seconds", 300))

        req_id = queue_sentinel_request(agent, action_class, action_type, target, scope, risk_level, ttl)
        action_digest = compute_action_digest(req_id, agent, action_type, target, scope)
        await broadcast_message({
            "type": "sentinel_card",
            "request_id": req_id,
            "agent": agent,
            "action_type": action_type,
            "target": target,
            "risk_level": risk_level,
            "scope": scope,
            "action_digest": action_digest
        })
        return JSONResponse({"success": True, "request_id": req_id, "risk_level": risk_level, "action_digest": action_digest})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_memory(request):
    try:
        body = await request.json()
        title = body.get("title", "").strip()
        content = body.get("content", "").strip()
        category = body.get("category", "observation")
        tags = body.get("tags", [])
        if not title or not content:
            return JSONResponse({"error": "Title and content required"}, status_code=400)
        mem_id = store_memory(title, content, category, tags=tags)
        return JSONResponse({"success": True, "memory_id": mem_id})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_memories(request):
    try:
        q = request.query_params.get("q")
        cat = request.query_params.get("category")
        rows = recall_memories(query=q, category=cat)
        return JSONResponse({"memories": rows})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_briefing(request):
    try:
        briefing = generate_daily_briefing()
        await broadcast_message({
            "type": "layout_update",
            "screen": "living_surface",
            "surface_data": {
                "title": "AADYA // DAILY BRIEFING",
                "greeting": briefing["date_str"],
                "mode": "Sovereign Briefing Active"
            }
        })
        return JSONResponse(briefing)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

import secrets
from concurrent.futures import ThreadPoolExecutor

heavy_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="aeonix_worker")
llm_inference_lock = asyncio.Lock()

_SERVER_SEQUENCE = 0
_SERVER_EVENT_RING_BUFFER: List[Dict[str, Any]] = []
_MAX_RING_BUFFER_SIZE = 128

def _next_server_sequence() -> int:
    global _SERVER_SEQUENCE
    _SERVER_SEQUENCE += 1
    return _SERVER_SEQUENCE

def _record_server_event(event: dict):
    global _SERVER_EVENT_RING_BUFFER
    _SERVER_EVENT_RING_BUFFER.append(event)
    if len(_SERVER_EVENT_RING_BUFFER) > _MAX_RING_BUFFER_SIZE:
        _SERVER_EVENT_RING_BUFFER.pop(0)

def get_events_since(last_seq: int) -> List[dict]:
    return [ev for ev in _SERVER_EVENT_RING_BUFFER if ev.get("server_sequence", 0) > last_seq]

async def broadcast_message(message: dict):
    seq = _next_server_sequence()
    message["server_sequence"] = seq
    _record_server_event(dict(message))
    payload = json.dumps(message)
    dead_connections = set()
    for ws in list(active_connections):
        try:
            await ws.send_text(payload)
        except Exception:
            dead_connections.add(ws)
    for dead in dead_connections:
        active_connections.discard(dead)
        active_terminals.pop(dead, None)

async def process_intent_pipeline(
    user_query: str, 
    actor: str = "Aadi", 
    actor_role: str = ROLE_POCO_CORE,
    correlation_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Unified Request Pipeline for REST and Voice:
    - Normalizes incoming queries.
    - Tier 0: Fast-Path match (<0.01s).
    - Tier 1: Local LLM generation offloaded to heavy_executor guarded by llm_inference_lock.
    - Synchronizes Living Surface HUD broadcasts across all connected glass terminals.
    """
    t0 = time.perf_counter()
    if not correlation_id:
        correlation_id = f"req_{int(time.time()*1000)}_{secrets.token_hex(3)}"

    clean_query = user_query.strip()
    if not clean_query:
        return {"success": False, "error": "Empty query", "correlation_id": correlation_id}

    # Tier 0: Fast-Path Match
    fast_match = match_fast_path(clean_query)
    if fast_match:
        action_name, confidence = fast_match
        intent_result = execute_fast_path(action_name, actor=actor)
        intent_result["confidence"] = confidence
        intent_result["tier"] = "Tier 0 (Fast-Path)"
        intent_result["correlation_id"] = correlation_id
        intent_result["query"] = clean_query
        intent_result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # Broadcast UI layout events to all connected Glass terminals
        if "media_play" in intent_result:
            await broadcast_message({
                "type": "media_play",
                **intent_result["media_play"]
            })
        elif "sanctuary" in intent_result:
            await broadcast_message({
                "type": "sanctuary_mode",
                "active": intent_result["sanctuary"]["is_active"]
            })
        elif intent_result.get("action", "").startswith("media_"):
            cmd = intent_result["action"].replace("media_", "")
            await broadcast_message({
                "type": "media_control",
                "command": cmd
            })
        elif "layout_intent" in intent_result:
            await broadcast_message({
                "type": "layout_intent",
                "action": intent_result.get("action", ""),
                "speech": intent_result.get("speech", ""),
                **intent_result["layout_intent"]
            })

        return intent_result

    # Tier 1: Dispatch through Sovereign Hybrid Router
    loop = asyncio.get_event_loop()
    try:
        async with llm_inference_lock:
            def _run_router():
                try:
                    from aeonix.core.router import route_query
                except ImportError:
                    from core.router import route_query
                return route_query(clean_query, actor=actor, allow_external=False, model_tier="fast")

            router_res = await loop.run_in_executor(heavy_executor, _run_router)
    except Exception as e:
        router_res = {
            "success": False,
            "error": str(e),
            "speech": "I am standing by for your directive, Aadi.",
            "tier": "tier_1_fallback"
        }

    llm_text = router_res.get("speech") or "I am standing by for your directive, Aadi."

    intent_result = {
        "success": router_res.get("success", True),
        "tier": router_res.get("tier", "Tier 1 (Qwen2.5 Micro-Prompt)"),
        "provider": router_res.get("provider", "qwen2.5_fast"),
        "action": "aadya_dialogue",
        "speech": llm_text,
        "query": clean_query,
        "correlation_id": correlation_id,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        "layout_intent": {
            "screen": "living_surface",
            "theme": "obsidian_cyan",
            "cards": [{"title": "AADYA", "content": llm_text, "type": "dialogue"}]
        }
    }

    await broadcast_message({
        "type": "layout_intent",
        "action": "aadya_dialogue",
        "speech": llm_text,
        **intent_result["layout_intent"]
    })

    return intent_result

async def post_intent(request):
    """Processes natural language intent via the unified request pipeline."""
    try:
        auth_role, caller = get_request_identity(request)
        body = await request.json()
        user_query = body.get("query", "").strip()
        actor = body.get("actor", caller)

        if not user_query:
            return JSONResponse({"error": "Empty query"}, status_code=400)

        result = await process_intent_pipeline(user_query, actor=actor, actor_role=auth_role)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_voice_transcribe(request):
    """Processes uploaded raw PCM or WAV audio and returns offline transcription via async worker."""
    try:
        body = await request.body()
        if not body:
            return JSONResponse({"error": "Empty audio payload"}, status_code=400)
        lang = request.query_params.get("lang") or request.headers.get("X-Whisper-Lang")
        model = request.query_params.get("model") or request.headers.get("X-Whisper-Model")
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(heavy_executor, lambda: transcribe_pcm(body, model_path=model, lang=lang))
        log_audit_event("REST_API", "voice_transcribed", "whisper", "ok", {"query": text, "lang": lang or "auto"})
        return JSONResponse({"success": True, "transcription": text, "lang": lang or "auto"})
    except ValueError as ve:
        return JSONResponse({"error": str(ve)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_voice_pipeline(request):
    """
    Physical POCO Microphone Pipeline:
    POCO mic capture -> local ASR -> deterministic intent -> policy check -> TV feedback.
    1. Validates audio buffer and enforces 15s ceiling.
    2. Runs Voice Activity Detection (VAD).
    3. Runs offline whisper transcription.
    4. Evaluates intent and Sentinel authority boundaries (voice cannot approve consequential actions).
    5. Dispatches layout_intent to Fire TV Living Surface over WebSocket.
    6. Ensures ephemeral audio cleanup.
    """
    try:
        auth_role, caller = get_request_identity(request)
        body = await request.body()
        if not body:
            return JSONResponse({"error": "EMPTY_AUDIO: Audio payload is empty"}, status_code=400)

        from aeonix.core.stt import detect_voice_activity, transcribe_pcm, MAX_AUDIO_BYTES
        if len(body) > MAX_AUDIO_BYTES:
            return JSONResponse({"error": f"AUDIO_PAYLOAD_TOO_LARGE: Audio payload {len(body)} bytes exceeds 15-second safety ceiling ({MAX_AUDIO_BYTES} bytes)"}, status_code=400)

        lang = request.query_params.get("lang") or request.headers.get("X-Whisper-Lang", "en")
        vad = detect_voice_activity(body)
        if vad.get("is_silent"):
            return JSONResponse({
                "success": True,
                "status": "SILENCE_REJECTED",
                "transcription": "",
                "vad": vad,
                "speech": "No voice activity detected."
            })

        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(heavy_executor, lambda: transcribe_pcm(body, lang=lang))
        clean_text = transcript.strip() if transcript else ""

        if not clean_text or clean_text.startswith("[STT Error"):
            await broadcast_message({
                "type": "voice_feedback",
                "transcription": clean_text or "[Unintelligible]",
                "speech": "I could not understand that command, Aadi.",
                "policy_status": "FALLBACK"
            })
            return JSONResponse({
                "success": False,
                "status": "ASR_FALLBACK",
                "transcription": clean_text,
                "fallback_message": "Could not recognize audio. Please repeat command.",
                "speech": "I could not understand that command, Aadi.",
                "tv_feedback_broadcast": True
            })

        # Sentinel Authority Boundary: Voice CANNOT authorize protected actions!
        lower_query = clean_text.lower()
        is_approval_attempt = any(w in lower_query for w in ["approve", "authorize", "confirm", "wipe", "format"])
        policy_verdict = "ALLOW"
        policy_notice = None

        if is_approval_attempt:
            policy_verdict = "DENIED_VOICE_AUTHORIZATION"
            policy_notice = "VOICE_AUTHORIZATION_PROHIBITED: Consequential approvals strictly require physical operator passphrase entry on POCO."
            intent_result = {
                "success": False,
                "action": "sentinel_voice_blocked",
                "query": clean_text,
                "speech": "Voice approval is prohibited. Please enter your operator passphrase on POCO.",
                "policy_status": policy_verdict,
                "policy_notice": policy_notice
            }
        else:
            intent_result = await process_intent_pipeline(clean_text, actor=caller, actor_role=auth_role)
            intent_result["policy_status"] = policy_verdict

        await broadcast_message({
            "type": "voice_feedback",
            "transcription": clean_text,
            "speech": intent_result.get("speech", ""),
            "policy_status": policy_verdict
        })

        return JSONResponse({
            "success": True,
            "transcription": clean_text,
            "vad": vad,
            "intent": intent_result,
            "tv_feedback_broadcast": True
        })
    except ValueError as ve:
        return JSONResponse({"error": str(ve)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_voice_model_info_endpoint(request):
    """Returns active and available Whisper model forensic metadata."""
    try:
        from aeonix.core.stt import get_stt_model_info
        return JSONResponse(get_stt_model_info())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_ui_ptt(request):
    """Serves the sovereign POCO tactile PTT operator console with zero embedded credentials."""
    html_content = get_ptt_console_html(api_token="")
    return HTMLResponse(html_content)

_BOOTSTRAP_RATE_LIMITS: Dict[str, List[float]] = {}
_BOOTSTRAP_GLOBAL_ATTEMPTS: List[float] = []

def _normalize_origin(origin_str: str) -> Optional[Tuple[str, str, int]]:
    """
    Normalizes an origin string into (scheme, hostname, port).
    Scheme must be 'https' (or 'http' strictly under AEONIX_TEST_MODE == '1').
    """
    if not origin_str or origin_str == "null":
        return None
    try:
        from urllib.parse import urlparse
        p = urlparse(origin_str.strip())
        scheme = (p.scheme or "").lower()
        if not scheme or scheme not in ("http", "https"):
            return None
        # Operational mode strictly requires https
        if scheme != "https" and os.getenv("AEONIX_TEST_MODE") != "1":
            return None
        hostname = (p.hostname or "").lower()
        if not hostname:
            return None
        port = p.port
        if port is None:
            port = 443 if scheme == "https" else 80
        return (scheme, hostname, port)
    except Exception:
        return None

def get_allowed_bootstrap_origins() -> Set[Tuple[str, str, int]]:
    """
    Returns the set of explicitly allowed normalized origins for POST /api/ptt/bootstrap.
    In operational mode, requires HTTPS on explicitly configured origins.
    Configured via AEONIX_BOOTSTRAP_ALLOWED_ORIGINS environment variable.
    Test origins are only permitted when AEONIX_TEST_MODE == '1'.
    """
    allowed: Set[Tuple[str, str, int]] = set()
    env_origins = os.getenv("AEONIX_BOOTSTRAP_ALLOWED_ORIGINS")
    if env_origins:
        for orig in env_origins.split(","):
            norm = _normalize_origin(orig.strip())
            if norm:
                allowed.add(norm)

    if os.getenv("AEONIX_TEST_MODE") == "1":
        # Test-only origins permitted strictly during test execution
        test_origins = os.getenv("AEONIX_TEST_ALLOWED_ORIGINS", "http://testserver,https://testserver")
        for orig in test_origins.split(","):
            norm = _normalize_origin(orig.strip())
            if norm:
                allowed.add(norm)
    return allowed

async def post_api_ptt_bootstrap(request):
    """
    Exchanges a single-use 128-bit bootstrap secret for a short-lived ROLE_PTT_OPERATOR session token.
    Defenses:
    - Origin: strict normalized allowlist comparison; reject absent/null/unapproved origins.
    - Content-Type: application/json required.
    - Bounded body reading: streaming with Content-Length pre-check and 1024-byte ceiling.
    - Rate limits: bounded per-IP (5/min) and global (20/min).
    - Format validation: 32 hex chars required.
    - Generic non-reflective 401 on failure; Cache-Control: no-store on response.
    """
    # 1. Origin header check (mandatory, strict allowlist)
    origin = request.headers.get("origin")
    if not origin:
        return JSONResponse({"error": "FORBIDDEN", "detail": "Origin header required"}, status_code=403, headers={"Cache-Control": "no-store"})
    if origin == "null":
        return JSONResponse({"error": "FORBIDDEN", "detail": "Null origin rejected"}, status_code=403, headers={"Cache-Control": "no-store"})

    norm_origin = _normalize_origin(origin)
    if not norm_origin:
        return JSONResponse({"error": "FORBIDDEN", "detail": "Malformed, insecure, or unapproved origin"}, status_code=403, headers={"Cache-Control": "no-store"})

    allowed_origins = get_allowed_bootstrap_origins()
    if norm_origin not in allowed_origins:
        return JSONResponse({"error": "FORBIDDEN", "detail": "Origin not permitted"}, status_code=403, headers={"Cache-Control": "no-store"})

    # 2. Content-Type check
    ct = request.headers.get("content-type", "").lower()
    if not ct.startswith("application/json"):
        return JSONResponse({"error": "BAD_REQUEST", "detail": "Content-Type must be application/json"}, status_code=400, headers={"Cache-Control": "no-store"})

    # 3. Rate limiting (using request.client.host, not spoofable X-Forwarded-For)
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    global _BOOTSTRAP_GLOBAL_ATTEMPTS, _BOOTSTRAP_RATE_LIMITS
    client_attempts = [t for t in _BOOTSTRAP_RATE_LIMITS.get(client_ip, []) if now - t < 60.0]
    if len(client_attempts) >= 5:
        return JSONResponse(
            {"error": "RATE_LIMIT_EXCEEDED", "detail": "Too many bootstrap attempts. Try again later."},
            status_code=429,
            headers={"Cache-Control": "no-store"}
        )
    client_attempts.append(now)
    _BOOTSTRAP_RATE_LIMITS[client_ip] = client_attempts

    _BOOTSTRAP_GLOBAL_ATTEMPTS = [t for t in _BOOTSTRAP_GLOBAL_ATTEMPTS if now - t < 60.0]
    if len(_BOOTSTRAP_GLOBAL_ATTEMPTS) >= 20:
        return JSONResponse(
            {"error": "RATE_LIMIT_EXCEEDED", "detail": "Service busy. Try again later."},
            status_code=429,
            headers={"Cache-Control": "no-store"}
        )
    _BOOTSTRAP_GLOBAL_ATTEMPTS.append(now)

    if len(_BOOTSTRAP_RATE_LIMITS) > 100:
        _BOOTSTRAP_RATE_LIMITS = {k: v for k, v in _BOOTSTRAP_RATE_LIMITS.items() if any(now - t < 60.0 for t in v)}

    # 4. Incremental bounded body reading (max 1024 bytes)
    cl_header = request.headers.get("content-length")
    if cl_header:
        try:
            cl = int(cl_header.strip())
            if cl > 1024:
                return JSONResponse({"error": "PAYLOAD_TOO_LARGE", "detail": "Payload exceeds 1024 bytes"}, status_code=413, headers={"Cache-Control": "no-store"})
        except ValueError:
            return JSONResponse({"error": "BAD_REQUEST", "detail": "Malformed Content-Length"}, status_code=400, headers={"Cache-Control": "no-store"})

    chunks = []
    total_bytes = 0
    max_bytes = 1024
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            chunks.clear()
            return JSONResponse({"error": "PAYLOAD_TOO_LARGE", "detail": "Payload exceeds 1024 bytes"}, status_code=413, headers={"Cache-Control": "no-store"})
        chunks.append(chunk)

    raw_body = b"".join(chunks)
    chunks.clear()

    try:
        body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        return JSONResponse({"error": "BAD_REQUEST", "detail": "Invalid JSON"}, status_code=400, headers={"Cache-Control": "no-store"})

    secret = str(body.get("secret", "") or body.get("code", "")).strip()
    # Format validation: 128-bit hex string (exactly 32 hex chars)
    if not secret or len(secret) != 32 or not all(c in "0123456789abcdefABCDEF" for c in secret):
        return JSONResponse(
            {"error": "UNAUTHENTICATED", "detail": "Invalid or expired bootstrap secret"},
            status_code=401,
            headers={"Cache-Control": "no-store"}
        )

    # 5. Atomic exchange using shared vault path
    from aeonix.core.db import get_db_path
    from aeonix.core.auth import get_secrets_dir
    d_path = os.environ.get("AEONIX_DB_PATH") or get_db_path()
    s_dir = os.environ.get("AEONIX_SECRETS_DIR") or get_secrets_dir()
    token = exchange_bootstrap_secret(secret, db_path=d_path, secrets_dir=s_dir)
    if not token:
        return JSONResponse(
            {"error": "UNAUTHENTICATED", "detail": "Invalid or expired bootstrap secret"},
            status_code=401,
            headers={"Cache-Control": "no-store"}
        )

    return JSONResponse(
        {
            "token": token,
            "role": ROLE_PTT_OPERATOR,
            "expires_in": 900,
            "token_type": "Bearer"
        },
        headers={"Cache-Control": "no-store"}
    )

async def post_api_ptt_logout(request):
    """Explicitly revokes the current operator session token."""
    auth_header = request.headers.get("Authorization", "") or request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        payload = verify_token(token)
        if payload and "nonce" in payload:
            from aeonix.core.db import revoke_token, get_db_path
            d_path = os.environ.get("AEONIX_DB_PATH") or get_db_path()
            revoke_token(payload["nonce"], reason="Operator logout", db_path=d_path)
            return JSONResponse({"status": "revoked", "detail": "Session token explicitly revoked"})
    return JSONResponse({"status": "noop", "detail": "No active token found to revoke"})

async def post_api_ptt_start(request):
    """Starts explicit POCO push-to-talk recording with burst rate-limiting."""
    global _ptt_start_history
    now = time.time()
    # Sliding window rate-limiting: max 5 starts per 5 seconds
    _ptt_start_history = [t for t in _ptt_start_history if now - t < 5.0]
    if len(_ptt_start_history) >= 5:
        return JSONResponse({"error": "RATE_LIMIT_EXCEEDED: Maximum 5 PTT activations per 5 seconds"}, status_code=429)
    if _ptt_start_history and (now - _ptt_start_history[-1]) < 0.1:
        return JSONResponse({"error": "RATE_LIMIT_EXCEEDED: PTT activation burst debounced"}, status_code=429)

    _ptt_start_history.append(now)

    auth_role, caller = get_request_identity(request)
    actor = caller if auth_role != "UNAUTHENTICATED" else "Aadi"
    res = _ptt_controller.start_recording(actor=actor)
    return JSONResponse(res)

def validate_browser_wav_payload(payload: bytes) -> Tuple[bool, str, bytes]:
    """
    Validates browser-uploaded WAV audio according to strict contract:
    - Must be valid RIFF WAVE format.
    - Format tag must be 1 (PCM).
    - Channels must be 1 (mono).
    - Bits per sample must be 16.
    - Sample rate must be 16000 Hz.
    - Duration <= 15.0 seconds (<= 480,000 bytes PCM).
    - Payload cannot be empty.
    Returns (is_valid, error_message, pcm_bytes).
    """
    if not payload:
        return False, "EMPTY_AUDIO: Audio payload is empty", b""

    # Hard ceiling: 480,000 bytes PCM + 4096 bytes header margin
    if len(payload) > 480000 + 4096:
        return False, "PAYLOAD_TOO_LARGE: Audio payload exceeds 480,000 bytes limit (15-second ceiling)", b""

    try:
        import io, wave
        with wave.open(io.BytesIO(payload), "rb") as w:
            channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            framerate = w.getframerate()
            nframes = w.getnframes()
            pcm_bytes = w.readframes(nframes)
    except Exception as e:
        return False, f"MALFORMED_WAV_HEADER: {str(e)}", b""

    if channels != 1:
        return False, f"UNSUPPORTED_CHANNELS: Expected mono (1 channel), got {channels}", b""
    if sampwidth != 2:
        return False, f"UNSUPPORTED_BIT_DEPTH: Expected 16-bit PCM (2 bytes), got {sampwidth * 8}-bit", b""
    if framerate != 16000:
        return False, f"UNSUPPORTED_SAMPLE_RATE: Expected 16000 Hz, got {framerate} Hz", b""
    if len(pcm_bytes) == 0:
        return False, "EMPTY_AUDIO: Audio payload contains 0 frames", b""
    if len(pcm_bytes) > 480000:
        return False, f"EXCESSIVE_DURATION: Audio length {len(pcm_bytes)} bytes exceeds 15-second ceiling (480000 bytes)", b""

    return True, "", pcm_bytes

async def post_api_ptt_stop(request):
    """Stops PTT recording, retrieves ephemeral audio, and runs voice intent pipeline."""
    auth_role, caller = get_request_identity(request)
    actor = caller if auth_role != "UNAUTHENTICATED" else "Aadi"

    content_type = request.headers.get("content-type", "").lower()
    reason = request.query_params.get("reason") or request.headers.get("X-Audio-Reason") or "release"
    allow_fallback = (request.query_params.get("allow_fallback", "false").lower() == "true")
    model_tier = request.query_params.get("model_tier") or request.headers.get("X-Model-Tier") or "0.5B"

    audio_bytes = b""
    stop_res: Dict[str, Any] = {}

    if "audio/wav" in content_type or "application/octet-stream" in content_type:
        raw_body = await request.body()
        ok, err, pcm_bytes = validate_browser_wav_payload(raw_body)
        if not ok:
            return JSONResponse({"error": err}, status_code=400)
        
        audio_bytes = pcm_bytes
        stop_res = {
            "status": "stopped",
            "reason": reason,
            "duration_s": round(len(pcm_bytes) / 32000.0, 3),
            "audio_bytes_length": len(pcm_bytes),
            "recording_indicator": False,
            "source": "browser_mic"
        }
    else:
        body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
        reason = body.get("reason", reason)
        allow_fallback = bool(body.get("allow_fallback", allow_fallback))
        model_tier = body.get("model_tier", model_tier)

        stop_res = _ptt_controller.stop_recording(reason=reason, actor=actor)
        audio_bytes = _ptt_controller.get_audio_buffer()
        _ptt_controller.clear_buffer()

    if not audio_bytes:
        return JSONResponse({
            **stop_res,
            "pipeline": {
                "status": "empty_audio",
                "speech": "No audio captured."
            }
        })

    # Dedicated bounded voice response loop for ROLE_PTT_OPERATOR
    if auth_role == ROLE_PTT_OPERATOR:
        ownership = get_voice_response_ownership()
        session = ownership.try_acquire()
        if not session:
            return JSONResponse({
                "status": "busy",
                "error": "VOICE_PIPELINE_BUSY: A voice response is already in progress. Overlapping responses are prohibited.",
                "pipeline": {
                    "success": False,
                    "status": "voice_pipeline_busy"
                }
            }, status_code=409)

        try:
            from aeonix.core.voice_pipeline import orchestrate_ptt_voice_response
            target_ws, target_meta = get_authorized_firetv_websocket()
            orchestration_res = await asyncio.wait_for(
                orchestrate_ptt_voice_response(
                    audio_bytes=audio_bytes,
                    actor=actor,
                    caller_role=auth_role,
                    target_websocket=target_ws,
                    target_device_meta=target_meta,
                    loop_executor=heavy_executor,
                    db_path=os.environ.get("AEONIX_DB_PATH"),
                    ownership_session=session
                ),
                timeout=30.0
            )
            return JSONResponse({
                **stop_res,
                "pipeline": orchestration_res
            })
        except asyncio.TimeoutError:
            session.mark_cancelled()
            return JSONResponse({
                **stop_res,
                "pipeline": {
                    "success": False,
                    "status": "voice_pipeline_timeout",
                    "error": "Inference and delivery exceeded 30.0s execution ceiling"
                }
            }, status_code=504)
        except Exception as e:
            session.mark_cancelled()
            return JSONResponse({
                **stop_res,
                "pipeline": {
                    "success": False,
                    "status": "voice_pipeline_error",
                    "error": str(e)
                }
            }, status_code=500)
        finally:
            audio_bytes = b""
            session.finish_orchestration()

    try:
        pipeline_res = process_voice_pipeline(
            audio_bytes=audio_bytes,
            actor=actor,
            model_tier=model_tier,
            allow_fallback=allow_fallback,
            db_path=os.environ.get("AEONIX_DB_PATH"),
            caller_role=auth_role
        )

        return JSONResponse({
            **stop_res,
            "pipeline": {
                "success": pipeline_res.success,
                "status": pipeline_res.status,
                "speech": pipeline_res.speech,
                "action": pipeline_res.action,
                "tier": pipeline_res.tier,
                "model_used": pipeline_res.model_used,
                "fallback_applied": pipeline_res.fallback_applied,
                "requires_sentinel_approval": pipeline_res.requires_sentinel_approval,
                "latency_ms": pipeline_res.latency_ms
            }
        })
    finally:
        audio_bytes = b""

async def get_api_ptt_status(request):
    """Returns combined status of PTT, model runner, queue, and connected glass terminals."""
    ptt_status = _ptt_controller.get_status()
    q_mgr = get_queue_manager(db_path=os.environ.get("AEONIX_DB_PATH"))
    queue_status = q_mgr.get_status()

    model_info = {
        "is_running": llama_runner.is_running(),
        "active_model": "Qwen2.5-0.5B" if llama_runner.is_running() else "None (Burst Only)"
    }

    sanctuary_info = get_sanctuary_status()
    firetv_connected = len(active_connections) > 0

    return JSONResponse({
        "ptt": ptt_status,
        "queue": queue_status,
        "model": model_info,
        "sanctuary": sanctuary_info,
        "firetv_connected": firetv_connected,
        "active_tv_terminals": len(active_connections)
    })

async def post_reconcile_mission(request):
    """Resolves an interrupted mission in NEEDS_RECONCILIATION state."""
    try:
        body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
        mission_id = body.get("mission_id")
        resolution = body.get("resolution", "ABORT")
        passphrase = body.get("operator_passphrase") or request.headers.get("X-Operator-Passphrase", "")
        if not mission_id:
            return JSONResponse({"error": "mission_id required"}, status_code=400)
        from aeonix.core.governed_mission import governor
        ok, msg = governor.resolve_reconciliation(mission_id=mission_id, resolution=resolution, operator_passphrase=passphrase)
        if not ok:
            return JSONResponse({"error": msg}, status_code=400)
        return JSONResponse({"success": True, "message": msg})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def websocket_endpoint(websocket: WebSocket):
    # Strictly reject query parameter tokens to eliminate URL token exposure
    if "token" in websocket.query_params:
        await websocket.close(
            code=4401, 
            reason="Unauthorized: Tokens in query parameters are strictly forbidden. Use RFC 6455 Authorization header."
        )
        return

    auth_header = websocket.headers.get("authorization", "") or websocket.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    if not token:
        await websocket.close(
            code=4401, 
            reason="Unauthorized: Missing Authorization header in WebSocket handshake"
        )
        return

    payload = verify_token(token)
    if not payload:
        await websocket.close(
            code=4401, 
            reason="Unauthorized: Invalid, expired, or revoked cryptographic bearer token"
        )
        return

    ws_role = payload.get("role", ROLE_FIRETV_GLASS)
    ws_device = payload.get("device_id", "paired_device")

    await websocket.accept()
    active_connections.add(websocket)
    active_terminals[websocket] = {
        "device_id": ws_device,
        "role": ws_role,
        "connected_at": time.time()
    }
    log_audit_event("GLASS_TERMINAL", "connect", "websocket", "ok", {"device": ws_device, "role": ws_role})
    
    # Audio buffer for PTT voice streaming
    audio_buffer = bytearray()
    voice_test_executed = False

    # Send initial Living Surface Layout Intent
    await websocket.send_text(json.dumps({
        "type": "layout_update",
        "screen": "living_surface",
        "theme": "obsidian_cyan",
        "surface_data": {
            "title": "ÆONIX PRISM",
            "greeting": "Welcome back, Aadi.",
            "mode": "Sovereign Glass Terminal",
            "device": ws_device,
            "role": ws_role,
            "voice_stt": "READY (100% OFFLINE)"
        }
    }))

    try:
        while True:
            data = await websocket.receive_text()
            # 32 KiB safety ceiling for control messages (Section 10 of 4 Nov Spec)
            if len(data) > 32768 and '"audio_chunk"' not in data:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "code": "FRAME_TOO_LARGE",
                    "error": f"Message exceeds 32 KiB safety ceiling ({len(data)} bytes)"
                }))
                continue

            try:
                msg = json.loads(data)
                msg_type = msg.get("type")
                if msg_type == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": time.time(),
                        "server_sequence": _SERVER_SEQUENCE
                    }))
                elif msg_type == "sync_request":
                    last_seq = int(msg.get("last_sequence", 0))
                    missed = get_events_since(last_seq)
                    await websocket.send_text(json.dumps({
                        "type": "sync_response",
                        "server_sequence": _SERVER_SEQUENCE,
                        "replayed_events": missed
                    }))
                elif msg_type == "sentinel_action":
                    req_id = msg.get("request_id")
                    approved = bool(msg.get("approved", False))
                    if approved is True and ws_role != ROLE_POCO_CORE:
                        await websocket.send_text(json.dumps({
                            "type": "sentinel_rejected",
                            "request_id": req_id,
                            "error": "POCO_AUTHORITY_REQUIRED: Approval of consequential actions restricted strictly to POCO Core Mind. TV may only deny/cancel."
                        }))
                    else:
                        ok, status_reason = resolve_sentinel_request(req_id, approved, resolver=ws_device, resolver_role=ws_role)
                        await websocket.send_text(json.dumps({
                            "type": "sentinel_resolved",
                            "request_id": req_id,
                            "status": status_reason
                        }))
                elif msg_type == "audio_start":
                    if is_sanctuary_active():
                        await websocket.send_text(json.dumps({
                            "type": "audio_status",
                            "status": "blocked",
                            "error": "MIC_INGESTION_DISABLED: Sanctuary Privacy Lockdown is ACTIVE"
                        }))
                        audio_buffer = bytearray()
                    else:
                        audio_buffer = bytearray()
                        await websocket.send_text(json.dumps({"type": "audio_status", "status": "recording"}))
                elif msg_type == "audio_chunk":
                    chunk_b64 = msg.get("data", "")
                    if chunk_b64:
                        decoded = base64.b64decode(chunk_b64)
                        # Bound audio buffer size to 1MB max to prevent memory exhaustion attacks
                        MAX_AUDIO_BUFFER_BYTES = 1024 * 1024
                        if len(audio_buffer) + len(decoded) <= MAX_AUDIO_BUFFER_BYTES:
                            audio_buffer.extend(decoded)
                        else:
                            print(f"[WebSocket] Audio buffer reached safety ceiling ({MAX_AUDIO_BUFFER_BYTES} bytes). Chunk dropped.")

                elif msg_type == "audio_end":
                    await websocket.send_text(json.dumps({"type": "audio_status", "status": "processing"}))
                    if audio_buffer:
                        loop = asyncio.get_event_loop()
                        query = await loop.run_in_executor(heavy_executor, transcribe_pcm, bytes(audio_buffer))
                        log_audit_event("GLASS_TERMINAL", "voice_command", "whisper_tiny", "ok", {"query": query})
                        
                        pipeline_res = await process_intent_pipeline(query, actor="Aadi", actor_role=ws_role)
                        reply_text = pipeline_res.get("speech", "")
                        intent_type = pipeline_res.get("action", "aadya_dialogue")
                        
                        await websocket.send_text(json.dumps({
                            "type": "voice_reply",
                            "query": query,
                            "intent": intent_type,
                            "reply": reply_text,
                            "correlation_id": pipeline_res.get("correlation_id", "")
                        }))
                    audio_buffer = bytearray()
                elif msg_type == "trigger_voice_test":
                    if voice_test_executed:
                        await websocket.send_text(json.dumps({
                            "type": "voice_audio_error",
                            "message_id": msg.get("message_id", "err"),
                            "error": "SINGLE_USE_EXCEEDED: Test trigger limited strictly to 1 execution per connection."
                        }))
                    else:
                        voice_test_executed = True
                        from aeonix.core.voice_protocol import stream_voice_audio
                        wav_source = msg.get("wav_source") or os.environ.get("PRISM_VOICE_TEST_WAV")
                        if not wav_source:
                            import io, wave
                            buf = io.BytesIO()
                            with wave.open(buf, "wb") as w:
                                w.setnchannels(1)
                                w.setsampwidth(2)
                                w.setframerate(22050)
                                w.writeframes(b"\x00" * 1000)
                            wav_source = buf.getvalue()
                        msg_id = msg.get("message_id")
                        await stream_voice_audio(websocket, wav_source, message_id=msg_id)
            except json.JSONDecodeError:
                pass
            except Exception as loop_err:
                print(f"[WS Loop Error]: {loop_err}")
    except WebSocketDisconnect:
        active_connections.discard(websocket)
        active_terminals.pop(websocket, None)
        log_audit_event("GLASS_TERMINAL", "disconnect", "websocket", "ok", {})
    except Exception as ws_err:
        print(f"[WS Connection Error]: {ws_err}")
        active_connections.discard(websocket)
        active_terminals.pop(websocket, None)

# PANOPTES Endpoints
async def post_panoptes_scan(request):
    try:
        body = await request.json()
        action = body.get("action", "passive_osint")
        if action == "active_probe":
            target = body.get("target", "10.116.23.1")
            ports = body.get("ports", [80, 443])
            res = request_active_probe(target, ports)
            await broadcast_message({
                "type": "sentinel_card",
                "request_id": res["request_id"],
                "agent": "PANOPTES",
                "action_type": "ACTIVE_PORT_SCAN",
                "target": target,
                "risk_level": "R3_HIGH",
                "scope": {"ports": ports}
            })
            return JSONResponse(res)
        else:
            domain = body.get("domain", "example.com")
            loop = asyncio.get_event_loop()
            graph = await loop.run_in_executor(heavy_executor, run_passive_osint, domain)
            return JSONResponse({"success": True, "graph": graph})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_panoptes_graph(request):
    try:
        start_id = request.query_params.get("start_id", "")
        depth = int(request.query_params.get("depth", 2))
        graph = get_entity_graph(start_id, max_depth=depth)
        return JSONResponse({"success": True, "graph": graph})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_panoptes_ingest_note(request):
    try:
        body = await request.json()
        content = body.get("content", "")
        if not content:
            return JSONResponse({"error": "Content required"}, status_code=400)
        source_path = body.get("source_path")
        source_url = body.get("source_url")
        author = body.get("author", "Aadi")
        case_id = body.get("case_id", "case_knowledge_vault")
        res = ingest_markdown_note(
            content=content,
            source_path=source_path,
            source_url=source_url,
            author=author,
            case_id=case_id
        )
        return JSONResponse({"success": True, "note": res})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_panoptes_topics(request):
    try:
        topics = list_monitored_topics()
        return JSONResponse({"success": True, "topics": topics})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_panoptes_topic_notes(request):
    try:
        topic = request.query_params.get("topic", "")
        if not topic:
            return JSONResponse({"error": "Topic parameter required"}, status_code=400)
        notes = query_notes_by_topic(topic)
        return JSONResponse({"success": True, "notes": notes})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# VERITAS Endpoints
async def list_veritas_cases(request):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM cases ORDER BY created_at DESC;")
        cases = [dict(r) for r in cur.fetchall()]
        conn.close()
        return JSONResponse({"success": True, "cases": cases})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_veritas_case(request):
    try:
        body = await request.json()
        title = body.get("title", "Forensic Investigation")
        description = body.get("description", "")
        legal_basis = body.get("legal_basis", "Authorized Sovereign Security Audit")
        cid = create_case(title, description, legal_basis)
        return JSONResponse({"success": True, "case_id": cid})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_veritas_evidence(request):
    try:
        body = await request.json()
        case_id = body.get("case_id")
        file_path = body.get("file_path")
        mime_type = body.get("mime_type", "application/octet-stream")
        metadata = body.get("metadata", {})
        if not case_id or not file_path:
            return JSONResponse({"error": "Missing case_id or file_path"}, status_code=400)
        res = ingest_evidence(case_id, file_path, mime_type, metadata)
        return JSONResponse({"success": True, "evidence": res})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_veritas_manifest(request):
    try:
        case_id = request.query_params.get("case_id")
        if not case_id:
            return JSONResponse({"error": "Missing case_id"}, status_code=400)
        manifest = generate_case_manifest(case_id)
        return JSONResponse({"success": True, "manifest": manifest})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# GUARDIAN & ATLAS WATCH Endpoints
async def get_guardian_network(request):
    try:
        inv = await async_get_network_inventory()
        return JSONResponse({"success": True, "network": inv})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_guardian_telemetry(request):
    try:
        force = request.query_params.get("force", "false").lower() == "true"
        telemetry = get_bounded_network_telemetry(force_refresh=force)
        return JSONResponse({"success": True, "telemetry": telemetry})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_atlas_health(request):
    try:
        rep = run_supervisor_cycle()
        return JSONResponse({"success": True, "supervisor": rep})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# =========================================================================
# Phase 4: SPECTRA Media, Live IPTV & Sanctuary Mode Endpoints
# =========================================================================

async def get_media_channels(request):
    return JSONResponse({"success": True, "channels": get_channel_catalog()})

async def get_media_current(request):
    return JSONResponse({"success": True, "playback": get_current_playback()})

async def post_media_play(request):
    try:
        body = await request.json()
        channel_id = body.get("channel_id")
        stream_url = body.get("stream_url")
        title = body.get("title")
        category = body.get("category", "Live IPTV")

        if channel_id:
            ch = find_channel_by_query(channel_id)
            if ch:
                stream_url = ch["stream_url"]
                title = ch["name"]
                category = ch["category"]

        if not stream_url:
            return JSONResponse({"error": "Missing stream_url or channel_id"}, status_code=400)

        channel_info = {
            "id": channel_id or "custom",
            "name": title or "Live Stream",
            "stream_url": stream_url,
            "category": category
        }
        set_playback_state(True, channel_info)

        await broadcast_message({
            "type": "media_play",
            "stream_url": stream_url,
            "title": title or "Live Stream",
            "category": category
        })
        return JSONResponse({"success": True, "playing": channel_info})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_media_control(request):
    try:
        body = await request.json()
        command = body.get("command", "pause")
        if command in ("stop", "halt"):
            set_playback_state(False)
        await broadcast_message({
            "type": "media_control",
            "command": command
        })
        return JSONResponse({"success": True, "command": command})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_sanctuary_status_endpoint(request):
    return JSONResponse({"success": True, "sanctuary": get_sanctuary_status()})

async def post_sanctuary_activate(request):
    try:
        auth_role, actor = get_request_identity(request)
        if auth_role == "UNAUTHENTICATED":
            return JSONResponse({"error": "Missing or invalid authorization header"}, status_code=401)
        if auth_role != ROLE_POCO_CORE:
            return JSONResponse({"error": "POCO_AUTHORITY_REQUIRED: Only POCO Core Mind can modify Sanctuary state"}, status_code=403)

        try:
            body = await request.json()
        except Exception:
            body = {}
        actor = body.get("actor", actor)
        reason = body.get("reason", "Operator Command")
        res = engage_sanctuary(actor=actor, reason=reason)
        _ptt_controller.on_sentinel_lockdown(actor=actor)
        await broadcast_message({
            "type": "sanctuary_mode",
            "active": True
        })
        return JSONResponse({"success": True, "sanctuary": res})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_sanctuary_deactivate(request):
    try:
        auth_role, actor = get_request_identity(request)
        if auth_role == "UNAUTHENTICATED":
            return JSONResponse({"error": "Missing or invalid authorization header"}, status_code=401)
        if auth_role != ROLE_POCO_CORE:
            return JSONResponse({"error": "POCO_AUTHORITY_REQUIRED: Only POCO Core Mind can modify Sanctuary state"}, status_code=403)

        try:
            body = await request.json()
        except Exception:
            body = {}
        actor = body.get("actor", actor)
        res = release_sanctuary(actor=actor)
        _ptt_controller.cancel(actor=actor, reason="sanctuary_released")
        await broadcast_message({
            "type": "sanctuary_mode",
            "active": False
        })
        return JSONResponse({"success": True, "sanctuary": res})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# =========================================================================
# Phase 5: FORGE Developer Engine & VISIA Visual Intel Endpoints
# =========================================================================

async def post_forge_draft(request):
    try:
        body = await request.json()
        prompt = body.get("prompt", "")
        if not prompt:
            return JSONResponse({"error": "Missing prompt"}, status_code=400)
        draft = draft_command_from_prompt(prompt)
        return JSONResponse({"success": True, "draft": draft})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_forge_execute(request):
    try:
        auth_role, actor = get_request_identity(request)
        if auth_role == "UNAUTHENTICATED":
            return JSONResponse({"error": "Missing or invalid authorization header"}, status_code=401)
        if auth_role not in (ROLE_POCO_CORE, ROLE_AGENT_EXECUTOR):
            return JSONResponse({"error": "FORBIDDEN: Execution requires POCO_CORE or AGENT_EXECUTOR role"}, status_code=403)

        body = await request.json()
        op_name = body.get("operation") or body.get("command", "")
        extra_args = body.get("extra_args")
        cwd = body.get("cwd")
        sentinel_req_id = body.get("sentinel_request_id")

        if not op_name:
            return JSONResponse({"error": "Missing 'operation' or 'command' in request"}, status_code=400)

        # Execute typed operation (Zero shell=True)
        res = execute_typed_operation(
            operation_name=op_name,
            extra_args=extra_args,
            cwd=cwd,
            sentinel_request_id=sentinel_req_id,
            actor=actor,
            actor_role=auth_role
        )

        if res.get("status") == "sentinel_gate_hold":
            await broadcast_message({
                "type": "sentinel_card",
                "request_id": res["request_id"],
                "agent": "FORGE",
                "action_type": f"TYPED_OP_{op_name.upper()}",
                "target": op_name,
                "risk_level": "R4_CRITICAL",
                "scope": {"cwd": cwd or "default", "extra_args": extra_args or []}
            })
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_forge_git(request):
    try:
        telemetry = get_git_telemetry()
        return JSONResponse({"success": True, "git": telemetry})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_visia_analyze(request):
    try:
        body = await request.json()
        file_path = body.get("file_path")
        case_id = body.get("case_id")
        run_ocr = body.get("run_ocr", True)
        actor = body.get("actor", "Aadi")

        if not file_path or not os.path.exists(file_path):
            return JSONResponse({"error": f"File not found: {file_path}"}, status_code=400)

        loop = asyncio.get_event_loop()
        analysis = await loop.run_in_executor(
            heavy_executor,
            lambda: analyze_visual_artifact(file_path, case_id=case_id, run_ocr=run_ocr, actor=actor)
        )
        return JSONResponse({"success": True, "analysis": analysis})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# =========================================================================
# Phase 6: Vault Backup, MORPH Evolution & Oracle's Council Endpoints
# =========================================================================

async def post_backup_create(request):
    try:
        body = await request.json() if request.headers.get("content-length") else {}
        actor = body.get("actor", "Aadi")
        note = body.get("note", "Operator Backup")
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(heavy_executor, lambda: create_vault_backup(actor=actor, note=note))
        return JSONResponse({"success": True, "backup": res})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_backup_list(request):
    try:
        backups = list_backups()
        return JSONResponse({"success": True, "backups": backups})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_backup_verify(request):
    try:
        body = await request.json()
        path = body.get("file_path")
        if not path or not os.path.exists(path):
            return JSONResponse({"error": f"Backup file not found: {path}"}, status_code=400)
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(heavy_executor, verify_backup, path)
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_recovery_key(request):
    try:
        key_data = generate_emergency_recovery_key()
        return JSONResponse({"success": True, "recovery": key_data})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_morph_proposals_endpoint(request):
    try:
        proposals = get_pending_proposals()
        return JSONResponse({"success": True, "proposals": proposals})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_morph_propose(request):
    try:
        body = await request.json() if request.headers.get("content-length") else {}
        actor = body.get("actor", "Aadi")
        res = generate_optimization_proposal(actor=actor)
        if res.get("sentinel_request_id"):
            await broadcast_message({
                "type": "sentinel_card",
                "request_id": res["sentinel_request_id"],
                "agent": "MORPH",
                "action_type": "SYSTEM_OPTIMIZATION",
                "target": res["title"],
                "risk_level": "R1_LOW",
                "scope": {"description": res["description"]}
            })
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_oracle_council(request):
    try:
        body = await request.json()
        query = body.get("query", "")
        actor = body.get("actor", "Aadi")
        if not query:
            return JSONResponse({"error": "Missing query"}, status_code=400)
        council_res = convene_council_session(query=query, actor=actor)
        return JSONResponse(council_res)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# =========================================================================
# Master System Engines: LUMEN, CHRONOS, ORACLE, AADYA, IDENTITY, ATLAS, TRUST & AGENTS
# =========================================================================

async def get_lumen_surface(request):
    try:
        from core.lumen import lumen
        return JSONResponse({"success": True, "lumen": lumen.compute_living_surface_state()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_chronos_routines(request):
    try:
        from core.chronos import chronos
        return JSONResponse({"success": True, "routines": chronos.list_routines()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_chronos_trigger(request):
    try:
        body = await request.json()
        routine_id = body.get("routine_id", "")
        from core.chronos import chronos
        return JSONResponse(chronos.trigger_routine(routine_id))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_oracle_research(request):
    try:
        body = await request.json()
        query = body.get("query", "")
        from core.oracle import oracle
        return JSONResponse({"success": True, "research": oracle.conduct_research(query)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_aadya_priority(request):
    try:
        body = await request.json()
        proposal = body.get("proposal", "")
        from core.aadya import aadya
        return JSONResponse({"success": True, "evaluation": aadya.evaluate_priority(proposal)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_aadya_radar(request):
    try:
        from core.aadya import aadya
        return JSONResponse({"success": True, "radar": aadya.scan_future_radar()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_aadya_protection(request):
    try:
        from core.aadya import aadya
        return JSONResponse({"success": True, "protection": aadya.protection_check()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_identity_analyze(request):
    try:
        body = await request.json()
        identifier = body.get("identifier", "")
        from core.identity import identity_engine
        return JSONResponse(identity_engine.analyze_public_exposure(identifier))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_atlas_summary(request):
    try:
        from core.atlas import atlas
        return JSONResponse({"success": True, "atlas": atlas.get_situational_summary()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_trust_signed_order(request):
    try:
        auth_role, actor = get_request_identity(request)
        if auth_role != ROLE_POCO_CORE:
            return JSONResponse({"error": "POCO_AUTHORITY_REQUIRED: Only POCO Core Mind can issue signed execution orders"}, status_code=403)

        body = await request.json()
        mission = body.get("mission", "general_mission")
        scope = body.get("scope", ["vault_read"])
        target = body.get("target", "local_system")
        model = body.get("model", "NOVA_LOCAL")
        user_verified = bool(body.get("user_verified", False))

        order = trust.generate_signed_order(
            mission_name=mission,
            scope=scope,
            target=target,
            model=model,
            user_verified=user_verified,
            actor_role=auth_role
        )
        return JSONResponse({"success": True, "order": order})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_trust_verify_order(request):
    try:
        body = await request.json()
        order = body.get("order")
        if not order:
            return JSONResponse({"error": "Missing order in request body"}, status_code=400)
        is_valid, reason = trust.verify_order(order)
        return JSONResponse({"success": True, "verified": is_valid, "reason": reason})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_trust_verify_audit_chain(request):
    try:
        from core.db import verify_audit_chain
        res = verify_audit_chain()
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_trust_kill_switch(request):
    try:
        auth_role, actor = get_request_identity(request)
        body = await request.json() if request.headers.get("content-length") else {}
        action = body.get("action", "engage")
        rationale = body.get("rationale", "Operator emergency stop")
        
        if action == "engage":
            status = trust.trigger_kill_switch(rationale=rationale, actor_role=auth_role)
            await broadcast_message({
                "type": "kill_switch_alert",
                "state": "ENGAGED",
                "rationale": rationale
            })
            return JSONResponse({"success": True, "status": status})
        else:
            ok, res = trust.reset_kill_switch(actor_role=auth_role)
            if not ok:
                return JSONResponse(res, status_code=403)
            await broadcast_message({
                "type": "kill_switch_alert",
                "state": "DISENGAGED"
            })
            return JSONResponse({"success": True, "status": res})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_agents_roster(request):
    try:
        from agents.orchestrator import orchestrator
        return JSONResponse({"success": True, "roster": orchestrator.list_roster()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_agents_dispatch(request):
    try:
        body = await request.json()
        objective = body.get("objective", "")
        target = body.get("target", "")
        if not objective:
            return JSONResponse({"error": "Empty objective"}, status_code=400)
        from agents.orchestrator import orchestrator
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(heavy_executor, lambda: orchestrator.dispatch_mission(objective, target=target))
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# =========================================================================
# Part 17 Advanced Engines Endpoints
# =========================================================================

async def post_advanced_paradox(request):
    try:
        body = await request.json()
        decision = body.get("decision", "")
        counterfactual = body.get("counterfactual", "")
        from core.paradox import paradox
        return JSONResponse({"success": True, "paradox": paradox.simulate_counterfactual(decision, counterfactual)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_advanced_ghost(request):
    try:
        from core.ghost import ghost
        return JSONResponse({"success": True, "ghost": ghost.get_digital_twin_state()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_advanced_chronoscope(request):
    try:
        from core.chronoscope import chronoscope
        return JSONResponse({"success": True, "replay": chronoscope.replay_audit_chain()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_advanced_dreamcatcher(request):
    try:
        body = await request.json()
        fragment = body.get("fragment", "")
        from core.dreamcatcher import dreamcatcher
        return JSONResponse({"success": True, "dreamcatcher": dreamcatcher.incubate_thought(fragment)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_advanced_mimic(request):
    try:
        body = await request.json()
        name = body.get("name", "custom_workflow")
        steps = body.get("steps", [])
        from core.mimic import mimic
        return JSONResponse(mimic.clone_workflow(name, steps))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_advanced_signal(request):
    try:
        try:
            from aeonix.core.signal_detector import signal_detector
        except ImportError:
            from core.signal_detector import signal_detector
        return JSONResponse({"success": True, "signal": signal_detector.scan_for_latent_patterns()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_advanced_forge_mind(request):
    try:
        body = await request.json()
        tool_name = body.get("tool_name", "")
        purpose = body.get("purpose", "")
        code = body.get("code", "")
        from core.forge_mind import forge_mind
        return JSONResponse(forge_mind.propose_new_tool(tool_name, purpose, code))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_advanced_nexus_room(request):
    try:
        from core.nexus_room import nexus_room
        return JSONResponse({"success": True, "nexus_room": nexus_room.render_celestial_topology()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_router_status_endpoint(request):
    try:
        from aeonix.core.router import get_router_status
        return JSONResponse({"success": True, "router": get_router_status()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_ai_benchmark(request):
    try:
        body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
        mode = body.get("mode", "fast")
        prompt = body.get("prompt", "Explain sovereign computation in one concise sentence.")
        loop = asyncio.get_event_loop()
        async with llm_inference_lock:
            bench = await loop.run_in_executor(
                heavy_executor, 
                lambda: llama_runner.benchmark(model_mode=mode, prompt=prompt)
            )
        return JSONResponse(bench)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_panoptes_report_endpoint(request):
    try:
        domain = request.query_params.get("domain", "example.com")
        from aeonix.core.panoptes import generate_osint_report
        loop = asyncio.get_event_loop()
        rep = await loop.run_in_executor(heavy_executor, generate_osint_report, domain)
        return JSONResponse({"success": True, "report": rep})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_veritas_timeline_endpoint(request):
    try:
        case_id = request.query_params.get("case_id")
        if not case_id:
            return JSONResponse({"error": "case_id query parameter required"}, status_code=400)
        from aeonix.core.veritas import build_case_timeline
        return JSONResponse({"success": True, "case_id": case_id, "timeline": build_case_timeline(case_id)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_veritas_export_endpoint(request):
    try:
        body = await request.json()
        case_id = body.get("case_id")
        if not case_id:
            return JSONResponse({"error": "case_id required"}, status_code=400)
        from aeonix.core.veritas import export_case_report
        return JSONResponse(export_case_report(case_id))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_operator_console(request):
    """Serves the Sovereign POCO Operator Console review deck."""
    from aeonix.core.operator_ui import OPERATOR_HTML
    return HTMLResponse(OPERATOR_HTML)

async def get_gateway_weather(request):
    """
    Returns open weather telemetry with cryptographic provenance and honest staleness.
    Allowed for POCO_CORE and FIRETV_GLASS (Master Spec Sections 14 & 19).
    """
    try:
        lat = float(request.query_params.get("lat", 28.6139))
        lon = float(request.query_params.get("lon", 77.2090))
        force = request.query_params.get("force_refresh", "false").lower() == "true"
        from aeonix.core.atlas import atlas
        data = atlas.get_weather_with_provenance(lat=lat, lon=lon, force_refresh=force)
        return JSONResponse({"success": True, "weather": data})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_chronos_timeline(request):
    """
    Returns durable event journal replay with sequence-based pagination and integrity validation.
    """
    try:
        start_seq = int(request.query_params.get("start_sequence", 1))
        limit = min(int(request.query_params.get("limit", 100)), 500)
        from aeonix.core.db import replay_event_journal
        res = replay_event_journal(start_sequence=start_seq, limit=limit)
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_events(request):
    """
    Ingests a durable event envelope with strict schema validation and safety bounds.
    """
    try:
        body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
        event_id = body.get("event_id")
        schema_version = body.get("schema_version", "1.0.0")
        observed_at = float(body.get("observed_at", time.time()))
        device_id = body.get("device_id", "unknown_device")
        source = body.get("source", "api")
        event_type = body.get("event_type", "generic")
        subject = body.get("subject", "system")
        payload = body.get("payload", {})
        classification = body.get("classification", "R1")
        evidence_refs = body.get("evidence_refs", [])
        correlation_id = body.get("correlation_id")

        from aeonix.core.db import record_durable_event
        ok, record, msg = record_durable_event(
            event_id=event_id,
            schema_version=schema_version,
            observed_at=observed_at,
            device_id=device_id,
            source=source,
            event_type=event_type,
            subject=subject,
            payload=payload,
            classification=classification,
            evidence_refs=evidence_refs,
            correlation_id=correlation_id
        )
        if not ok:
            status_code = 409 if "DUPLICATE" in msg else 400
            return JSONResponse({"error": msg}, status_code=status_code)
        return JSONResponse({"success": True, "event": record})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_wal_checkpoint(request):
    """
    Triggers controlled SQLite WAL checkpoint (POCO_CORE only).
    """
    try:
        body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
        mode = body.get("mode", "PASSIVE")
        from aeonix.core.db import checkpoint_wal
        res = checkpoint_wal(mode=mode)
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_missions_list(request):
    """Returns list of recent governed missions."""
    try:
        from aeonix.core.db import query_db
        rows = query_db("SELECT id, objective, target, status, current_phase, total_phases, created_at, updated_at FROM missions ORDER BY created_at DESC LIMIT 50;")
        missions = [dict(r) for r in rows]
        return JSONResponse({"success": True, "missions": missions})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def post_create_mission(request):
    """Submits a new governed mission proposal."""
    try:
        body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
        m_type = body.get("mission_type", "storage_diagnostic")
        objective = body.get("objective", "Autonomous storage diagnostic")
        target = body.get("target", "storage_vault")
        scope = body.get("scope", {})
        from aeonix.core.governed_mission import governor
        res = governor.create_mission(mission_type=m_type, objective=objective, target=target, scope=scope)
        return JSONResponse({"success": True, "mission": res})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

async def post_claim_mission(request):
    """Claims and executes an approved governed mission."""
    try:
        body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
        mission_id = body.get("mission_id")
        claimer = body.get("claimer", "POCO_CORE_MIND")
        digest = body.get("action_digest")
        if not mission_id:
            return JSONResponse({"error": "mission_id required"}, status_code=400)
        from aeonix.core.governed_mission import governor
        ok, receipt, msg = governor.claim_and_execute(mission_id=mission_id, claimer=claimer, expected_digest=digest)
        if not ok:
            return JSONResponse({"error": msg}, status_code=400)
        return JSONResponse({"success": True, "receipt": receipt})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

PUBLIC_ENDPOINTS = {
    ("GET", "/api/status"),
    ("GET", "/ui/ptt"),
    ("POST", "/api/ptt/bootstrap"),
}

PTT_OPERATOR_ALLOWED_ENDPOINTS = {
    ("GET", "/ui/ptt"),
    ("POST", "/api/ptt/start"),
    ("POST", "/api/ptt/stop"),
    ("GET", "/api/ptt/status"),
    ("POST", "/api/ptt/logout"),
}

FIRETV_ALLOWED_ENDPOINTS = {
    ("GET", "/api/status"),
    ("GET", "/api/sentinel/pending"),
    ("POST", "/api/sentinel/resolve"),
    ("POST", "/api/intent"),
    ("POST", "/api/voice/transcribe"),
    ("GET", "/api/voice/model"),
    ("GET", "/api/lumen/surface"),
    ("GET", "/api/briefing"),
    ("GET", "/api/media/channels"),
    ("GET", "/api/media/current"),
    ("POST", "/api/media/play"),
    ("POST", "/api/media/control"),
    ("GET", "/api/sanctuary/status"),
    ("GET", "/gateway/weather"),
    ("GET", "/api/gateway/weather"),
    ("GET", "/chronos/timeline"),
    ("GET", "/api/chronos/timeline"),
    ("GET", "/missions"),
    ("GET", "/api/missions"),
}

AGENT_ALLOWED_ENDPOINTS = {
    ("GET", "/api/status"),
    ("POST", "/api/sentinel/create"),
    ("POST", "/api/agents/dispatch"),
    ("POST", "/api/memory/remember"),
    ("GET", "/api/memory/recall"),
    ("POST", "/events"),
    ("POST", "/api/events"),
}

class CentralAuthMiddleware(BaseHTTPMiddleware):
    """
    Central Authentication and Sovereign RBAC Role Enforcement Middleware.
    Enforces:
    - Zero unauthenticated access outside PUBLIC_ENDPOINTS allowlist.
    - Bearer token authentication via RFC 6750 Authorization header only.
    - Rejection of expired, forged, or revoked tokens with 401.
    - Strict role segregation (POCO_CORE, FIRETV_GLASS, AGENT_EXECUTOR) with 403.
    """
    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        clean_path = request.url.path.rstrip("/") if request.url.path != "/" else "/"
        endpoint_key = (request.method, clean_path)

        # 1. Public Allowlist (Minimal liveness only)
        if endpoint_key in PUBLIC_ENDPOINTS:
            return await call_next(request)

        # Check disaster recovery maintenance mode lock
        try:
            from aeonix.core.backup import is_maintenance_mode
            if is_maintenance_mode() and not clean_path.startswith("/api/backup"):
                return JSONResponse(
                    {
                        "error": "MAINTENANCE_LOCKED", 
                        "detail": "Disaster recovery vault restore in progress. Database operations locked."
                    }, 
                    status_code=503
                )
        except Exception:
            pass

        # 2. Extract Bearer token strictly from Authorization header
        auth_header = request.headers.get("Authorization", "") or request.headers.get("authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

        if not token:
            return JSONResponse(
                {
                    "error": "UNAUTHENTICATED: Cryptographic Bearer token required in authorization header", 
                    "detail": "Missing Authorization header"
                }, 
                status_code=401
            )

        payload = verify_token(token)
        if not payload:
            return JSONResponse(
                {
                    "error": "UNAUTHENTICATED: Invalid, expired, or revoked cryptographic token in authorization header", 
                    "detail": "Invalid, expired, or revoked token"
                }, 
                status_code=401
            )

        role = payload.get("role", "UNKNOWN")
        device_id = payload.get("device_id", "unknown")
        request.state.auth_role = role
        request.state.device_id = device_id

        # 3. RBAC Role Matrix Enforcement
        if role == ROLE_POCO_CORE:
            return await call_next(request)
        elif role == ROLE_PTT_OPERATOR:
            if endpoint_key in PTT_OPERATOR_ALLOWED_ENDPOINTS:
                return await call_next(request)
            return JSONResponse(
                {
                    "error": "FORBIDDEN",
                    "detail": f"Role '{role}' is not authorized to access {request.method} {clean_path}"
                },
                status_code=403
            )
        elif role == ROLE_FIRETV_GLASS:
            if endpoint_key in FIRETV_ALLOWED_ENDPOINTS:
                return await call_next(request)
            return JSONResponse(
                {
                    "error": "FORBIDDEN", 
                    "detail": f"Role '{role}' is not authorized to access {request.method} {clean_path}"
                }, 
                status_code=403
            )
        elif role == ROLE_AGENT_EXECUTOR:
            if endpoint_key in AGENT_ALLOWED_ENDPOINTS:
                return await call_next(request)
            return JSONResponse(
                {
                    "error": "FORBIDDEN", 
                    "detail": f"Role '{role}' is not authorized to access {request.method} {clean_path}"
                }, 
                status_code=403
            )
        else:
            return JSONResponse(
                {
                    "error": "FORBIDDEN", 
                    "detail": f"Unrecognized sovereign role: '{role}'"
                }, 
                status_code=403
            )

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    ),
    Middleware(CentralAuthMiddleware),
]

app = Starlette(
    routes=[
        Route("/operator", get_operator_console, methods=["GET"]),
        Route("/console", get_operator_console, methods=["GET"]),
        Route("/api/status", get_status, methods=["GET"]),
        Route("/api/system/status", get_system_status, methods=["GET"]),
        Route("/api/router/status", get_router_status_endpoint, methods=["GET"]),
        Route("/api/ai/benchmark", post_ai_benchmark, methods=["POST"]),
        Route("/api/panoptes/report", get_panoptes_report_endpoint, methods=["GET"]),
        Route("/api/veritas/timeline", get_veritas_timeline_endpoint, methods=["GET"]),
        Route("/api/veritas/export", post_veritas_export_endpoint, methods=["POST"]),
        Route("/api/sentinel/pending", list_sentinel_pending, methods=["GET"]),

        Route("/api/sentinel/create", create_sentinel, methods=["POST"]),
        Route("/api/sentinel/resolve", resolve_sentinel, methods=["POST"]),
        Route("/api/memory/remember", post_memory, methods=["POST"]),
        Route("/api/memory/recall", get_memories, methods=["GET"]),
        Route("/api/briefing", get_briefing, methods=["GET"]),
        Route("/api/intent", post_intent, methods=["POST"]),
        Route("/api/voice/transcribe", post_voice_transcribe, methods=["POST"]),
        Route("/api/voice/pipeline", post_voice_pipeline, methods=["POST"]),
        Route("/api/voice/process", post_voice_pipeline, methods=["POST"]),
        Route("/api/panoptes/scan", post_panoptes_scan, methods=["POST"]),
        Route("/api/panoptes/graph", get_panoptes_graph, methods=["GET"]),
        Route("/api/panoptes/ingest-note", post_panoptes_ingest_note, methods=["POST"]),
        Route("/api/panoptes/topics", get_panoptes_topics, methods=["GET"]),
        Route("/api/panoptes/topics/notes", get_panoptes_topic_notes, methods=["GET"]),
        Route("/api/veritas/cases", list_veritas_cases, methods=["GET"]),
        Route("/api/veritas/cases", post_veritas_case, methods=["POST"]),
        Route("/api/veritas/evidence", post_veritas_evidence, methods=["POST"]),
        Route("/api/veritas/manifest", get_veritas_manifest, methods=["GET"]),
        Route("/api/guardian/network", get_guardian_network, methods=["GET"]),
        Route("/api/guardian/telemetry", get_guardian_telemetry, methods=["GET"]),
        Route("/api/atlas/health", get_atlas_health, methods=["GET"]),
        Route("/api/media/channels", get_media_channels, methods=["GET"]),
        Route("/api/media/current", get_media_current, methods=["GET"]),
        Route("/api/media/play", post_media_play, methods=["POST"]),
        Route("/api/media/control", post_media_control, methods=["POST"]),
        Route("/api/sanctuary/status", get_sanctuary_status_endpoint, methods=["GET"]),
        Route("/api/sanctuary/activate", post_sanctuary_activate, methods=["POST"]),
        Route("/api/sanctuary/deactivate", post_sanctuary_deactivate, methods=["POST"]),
        Route("/api/forge/draft", post_forge_draft, methods=["POST"]),
        Route("/api/forge/execute", post_forge_execute, methods=["POST"]),
        Route("/api/forge/git", get_forge_git, methods=["GET"]),
        Route("/api/visia/analyze", post_visia_analyze, methods=["POST"]),
        Route("/api/backup/create", post_backup_create, methods=["POST"]),
        Route("/api/backup/list", get_backup_list, methods=["GET"]),
        Route("/api/backup/verify", post_backup_verify, methods=["POST"]),
        Route("/api/backup/recovery-key", get_recovery_key, methods=["GET"]),
        Route("/api/morph/proposals", get_morph_proposals_endpoint, methods=["GET"]),
        Route("/api/morph/propose", post_morph_propose, methods=["POST"]),
        Route("/api/oracle/council", post_oracle_council, methods=["POST"]),
        Route("/api/lumen/surface", get_lumen_surface, methods=["GET"]),
        Route("/api/chronos/routines", get_chronos_routines, methods=["GET"]),
        Route("/api/chronos/trigger", post_chronos_trigger, methods=["POST"]),
        Route("/api/oracle/research", post_oracle_research, methods=["POST"]),
        Route("/api/aadya/priority", post_aadya_priority, methods=["POST"]),
        Route("/api/aadya/radar", get_aadya_radar, methods=["GET"]),
        Route("/api/aadya/protection", get_aadya_protection, methods=["GET"]),
        Route("/api/identity/analyze", post_identity_analyze, methods=["POST"]),
        Route("/api/atlas/summary", get_atlas_summary, methods=["GET"]),
        Route("/api/trust/signed-order", post_trust_signed_order, methods=["POST"]),
        Route("/api/trust/verify-order", post_trust_verify_order, methods=["POST"]),
        Route("/api/trust/verify-audit-chain", get_trust_verify_audit_chain, methods=["GET"]),
        Route("/api/trust/kill-switch", post_trust_kill_switch, methods=["POST"]),
        Route("/api/agents/roster", get_agents_roster, methods=["GET"]),
        Route("/api/agents/dispatch", post_agents_dispatch, methods=["POST"]),
        Route("/api/advanced/paradox", post_advanced_paradox, methods=["POST"]),
        Route("/api/advanced/ghost", get_advanced_ghost, methods=["GET"]),
        Route("/api/advanced/chronoscope", get_advanced_chronoscope, methods=["GET"]),
        Route("/api/advanced/dreamcatcher", post_advanced_dreamcatcher, methods=["POST"]),
        Route("/api/advanced/mimic", post_advanced_mimic, methods=["POST"]),
        Route("/api/advanced/signal", get_advanced_signal, methods=["GET"]),
        Route("/api/advanced/forge-mind", post_advanced_forge_mind, methods=["POST"]),
        Route("/api/advanced/nexus-room", get_advanced_nexus_room, methods=["GET"]),
        Route("/gateway/weather", get_gateway_weather, methods=["GET"]),
        Route("/api/gateway/weather", get_gateway_weather, methods=["GET"]),
        Route("/chronos/timeline", get_chronos_timeline, methods=["GET"]),
        Route("/api/chronos/timeline", get_chronos_timeline, methods=["GET"]),
        Route("/events", post_events, methods=["POST"]),
        Route("/api/events", post_events, methods=["POST"]),
        Route("/system/wal-checkpoint", post_wal_checkpoint, methods=["POST"]),
        Route("/api/system/wal-checkpoint", post_wal_checkpoint, methods=["POST"]),
        Route("/missions", get_missions_list, methods=["GET"]),
        Route("/api/missions", get_missions_list, methods=["GET"]),
        Route("/missions", post_create_mission, methods=["POST"]),
        Route("/api/missions", post_create_mission, methods=["POST"]),
        Route("/missions/claim", post_claim_mission, methods=["POST"]),
        Route("/api/missions/claim", post_claim_mission, methods=["POST"]),
        Route("/api/missions/reconcile", post_reconcile_mission, methods=["POST"]),
        Route("/api/voice/model", get_voice_model_info_endpoint, methods=["GET"]),
        Route("/ui/ptt", get_ui_ptt, methods=["GET"]),
        Route("/api/ptt/bootstrap", post_api_ptt_bootstrap, methods=["POST"]),
        Route("/api/ptt/logout", post_api_ptt_logout, methods=["POST"]),
        Route("/api/ptt/start", post_api_ptt_start, methods=["POST"]),
        Route("/api/ptt/stop", post_api_ptt_stop, methods=["POST"]),
        Route("/api/ptt/status", get_api_ptt_status, methods=["GET"]),
        WebSocketRoute("/ws", websocket_endpoint),
    ],
    middleware=middleware,
    lifespan=lifespan
)
