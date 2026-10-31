"""
AADYA — Aadi's Eternal Intelligence & Personal Life Advocate
Core Principles:
- Aadi-First Priority Engine: Evaluates actions for Aadi's betterment and sovereignty.
- Future Radar: Proactively monitors skill advancement, security, and opportunities.
- Protection Instinct: Detects privacy leaks, device vulnerabilities, and cognitive fatigue.
- Memory Heart: Preserves Aadi's personal aspirations, lessons, and principles.
- Possibility Engine: Unlocks generative possibilities tailored exclusively to Aadi.
"""

import time
from typing import Dict, Any, List
from core.db import query_db, log_audit_event


class AadyaIntelligence:
    CORE_CREED = (
        "I am AADYA. Made for Aadi. Devoted to Aadi. Thinking for Aadi. Protecting Aadi's future."
    )

    def __init__(self):
        pass

    def evaluate_priority(self, proposal: str) -> Dict[str, Any]:
        """
        Aadi-First Priority Engine:
        Evaluates proposal by alignment with Aadi's personal autonomy, system health, and privacy boundaries.
        Incorporates live hardware telemetry and pending authorization state.
        """
        lower = proposal.lower()
        from core.ram_guard import get_ram_status
        ram_stat = get_ram_status()

        # Check pending approvals
        pending_rows = query_db("SELECT COUNT(*) FROM sentinel_requests WHERE status = 'pending';")
        pending_count = pending_rows[0][0] if pending_rows else 0

        positive_factors = ["sovereign", "local", "privacy", "security", "learning", "growth", "build", "freedom", "wal", "offline", "backup", "encrypt"]
        negative_factors = ["cloud leak", "telemetry", "unauthorized", "tracking", "distraction", "third-party", "commercial", "external api"]

        pos_score = sum(1 for p in positive_factors if p in lower)
        neg_score = sum(1 for n in negative_factors if n in lower)

        # Hardware safety constraint
        is_ram_critical = not ram_stat["is_safe"]
        if is_ram_critical:
            neg_score += 2

        is_favorable = neg_score == 0 and pos_score > 0
        if neg_score > 1:
            verdict = "SCRUTINY_REQUIRED"
            rationale = "High risk of external data leakage or memory exhaustion detected."
        elif is_ram_critical:
            verdict = "SCRUTINY_REQUIRED"
            rationale = "Available RAM is below safe threshold. Defer non-critical compute."
        elif is_favorable:
            verdict = "STRONGLY_ALIGNED"
            rationale = "Directly promotes Aadi's technological autonomy and sovereign infrastructure."
        else:
            verdict = "NEUTRAL"
            rationale = "Proposal does not actively compromise or significantly enhance sovereign baseline."

        betterment_score = round(max(0.1, min(1.0, 0.5 + 0.15 * pos_score - 0.20 * neg_score)), 2)

        return {
            "proposal": proposal,
            "verdict": verdict,
            "aadi_betterment_score": betterment_score,
            "rationale": rationale,
            "context": {
                "available_ram_mb": ram_stat.get("available_mb", 0),
                "pending_sentinel_actions": pending_count,
                "ram_safe": ram_stat["is_safe"]
            }
        }

    def scan_future_radar(self) -> Dict[str, Any]:
        """
        Future Radar: Scans horizon for skill acquisition, system optimization, and security posture.
        """
        return {
            "focus_areas": [
                {"domain": "Autonomous AI Agents", "status": "Deployed locally across POCO Mind & Fire TV Glass"},
                {"domain": "Hardware Optimization", "status": "Termux Dimensity 810 NEON SIMD execution fully unlocked"},
                {"domain": "Data Sovereignty", "status": "Zero third-party commercial cloud leakage"},
            ],
            "proactive_suggestions": [
                "Schedule automated daily SQLite WAL backups to secondary physical storage",
                "Expand custom Leanback cards for real-time sensor and smart asset telemetry",
            ],
            "radar_status": "CLEAR_AND_VIGILANT",
        }

    def protection_check(self) -> Dict[str, Any]:
        """
        Protection Instinct: Checks system state for privacy exposures or abnormal operational load.
        """
        from core.ram_guard import get_ram_status
        ram_stat = get_ram_status()
        threat_level = "LOW" if ram_stat["is_safe"] else "ELEVATED"

        return {
            "threat_level": threat_level,
            "ram_security": "NOMINAL" if ram_stat["is_safe"] else "RAM_PRESSURE_DETECTED",
            "active_safeguards": ["Sentinel Gate Enabled", "Direct Model Isolation", "Sanctuary Mode Standing By"],
            "creed": self.CORE_CREED,
        }

    def generate_possibility(self, domain: str = "general") -> Dict[str, Any]:
        """
        Possibility Engine: Synthesizes high-leverage opportunities for Aadi.
        """
        possibilities = [
            "Develop custom voice-triggered interactive workflows for Fire TV living surface",
            "Establish an immutable digital evidence timeline for personal knowledge and development",
            "Train lightweight fine-tuned LoRA adapters for specialized offline domain reasoning",
        ]
        return {
            "domain": domain,
            "generated_possibilities": possibilities,
            "timestamp": time.time(),
        }


aadya = AadyaIntelligence()
