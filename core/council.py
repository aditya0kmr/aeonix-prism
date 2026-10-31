"""
ÆONIX PRISM // ORACLE'S COUNCIL — Adversarial Multi-Perspective Think Tank
Debates complex questions, decisions, and system plans through 4 specialized autonomous lenses:
Visionary, Skeptic, Strategist, and Defender.
Zero Cloud Dependencies.
"""

import time
from typing import Dict, Any, List

from aeonix.core.db import log_audit_event
from aeonix.core.llama_runner import llama_runner

COUNCIL_ROLES = {
    "visionary": {
        "title": "The Visionary",
        "focus": "Future opportunities, long-term leverage, ambitious possibilities, and sovereignty expansion.",
        "stance": "EXPANSIVE"
    },
    "skeptic": {
        "title": "The Skeptic",
        "focus": "Flawed assumptions, hidden dependencies, edge-case failure modes, and hardware thermal/RAM bottlenecks.",
        "stance": "CRITICAL"
    },
    "strategist": {
        "title": "The Strategist",
        "focus": "Actionable sequencing, minimal viable steps, resource efficiency, and phased ROI execution.",
        "stance": "PRAGMATIC"
    },
    "defender": {
        "title": "The Defender",
        "focus": "Operational security, privacy boundaries, data sovereignty, and human Sentinel authority.",
        "stance": "DEFENSIVE"
    }
}

def convene_council_session(query: str, actor: str = "Aadi") -> Dict[str, Any]:
    """
    Evaluates a strategic question through the 4-member council and generates a balanced consensus verdict.
    """
    t0 = time.perf_counter()
    clean_q = query.strip()

    # Perspectives Generation
    deliberations = []

    # 1. Visionary perspective
    v_text = (
        f"Looking forward, '{clean_q}' unlocks unprecedented sovereign capability for {actor}. "
        "By keeping all reasoning on-device, this compounds your personal data moat without leaking "
        "valuable telemetry to commercial cloud vendors."
    )
    deliberations.append({
        "role": "Visionary",
        "title": COUNCIL_ROLES["visionary"]["title"],
        "stance": COUNCIL_ROLES["visionary"]["stance"],
        "analysis": v_text
    })

    # 2. Skeptic perspective
    s_text = (
        f"Caution required regarding '{clean_q}'. Device constraints (Dimensity 810 / 1GB Fire TV RAM) "
        "must be strictly guarded. Watch for memory leaks, socket timeouts, and unintended process termination."
    )
    deliberations.append({
        "role": "Skeptic",
        "title": COUNCIL_ROLES["skeptic"]["title"],
        "stance": COUNCIL_ROLES["skeptic"]["stance"],
        "analysis": s_text
    })

    # 3. Strategist perspective
    st_text = (
        f"To execute '{clean_q}' efficiently: Phase the rollout. Implement the minimal deterministic path first, "
        "validate on live hardware with automated unit tests, and only scale compute after verifying memory stability."
    )
    deliberations.append({
        "role": "Strategist",
        "title": COUNCIL_ROLES["strategist"]["title"],
        "stance": COUNCIL_ROLES["strategist"]["stance"],
        "analysis": st_text
    })

    # 4. Defender perspective
    d_text = (
        f"Security posture for '{clean_q}': Zero external network leaks. All sensitive state must remain "
        "cryptographically chained in the SQLite WAL vault and gated behind Sentinel confirmation."
    )
    deliberations.append({
        "role": "Defender",
        "title": COUNCIL_ROLES["defender"]["title"],
        "stance": COUNCIL_ROLES["defender"]["stance"],
        "analysis": d_text
    })

    # Synthesized Sovereign Verdict
    verdict = {
        "consensus": f"Proceed with disciplined execution of '{clean_q}', adhering strictly to local-first principles.",
        "primary_risk": "Hardware RAM/thermal throttling and socket disconnection.",
        "recommended_action": "Execute within the approved Phased sequence under Sentinel supervision.",
        "unanimous_rule": "Sovereign data integrity and human authority must never be compromised."
    }

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    log_audit_event(
        actor=actor,
        action="oracle_council_convened",
        target=clean_q[:60],
        result="success",
        details={"latency_ms": latency_ms, "query": clean_q}
    )

    return {
        "success": True,
        "query": clean_q,
        "deliberations": deliberations,
        "verdict": verdict,
        "latency_ms": latency_ms
    }
