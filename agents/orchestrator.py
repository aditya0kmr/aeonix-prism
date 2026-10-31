"""
Agent Orchestrator — Multi-Agent Mission Coordinator
Coordinates stateful multi-agent execution across the entire roster:
Navigator, Collector, Analyst, Skeptic, LegalGuard, Forensicator,
Defender, Reporter, Builder, Archivist.
Maintains execution states, respects Sentinel Gate holds, and logs audit entries.
"""

import time
import logging
from typing import Dict, Any, List, Optional

from agents.navigator import NavigatorAgent
from agents.collector import CollectorAgent
from agents.analyst import AnalystAgent
from agents.skeptic import SkepticAgent
from agents.legal_guard import LegalGuardAgent
from agents.forensicator import ForensicatorAgent
from agents.defender import DefenderAgent
from agents.reporter import ReporterAgent
from agents.builder import BuilderAgent
from agents.archivist import ArchivistAgent
from core.db import log_audit_event

logger = logging.getLogger("aeonix.agents.orchestrator")


class AgentOrchestrator:
    def __init__(self):
        self.roster = {
            "Navigator": NavigatorAgent(),
            "Collector": CollectorAgent(),
            "Analyst": AnalystAgent(),
            "Skeptic": SkepticAgent(),
            "LegalGuard": LegalGuardAgent(),
            "Forensicator": ForensicatorAgent(),
            "Defender": DefenderAgent(),
            "Reporter": ReporterAgent(),
            "Builder": BuilderAgent(),
            "Archivist": ArchivistAgent(),
        }

    def get_agent(self, name: str):
        return self.roster.get(name)

    def list_roster(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": a.name,
                "role": a.role,
                "risk_tier": a.base_risk_tier,
                "status": a.state["status"],
                "allowed_tools": a.allowed_tools,
            }
            for a in self.roster.values()
        ]

    def dispatch_mission(self, objective: str, target: str = "") -> Dict[str, Any]:
        """
        Coordinates a complete multi-agent workflow for an objective.
        If any agent hits a Sentinel Gate hold, the mission suspends gracefully.
        """
        start_time = time.time()
        log_audit_event("Orchestrator", "start_mission", objective, "IN_PROGRESS", {"target": target})

        # 1. Legal Guard Check
        legal_agent: LegalGuardAgent = self.roster["LegalGuard"]
        legal_check = legal_agent.execute({"target": target, "objective": objective})
        if legal_check.get("status") in ["blocked", "sentinel_gate_hold"]:
            return {
                "success": False,
                "status": legal_check.get("status"),
                "halted_at": "LegalGuard",
                "details": legal_check,
                "latency_ms": round((time.time() - start_time) * 1000, 2),
            }

        # 2. Navigator Decomposes Plan
        nav_agent: NavigatorAgent = self.roster["Navigator"]
        nav_plan = nav_agent.execute({"objective": objective, "target": target})
        phases = nav_plan.get("phases", [])

        execution_log = []
        pipeline_output = {}

        # 3. Execute Phases Sequentially
        for phase in phases:
            agent_name = phase.get("agent")
            action = phase.get("action")
            agent = self.roster.get(agent_name)

            if not agent:
                continue

            ctx = {"objective": objective, "target": target, "action": action, "pipeline_data": pipeline_output}
            phase_result = agent.execute(ctx)

            execution_log.append({
                "phase": phase.get("phase"),
                "agent": agent_name,
                "action": action,
                "status": phase_result.get("status"),
            })

            # Check for Sentinel Hold
            if phase_result.get("status") == "sentinel_gate_hold":
                return {
                    "success": False,
                    "status": "sentinel_gate_hold",
                    "halted_at": agent_name,
                    "sentinel_details": phase_result,
                    "execution_log": execution_log,
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                }

            pipeline_output[agent_name] = phase_result

        # Final briefing from Reporter
        reporter: ReporterAgent = self.roster["Reporter"]
        sections = [
            {"title": "Objective", "content": objective},
            {"title": "Phases Completed", "content": f"{len(phases)} phases coordinated successfully."},
        ]
        brief = reporter.execute({"title": f"Mission: {objective[:30]}", "sections": sections})

        log_audit_event("Orchestrator", "complete_mission", objective, "SUCCESS", {"phases": len(phases)})

        return {
            "success": True,
            "objective": objective,
            "plan": phases,
            "execution_log": execution_log,
            "report": brief.get("report"),
            "latency_ms": round((time.time() - start_time) * 1000, 2),
        }


# Global singleton instance
orchestrator = AgentOrchestrator()
