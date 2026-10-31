"""
NEXUS ROOM — Living Interface Universe Mapper
Transforms real-time system state into a cosmic living visual topology for the Fire TV:
- Network as star map
- Connected devices as celestial bodies
- Autonomous agents as active energy beacons
- Sentinel alerts as solar disturbances
- Forensic cases as stellar constellations
"""

import time
from typing import Dict, Any, List
from core.db import query_db


class NexusRoomUniverse:
    def __init__(self):
        pass

    def render_celestial_topology(self) -> Dict[str, Any]:
        start_time = time.time()

        # Devices as celestial nodes
        device_nodes = [
            {"name": "POCO Core Mind", "role": "Sun (Central Star)", "ip": "10.116.23.168", "orbit": 0, "energy": "HIGH"},
            {"name": "Fire TV Glass", "role": "Living Surface (Primary Planet)", "ip": "10.116.23.179", "orbit": 1, "energy": "NOMINAL"},
            {"name": "Local Gateway", "role": "Outer Boundary (Beacon)", "ip": "10.116.23.1", "orbit": 2, "energy": "STABLE"},
        ]

        # Active agents as stellar energy beacons
        agent_beacons = [
            {"agent": "Sentinel", "status": "Vigilant Orbit"},
            {"agent": "Navigator", "status": "Pathfinding Vector"},
            {"agent": "Analyst", "status": "Graph Weaver"},
            {"agent": "Defender", "status": "Shield Harmonic"},
        ]

        # Sentinel alerts as cosmic disturbances
        alert_rows = query_db("SELECT COUNT(*) FROM sentinel_requests WHERE status = 'pending'")
        disturbances = alert_rows[0][0] if alert_rows else 0

        # Forensic cases as constellations
        case_rows = query_db("SELECT id, title FROM cases LIMIT 3")
        constellations = [{"id": r[0], "title": r[1]} for r in case_rows]

        return {
            "view": "nexus_room_celestial_universe",
            "celestial_nodes": device_nodes,
            "agent_beacons": agent_beacons,
            "disturbances_count": disturbances,
            "constellations": constellations,
            "theme": "deep_space_obsidian",
            "latency_ms": round((time.time() - start_time) * 1000, 2),
        }


nexus_room = NexusRoomUniverse()
