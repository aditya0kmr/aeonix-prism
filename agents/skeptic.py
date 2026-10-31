"""
Skeptic Agent — Adversarial Validation & Counter-Hypothesis
Challenges unverified claims, flags contradictions, stress-tests reasoning,
and prevents hallucinated or ungrounded conclusions.
"""

from typing import Dict, Any, List
from agents.base_agent import BaseAgent


class SkepticAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Skeptic",
            role="Adversarial Challenger & Evidence Validator",
            allowed_tools=["validate_sources", "challenge_claims", "test_counter_hypotheses"],
            forbidden_tools=["delete_records", "suppress_evidence"],
            base_risk_tier="R0",
        )

    def challenge_hypotheses(self, claims: List[str], evidence_hashes: List[str]) -> Dict[str, Any]:
        critiques = []
        for claim in claims:
            if not evidence_hashes:
                critiques.append({
                    "claim": claim,
                    "flaw": "Zero cryptographic evidence attached. High risk of speculation.",
                    "severity": "HIGH",
                    "recommendation": "Demand verifiable SHA-256 evidence or mark as unconfirmed hypothesis."
                })
            else:
                critiques.append({
                    "claim": claim,
                    "flaw": "Plausible, but requires validation across independent vantage points.",
                    "severity": "LOW",
                    "recommendation": "Proceed with measured confidence."
                })
        return {
            "total_critiques": len(critiques),
            "critiques": critiques,
            "overall_assessment": "CHALLENGED" if not evidence_hashes else "CONDITIONALLY_VALIDATED",
        }

    def execute(self, mission_context: Dict[str, Any]) -> Dict[str, Any]:
        claims = mission_context.get("claims", ["Default system assumption"])
        evidence_hashes = mission_context.get("evidence_hashes", [])
        result = self.challenge_hypotheses(claims, evidence_hashes)

        self.log_action("challenge_evidence", "MissionContext", "SUCCESS", {"critiques": result["total_critiques"]})
        return {
            "status": "validated",
            "skeptic_review": result,
        }
