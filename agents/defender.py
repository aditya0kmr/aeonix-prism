"""
Defender Agent — Perimeter Defense & Incident Mitigation
Translates security findings into defensive countermeasures, identifies rogue assets,
and triggers Sentinel Gate approval for disruptive isolation actions.
"""

from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from core.guardian import get_network_inventory


class DefenderAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Defender",
            role="Perimeter Hardening & Countermeasure Coordinator",
            allowed_tools=["audit_subnet", "recommend_mitigation", "isolate_rogue_asset"],
            forbidden_tools=["offensive_counterattack", "dos"],
            base_risk_tier="R2",
        )

    def assess_network_threats(self) -> Dict[str, Any]:
        inventory = get_network_inventory()
        rogue_devices = inventory.get("rogue_devices", [])
        return {
            "total_devices": inventory.get("total_discovered", 0),
            "rogue_count": len(rogue_devices),
            "rogue_devices": rogue_devices,
            "threat_level": "ELEVATED" if rogue_devices else "NOMINAL",
        }

    def execute(self, mission_context: Dict[str, Any]) -> Dict[str, Any]:
        action = mission_context.get("action", "assess")
        target_ip = mission_context.get("target_ip")

        if action == "isolate" and target_ip:
            # Disruptive isolation halts at Sentinel Gate
            return self.request_sentinel_gate(
                action_type="network_asset_isolation",
                target=target_ip,
                scope={"method": "ARP_RESTRICTION / IPTABLES_BLOCK"},
                risk_level="R4",
            )

        assessment = self.assess_network_threats()
        self.log_action("perimeter_assessment", "10.116.23.0/24", "SUCCESS", {"threat_level": assessment["threat_level"]})

        return {
            "status": "assessed",
            "threat_assessment": assessment,
            "recommendation": "Maintain standard monitoring" if assessment["threat_level"] == "NOMINAL" else "Engage Sentinel Gate to isolate rogue asset.",
        }
