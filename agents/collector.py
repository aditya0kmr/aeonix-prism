"""
Collector Agent — Lawful Data & Evidence Ingestion
Gathers authorized intel from local memories, vault files, and lawful passive public sources.
Active probes or sensitive data accesses immediately halt at the Sentinel Gate.
"""

from typing import Dict, Any
from agents.base_agent import BaseAgent
from core.panoptes import panoptes_scan
from core.memory import recall_memories


class CollectorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Collector",
            role="Lawful Intelligence & Evidence Ingestion",
            allowed_tools=["read_memory", "read_cache", "passive_osint", "active_probe"],
            forbidden_tools=["credential_dump", "exploit", "stealth_intercept"],
            base_risk_tier="R1",
        )

    def execute(self, mission_context: Dict[str, Any]) -> Dict[str, Any]:
        target = mission_context.get("target", "")
        mode = mission_context.get("mode", "passive")

        if mode == "active" or mission_context.get("active_scan", False):
            # Sentinel Gate hard intercept for active probes
            return self.request_sentinel_gate(
                action_type="active_network_probe",
                target=target,
                scope={"ports": [80, 443, 8080], "mode": "TCP SYN"},
                risk_level="R3",
            )

        # Passive collection
        results = {"memories": [], "osint": {}}
        if target:
            # Query local memory heart first
            mems = recall_memories(target, limit=3)
            results["memories"] = mems

            # Lawful passive domain scan if target is a hostname/domain
            if "." in target and not target.endswith(".db"):
                osint_data = panoptes_scan(target, active_probe=False)
                results["osint"] = osint_data

        self.log_action("collect_passive", target, "SUCCESS", {"collected_items": len(results["memories"])})
        return {
            "status": "collected",
            "target": target,
            "data": results,
        }
