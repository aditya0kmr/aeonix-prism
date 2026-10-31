"""
BLACK BOX — Autonomous Mission Flight Recorder
Maintains immutable, structured flight records of every multi-agent mission:
Initial prompt, tool calls, parameters, latency, error states, and outcome telemetry.
"""

import time
import json
from typing import Dict, Any, List
from core.db import log_audit_event


class BlackBoxFlightRecorder:
    def __init__(self):
        self.flight_logs: List[Dict[str, Any]] = []

    def record_mission_flight(
        self,
        mission_id: str,
        goal: str,
        agents_involved: List[str],
        tool_calls: List[Dict[str, Any]],
        outcome: str,
        total_latency_ms: float,
    ) -> Dict[str, Any]:
        flight_record = {
            "flight_id": f"bb_{int(time.time())}_{hash(mission_id) % 10000}",
            "mission_id": mission_id,
            "goal": goal,
            "timestamp": time.time(),
            "agents_involved": agents_involved,
            "tool_call_count": len(tool_calls),
            "tool_calls": tool_calls,
            "outcome": outcome,
            "latency_ms": total_latency_ms,
        }
        self.flight_logs.append(flight_record)

        log_audit_event(
            "BlackBox",
            "record_flight",
            mission_id,
            outcome,
            {"flight_id": flight_record["flight_id"], "tool_calls": len(tool_calls)}
        )

        return flight_record

    def get_recent_flights(self, limit: int = 5) -> List[Dict[str, Any]]:
        return self.flight_logs[-limit:]


blackbox = BlackBoxFlightRecorder()
