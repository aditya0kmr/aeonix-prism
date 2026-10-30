import os
import json
import time
import asyncio
import base64
from typing import List, Set
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from aeonix.core.db import (
    init_database,
    get_connection,
    log_audit_event,
    queue_sentinel_request,
    resolve_sentinel_request
)
from aeonix.core.ram_guard import check_ram_guard
from aeonix.core.discovery import AeonixDiscoveryService
from aeonix.core.llama_runner import llama_runner
from aeonix.core.fast_path import match_fast_path, execute_fast_path
from aeonix.core.memory import store_memory, recall_memories, generate_daily_briefing
from aeonix.core.stt import transcribe_pcm

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
        approved = bool(body.get("approved"))
        resolver = body.get("resolver", "Aadi")

        if not req_id:
            return JSONResponse({"error": "Missing request_id"}, status_code=400)

        ok = resolve_sentinel_request(req_id, approved, resolver)
        if ok:
            # Broadcast resolution event to TV over WebSocket
            await broadcast_message({
                "type": "sentinel_resolved",
                "request_id": req_id,
                "status": "approved" if approved else "denied"
            })
            return JSONResponse({"success": True, "request_id": req_id, "approved": approved})
        else:
            return JSONResponse({"error": "Request not found or expired"}, status_code=404)
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
        await broadcast_message({
            "type": "sentinel_card",
            "request_id": req_id,
            "agent": agent,
            "action_type": action_type,
            "target": target,
            "risk_level": risk_level,
            "scope": scope
        })
        return JSONResponse({"success": True, "request_id": req_id, "risk_level": risk_level})
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

async def post_intent(request):
    """
    Two-Tier Intent Router:
    1. Fast-Path Dictionary / SequenceMatcher (<0.01s, 0% LLM load).
    2. Local Qwen2.5-0.5B Micro-Prompt (<50 tokens, burst-execution).
    """
    try:
        body = await request.json()
        user_query = body.get("query", "").strip()
        actor = body.get("actor", "Aadi")

        if not user_query:
            return JSONResponse({"error": "Empty query"}, status_code=400)

        # Tier 0: Fast-Path match
        fast_match = match_fast_path(user_query)
        if fast_match:
            action_name, confidence = fast_match
            intent_result = execute_fast_path(action_name, actor=actor)
            intent_result["confidence"] = confidence
            return JSONResponse(intent_result)

        # Tier 1: Local Qwen2.5-0.5B Micro-Prompt (<50 tokens)
        system_micro_prompt = (
            "You are AADYA, devoted personal intelligence for Aadi. "
            "Reply strictly under 35 words. Loyal, concise, sovereign."
        )
        messages = [
            {"role": "system", "content": system_micro_prompt},
            {"role": "user", "content": user_query}
        ]
        
        # Max 40 tokens generation for extreme speed and low compute
        llm_text = llama_runner.generate(messages, max_tokens=40, temperature=0.6)
        if not llm_text:
            llm_text = "I am standing by for your directive, Aadi."
        else:
            llama_runner.stop_server()

        intent_result = {
            "tier": "Tier 1 (Qwen2.5 Micro-Prompt)",
            "action": "aadya_dialogue",
            "speech": llm_text,
            "layout_intent": {
                "screen": "living_surface",
                "theme": "obsidian_cyan",
                "cards": [{"title": "AADYA", "content": llm_text, "type": "dialogue"}]
            }
        }
        return JSONResponse(intent_result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

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

async def post_voice_transcribe(request):
    """Processes uploaded raw PCM or WAV audio and returns offline transcription."""
    try:
        body = await request.body()
        if not body:
            return JSONResponse({"error": "Empty audio payload"}, status_code=400)
        text = transcribe_pcm(body)
        log_audit_event("REST_API", "voice_transcribed", "whisper_tiny", "ok", {"query": text})
        return JSONResponse({"success": True, "transcription": text})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    log_audit_event("GLASS_TERMINAL", "connect", "websocket", "ok", {})
    
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
            "device": "Fire TV Stick Lite",
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
                    approved = msg.get("approved", False)
                    resolve_sentinel_request(req_id, approved, "FireTV_Remote")
                    await websocket.send_text(json.dumps({
                        "type": "sentinel_resolved",
                        "request_id": req_id,
                        "status": "approved" if approved else "denied"
                    }))
                elif msg_type == "audio_start":
                    audio_buffer = bytearray()
                    await websocket.send_text(json.dumps({"type": "audio_status", "status": "recording"}))
                elif msg_type == "audio_chunk":
                    chunk_b64 = msg.get("data", "")
                    if chunk_b64:
                        audio_buffer.extend(base64.b64decode(chunk_b64))
                elif msg_type == "audio_end":
                    await websocket.send_text(json.dumps({"type": "audio_status", "status": "processing"}))
                    if audio_buffer:
                        query = transcribe_pcm(bytes(audio_buffer))
                        log_audit_event("GLASS_TERMINAL", "voice_command", "whisper_tiny", "ok", {"query": query})
                        
                        # Fast-Path check first (<0.05ms)
                        fp = match_fast_path(query)
                        if fp:
                            reply_text = fp.get("response", "")
                            intent_type = fp.get("intent", "fast_path")
                        else:
                            # Micro-prompt Qwen2.5-0.5B inference
                            messages = [
                                {"role": "system", "content": "You are AADYA, sovereign AI for Aadi. Answer concisely in under 30 words."},
                                {"role": "user", "content": query}
                            ]
                            reply_text = llama_runner.generate(messages, mode="fast", max_tokens=60) or "Understood, Aadi."
                            intent_type = "deep_query"
                        
                        await websocket.send_text(json.dumps({
                            "type": "voice_reply",
                            "query": query,
                            "intent": intent_type,
                            "reply": reply_text
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

app = Starlette(
    routes=[
        Route("/api/status", get_status, methods=["GET"]),
        Route("/api/sentinel/pending", list_sentinel_pending, methods=["GET"]),
        Route("/api/sentinel/create", create_sentinel, methods=["POST"]),
        Route("/api/sentinel/resolve", resolve_sentinel, methods=["POST"]),
        Route("/api/memory/remember", post_memory, methods=["POST"]),
        Route("/api/memory/recall", get_memories, methods=["GET"]),
        Route("/api/briefing", get_briefing, methods=["GET"]),
        Route("/api/intent", post_intent, methods=["POST"]),
        Route("/api/voice/transcribe", post_voice_transcribe, methods=["POST"]),
        WebSocketRoute("/ws", websocket_endpoint),
    ],
    lifespan=lifespan
)
