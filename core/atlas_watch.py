"""
ÆONIX PRISM // ATLAS WATCH Self-Healing Supervisor Daemon
Monitors Core Server, POCO RAM budget, Fire TV ADB link, and Living Surface UI.
Automatically heals degraded workers and recovers connectivity.
"""

import os
import sys
import time
import subprocess
import httpx
from typing import Dict, Any

from aeonix.core.ram_guard import check_ram_guard
from aeonix.core.db import log_audit_event

CORE_STATUS_URL = "http://127.0.0.1:8080/api/status"
FIRETV_ADB_TARGET = "10.116.23.179:5555"
FIRETV_COMPONENT = "com.aether.launcher/com.gathin.tvhome.MainActivity"

def check_core_server() -> Dict[str, Any]:
    """Verifies that POCO Core Mind ASGI daemon is responsive via non-blocking TCP socket connect."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 8080), timeout=1.0):
            return {"online": True}
    except Exception as e:
        return {"online": False, "error": str(e)}

def heal_core_server():
    """Restarts the Core Mind server daemon if crashed."""
    script_path = os.path.expanduser("~/aeonix/scripts/start-core.sh")
    subprocess.Popen(["bash", script_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log_audit_event("ATLAS_WATCH", "self_heal_core_server", "aeonix_core", "restarted", {})

def check_firetv_adb() -> bool:
    """Verifies ADB connectivity to the Fire TV Stick Lite."""
    try:
        out = subprocess.check_output(["adb", "devices"], text=True, timeout=3.0)
        return f"{FIRETV_ADB_TARGET}\tdevice" in out
    except Exception:
        return False

def heal_firetv_adb():
    """Re-establishes ADB TCP connection to the Fire TV."""
    try:
        subprocess.run(["adb", "connect", FIRETV_ADB_TARGET], timeout=5.0, capture_output=True)
        log_audit_event("ATLAS_WATCH", "self_heal_adb_link", FIRETV_ADB_TARGET, "reconnected", {})
    except Exception:
        pass

def check_firetv_launcher() -> bool:
    """Verifies that the Living Surface launcher is active on the Fire TV."""
    try:
        out = subprocess.check_output(
            ["adb", "-s", FIRETV_ADB_TARGET, "shell", "dumpsys", "activity", "activities"], 
            text=True, 
            timeout=4.0
        )
        return "com.aether.launcher" in out
    except Exception:
        return False

def heal_firetv_launcher():
    """Restarts the Living Surface launcher on the Fire TV."""
    try:
        subprocess.run([
            "adb", "-s", FIRETV_ADB_TARGET, "shell", "am", "start", "-n", FIRETV_COMPONENT
        ], timeout=5.0, capture_output=True)
        log_audit_event("ATLAS_WATCH", "self_heal_living_surface", FIRETV_COMPONENT, "launched", {})
    except Exception:
        pass

def run_supervisor_cycle() -> Dict[str, Any]:
    """Runs a single supervisory check and healing pass across all sovereign nodes."""
    cycle_report = {
        "timestamp": time.time(),
        "core_server": None,
        "ram_guard": None,
        "firetv_adb": None,
        "firetv_launcher": None,
        "healed_actions": []
    }
    
    # 1. Core Server Health
    server_stat = check_core_server()
    cycle_report["core_server"] = server_stat["online"]
    if not server_stat["online"]:
        heal_core_server()
        cycle_report["healed_actions"].append("core_server_restarted")
    
    # 2. POCO RAM Guard
    ram_stat = check_ram_guard()
    cycle_report["ram_guard"] = ram_stat
    if not ram_stat["is_safe"]:
        # Emergency RAM relief: stop LLM runner
        try:
            from aeonix.core.llama_runner import llama_runner
            llama_runner.stop_server()
            cycle_report["healed_actions"].append("llama_runner_unloaded_for_ram")
        except Exception:
            pass
            
    # 3. Fire TV ADB Connectivity
    adb_ok = check_firetv_adb()
    cycle_report["firetv_adb"] = adb_ok
    if not adb_ok:
        heal_firetv_adb()
        cycle_report["healed_actions"].append("adb_link_reconnected")
    else:
        # 4. Living Surface Process
        launcher_ok = check_firetv_launcher()
        cycle_report["firetv_launcher"] = launcher_ok
        if not launcher_ok:
            heal_firetv_launcher()
            cycle_report["healed_actions"].append("living_surface_relaunched")
            
    return cycle_report

if __name__ == "__main__":
    print("Executing ATLAS WATCH Supervisor Cycle...")
    t0 = time.time()
    rep = run_supervisor_cycle()
    dt = time.time() - t0
    print(f"Supervisor cycle completed in {dt:.2f}s:")
    print(f"  • Core Server: {'ONLINE' if rep['core_server'] else 'HEALED'}")
    print(f"  • POCO RAM: {rep['ram_guard']['available_mb']} MB (Safe: {rep['ram_guard']['is_safe']})")
    print(f"  • Fire TV ADB Link: {'CONNECTED' if rep['firetv_adb'] else 'HEALED'}")
    print(f"  • Living Surface: {'ACTIVE' if rep['firetv_launcher'] else 'HEALED'}")
    if rep["healed_actions"]:
        print(f"  • Healing Actions Taken: {rep['healed_actions']}")
    else:
        print("  • System Health: ALL NODES NOMINAL")
