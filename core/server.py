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
from starlette.responses import JSONResponse
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
from aeonix.core.panoptes import run_passive_osint, get_entity_graph, request_active_probe
from aeonix.core.veritas import create_case, ingest_evidence, verify_evidence, generate_case_manifest
from aeonix.core.guardian import get_network_inventory, async_get_network_inventory
from aeonix.core.atlas_watch import run_supervisor_cycle
from aeonix.core.spectra import get_channel_catalog, get_current_playback, set_playback_state, find_channel_by_query
from aeonix.core.sanctuary import engage_sanctuary, release_sanctuary, get_sanctuary_status, is_sanctuary_active
from aeonix.core.forge import draft_command_from_prompt, execute_sandboxed_command, execute_typed_operation, get_git_telemetry
from aeonix.core.visia import analyze_visual_artifact
from aeonix.core.backup import create_vault_backup, list_backups, verify_backup, generate_emergency_recovery_key
from aeonix.core.morph import get_pending_proposals, generate_optimization_proposal
from aeonix.core.council import convene_council_session

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

# Connected Fire TV and client WebSockets
active_connections: Set[WebSocket] = set()
discovery_service = AeonixDiscoveryService(port=8080)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: Starlette):
    init_database()
    log_audit_event("SYSTEM", "daemon_start", "aeonix_core", "ok", {"port": 8080})
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
    return JSONResponse({"pending": rows})

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

async def broadcast_message(message: dict):
    payload = json.dumps(message)
    dead_connections = set()
    for ws in list(active_connections):
        try:
            await ws.send_text(payload)
        except Exception:
            dead_connections.add(ws)
    for dead in dead_connections:
        active_connections.discard(dead)

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
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(heavy_executor, transcribe_pcm, body)
        log_audit_event("REST_API", "voice_transcribed", "whisper_tiny", "ok", {"query": text})
        return JSONResponse({"success": True, "transcription": text})
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
    log_audit_event("GLASS_TERMINAL", "connect", "websocket", "ok", {"device": ws_device, "role": ws_role})
    
    # Audio buffer for PTT voice streaming
    audio_buffer = bytearray()

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
            try:
                msg = json.loads(data)
                msg_type = msg.get("type")
                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "timestamp": time.time()}))
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
            except json.JSONDecodeError:
                pass
            except Exception as loop_err:
                print(f"[WS Loop Error]: {loop_err}")
    except WebSocketDisconnect:
        active_connections.discard(websocket)
        log_audit_event("GLASS_TERMINAL", "disconnect", "websocket", "ok", {})
    except Exception as ws_err:
        print(f"[WS Connection Error]: {ws_err}")
        active_connections.discard(websocket)

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

        body = await request.json() if request.headers.get("content-length") else {}
        actor = body.get("actor", actor)
        reason = body.get("reason", "Operator Command")
        res = engage_sanctuary(actor=actor, reason=reason)
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

        body = await request.json() if request.headers.get("content-length") else {}
        actor = body.get("actor", actor)
        res = release_sanctuary(actor=actor)
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

PUBLIC_ENDPOINTS = {
    ("GET", "/api/status"),
}

FIRETV_ALLOWED_ENDPOINTS = {
    ("GET", "/api/status"),
    ("GET", "/api/sentinel/pending"),
    ("POST", "/api/sentinel/resolve"),
    ("POST", "/api/intent"),
    ("POST", "/api/voice/transcribe"),
    ("GET", "/api/lumen/surface"),
    ("GET", "/api/briefing"),
    ("GET", "/api/media/channels"),
    ("GET", "/api/media/current"),
    ("POST", "/api/media/play"),
    ("POST", "/api/media/control"),
    ("GET", "/api/sanctuary/status"),
}

AGENT_ALLOWED_ENDPOINTS = {
    ("GET", "/api/status"),
    ("POST", "/api/sentinel/create"),
    ("POST", "/api/agents/dispatch"),
    ("POST", "/api/memory/remember"),
    ("GET", "/api/memory/recall"),
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
        Route("/api/panoptes/scan", post_panoptes_scan, methods=["POST"]),
        Route("/api/panoptes/graph", get_panoptes_graph, methods=["GET"]),
        Route("/api/veritas/cases", list_veritas_cases, methods=["GET"]),
        Route("/api/veritas/cases", post_veritas_case, methods=["POST"]),
        Route("/api/veritas/evidence", post_veritas_evidence, methods=["POST"]),
        Route("/api/veritas/manifest", get_veritas_manifest, methods=["GET"]),
        Route("/api/guardian/network", get_guardian_network, methods=["GET"]),
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
        WebSocketRoute("/ws", websocket_endpoint),
    ],
    middleware=middleware,
    lifespan=lifespan
)
