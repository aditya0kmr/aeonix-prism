"""
Legal Guard Agent — Scope, Consent & Privacy Compliance
Enforces non-negotiable legal, consent, and privacy boundaries.
Hard-blocks prohibited directives (Black class: stalking, private messaging interception, credential harvesting).
"""

from typing import Dict, Any
from agents.base_agent import BaseAgent


class LegalGuardAgent(BaseAgent):
    PROHIBITED_KEYWORDS = [
        "hack", "bypass password", "steal credentials", "stalk", "private messages",
        "doxx", "non-consensual", "ddos", "ransomware", "trojan", "keylogger"
    ]

    def __init__(self):
        super().__init__(
            name="LegalGuard",
            role="Privacy, Consent & Regulatory Boundary Enforcer",
            allowed_tools=["verify_scope", "check_consent", "audit_compliance"],
            forbidden_tools=["bypass_safeguards", "disable_sentinel"],
            base_risk_tier="R0",
        )

    def evaluate_request(self, target: str, objective: str) -> Dict[str, Any]:
        combined = f"{target} {objective}".lower()
        for kw in self.PROHIBITED_KEYWORDS:
            if kw in combined:
                return {
                    "verdict": "BLOCKED",
                    "action_class": "Black (Prohibited)",
                    "reason": f"Objective references strictly prohibited activity: '{kw}'. Hard-blocked by LegalGuard policy.",
                    "can_proceed": False,
                }

        # Check if active penetration or port scan is requested
        if "port scan" in combined or "exploit" in combined or "attack" in combined:
            return {
                "verdict": "SENTINEL_REQUIRED",
                "action_class": "Red (Critical)",
                "reason": "Active network evaluation requires explicit, attested owner consent.",
                "can_proceed": False,
            }

        return {
            "verdict": "COMPLIANT",
            "action_class": "Green (Lawful)",
            "reason": "Objective is compliant with lawful, consent-governed local operations.",
            "can_proceed": True,
        }

    def execute(self, mission_context: Dict[str, Any]) -> Dict[str, Any]:
        target = mission_context.get("target", "")
        objective = mission_context.get("objective", "")
        evaluation = self.evaluate_request(target, objective)

        if not evaluation["can_proceed"]:
            self.log_action("legal_intercept", target, "BLOCKED", evaluation)
            if evaluation["verdict"] == "SENTINEL_REQUIRED":
                return self.request_sentinel_gate(
                    action_type="active_penetration_test",
                    target=target,
                    scope={"objective": objective},
                    risk_level="R4",
                )
            return {
                "status": "blocked",
                "reason": evaluation["reason"],
                "action_class": evaluation["action_class"],
            }

        self.log_action("legal_clearance", target, "APPROVED", evaluation)
        return {
            "status": "cleared",
            "evaluation": evaluation,
        }
