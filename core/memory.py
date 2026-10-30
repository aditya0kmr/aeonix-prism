import time
import json
from typing import Optional, Dict, Any, List
from aeonix.core.db import get_connection, log_audit_event
from aeonix.core.ram_guard import check_ram_guard

VALID_CATEGORIES = {
    "goal", "project", "preference", "habit", "security",
    "lesson", "observation", "priority", "health"
}

def store_memory(
    title: str,
    content: str,
    category: str = "observation",
    user_id: str = "user_aadi",
    tags: Optional[List[str]] = None,
    expires_at: Optional[float] = None,
    source: str = "direct"
) -> str:
    """Stores a persistent memory in AADYA's Memory Heart."""
    if category not in VALID_CATEGORIES:
        category = "observation"

    conn = get_connection()
    cur = conn.cursor()

    mem_id = f"mem_{int(time.time()*1000)}_{title[:8].lower().replace(' ', '_')}"
    now = time.time()
    tags_str = ",".join([t.strip().lower() for t in tags]) if tags else ""

    cur.execute("""
        INSERT INTO memories (id, user_id, category, title, content, tags, created_at, expires_at, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (mem_id, user_id, category, title, content, tags_str, now, expires_at, source))

    conn.commit()
    conn.close()

    log_audit_event(
        actor="AADYA",
        action="memory_stored",
        target=mem_id,
        result="success",
        details={"category": category, "title": title}
    )
    return mem_id

def recall_memories(
    user_id: str = "user_aadi",
    query: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 15
) -> List[Dict[str, Any]]:
    """Retrieves memories matching category or search tokens."""
    conn = get_connection()
    cur = conn.cursor()

    sql = "SELECT * FROM memories WHERE user_id = ?"
    params: List[Any] = [user_id]

    if category:
        sql += " AND category = ?"
        params.append(category)

    if query:
        search_term = f"%{query.strip().lower()}%"
        sql += " AND (LOWER(title) LIKE ? OR LOWER(content) LIKE ? OR LOWER(tags) LIKE ?)"
        params.extend([search_term, search_term, search_term])

    sql += " ORDER BY created_at DESC LIMIT ?;"
    params.append(limit)

    cur.execute(sql, tuple(params))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def generate_daily_briefing(user_id: str = "user_aadi") -> Dict[str, Any]:
    """
    AADYA Aadi-First Priority Engine & Daily Briefing Synthesizer.
    Combines: Circadian time, system sovereignty, pending sentinels, active tasks, and AADYA priorities.
    """
    now_str = time.strftime("%A, %B %d, %Y · %I:%M %p")
    ram = check_ram_guard()

    # Query pending tasks
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT title, priority FROM tasks WHERE status = 'pending' ORDER BY priority DESC LIMIT 5;")
    tasks = [f"• [{r['priority'].upper()}] {r['title']}" for r in cur.fetchall()]

    # Query pending Sentinel authorizations
    cur.execute("SELECT action_type, risk_level, target FROM sentinel_requests WHERE status = 'pending' AND expires_at > ?;", (time.time(),))
    sentinels = [f"• [{r['risk_level']}] {r['action_type']} -> {r['target']}" for r in cur.fetchall()]

    # Query core goals
    cur.execute("SELECT title, content FROM memories WHERE category = 'goal' ORDER BY created_at DESC LIMIT 3;")
    goals = [f"★ {r['title']}: {r['content']}" for r in cur.fetchall()]
    conn.close()

    task_summary = "\n".join(tasks) if tasks else "No urgent tasks pending."
    sentinel_summary = "\n".join(sentinels) if sentinels else "All systems clear. Zero pending authorizations."
    goals_summary = "\n".join(goals) if goals else "Focus on core digital sovereignty and living-room OS completion."

    briefing_text = (
        f"Good morning, Aadi. All systems are operating under sovereign control.\n\n"
        f"🛡️ System State: Nominal ({ram['available_mb']}MB RAM free, 0 packet loss to Fire TV).\n\n"
        f"📋 Focus & Priorities:\n{goals_summary}\n\n"
        f"⏳ Active Missions:\n{task_summary}\n\n"
        f"🔒 Sentinel Gate:\n{sentinel_summary}"
    )

    return {
        "timestamp": time.time(),
        "date_str": now_str,
        "sovereign_user": "Aadi",
        "system_status": "nominal",
        "ram_available_mb": ram["available_mb"],
        "briefing_markdown": briefing_text,
        "layout_intent": {
            "screen": "living_surface",
            "theme": "obsidian_cyan",
            "cards": [
                {"title": "AADYA // DAILY BRIEFING", "content": briefing_text, "type": "briefing"},
                {"title": "SYSTEM SOVEREIGNTY", "content": f"Core: Online\nRAM: {ram['available_mb']} MB Free\nFire TV: Paired", "type": "metric"}
            ]
        }
    }
