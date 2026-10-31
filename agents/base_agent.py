"""
Base Agent Module for ÆONIX PRISM
Defines the foundational BaseAgent class adhering strictly to:
- POCO-controlled human authorization (Sentinel Gate)
- Stateful pause / resume mechanics
- Cryptographic hash-chained audit logging
- Zero cloud / Zero commercial API dependencies
"""

import time
import json
import logging
from typing import Dict, Any, List, Optional
from core.db import log_audit_event, create_sentinel_request

logger = logging.getLogger("aeonix.agents.base")


class BaseAgent:
    """
    Base class for all ÆONIX PRISM autonomous agents.
    Every agent possesses:
    - name: Unique identifier
    - role: Canonical duty description
    - allowed_tools: Whitelist of permissible capabilities
    - forbidden_tools: Blacklisted capabilities
    - risk_tier: Baseline risk tier (R0 to R4)
    """

    def __init__(
        self,
        name: str,
        role: str,
        allowed_tools: Optional[List[str]] = None,
        forbidden_tools: Optional[List[str]] = None,
        base_risk_tier: str = "R1",
    ):
        self.name = name
        self.role = role
        self.allowed_tools = allowed_tools or []
        self.forbidden_tools = forbidden_tools or []
        self.base_risk_tier = base_risk_tier
        self.state: Dict[str, Any] = {"status": "idle", "current_task": None}

    def evaluate_tool_permission(self, tool_name: str) -> Dict[str, Any]:
        """
        Validates if tool is authorized for this agent.
        """
        if tool_name in self.forbidden_tools:
            return {
                "permitted": False,
                "reason": f"Tool '{tool_name}' is explicitly forbidden for agent '{self.name}'.",
                "risk": "R4",
            }
        if self.allowed_tools and tool_name not in self.allowed_tools:
            return {
                "permitted": False,
                "reason": f"Tool '{tool_name}' is not in allowed whitelist for agent '{self.name}'.",
                "risk": "R3",
            }
        return {"permitted": True, "risk": self.base_risk_tier}

    def request_sentinel_gate(
        self,
        action_type: str,
        target: str,
        scope: Dict[str, Any],
        risk_level: str = "R3",
    ) -> Dict[str, Any]:
        """
        Pauses agent execution and stages a formal Sentinel Gate approval card.
        Execution resumes only upon physical human approval.
        """
        request_id = create_sentinel_request(
            agent=self.name,
            action_class=self.base_risk_tier,
            action_type=action_type,
            target=target,
            scope=scope,
            risk_level=risk_level,
            timeout_seconds=300.0,
        )

        log_audit_event(
            actor=self.name,
            action="sentinel_gate_hold",
            target=target,
            result="PENDING_HUMAN_APPROVAL",
            details={
                "request_id": request_id,
                "action_type": action_type,
                "risk_level": risk_level,
            },
        )

        self.state["status"] = "suspended_at_sentinel"
        self.state["pending_request_id"] = request_id

        return {
            "status": "sentinel_gate_hold",
            "request_id": request_id,
            "agent": self.name,
            "target": target,
            "message": f"Action '{action_type}' halted at Sentinel Gate. Requires physical authorization on Fire TV or phone.",
        }

    def log_action(self, action: str, target: str, result: str, details: Dict[str, Any]) -> str:
        """
        Records an event into the cryptographic SHA-256 hash-chained audit vault.
        """
        return log_audit_event(
            actor=self.name,
            action=action,
            target=target,
            result=result,
            details=details,
        )

    def execute(self, mission_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Primary execution hook. Subclasses override this method.
        """
        raise NotImplementedError("Each agent must implement execute().")
