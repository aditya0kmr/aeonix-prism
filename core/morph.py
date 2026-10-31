"""
ÆONIX PRISM // MORPH Autonomous Self-Evolution Engine
Analyzes system usage telemetry, detects performance bottlenecks, and drafts Sentinel-governed optimization proposals.
Strict Guardrails: MORPH can PROPOSE improvements, but CANNOT bypass Sentinel, alter audit logs, or self-authorize.
"""

import os
import json
import time
from typing import Dict, Any, List, Optional

from aeonix.core.db import get_connection, log_audit_event, queue_sentinel_request

PROPOSALS_TABLE_INIT = """
CREATE TABLE IF NOT EXISTS morph_proposals (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    proposed_changes_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    resolved_at REAL,
    sentinel_req_id TEXT
);
"""

def init_morph_tables():
    conn = get_connection()
    conn.execute(PROPOSALS_TABLE_INIT)
    conn.commit()
    conn.close()

def analyze_system_patterns() -> List[Dict[str, Any]]:
    """
    Inspects audit_log, sentinel_requests, and system health to identify potential optimizations.
    """
    init_morph_tables()
    conn = get_connection()
    cur = conn.cursor()

    proposals = []
    now = time.time()

    # 1. Check for expired sentinel requests
    cur.execute("SELECT count(*) as cnt FROM sentinel_requests WHERE status = 'pending' AND expires_at < ?;", (now,))
    expired_cnt = cur.fetchone()["cnt"]
    if expired_cnt > 0:
        p_id = f"morph_prune_expired_{int(now)}"
        proposals.append({
            "id": p_id,
            "category": "MAINTENANCE",
            "title": f"Prune {expired_cnt} Expired Sentinel Requests",
            "description": f"There are {expired_cnt} stale authorization requests that have passed their 300s TTL. Prune them to optimize query times.",
            "changes": {"action": "prune_expired_sentinel", "count": expired_cnt}
        })

    # 2. Check WAL vault size
    db_file = os.path.expanduser("~/aeonix/data/aeonix_vault.db")
    if os.path.exists(db_file):
        db_size_mb = os.path.getsize(db_file) / (1024 * 1024)
        if db_size_mb > 10.0:
            p_id = f"morph_wal_checkpoint_{int(now)}"
            proposals.append({
                "id": p_id,
                "category": "DATABASE_OPTIMIZATION",
                "title": "Execute WAL Checkpoint & Vacuum",
                "description": f"Active SQLite Vault has grown to {db_size_mb:.2f} MB. Running PRAGMA wal_checkpoint(TRUNCATE) will reclaim space.",
                "changes": {"action": "wal_checkpoint"}
            })

    # 3. Check frequent actions from audit_log
    cur.execute("""
        SELECT action, count(*) as cnt 
        FROM audit_log 
        GROUP BY action 
        ORDER BY cnt DESC 
        LIMIT 5;
    """)
    top_actions = [dict(r) for r in cur.fetchall()]
    if top_actions:
        p_id = f"morph_cache_priority_{int(now)}"
        proposals.append({
            "id": p_id,
            "category": "PERFORMANCE",
            "title": "Optimize Fast-Path Priority for High-Frequency Directives",
            "description": f"Top action '{top_actions[0]['action']}' occurred {top_actions[0]['cnt']} times. Prioritize in Fast-Path routing index.",
            "changes": {"action": "prioritize_routing", "top_action": top_actions[0]["action"]}
        })

    conn.close()
    return proposals

def generate_optimization_proposal(actor: str = "Aadi") -> Dict[str, Any]:
    """
    Evaluates system patterns and persists a new optimization proposal.
    Any actionable proposal requires explicit human Sentinel confirmation!
    """
    init_morph_tables()
    proposals = analyze_system_patterns()
    if not proposals:
        return {
            "status": "nominal",
            "message": "System operating at peak efficiency. Zero optimization actions required."
        }

    selected = proposals[0]
    now = time.time()

    # Queue Sentinel Request for applying this proposal (Human Authority Rule)
    sentinel_id = queue_sentinel_request(
        agent="MORPH",
        action_class="SYSTEM_OPTIMIZATION",
        action_type=selected["category"],
        target=selected["title"],
        scope=selected["changes"],
        risk_level="R1_LOW",
        ttl_seconds=600
    )

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO morph_proposals (id, category, title, description, proposed_changes_json, status, created_at, sentinel_req_id)
        VALUES (?, ?, ?, ?, ?, 'proposed', ?, ?);
    """, (selected["id"], selected["category"], selected["title"], selected["description"], json.dumps(selected["changes"]), now, sentinel_id))
    conn.commit()
    conn.close()

    log_audit_event(
        actor="MORPH",
        action="optimization_proposed",
        target=selected["id"],
        result="success",
        details={"category": selected["category"], "title": selected["title"], "sentinel_id": sentinel_id}
    )

    return {
        "status": "proposal_generated",
        "proposal_id": selected["id"],
        "category": selected["category"],
        "title": selected["title"],
        "description": selected["description"],
        "sentinel_request_id": sentinel_id,
        "message": "Proposal submitted to Sentinel Gate for human operator review."
    }

def get_pending_proposals() -> List[Dict[str, Any]]:
    """Returns list of all pending MORPH proposals."""
    init_morph_tables()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM morph_proposals ORDER BY created_at DESC;")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
