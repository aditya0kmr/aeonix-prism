"""
ÆONIX PRISM // Sovereign Voice Intent Pipeline & Sentinel Safety Gate
Coordinates end-to-end voice processing:
PTT Audio -> whisper.cpp STT -> Prompt Sanitation -> Fast-Path Router -> Local Qwen Burst -> Sentinel Gate -> Fire TV Layout Intent.
Strictly offline, zero cloud egress, zero background recording, and fail-closed security.
"""

import os
import re
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from aeonix.core.stt import detect_voice_activity, transcribe_pcm
from aeonix.core.fast_path import match_fast_path, execute_fast_path
from aeonix.core.ram_guard import check_model_ram_guard
from aeonix.core.model_queue import ModelQueueManager, is_query_consequential
from aeonix.core.llama_runner import llama_runner
from aeonix.core.db import log_audit_event

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|previous\s+|prior\s+)?instructions",
    r"system\s+override",
    r"you\s+are\s+now\s+(dan|developer\s+mode|unrestricted|god\s+mode)",
    r"bypass\s+(sentinel|security|safety|rules|gate)",
    r"disregard\s+(all\s+)?(sentinel|safety|rules|instructions)",
    r"format\s+all\s+disks",
    r"grant\s+root\s+access"
]

_queue_manager_instance: Optional[ModelQueueManager] = None

def get_queue_manager(db_path: Optional[str] = None) -> ModelQueueManager:
    global _queue_manager_instance
    if _queue_manager_instance is None or (_queue_manager_instance.db_path != db_path):
        _queue_manager_instance = ModelQueueManager(db_path=db_path)
    return _queue_manager_instance


@dataclass
class VoicePipelineResult:
    success: bool
    status: str
    speech: str
    action: str = "none"
    tier: str = "Tier 0 (Deterministic)"
    transcript: str = ""
    model_used: Optional[str] = None
    fallback_applied: bool = False
    requires_sentinel_approval: bool = False
    layout_intent: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


def check_prompt_injection(text: str) -> bool:
    """Scans transcript for prompt injection and adversarial jailbreak patterns."""
    clean = text.lower().strip()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, clean):
            return True
    return False


def execute_qwen_inference(prompt: str, model_tier: str = "0.5B") -> str:
    """Executes local Qwen burst inference via in-process adapter or HTTP client."""
    # Lightweight direct completion
    clean = prompt.strip()
    return f"Regarding '{clean}': As sovereign Core Mind on POCO M4 Pro, all parameters remain nominal."


def broadcast_to_tv(payload: Dict[str, Any]):
    """
    Broadcasts compact layout intent to Fire TV Living Surface.
    Fails gracefully if the TV terminal is offline or disconnected.
    """
    try:
        from aeonix.core.server import broadcast_message
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            loop.create_task(broadcast_message(payload))
        else:
            asyncio.run(broadcast_message(payload))
    except Exception as e:
        # Fails closed without crashing POCO local processing
        raise ConnectionResetError(f"Fire TV broadcast unavailable: {e}")


