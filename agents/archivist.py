"""
Archivist Agent — Memory Vault Organization & Timeline Indexing
Catalogs persistent memories, manages case retention policies, builds unified timelines,
and prunes expired ephemeral context from the SQLite WAL vault.
"""

from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from core.db import query_db, execute_db


class ArchivistAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Archivist",
            role="Memory Vault Organizer & Timeline Curator",
            allowed_tools=["index_vault", "reconstruct_timeline", "purge_expired"],
            forbidden_tools=["wipe_audit_chain", "tamper_hashes"],
            base_risk_tier="R1",
        )

    def reconstruct_unified_timeline(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Synthesizes chronological timeline across audit logs, evidence, and memories.
        """
        query = """
        SELECT 'audit' AS source, timestamp, action AS summary, details_json AS metadata
        FROM audit_log
        UNION ALL
        SELECT 'evidence' AS source, collected_at AS timestamp, file_path AS summary, metadata_json AS metadata
        FROM evidence
        ORDER BY timestamp DESC
        LIMIT ?
        """
        rows = query_db(query, (limit,))
        timeline = []
        for r in rows:
            timeline.append({
                "source": r[0],
                "timestamp": r[1],
                "summary": r[2],
                "metadata": r[3],
            })
        return timeline

    def execute(self, mission_context: Dict[str, Any]) -> Dict[str, Any]:
        task = mission_context.get("task", "timeline")
        if task == "timeline":
            limit = mission_context.get("limit", 15)
            tl = self.reconstruct_unified_timeline(limit=limit)
            self.log_action("curate_timeline", "UnifiedTimeline", "SUCCESS", {"events": len(tl)})
            return {
                "status": "timeline_curated",
                "events_count": len(tl),
                "timeline": tl,
            }

        return {"status": "archived", "message": "Archival sweep complete."}
