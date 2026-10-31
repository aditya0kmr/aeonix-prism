"""
ÆONIX PRISM // Sanctuary Mode — Autonomous Privacy Lockdown
Isolates sovereign infrastructure, sets Core Mind to privacy defense posture,
drops microphone ingestion, blocks external intelligence tools, and halts background LLMs.
Persisted in database to survive process restarts.
"""

import os
import time
from typing import Dict, Any, Optional

from aeonix.core.db import get_connection, log_audit_event, get_system_state, set_system_state
from aeonix.core.llama_runner import llama_runner

def is_sanctuary_active() -> bool:
    """Returns True if the system is currently under persistent Sanctuary Lockdown."""
    state = get_system_state("sanctuary_mode", {"is_active": False})
    if isinstance(state, dict):
        return bool(state.get("is_active", False))
    return bool(state)

def get_sanctuary_status() -> Dict[str, Any]:
    """Returns full status of Sanctuary posture."""
    state = get_system_state("sanctuary_mode", {
        "is_active": False,
        "engaged_at": None,
        "engaged_by": None,
        "reason": None
    })
    if not isinstance(state, dict):
        state = {"is_active": bool(state), "engaged_at": None, "engaged_by": None, "reason": None}
    return state

def engage_sanctuary(actor: str = "Aadi", actor_role: str = "POCO_CORE", reason: str = "Operator Directive") -> Dict[str, Any]:
    """Engages persistent Sanctuary Lockdown posture."""
    now = time.time()
    state = {
        "is_active": True,
        "engaged_at": now,
        "engaged_by": actor,
        "actor_role": actor_role,
        "reason": reason
    }
    set_system_state("sanctuary_mode", state)

    # 1. Immediately terminate any resident LLM process
    try:
        llama_runner.stop_server()
    except Exception:
        pass

    # 2. Log cryptographic audit event
    log_audit_event(
        actor=actor,
        action="sanctuary_lockdown_engaged",
        target="sovereign_perimeter",
        result="success",
        details={"reason": reason, "timestamp": now, "actor_role": actor_role}
    )

    return {
        "status": "engaged",
        "is_active": True,
        "theme": "obsidian_crimson",
        "headline": "SANCTUARY ACTIVE // PRIVACY POSTURE",
        "subline": "Audio ingestion disabled on Core Mind. External OSINT tools blocked. Local vault in privacy posture.",
        "engaged_at": now
    }

def release_sanctuary(actor: str = "Aadi", actor_role: str = "POCO_CORE") -> Dict[str, Any]:
    """Releases Sanctuary Lockdown and returns system to normal living surface."""
    now = time.time()
    state = {
        "is_active": False,
        "engaged_at": None,
        "engaged_by": None,
        "actor_role": None,
        "reason": None
    }
    set_system_state("sanctuary_mode", state)

    log_audit_event(
        actor=actor,
        action="sanctuary_lockdown_released",
        target="sovereign_perimeter",
        result="success",
        details={"timestamp": now, "actor_role": actor_role}
    )

    return {
        "status": "released",
        "is_active": False,
        "theme": "obsidian_cyan",
        "headline": "SANCTUARY RELEASED",
        "subline": "Standard sovereign living surface resumed. All subsystems nominal.",
        "released_at": now
    }