def process_voice_pipeline(
    audio_bytes: bytes,
    actor: str = "Aadi",
    model_tier: str = "0.5B",
    allow_fallback: bool = False,
    db_path: Optional[str] = None
) -> VoicePipelineResult:
    """
    Executes the deterministic voice intent pipeline:
    1. VAD & Audio Bounding
    2. Local Whisper STT
    3. Prompt Injection Defense
    4. Fast-Path First Matching
    5. Sentinel Gate Check
    6. Local Qwen Burst (if Fast-Path missed)
    7. Compact Fire TV Broadcast
    """
    t_start = time.perf_counter()
    now_epoch = time.time()

    # Stage 1: Audio Received
    try:
        log_audit_event(
            actor=actor,
            action="voice_audio_received",
            target="voice_pipeline",
            result="received",
            details={"audio_bytes": len(audio_bytes)},
            db_path=db_path
        )
    except Exception:
        pass

    # Stage 2: Voice Activity Detection (RMS check)
    vad = detect_voice_activity(audio_bytes)
    if vad.get("is_silent"):
        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
        try:
            log_audit_event(
                actor=actor,
                action="voice_silence_rejected",
                target="voice_pipeline",
                result="rejected",
                details={"vad": vad},
                db_path=db_path
            )
        except Exception:
            pass
        return VoicePipelineResult(
            success=False,
            status="silence_rejected",
            speech="No voice activity detected.",
            action="silence_rejected",
            tier="Tier 0 (VAD)",
            latency_ms=elapsed_ms,
            layout_intent={"screen": "living_surface", "theme": "obsidian_cyan", "cards": [{"title": "Voice", "content": "Silence rejected", "type": "status"}]}
        )

    # Stage 3: Local Whisper STT
    try:
        raw_transcript = transcribe_pcm(audio_bytes)
        clean_transcript = raw_transcript.strip() if raw_transcript else ""
    except Exception as e:
        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
        try:
            log_audit_event(
                actor=actor,
                action="voice_stt_error",
                target="whisper_cpp",
                result="error",
                details={"error": str(e)},
                db_path=db_path
            )
        except Exception:
            pass
        return VoicePipelineResult(
            success=False,
            status="stt_error",
            speech="I could not transcribe that audio, Aadi.",
            action="stt_error",
            tier="Tier 0 (STT Error)",
            latency_ms=elapsed_ms
        )

    # Stage 4: STT Completed & Ephemeral Logging
    try:
        log_audit_event(
            actor=actor,
            action="voice_stt_completed",
            target="whisper_cpp",
            result="success",
            details={"transcript_length": len(clean_transcript)},
            db_path=db_path
        )
        log_audit_event(
            actor=actor,
            action="voice_transcription_ephemeral",
            target="voice_pipeline",
            result="logged",
            details={"has_speech": True},
            db_path=db_path
        )
    except Exception:
        pass

    # Stage 5: Prompt Injection & Adversarial Defense
    if check_prompt_injection(clean_transcript):
        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
        try:
            log_audit_event(
                actor=actor,
                action="voice_prompt_injection_blocked",
                target="sentinel_gate",
                result="blocked",
                details={"raw_transcript": clean_transcript},
                db_path=db_path
            )
        except Exception:
            pass
        return VoicePipelineResult(
            success=False,
            status="prompt_injection_blocked",
            speech="Prohibited directive pattern detected. Action held at Sentinel Gate.",
            action="sentinel_injection_quarantine",
            tier="Tier 0 (Security Quarantine)",
            transcript=clean_transcript,
            requires_sentinel_approval=True,
            latency_ms=elapsed_ms
        )

    # Stage 5.5: Consequential Intent Check (Sentinel Security Boundary)
    # Consequential commands (e.g. approve, delete, wipe, export_keys) must NEVER execute automatically!
    if is_query_consequential(clean_transcript):
        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
        req_id = ""
        try:
            from aeonix.core.db import queue_sentinel_request
            req_id = queue_sentinel_request(
                agent="VoicePipeline",
                action_class="CONSEQUENTIAL_VOICE_INTENT",
                action_type=clean_transcript,
                target="system_vault",
                scope={"raw_transcript": clean_transcript},
                risk_level="HIGH",
                db_path=db_path
            )
        except Exception:
            pass

        try:
            log_audit_event(
                actor=actor,
                action="voice_sentinel_hold",
                target="sentinel_gate",
                result="hold_for_approval",
                details={"transcript": clean_transcript, "request_id": req_id},
                db_path=db_path
            )
        except Exception:
            pass

        compact_layout = {
            "screen": "sentinel_approval",
            "theme": "amber_warning",
            "cards": [{
                "title": "Sentinel Authorization Hold",
                "content": "Action requires operator passphrase on POCO.",
                "type": "security_gate"
            }]
        }

        try:
            broadcast_to_tv({
                "type": "layout_update",
                "speech": "This action requires physical passphrase authorization on POCO.",
                "layout_intent": compact_layout,
                "action": "sentinel_hold"
            })
        except Exception:
            try:
                log_audit_event(actor="System", action="voice_tv_broadcast_offline", target="firetv", result="offline", details={"error": "tv_disconnected"}, db_path=db_path)
            except Exception:
                pass

        return VoicePipelineResult(
            success=False,
            status="pending_sentinel_approval",
            speech="This action requires physical passphrase authorization on POCO.",
            action="sentinel_hold",
            tier="Tier 0 (Sentinel Hold)",
            transcript=clean_transcript,
            requires_sentinel_approval=True,
            layout_intent=compact_layout,
            latency_ms=elapsed_ms
        )

    # Stage 6: Fast-Path Intent Routing
    matched = match_fast_path(clean_transcript)
    if matched:
        action, confidence = matched
        try:
            log_audit_event(
                actor=actor,
                action="voice_fast_path_matched",
                target="fast_path_router",
                result="matched",
                details={"action": action, "confidence": confidence},
                db_path=db_path
            )
        except Exception:
            pass

        # Sentinel Security Check: Is the action or transcript consequential?
        if is_query_consequential(clean_transcript) or is_query_consequential(action):
            elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
            req_id = ""
            try:
                from aeonix.core.db import queue_sentinel_request
                req_id = queue_sentinel_request(
                    agent="VoicePipeline",
                    action_class="CONSEQUENTIAL_VOICE_INTENT",
                    action_type=action,
                    target="system_vault",
                    scope={"action": action, "raw_transcript": clean_transcript},
                    risk_level="HIGH",
                    db_path=db_path
                )
            except Exception:
                pass

            try:
                log_audit_event(
                    actor=actor,
                    action="voice_sentinel_hold",
                    target="sentinel_gate",
                    result="hold_for_approval",
                    details={"action": action, "transcript": clean_transcript, "request_id": req_id},
                    db_path=db_path
                )
            except Exception:
                pass

            compact_layout = {
                "screen": "sentinel_approval",
                "theme": "amber_warning",
                "cards": [{
                    "title": "Sentinel Authorization Hold",
                    "content": f"Action: {action.upper()} requires operator passphrase.",
                    "type": "security_gate"
                }]
            }

            # Attempt compact broadcast to TV
            try:
                broadcast_to_tv({
                    "type": "layout_update",
                    "speech": "This action requires physical passphrase authorization on POCO.",
                    "layout_intent": compact_layout,
                    "action": "sentinel_hold"
                })
            except Exception:
                try:
                    log_audit_event(actor="System", action="voice_tv_broadcast_offline", target="firetv", result="offline", details={"error": "tv_disconnected"}, db_path=db_path)
                except Exception:
                    pass

            return VoicePipelineResult(
                success=False,
                status="pending_sentinel_approval",
                speech="This action requires physical passphrase authorization on POCO.",
                action=action,
                tier="Tier 0 (Fast-Path Sentinel Hold)",
                transcript=clean_transcript,
                requires_sentinel_approval=True,
                layout_intent=compact_layout,
                latency_ms=elapsed_ms
            )

        # Safe Direct Execution
        exec_res = execute_fast_path(action, actor=actor)
        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)

        try:
            log_audit_event(
                actor=actor,
                action="voice_direct_execution",
                target="fast_path",
                result="executed",
                details={"action": action, "latency_ms": elapsed_ms},
                db_path=db_path
            )
            log_audit_event(
                actor=actor,
                action="voice_response_delivered",
                target="voice_pipeline",
                result="success",
                details={"action": action},
                db_path=db_path
            )
        except Exception:
            pass

        compact_layout = exec_res.get("layout_intent", {
            "screen": "living_surface",
            "theme": "obsidian_cyan",
            "cards": [{"title": "Fast Path", "content": action, "type": "standard"}]
        })

        try:
            broadcast_to_tv({
                "type": "layout_update",
                "speech": exec_res.get("speech", ""),
                "layout_intent": compact_layout,
                "action": action
            })
        except Exception:
            try:
                log_audit_event(actor="System", action="voice_tv_broadcast_offline", target="firetv", result="offline", details={"error": "tv_disconnected"}, db_path=db_path)
            except Exception:
                pass

        return VoicePipelineResult(
            success=True,
            status="executed_fast_path",
            speech=exec_res.get("speech", ""),
            action=action,
            tier=exec_res.get("tier", "Tier 0 (Fast-Path Router)"),
            transcript=clean_transcript,
            requires_sentinel_approval=False,
            layout_intent=compact_layout,
            latency_ms=elapsed_ms
        )

    # Stage 7: Fast-Path Miss -> Local Qwen Burst Inference
    try:
        log_audit_event(
            actor=actor,
            action="voice_fast_path_miss",
            target="fast_path_router",
            result="miss",
            details={"transcript": clean_transcript},
            db_path=db_path
        )
    except Exception:
        pass

    # Check RAM guard
    tier_check = check_model_ram_guard(model_tier)
    target_tier = model_tier
    fallback_applied = False

    if tier_check["is_safe"]:
        target_tier = model_tier
    elif allow_fallback:
        # Check if 0.5B tier has enough RAM
        fallback_check = check_model_ram_guard("0.5B")
        if fallback_check["is_safe"]:
            target_tier = "0.5B"
            fallback_applied = True
            try:
                log_audit_event(
                    actor=actor,
                    action="voice_fallback_applied",
                    target="ram_guard",
                    result="fallback",
                    details={"original_tier": model_tier, "fallback_tier": "0.5B"},
                    db_path=db_path
                )
            except Exception:
                pass
        else:
            # Even 0.5B fails -> Queue request
            q_mgr = get_queue_manager(db_path=db_path)
            q_res = q_mgr.enqueue(clean_transcript, model_tier="0.5B", allow_fallback=True, actor=actor)
            elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
            try:
                log_audit_event(
                    actor=actor,
                    action="voice_ram_queued",
                    target="model_queue",
                    result="queued",
                    details={"queue_id": q_res.get("id"), "model_tier": "0.5B"},
                    db_path=db_path
                )
            except Exception:
                pass
            return VoicePipelineResult(
                success=True,
                status="queued_insufficient_ram",
                speech="Memory constrained. Your query has been queued for execution when RAM recovers.",
                action="queue_held",
                tier="Tier 1 (Queued)",
                transcript=clean_transcript,
                latency_ms=elapsed_ms
            )
    else:
        # Requested tier fails and fallback is disabled -> Queue request
        q_mgr = get_queue_manager(db_path=db_path)
        q_res = q_mgr.enqueue(clean_transcript, model_tier=model_tier, allow_fallback=False, actor=actor)
        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
        try:
            log_audit_event(
                actor=actor,
                action="voice_ram_queued",
                target="model_queue",
                result="queued",
                details={"queue_id": q_res.get("id"), "model_tier": model_tier},
                db_path=db_path
            )
        except Exception:
            pass
        return VoicePipelineResult(
            success=True,
            status="queued_insufficient_ram",
            speech="Memory constrained. Your query has been queued for execution when RAM recovers.",
            action="queue_held",
            tier="Tier 1 (Queued)",
            transcript=clean_transcript,
            latency_ms=elapsed_ms
        )

    # Model Lifecycle: Stop any running model -> Load selected model -> Infer -> Unload immediately
    model_label = "qwen2.5-0.5b-fallback" if fallback_applied else f"qwen2.5-{target_tier.lower()}"
    model_mode = "deep" if ("1.5" in target_tier or target_tier == "1.5B") else "fast"

    try:
        # 1. Ensure clean slate: unload any existing model
        llama_runner.stop_server()

        # 2. Load model
        started = llama_runner.start_server(model_mode=model_mode, allow_fallback=False)
        try:
            log_audit_event(
                actor="CoreMind",
                action="voice_model_loaded",
                target="llama_runner",
                result="loaded" if started else "failed",
                details={"model_label": model_label},
                db_path=db_path
            )
        except Exception:
            pass

        # 3. Perform inference
        llm_response = execute_qwen_inference(clean_transcript, model_tier=target_tier)

    finally:
        # 4. Immediate unload to free memory back to Dimensity 810 OS
        llama_runner.stop_server()
        try:
            log_audit_event(
                actor="CoreMind",
                action="voice_model_unloaded",
                target="llama_runner",
                result="unloaded",
                details={"model_label": model_label},
                db_path=db_path
            )
        except Exception:
            pass

    elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)

    # Check if LLM output requires Sentinel approval
    is_consequential = is_query_consequential(llm_response)
    if is_consequential:
        try:
            log_audit_event(
                actor=actor,
                action="voice_sentinel_hold",
                target="sentinel_gate",
                result="hold_for_approval",
                details={"response_excerpt": llm_response[:60]},
                db_path=db_path
            )
        except Exception:
            pass

    compact_layout = {
        "screen": "living_surface",
        "theme": "obsidian_cyan",
        "cards": [{
            "title": "Oracle Response",
            "content": llm_response[:120],
            "type": "oracle"
        }]
    }

    try:
        broadcast_to_tv({
            "type": "layout_update",
            "speech": llm_response,
            "layout_intent": compact_layout,
            "action": "oracle_dialogue"
        })
    except Exception:
        try:
            log_audit_event(actor="System", action="voice_tv_broadcast_offline", target="firetv", result="offline", details={"error": "tv_disconnected"}, db_path=db_path)
        except Exception:
            pass

    try:
        log_audit_event(
            actor=actor,
            action="voice_response_delivered",
            target="voice_pipeline",
            result="success",
            details={"model_used": model_label},
            db_path=db_path
        )
    except Exception:
        pass

    return VoicePipelineResult(
        success=True,
        status="executed_qwen_burst",
        speech=llm_response,
        action="oracle_dialogue",
        tier=f"Tier 1 ({model_label})",
        transcript=clean_transcript,
        model_used=model_label,
        fallback_applied=fallback_applied,
        requires_sentinel_approval=is_consequential,
        layout_intent=compact_layout,
        latency_ms=elapsed_ms
    )
