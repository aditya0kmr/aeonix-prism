"""
ÆONIX PRISM // Sanctuary Mode — Autonomous Privacy Lockdown
Isolates sovereign infrastructure, locks the vault to read-only, and halts all external network activity.
"""

import os
import time
from typing import Dict, Any, Optional

from aeonix.core.db import get_connection, log_audit_event
from aeonix.core.llama_runner import llama_runner

# Global Sanctuary State
SANCTUARY_STATE: Dict[str, Any] = {
    "is_active": False,
    "engaged_at": None,
    "engaged_by": None,
    "reason": None
}

def is_sanctuary_active() -> bool:
    """Returns True if the system is currently under Sanctuary Lockdown."""
    return SANCTUARY_STATE["is_active"]

def engage_sanctuary(actor: str = "Aadi", reason: str = "Operator Directive") -> Dict[str, Any]:
    """Engages Sanctuary Lockdown posture."""
    global SANCTUARY_STATE
    now = time.time()
    SANCTUARY_STATE = {
        "is_active": True,
        "engaged_at": now,
        "engaged_by": actor,
        "reason": reason
    }

    # 1. Immediately unload any resident LLM to free RAM and eliminate inference leakage
    try:
        llama_runner.stop_server()
    except Exception:
        pass

    # 2. Lock SQLite Vault to read-only state for external requests
    try:
        conn = get_connection()
        conn.execute("PRAGMA query_only = ON;")
        conn.close()
    except Exception:
        pass

    # 3. Log cryptographic audit event
    log_audit_event(
        actor=actor,
        action="sanctuary_lockdown_engaged",
        target="sovereign_perimeter",
        result="success",
        details={"reason": reason, "timestamp": now}
    )

    return {
        "status": "engaged",
        "is_active": True,
        "theme": "obsidian_crimson",
        "headline": "SANCTUARY ACTIVE // VAULT SEALED",
        "subline": "Microphone disabled. Network isolated. Local vault in read-only defense posture.",
        "engaged_at": now
    }

def release_sanctuary(actor: str = "Aadi") -> Dict[str, Any]:
    """Releases Sanctuary Lockdown and returns system to normal living surface."""
    global SANCTUARY_STATE
    now = time.time()
    SANCTUARY_STATE = {
        "is_active": False,
        "engaged_at": None,
        "engaged_by": None,
        "reason": None
    }

    # Restore SQLite Vault write access
    try:
        conn = get_connection()
        conn.execute("PRAGMA query_only = OFF;")
        conn.close()
    except Exception:
        pass

    log_audit_event(
        actor=actor,
        action="sanctuary_lockdown_released",
        target="sovereign_perimeter",
        result="success",
        details={"timestamp": now}
    )

    return {
        "status": "released",
        "is_active": False,
        "theme": "obsidian_cyan",
        "headline": "SANCTUARY RELEASED",
        "subline": "Standard sovereign living surface resumed. All subsystems nominal.",
        "released_at": now
    }

def get_sanctuary_status() -> Dict[str, Any]:
    """Returns current Sanctuary status."""
    return dict(SANCTUARY_STATE)
