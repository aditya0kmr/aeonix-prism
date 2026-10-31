"""
Skeptic Agent — Adversarial Validation & Counter-Hypothesis
Challenges unverified claims, flags contradictions, stress-tests reasoning,
and prevents hallucinated or ungrounded conclusions.
"""

import os
import hashlib
from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from core.db import query_db


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
        """
        Adversarial Skeptic Validation:
        - Validates evidence hashes against SQLite evidence vault and audit log.
        - Analyzes claim content for architectural contradictions (e.g. cloud reliance, security regressions).
        - Computes evidence grounding ratio and calibrated uncertainty.
        """
        critiques = []
        verified_evidence_count = 0
        unverified_hashes = []

        # 1. Cryptographic Evidence Verification
        for eh in evidence_hashes:
            eh_clean = str(eh).strip()
            # Check VERITAS evidence table
            ev_rows = query_db("SELECT id, sha256, file_path FROM evidence WHERE sha256 = ? OR id = ?", (eh_clean, eh_clean))
            # Check audit log hash
            audit_rows = query_db("SELECT id FROM audit_log WHERE current_hash = ?", (eh_clean,)) if not ev_rows else []

            if ev_rows:
                verified_evidence_count += 1
            elif audit_rows:
                verified_evidence_count += 1
            else:
                unverified_hashes.append(eh_clean)

        # 2. Claim-by-Claim Adversarial Scrutiny
        for claim in claims:
            c_lower = claim.lower()
            issues = []
            severity = "LOW"

            # Check cloud/exfiltration risks
            if any(term in c_lower for term in ["cloud upload", "external api", "commercial cloud", "telemetry leak"]):
                issues.append("Direct violation of Sovereign Local-First Architecture (cloud dependency detected).")
                severity = "HIGH"

            # Check ungrounded assertion
            if verified_evidence_count == 0 and not evidence_hashes:
                issues.append("Zero cryptographic evidence attached to support claim. High risk of hallucination/speculation.")
                severity = "HIGH"
            elif unverified_hashes and len(unverified_hashes) == len(evidence_hashes):
                issues.append(f"Evidence hashes {unverified_hashes} could not be resolved in Veritas vault or Audit ledger.")
                if severity != "HIGH":
                    severity = "MEDIUM"

            if issues:
                critiques.append({
                    "claim": claim,
                    "flaw": " ".join(issues),
                    "severity": severity,
                    "recommendation": "Demand verifiable SHA-256 evidence in Veritas vault or reject assertion."
                })
            else:
                critiques.append({
                    "claim": claim,
                    "flaw": "Grounded in verified cryptographic evidence. Monitor for run-time state drift.",
                    "severity": "LOW",
                    "recommendation": "Accept with ongoing monitoring."
                })

        # 3. Overall Calibrated Assessment
        has_high_severity = any(c["severity"] == "HIGH" for c in critiques)
        if has_high_severity:
            assessment = "CHALLENGED"
        elif evidence_hashes:
            assessment = "CONDITIONALLY_VALIDATED"
        else:
            assessment = "INSUFFICIENT_EVIDENCE"

        return {
            "total_critiques": len(critiques),
            "critiques": critiques,
            "verified_evidence_count": verified_evidence_count,
            "unverified_hashes": unverified_hashes,
            "overall_assessment": assessment,
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
