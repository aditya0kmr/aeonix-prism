"""
Forensicator Agent — Digital Evidence Integrity & Custody
Hashes evidence items with SHA-256, enforces read-only storage (0o444),
and records cryptographically verifiable chain-of-custody entries in VERITAS.
"""

from typing import Dict, Any
from agents.base_agent import BaseAgent
from core.veritas import ingest_evidence, get_case_manifest


class ForensicatorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Forensicator",
            role="Evidence Custodian & Cryptographic Hash Preserver",
            allowed_tools=["hash_evidence", "seal_evidence", "maintain_custody"],
            forbidden_tools=["modify_file", "delete_evidence"],
            base_risk_tier="R1",
        )

    def preserve_item(
        self,
        case_id: str,
        file_path: str,
        mime_type: str = "text/plain",
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        result = ingest_evidence(
            case_id=case_id,
            file_path=file_path,
            mime_type=mime_type,
            metadata=metadata or {},
            collected_by=self.name,
        )
        return result

    def execute(self, mission_context: Dict[str, Any]) -> Dict[str, Any]:
        case_id = mission_context.get("case_id", "default_case")
        file_path = mission_context.get("file_path")

        if not file_path:
            return {
                "status": "manifest_only",
                "manifest": get_case_manifest(case_id),
            }

        ingest_res = self.preserve_item(
            case_id=case_id,
            file_path=file_path,
            mime_type=mission_context.get("mime_type", "application/octet-stream"),
            metadata=mission_context.get("metadata", {}),
        )

        self.log_action("preserve_evidence", file_path, "SUCCESS", {"sha256": ingest_res.get("sha256")})
        return {
            "status": "preserved",
            "evidence": ingest_res,
        }
