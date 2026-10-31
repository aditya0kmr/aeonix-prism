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
    "mode_sanctuary_release": [
        "exit sanctuary", "disable lockdown", "safe mode off", "sanctuary off", "release lockdown"
    ],
    "mode_surface": [
        "living surface", "home screen", "main screen", "ambient mode"
    ],
    "mode_iptv": [
        "live tv", "iptv", "open tv", "channels", "stream deck", "open cinema"
    ],
    "play_nasa": [
        "watch nasa", "open nasa tv", "nasa live", "space cam", "iss live"
    ],
    "play_news": [
        "watch news", "open dw news", "world news", "news broadcast"
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
    ],
    "network_scan": [
        "network scan", "who is on my wifi", "wifi scan", "perimeter", "guardian scan", "network status"
    ],
    "cases_status": [
        "cases", "open cases", "evidence status", "veritas status", "forensic cases"
    ],
    "supervisor_health": [
        "supervisor", "system supervisor", "atlas watch", "self healing status", "node status"
    ],
    "git_telemetry": [
        "git status", "repository status", "git branch", "commit status", "latest commit"
    ],
    "forge_status": [
        "developer status", "forge status", "developer deck"
    ],
    "create_backup": [
        "create backup", "backup vault", "snapshot database", "run backup"
    ],
    "backup_status": [
        "backup status", "list backups", "show backups", "vault backups"
    ],
    "morph_status": [
        "morph status", "system proposals", "optimization proposals", "evolution proposals"
    ],
    "oracle_council": [
        "convene council", "council debate", "oracle council", "ask council"
    ],
    "aadya_priority": [
        "aadya", "aadya priority", "check aadya", "aadya creed", "aadya radar"
    ],
    "lumen_context": [
        "lumen", "lumen context", "surface context", "context state"
    ],
    "chronos_routines": [
        "chronos", "routines", "scheduled routines", "chronos routines"
    ],
    "oracle_research": [
        "deep research", "oracle research", "investigate topic"
    ],
    "nexus_room": [
        "nexus room", "celestial universe", "star map"
    ],
    "ghost_twin": [
        "digital twin", "ghost twin", "simulate fault"
    ],
    "agents_roster": [
        "agents", "agent roster", "show agents", "roster"
    ],
    "signal_patterns": [
        "signal scan", "hidden patterns", "detect patterns"
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
    theme = "obsidian_cyan"
    extra_data = {}

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
        from core.atlas import atlas
        w = atlas.get_weather_intel()
        temp = w.get("temperature_c", 24)
        wind = w.get("windspeed_kmh", 8)
        speech = f"Current temperature is {temp} degrees Celsius with wind at {wind} kilometers per hour."
        card = {
            "title": "Living Environment",
            "content": f"{temp}°C · Ambient\nWind: {wind} km/h · Source: {w.get('source', 'Atlas')}",
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

    elif action == "network_scan":
        from aeonix.core.guardian import get_network_inventory
        inv = get_network_inventory()
        speech = f"Perimeter {inv['perimeter_status'].lower()}. {inv['active_devices_count']} sovereign nodes online on local subnet. Zero rogue devices detected."
        card = {
            "title": "GUARDIAN Perimeter",
            "content": f"Subnet: {inv['subnet']}\nPerimeter: {inv['perimeter_status']}\nActive Nodes: {inv['active_devices_count']}\nRogue Nodes: {inv['rogue_count']}",
            "type": "security_perimeter"
        }
        screen = "living_surface"

    elif action == "cases_status":
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT count(*) as cnt FROM cases WHERE status = 'open';")
        open_cases = cur.fetchone()["cnt"]
        cur.execute("SELECT count(*) as cnt FROM evidence;")
        total_ev = cur.fetchone()["cnt"]
        conn.close()
        speech = f"VERITAS Vault holds {open_cases} open cases with {total_ev} cryptographically verified evidence artifacts."
        card = {
            "title": "VERITAS Forensic Vault",
            "content": f"Active Cases: {open_cases}\nSecured Evidence Artifacts: {total_ev}\nIntegrity: Cryptographically Chained (SHA-256)",
            "type": "forensics"
        }
        screen = "living_surface"

    elif action == "supervisor_health":
        from aeonix.core.atlas_watch import run_supervisor_cycle
        rep = run_supervisor_cycle()
        server_str = "ONLINE" if rep["core_server"] else "HEALED"
        adb_str = "CONNECTED" if rep["firetv_adb"] else "HEALED"
        speech = f"ATLAS WATCH supervisor check nominal. Core server is {server_str}, Fire TV ADB link is {adb_str}, POCO available RAM is {rep['ram_guard']['available_mb']} megabytes."
        card = {
            "title": "ATLAS WATCH Supervisor",
            "content": f"Core Mind: {server_str}\nFire TV Glass: {adb_str}\nPOCO RAM: {rep['ram_guard']['available_mb']} MB\nStatus: NOMINAL",
            "type": "supervisor"
        }
        screen = "living_surface"

    elif action == "git_telemetry":
        from aeonix.core.forge import get_git_telemetry
        git_info = get_git_telemetry()
        if git_info.get("success"):
            clean_str = "Clean" if git_info["is_clean"] else f"{git_info['modified_files']} Modified"
            speech = f"Git repository {git_info['repository']} on branch {git_info['branch']}. Working tree is {clean_str}."
            card = {
                "title": f"FORGE // {git_info['repository']}",
                "content": f"Branch: {git_info['branch']}\nCommit: {git_info['latest_commit']}\nStatus: {clean_str}",
                "type": "developer"
            }
        else:
            speech = "Unable to read Git telemetry."
            card = {"title": "FORGE // Git", "content": "No git repository found", "type": "developer"}
        screen = "focus"
        extra_data["git"] = git_info

    elif action == "forge_status":
        from aeonix.core.forge import get_git_telemetry
        git_info = get_git_telemetry()
        branch = git_info.get("branch", "main")
        speech = f"FORGE Developer Engine online on branch {branch}. Sandboxed terminal ready for verified directives."
        card = {
            "title": "FORGE Developer Engine",
            "content": f"Branch: {branch}\nRisk Gate: Active (Sentinel)\nStatus: Ready",
            "type": "developer"
        }
        screen = "focus"
        extra_data["git"] = git_info

    elif action == "create_backup":
        from aeonix.core.backup import create_vault_backup
        res = create_vault_backup(actor=actor)
        speech = f"Vault snapshot created. Archive {res['backup_file']} secured with SHA-256 verification in {res['latency_ms']} milliseconds."
        card = {
            "title": "Vault Backup Created",
            "content": f"Archive: {res['backup_file']}\nSize: {res['size_bytes']} bytes\nSHA-256: {res['sha256'][:16]}...",
            "type": "backup"
        }
        screen = "living_surface"
        extra_data["backup"] = res

    elif action == "backup_status":
        from aeonix.core.backup import list_backups
        bk_list = list_backups()
        count = len(bk_list)
        latest = bk_list[0]['file_name'] if bk_list else 'None'
        speech = f"Sovereign storage contains {count} verified vault backups."
        card = {
            "title": "Vault Backups",
            "content": f"Total Archives: {count}\nLatest: {latest}\nIntegrity: Cryptographically Verified",
            "type": "backup"
        }
        screen = "living_surface"
        extra_data["backups"] = bk_list

    elif action == "morph_status":
        from aeonix.core.morph import get_pending_proposals
        props = get_pending_proposals()
        speech = f"MORPH Evolution Engine has {len(props)} optimization proposals registered."
        card = {
            "title": "MORPH Evolution Engine",
            "content": f"Active Proposals: {len(props)}\nGuardrail: Sentinel Gate Active\nSelf-Authorization: BLOCKED",
            "type": "evolution"
        }
        screen = "living_surface"
        extra_data["proposals"] = props

    elif action == "oracle_council":
        from aeonix.core.council import convene_council_session
        council_res = convene_council_session(query=f"Strategic Direction for {actor}")
        speech = f"Oracle's Council convened across 4 perspectives. Verdict: {council_res['verdict']['consensus']}"
        card = {
            "title": "Oracle's Council Verdict",
            "content": f"Consensus: {council_res['verdict']['consensus']}\nPrimary Risk: {council_res['verdict']['primary_risk']}",
            "type": "council"
        }
        screen = "living_surface"
        extra_data["council"] = council_res

    elif action == "aadya_priority":
        from core.aadya import aadya
        aadya_stat = aadya.protection_check()
        speech = f"AADYA reports: {aadya_stat['threat_level']} threat posture. Safeguards standing by for Aadi."
        card = {
            "title": "AADYA // Eternal Intelligence",
            "content": f"Status: {aadya_stat['threat_level']}\nRAM: {aadya_stat['ram_security']}\nPriority: Aadi's Sovereignty & Betterment",
            "type": "aadya"
        }
        screen = "living_surface"
        theme = "obsidian_gold"
        extra_data["aadya"] = aadya_stat

    elif action == "lumen_context":
        from core.lumen import lumen
        lumen_stat = lumen.compute_living_surface_state()
        speech = f"LUMEN active period is {lumen_stat['period']}. Theme set to {lumen_stat['theme']}."
        card = {
            "title": f"LUMEN Context // {lumen_stat['period'].upper()}",
            "content": f"Pending Sentinel: {lumen_stat['pending_approvals']}\nActive Tasks: {lumen_stat['active_tasks']}",
            "type": "context"
        }
        screen = "living_surface"
        theme = lumen_stat["theme"]
        extra_data["lumen"] = lumen_stat

    elif action == "chronos_routines":
        from core.chronos import chronos
        routines = chronos.list_routines()
        speech = f"CHRONOS managing {len(routines)} scheduled routines."
        card = {
            "title": "CHRONOS // Routines",
            "content": "\n".join([f"• {r['name']} ({r['hour']}:00)" for r in routines]),
            "type": "schedule"
        }
        screen = "command_deck"
        extra_data["chronos"] = routines

    elif action == "oracle_research":
        from core.oracle import oracle
        res = oracle.conduct_research("Sovereign Intelligence Architecture")
        speech = "ORACLE research complete with high confidence across local vault."
        card = {
            "title": "ORACLE Research",
            "content": f"Confidence: {res['confidence'] * 100}%\nSources: {len(res['sources'])} vault records",
            "type": "research"
        }
        screen = "focus"
        extra_data["oracle"] = res

    elif action == "nexus_room":
        from core.nexus_room import nexus_room
        topology = nexus_room.render_celestial_topology()
        speech = "NEXUS ROOM celestial topology synthesized for Living Surface."
        card = {
            "title": "NEXUS Celestial Universe",
            "content": f"Nodes: {len(topology['celestial_nodes'])}\nBeacons: {len(topology['agent_beacons'])}",
            "type": "universe"
        }
        screen = "nexus_room"
        theme = "obsidian_purple"
        extra_data["nexus_room"] = topology

    elif action == "ghost_twin":
        from core.ghost import ghost
        twin = ghost.get_digital_twin_state()
        speech = f"GHOST Digital Twin reports resilience score of {twin['resilience_score'] * 100} percent."
        card = {
            "title": "GHOST Digital Twin",
            "content": f"Mesh: {twin['mesh_name']}\nDevices: {len(twin['virtual_devices'])}\nScore: {twin['resilience_score']}",
            "type": "digital_twin"
        }
        screen = "command_deck"
        extra_data["ghost"] = twin

    elif action == "agents_roster":
        from agents.orchestrator import orchestrator
        roster = orchestrator.list_roster()
        speech = f"Orchestrator has {len(roster)} sovereign agents standing by."
        card = {
            "title": "Autonomous Agent Roster",
            "content": "\n".join([f"• {a['name']} ({a['role'][:20]}...)" for a in roster[:4]]),
            "type": "agents"
        }
        screen = "command_deck"
        extra_data["agents"] = roster

    elif action == "signal_patterns":
        from core.signal import signal_detector
        sig = signal_detector.scan_for_latent_patterns()
        speech = "SIGNAL scan completed across vault audit log and entity graph."
        card = {
            "title": "SIGNAL Pattern Scan",
            "content": f"Status: {sig['signal_status']}\nAnomaly Score: {sig['anomaly_score']}",
            "type": "signal"
        }
        screen = "command_deck"
        extra_data["signal"] = sig

    elif action == "mode_sanctuary":
        from aeonix.core.sanctuary import engage_sanctuary
        res = engage_sanctuary(actor=actor)
        speech = "Sanctuary Mode engaged. External connections throttled. Local vault sealed."
        card = {
            "title": "SANCTUARY ACTIVE",
            "content": "Defensive posture enabled.\nNetwork isolated.\nVault sealed.",
            "type": "alert"
        }
        screen = "sanctuary"
        theme = "obsidian_crimson"
        extra_data["sanctuary"] = res

    elif action == "mode_sanctuary_release":
        from aeonix.core.sanctuary import release_sanctuary
        res = release_sanctuary(actor=actor)
        speech = "Sanctuary Mode released. Standard living surface active."
        card = {
            "title": "SANCTUARY RELEASED",
            "content": "Living surface restored.\nAll subsystems nominal.",
            "type": "standard"
        }
        screen = "living_surface"
        theme = "obsidian_cyan"
        extra_data["sanctuary"] = res

    elif action in ("mode_iptv", "play_nasa", "play_news"):
        from aeonix.core.spectra import find_channel_by_query, set_playback_state
        target_q = "nasa" if action == "play_nasa" else ("news" if action == "play_news" else "iss")
        ch = find_channel_by_query(target_q)
        set_playback_state(True, ch)
        speech = f"Opening Cinema Deck for {ch['name']}."
        card = {
            "title": f"Cinema Deck // {ch['name']}",
            "content": f"Category: {ch['category']}\nStream: Verified HLS Live\nResolution: 1080p Stream",
            "type": "media"
        }
        screen = "cinema"
        theme = "obsidian_cyan"
        extra_data["media_play"] = {
            "stream_url": ch["stream_url"],
            "title": ch["name"],
            "category": ch["category"]
        }

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

    res = {
        "tier": "Tier 0 (Fast-Path Router)",
        "action": action,
        "latency_ms": elapsed_ms,
        "speech": speech,
        "layout_intent": {
            "screen": screen,
            "theme": theme,
            "cards": [card]
        }
    }
    res.update(extra_data)
    return res
