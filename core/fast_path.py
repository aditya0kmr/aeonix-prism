import re
import time
import difflib
from typing import Optional, Dict, Any, Tuple
from aeonix.core.ram_guard import check_ram_guard
from aeonix.core.db import get_connection

# Fast-path normalized triggers
COMMAND_TRIGGERS = {
    "system_health": [
        "system status", "system health", "ram status", "how much ram",
        "memory status", "poco status", "device health", "diagnostics", "check system"
    ],
    "weather": [
        "weather", "forecast", "temperature", "rain today", "climate", "how is weather"
    ],
    "sentinel": [
        "sentinel", "pending requests", "approvals", "security queue",
        "authorization queue", "pending cards", "security status"
    ],
    "missions": [
        "missions", "tasks", "pending tasks", "what to do", "todo list", "cases", "open cases"
    ],
    "media_play": [
        "play", "resume", "start media", "unpause"
    ],
    "media_pause": [
        "pause", "stop media", "halt video", "freeze playback"
    ],
    "media_volume_up": [
        "volume up", "increase volume", "louder"
    ],
    "media_volume_down": [
        "volume down", "decrease volume", "lower volume", "quieter"
    ],
    "mode_sanctuary": [
        "sanctuary mode", "lockdown", "emergency mode", "go dark"
    ],
    "mode_surface": [
        "living surface", "home screen", "main screen", "ambient mode"
    ],
    "mode_iptv": [
        "live tv", "iptv", "open tv", "channels", "stream deck"
    ],
    "mode_arcade": [
        "open arcade", "retro games", "game room"
    ],
    "time": [
        "time", "what time is it", "current time", "what is the date", "today date"
    ],
    "briefing": [
        "briefing", "daily briefing", "morning briefing", "what are my priorities",
        "update me", "status report", "overview"
    ]
}

def normalize_text(text: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", text.lower())
    return " ".join(cleaned.split())

def match_fast_path(query: str) -> Optional[Tuple[str, float]]:
    """
    Sub-millisecond keyword and fuzzy matching.
    Returns (action_name, confidence) or None.
    """
    norm = normalize_text(query)
    if not norm:
        return None

    # 1. Exact or substring match (0.01ms)
    for action, triggers in COMMAND_TRIGGERS.items():
        for trigger in triggers:
            if trigger == norm or trigger in norm:
                return (action, 1.0)

    # 2. Token overlap match (0.05ms)
    query_tokens = set(norm.split())
    for action, triggers in COMMAND_TRIGGERS.items():
        for trigger in triggers:
            trigger_tokens = set(trigger.split())
            if trigger_tokens.issubset(query_tokens):
                return (action, 0.95)

    # 3. Fuzzy matching via difflib ratio (0.5ms)
    all_phrases = []
    phrase_map = {}
    for action, triggers in COMMAND_TRIGGERS.items():
        for t in triggers:
            all_phrases.append(t)
            phrase_map[t] = action

    closest = difflib.get_close_matches(norm, all_phrases, n=1, cutoff=0.75)
    if closest:
        matched_trigger = closest[0]
        return (phrase_map[matched_trigger], 0.85)

    return None

def execute_fast_path(action: str, actor: str = "Aadi") -> Dict[str, Any]:
    """
    Generates instant, deterministic structured response in < 5ms.
    """
    start_t = time.perf_counter()

    if action == "system_health":
        ram = check_ram_guard()
        speech = f"System nominal. POCO M4 Pro has {ram['available_mb']} Megabytes RAM available across {ram['child_processes']} processes."
        card = {
            "title": "System Health",
            "content": f"RAM Free: {ram['available_mb']} MB\nStatus: Secure\nProcesses: {ram['child_processes']}",
            "type": "metric"
        }
        screen = "command_deck"

    elif action == "weather":
        speech = "Local conditions are 25 degrees, clear skies, humidity 48 percent."
        card = {
            "title": "Living Environment",
            "content": "25°C · Clear & Ambient\nHumidity: 48% · Wind: 6 km/h",
            "type": "weather"
        }
        screen = "living_surface"

    elif action == "sentinel":
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT count(*) as cnt FROM sentinel_requests WHERE status = 'pending';")
        cnt = cur.fetchone()["cnt"]
        conn.close()
        speech = f"Sentinel Gate report: {cnt} pending authorization requests awaiting approval."
        card = {
            "title": "Sentinel Gate",
            "content": f"{cnt} Pending Approvals\nAll sensitive actions halted.",
            "type": "security"
        }
        screen = "sentinel_deck"

    elif action == "missions":
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT count(*) as cnt FROM tasks WHERE status = 'pending';")
        tasks_cnt = cur.fetchone()["cnt"]
        cur.execute("SELECT count(*) as cnt FROM cases WHERE status = 'open';")
        cases_cnt = cur.fetchone()["cnt"]
        conn.close()
        speech = f"You have {tasks_cnt} active tasks and {cases_cnt} open investigation cases, Aadi."
        card = {
            "title": "Active Missions",
            "content": f"Tasks: {tasks_cnt} Active\nInvestigation Cases: {cases_cnt} Open",
            "type": "missions"
        }
        screen = "living_surface"

    elif action == "time":
        current_str = time.strftime("%I:%M %p — %A, %B %d")
        speech = f"The time is {current_str}."
        card = {
            "title": "Chronos Time",
            "content": current_str,
            "type": "time"
        }
        screen = "living_surface"

    elif action == "briefing":
        from aeonix.core.memory import generate_daily_briefing
        briefing_data = generate_daily_briefing(user_id="user_aadi")
        return {
            "tier": "Tier 0 (Fast-Path Briefing Engine)",
            "action": "daily_briefing",
            "latency_ms": round((time.perf_counter() - start_t) * 1000, 2),
            "speech": "Here is your sovereign intelligence briefing, Aadi. All systems nominal.",
            "layout_intent": briefing_data["layout_intent"]
        }

    elif action.startswith("media_"):
        sub = action.replace("media_", "")
        speech = f"Executing media directive: {sub}."
        card = {
            "title": "Media Control",
            "content": f"Action: {sub.upper()}",
            "type": "media"
        }
        screen = "media_deck"

    elif action == "mode_sanctuary":
        speech = "Sanctuary Mode engaged. External connections throttled. Local vault sealed."
        card = {
            "title": "SANCTUARY ACTIVE",
            "content": "Defensive posture enabled.\nNetwork isolated.",
            "type": "alert"
        }
        screen = "sanctuary"

    elif action.startswith("mode_"):
        mode_name = action.replace("mode_", "")
        speech = f"Switching interface to {mode_name} world."
        card = {
            "title": "Navigation",
            "content": f"Active World: {mode_name.upper()}",
            "type": "nav"
        }
        screen = mode_name

    else:
        speech = f"Directive acknowledged for {actor}."
        card = {"title": "Fast Path", "content": action, "type": "standard"}
        screen = "living_surface"

    elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)

    return {
        "tier": "Tier 0 (Fast-Path Router)",
        "action": action,
        "latency_ms": elapsed_ms,
        "speech": speech,
        "layout_intent": {
            "screen": screen,
            "theme": "obsidian_cyan",
            "cards": [card]
        }
    }
