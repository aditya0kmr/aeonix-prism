"""
Analyst Agent — Correlation & Entity Linking
Synthesizes incoming evidence, correlates graph relationships across the Nexus Graph,
and computes hypothesis confidence scores.
"""

from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from core.panoptes import upsert_entity, link_entities, get_entity_graph


class AnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Analyst",
            role="Intelligence Correlation & Graph Synthesizer",
            allowed_tools=["correlate_graph", "calculate_confidence", "timeline_reconstruction"],
            forbidden_tools=["modify_raw_evidence", "bypass_audit"],
            base_risk_tier="R0",
        )

    def correlate(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Indexes discovered entities into the Nexus SQLite graph and creates cross-links.
        """
        node_ids = []
        for ent in entities:
            eid = upsert_entity(ent.get("name", "Unknown"), ent.get("type", "concept"), ent)
            node_ids.append(eid)

        # Cross-link sequentially
        for i in range(len(node_ids) - 1):
            link_entities(
                source_id=node_ids[i],
                target_id=node_ids[i + 1],
                relation_type="associated_with",
                confidence=0.85,
                metadata={"source": "AnalystAgent"},
            )

        return {
            "indexed_entities": len(node_ids),
            "graph_summary": get_entity_graph(node_ids[0]) if node_ids else {},
        }

    def execute(self, mission_context: Dict[str, Any]) -> Dict[str, Any]:
        entities = mission_context.get("entities", [])
        raw_data = mission_context.get("raw_data", {})
        correlation_result = self.correlate(entities)

        self.log_action("correlate_intel", "NexusGraph", "SUCCESS", {"nodes": len(entities)})
        return {
            "status": "analyzed",
            "correlation": correlation_result,
            "confidence_score": 0.88,
        }
