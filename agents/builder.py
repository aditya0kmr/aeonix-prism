"""
Builder Agent — Software Engineering, Testing & Deployment
Drafts code, runs sandboxed test suites, checks Git repositories,
and routes all consequential filesystem/process commands through the Sentinel Gate.
"""

from typing import Dict, Any
from agents.base_agent import BaseAgent
from core.forge import draft_command, execute_sandboxed_command, get_git_status


class BuilderAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Builder",
            role="Software Engineer, Test Runner & Deployment Specialist",
            allowed_tools=["draft_shell", "run_sandbox", "git_telemetry"],
            forbidden_tools=["root_wipe", "bypass_git_auth"],
            base_risk_tier="R1",
        )

    def execute(self, mission_context: Dict[str, Any]) -> Dict[str, Any]:
        task = mission_context.get("task", "git_status")

        if task == "git_status":
            telemetry = get_git_status()
            self.log_action("builder_git_telemetry", "aeonix-repo", "SUCCESS", telemetry)
            return {
                "status": "completed",
                "git_telemetry": telemetry,
            }

        directive = mission_context.get("directive", "")
        if not directive:
            return {"status": "error", "message": "No build directive provided."}

        draft = draft_command(directive)
        if draft["risk_assessment"]["risk_tier"] in ["R3", "R4", "R5"]:
            return self.request_sentinel_gate(
                action_type="execute_destructive_command",
                target=draft["command"],
                scope={"rationale": draft["risk_assessment"]["rationale"]},
                risk_level=draft["risk_assessment"]["risk_tier"],
            )

        exec_res = execute_sandboxed_command(draft["command"])
        if exec_res.get("status") == "sentinel_gate_hold":
            return {
                "status": "sentinel_gate_hold",
                "command": draft["command"],
                "request_id": exec_res.get("request_id"),
                "message": exec_res.get("message")
            }
        self.log_action("builder_exec", draft["command"], "SUCCESS", exec_res)

        return {
            "status": "executed",
            "command": draft["command"],
            "output": exec_res,
        }
