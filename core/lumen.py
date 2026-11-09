"""
LUMEN — Context & Living Surface Display Engine
Decides what the Fire TV Living Surface displays based on temporal signals,
active approvals, system alerts, and user habits.
"""

import time
from typing import Dict, Any, List
from core.db import query_db


class LumenContextEngine:
    def __init__(self):
        pass

    def evaluate_time_context(self) -> Dict[str, str]:
        """
        Calculates time-of-day phase and aesthetic theme.
        """
        hour = time.localtime().tm_hour
        if 5 <= hour < 12:
            return {"period": "morning", "theme": "obsidian_gold", "greeting": "Good morning, Aadi."}
        elif 12 <= hour < 17:
            return {"period": "afternoon", "theme": "obsidian_cyan", "greeting": "Good afternoon, Aadi."}
        elif 17 <= hour < 22:
            return {"period": "evening", "theme": "obsidian_purple", "greeting": "Good evening, Aadi."}
        else:
            return {"period": "night", "theme": "obsidian_dark", "greeting": "Late hours. Low distraction mode."}

    def get_pending_approvals_count(self) -> int:
        rows = query_db("SELECT COUNT(*) FROM sentinel_requests WHERE status = 'pending'")
        return rows[0][0] if rows else 0

    def get_active_tasks_count(self) -> int:
        rows = query_db("SELECT COUNT(*) FROM tasks WHERE status = 'pending'")
        return rows[0][0] if rows else 0

    def get_monitored_topics_summary(self) -> List[str]:
        try:
            from aeonix.core.panoptes import list_monitored_topics
            topics = list_monitored_topics()
            return [t["name"] for t in topics if t.get("document_count", 0) > 0][:5]
        except Exception:
            return []

    def compute_living_surface_state(self) -> Dict[str, Any]:
        """
        Synthesizes the complete Living Surface HUD payload for the Fire TV.
        """
        time_ctx = self.evaluate_time_context()
        pending_sentinel = self.get_pending_approvals_count()
        pending_tasks = self.get_active_tasks_count()
        active_topics = self.get_monitored_topics_summary()

        cards: List[Dict[str, Any]] = []

        # Urgent Sentinel Alert Card
        if pending_sentinel > 0:
            cards.append({
                "title": "Sentinel Gate Holds",
                "content": f"{pending_sentinel} consequential action(s) awaiting physical remote approval.",
                "type": "sentinel_alert",
                "priority": "HIGH",
            })

        # Knowledge Vault Topics Card (if active topics exist)
        if active_topics:
            cards.append({
                "title": "Knowledge Vault & Monitored Topics",
                "content": f"{len(active_topics)} active research topics: {', '.join(active_topics)}",
                "type": "knowledge_topics",
                "priority": "NORMAL",
            })

        # Contextual Period Card
        period = time_ctx["period"]
        if period == "morning":
            cards.append({
                "title": "Morning Briefing",
                "content": "Review daily schedule, network perimeter baseline, and queued research missions.",
                "type": "briefing",
                "priority": "NORMAL",
            })
        elif period == "afternoon":
            cards.append({
                "title": "Active Focus Deck",
                "content": f"{pending_tasks} tasks queued in vault. Core Mind operating at full efficiency.",
                "type": "focus",
                "priority": "NORMAL",
            })
        elif period == "evening":
            cards.append({
                "title": "Cinema & Relax",
                "content": "Curated HLS streams ready: NASA TV, DW News Global, Cyber Synth.",
                "type": "media",
                "priority": "NORMAL",
            })
        else:
            cards.append({
                "title": "Night Sanctuary",
                "content": "Acoustic and visual distractions minimized. Background inference throttled.",
                "type": "sanctuary",
                "priority": "LOW",
            })

        return {
            "screen": "living_surface",
            "period": period,
            "theme": time_ctx["theme"],
            "greeting": time_ctx["greeting"],
            "pending_approvals": pending_sentinel,
            "active_tasks": pending_tasks,
            "cards": cards,
            "timestamp": time.time(),
        }


lumen = LumenContextEngine()
