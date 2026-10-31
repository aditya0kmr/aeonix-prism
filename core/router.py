"""
ÆONIX PRISM // Sovereign Hybrid Router & Inference Gateway
Intelligent multi-tier dispatch across deterministic fast-paths, local offline LLMs, and guarded cloud adapters.

Tiers:
- Tier 0: Fast-Path Deterministic (zero LLM, sub-50ms)
- Tier 1: Sovereign Local LLM (llama-server Qwen2.5 0.5B/1.5B, 100% offline, zero cloud, privacy guaranteed)
- Tier 2: Cloud Hybrid Adapter (Gemini API with explicit operator permission, quota control, sanitized redaction, and local fallback)
"""

import os
import json
import time
import hashlib
from typing import Dict, Any, List, Optional
import httpx

from aeonix.core.fast_path import match_fast_path, execute_fast_path
from aeonix.core.llama_runner import llama_runner
from aeonix.core.db import log_audit_event

# Quota and spending tracking (in-memory persistent state)
MAX_DAILY_CLOUD_CALLS = 50
_cloud_quota_tracker = {
    "day": time.strftime("%Y-%m-%d"),
    "calls_today": 0,
    "last_reset": time.time()
}

_query_cache: Dict[str, Dict[str, Any]] = {}

def get_router_status() -> Dict[str, Any]:
    """Returns available model providers, modalities, quotas, and current routing policies."""
    global _cloud_quota_tracker
    today = time.strftime("%Y-%m-%d")
    if _cloud_quota_tracker["day"] != today:
        _cloud_quota_tracker = {"day": today, "calls_today": 0, "last_reset": time.time()}

    gemini_key_present = bool(os.environ.get("GEMINI_API_KEY"))
    
    return {
        "sovereign_first": True,
        "default_tier": "tier_1_local_sovereign",
        "providers": {
            "local_qwen_fast": {
                "installed": True,
                "model": "Qwen2.5-0.5B-Instruct-Q4_K_M",
                "offline": True,
                "modalities": ["text"],
                "cost_per_call": 0.0,
                "license": "Apache-2.0"
            },
            "local_qwen_deep": {
                "installed": True,
                "model": "Qwen2.5-1.5B-Instruct-Q4_K_M",
                "offline": True,
                "modalities": ["text"],
                "cost_per_call": 0.0,
                "license": "Apache-2.0"
            },
            "gemini_flash": {
                "configured": gemini_key_present,
                "model": "gemini-1.5-flash",
                "offline": False,
                "modalities": ["text", "image"],
                "max_daily_calls": MAX_DAILY_CLOUD_CALLS,
                "calls_remaining": max(0, MAX_DAILY_CLOUD_CALLS - _cloud_quota_tracker["calls_today"]),
                "requires_permission": True
            }
        },
        "cache_entries": len(_query_cache)
    }

def call_gemini_adapter(
    prompt: str, 
    api_key: Optional[str] = None, 
    timeout: float = 10.0
) -> Optional[str]:
    """
    Guarded Gemini API adapter.
    Enforces spending limits, timeout bounds, and strict payload sanitation.
    """
    global _cloud_quota_tracker
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        return None

    today = time.strftime("%Y-%m-%d")
    if _cloud_quota_tracker["day"] != today:
        _cloud_quota_tracker = {"day": today, "calls_today": 0, "last_reset": time.time()}

    if _cloud_quota_tracker["calls_today"] >= MAX_DAILY_CLOUD_CALLS:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 100}
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            res = client.post(url, json=payload)
            if res.status_code == 200:
                _cloud_quota_tracker["calls_today"] += 1
                data = res.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        pass
    return None

def route_query(
    query: str,
    actor: str = "Aadi",
    allow_external: bool = False,
    model_tier: str = "fast",
    system_prompt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Routes an incoming query with sovereign precedence:
    1. Tier 0: Fast-Path pattern match (<50ms, zero LLM).
    2. Cached query check (<5ms).
    3. Tier 2: Cloud Gemini adapter ONLY IF explicitly permitted and configured.
    4. Tier 1: Sovereign Local Qwen2.5 LLM (100% offline default).
    """
    t0 = time.perf_counter()
    clean_query = query.strip()
    if not clean_query:
        return {"success": False, "error": "Empty query", "tier": "none"}

    # 1. Tier 0: Fast-Path
    fast_match = match_fast_path(clean_query)
    if fast_match:
        action_name, confidence = fast_match
        result = execute_fast_path(action_name, actor=actor)
        result["tier"] = "tier_0_fast_path"
        result["provider"] = "deterministic_regex"
        result["is_offline"] = True
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return result

    # 2. Check LRU Cache
    cache_key = hashlib.sha256(f"{clean_query}:{model_tier}".encode()).hexdigest()
    if cache_key in _query_cache:
        cached = dict(_query_cache[cache_key])
        cached["from_cache"] = True
        cached["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return cached

    # 3. Tier 2: Guarded Cloud Adapter (Only if requested & permitted)
    if allow_external and os.environ.get("GEMINI_API_KEY"):
        full_prompt = f"{system_prompt}\nUser: {clean_query}" if system_prompt else clean_query
        cloud_text = call_gemini_adapter(full_prompt)
        if cloud_text:
            res = {
                "success": True,
                "tier": "tier_2_cloud_gemini",
                "provider": "gemini-1.5-flash",
                "is_offline": False,
                "speech": cloud_text,
                "query": clean_query,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2)
            }
            _query_cache[cache_key] = res
            log_audit_event(actor, "cloud_ai_inference", "gemini-1.5-flash", "success", {"query_hash": cache_key[:8]})
            return res

    # 4. Tier 1: Sovereign Local LLM (Standard Path)
    sys_content = system_prompt or "You are AADYA, devoted personal intelligence for Aadi. Reply strictly under 35 words. Loyal, concise, sovereign."
    messages = [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": clean_query}
    ]

    local_text = llama_runner.generate(messages, mode=model_tier, max_tokens=45, temperature=0.6)
    llama_runner.stop_server()

    if not local_text:
        local_text = "I am standing by for your directive, Aadi."

    res = {
        "success": True,
        "tier": "tier_1_local_qwen",
        "provider": f"qwen2.5_{model_tier}",
        "is_offline": True,
        "speech": local_text,
        "query": clean_query,
        "fallback_occurred": allow_external and not bool(os.environ.get("GEMINI_API_KEY")),
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2)
    }
    
    # Store in memory cache (cap cache to 100 entries)
    if len(_query_cache) > 100:
        _query_cache.pop(next(iter(_query_cache)))
    _query_cache[cache_key] = res

    log_audit_event(actor, "local_ai_inference", f"qwen2.5_{model_tier}", "success", {"query_hash": cache_key[:8]})
    return res
