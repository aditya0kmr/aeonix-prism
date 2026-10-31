"""
Navigator Agent — Mission Strategy & Phased Planning
Understands goals, decomposes objectives into deterministic phased workflows,
and assigns subtasks to specialized agents under the Sentinel Gate contract.
"""

from typing import Dict, Any, List
from agents.base_agent import BaseAgent


class NavigatorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Navigator",
            role="Mission Planner & Strategic Decomposer",
            allowed_tools=["plan_decomposition", "route_intent", "schedule_task"],
            forbidden_tools=["rm", "kill", "format", "port_scan"],
            base_risk_tier="R0",
        )

    def decompose_mission(self, objective: str) -> List[Dict[str, Any]]:
        """
        Decomposes an abstract user objective into actionable deterministic phases.
        """
        lower = objective.lower()
        if "investigat" in lower or "osint" in lower or "whois" in lower:
            return [
                {"phase": 1, "agent": "LegalGuard", "action": "verify_scope", "target": objective},
                {"phase": 2, "agent": "Collector", "action": "gather_passive_intel", "target": objective},
                {"phase": 3, "agent": "Analyst", "action": "correlate_entities", "target": objective},
                {"phase": 4, "agent": "Skeptic", "action": "test_contradictions", "target": objective},
                {"phase": 5, "agent": "Reporter", "action": "generate_brief", "target": objective},
            ]
        elif "forensic" in lower or "case" in lower or "evidence" in lower:
            return [
                {"phase": 1, "agent": "Forensicator", "action": "hash_and_preserve", "target": objective},
                {"phase": 2, "agent": "Analyst", "action": "extract_timeline", "target": objective},
                {"phase": 3, "agent": "Archivist", "action": "index_case", "target": objective},
                {"phase": 4, "agent": "Reporter", "action": "compile_manifest", "target": objective},
            ]
        elif "security" in lower or "network" in lower or "audit" in lower:
            return [
                {"phase": 1, "agent": "Defender", "action": "scan_perimeter", "target": objective},
                {"phase": 2, "agent": "Analyst", "action": "assess_vulnerabilities", "target": objective},
                {"phase": 3, "agent": "Reporter", "action": "alert_summary", "target": objective},
            ]
        else:
            return [
                {"phase": 1, "agent": "Analyst", "action": "synthesize_context", "target": objective},
                {"phase": 2, "agent": "Reporter", "action": "format_layout", "target": objective},
            ]

    def execute(self, mission_context: Dict[str, Any]) -> Dict[str, Any]:
        objective = mission_context.get("objective", "Unknown Mission")
        plan = self.decompose_mission(objective)
        self.log_action("decompose_mission", objective, "SUCCESS", {"phases": len(plan)})
        return {
            "status": "planned",
            "objective": objective,
            "phases": plan,
            "recommended_lead_agent": plan[0]["agent"] if plan else "Reporter",
        }
