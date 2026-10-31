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
        Coordinates a complete multi-agent workflow for an objective:
        - Validates legal basis with LegalGuard.
        - Decomposes plan with Navigator.
        - Persists stateful mission progression in SQLite.
        - Enforces step budget and runtime timeout (max 60s).
        - Halts immediately on missing agents or failed stages.
        - Suspends gracefully on Sentinel Gate hold for POCO authorization.
        """
        start_time = time.time()
        import secrets
        import json
        from core.db import get_connection

        mission_id = f"msn_{int(start_time)}_{secrets.token_hex(4)}"
        log_audit_event("Orchestrator", "start_mission", objective, "IN_PROGRESS", {
            "mission_id": mission_id,
            "target": target
        })

        # 1. Legal Guard Check
        legal_agent: LegalGuardAgent = self.roster["LegalGuard"]
        legal_check = legal_agent.execute({"target": target, "objective": objective})
        if legal_check.get("status") in ["blocked", "sentinel_gate_hold"]:
            return {
                "mission_id": mission_id,
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

        # Enforce step limit budget (max 10 phases)
        if len(phases) > 10:
            phases = phases[:10]

        # Initial persistence in missions table
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO missions (id, objective, target, status, current_phase, total_phases, plan_json, execution_log_json, created_at, updated_at)
                VALUES (?, ?, ?, 'running', 0, ?, ?, '[]', ?, ?);
            """, (mission_id, objective, target, len(phases), json.dumps(phases), start_time, start_time))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to persist initial mission state: {e}")

        execution_log = []
        pipeline_output = {}

        # 3. Execute Phases Sequentially
        for idx, phase in enumerate(phases):
            # Enforce 60-second runtime budget
            if (time.time() - start_time) > 60.0:
                self._update_mission_db(mission_id, "failed", idx, phases, execution_log)
                return {
                    "mission_id": mission_id,
                    "success": False,
                    "status": "timeout",
                    "error": "MISSION_TIMEOUT: Execution exceeded 60.0s time limit",
                    "execution_log": execution_log,
                    "latency_ms": round((time.time() - start_time) * 1000, 2)
                }

            agent_name = phase.get("agent")
            action = phase.get("action")
            agent = self.roster.get(agent_name)

            # Do NOT silently skip missing agents!
            if not agent:
                err_msg = f"MISSING_AGENT: Phase required agent '{agent_name}', but it is not in the roster."
                execution_log.append({
                    "phase": phase.get("phase", idx + 1),
                    "agent": agent_name,
                    "status": "error",
                    "error": err_msg
                })
                self._update_mission_db(mission_id, "failed", idx, phases, execution_log)
                return {
                    "mission_id": mission_id,
                    "success": False,
                    "status": "failed",
                    "halted_at": agent_name,
                    "error": err_msg,
                    "execution_log": execution_log,
                    "latency_ms": round((time.time() - start_time) * 1000, 2)
                }

            ctx = {"objective": objective, "target": target, "action": action, "pipeline_data": pipeline_output}
            phase_result = agent.execute(ctx)

            execution_log.append({
                "phase": phase.get("phase", idx + 1),
                "agent": agent_name,
                "action": action,
                "status": phase_result.get("status"),
                "result": phase_result
            })

            # Halt immediately on Sentinel Hold
            if phase_result.get("status") == "sentinel_gate_hold":
                self._update_mission_db(mission_id, "sentinel_hold", idx, phases, execution_log)
                return {
                    "mission_id": mission_id,
                    "success": False,
                    "status": "sentinel_gate_hold",
                    "halted_at": agent_name,
                    "sentinel_details": phase_result,
                    "execution_log": execution_log,
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                }

            # Stop on failed or invalid stages
            if phase_result.get("status") in ("error", "failed", "denied"):
                self._update_mission_db(mission_id, "failed", idx, phases, execution_log)
                return {
                    "mission_id": mission_id,
                    "success": False,
                    "status": "stage_failed",
                    "halted_at": agent_name,
                    "stage_error": phase_result.get("error") or phase_result.get("message"),
                    "execution_log": execution_log,
                    "latency_ms": round((time.time() - start_time) * 1000, 2)
                }

            pipeline_output[agent_name] = phase_result
            self._update_mission_db(mission_id, "running", idx + 1, phases, execution_log)

        # 4. Final briefing from Reporter
        reporter: ReporterAgent = self.roster["Reporter"]
        sections = [
            {"title": "Objective", "content": objective},
            {"title": "Phases Completed", "content": f"{len(phases)} phases coordinated successfully."},
        ]
        brief = reporter.execute({"title": f"Mission: {objective[:30]}", "sections": sections})
        report_data = brief.get("report", {})

        self._update_mission_db(mission_id, "completed", len(phases), phases, execution_log, report_json=report_data)

        log_audit_event("Orchestrator", "complete_mission", objective, "SUCCESS", {
            "mission_id": mission_id,
            "phases": len(phases)
        })

        return {
            "mission_id": mission_id,
            "success": True,
            "objective": objective,
            "plan": phases,
            "execution_log": execution_log,
            "report": report_data,
            "latency_ms": round((time.time() - start_time) * 1000, 2),
        }

    def _update_mission_db(self, mission_id: str, status: str, current_phase: int, phases: list, log: list, report_json: Optional[dict] = None):
        """Helper to update persistent mission state in SQLite."""
        try:
            import json
            from core.db import get_connection
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                UPDATE missions
                SET status = ?, current_phase = ?, execution_log_json = ?, report_json = ?, updated_at = ?
                WHERE id = ?;
            """, (status, current_phase, json.dumps(log), json.dumps(report_json or {}), time.time(), mission_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Error persisting mission update: {e}")


# Global singleton instance
orchestrator = AgentOrchestrator()
