import os
import subprocess
from typing import Dict, Any

def get_memory_info() -> Dict[str, int]:
    """Reads /proc/meminfo and returns values in KB."""
    meminfo = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    meminfo[key] = int(val)
    except Exception as e:
        meminfo["MemAvailable"] = 0
        meminfo["MemFree"] = 0
        meminfo["error"] = str(e)
    return meminfo

def get_child_process_count() -> int:
    """Returns number of child processes for the current user to prevent Android Phantom Process limits."""
    try:
        res = subprocess.run(["ps", "-u", str(os.getuid())], capture_output=True, text=True)
        lines = [l for l in res.stdout.strip().split("\n") if l]
        return max(0, len(lines) - 1)
    except Exception:
        return 1

def check_ram_guard(threshold_kb: int = 800000) -> Dict[str, Any]:
    """
    Guarantees safety before launching local LLM inference.
    Default threshold: ~800MB (0.8GB) available RAM.
    """
    mem = get_memory_info()
    available_kb = mem.get("MemAvailable", mem.get("MemFree", 0))
    child_count = get_child_process_count()

    is_safe = (available_kb >= threshold_kb) and (child_count < 24)

    return {
        "is_safe": is_safe,
        "available_mb": round(available_kb / 1024, 1),
        "threshold_mb": round(threshold_kb / 1024, 1),
        "child_processes": child_count,
        "process_limit_ok": child_count < 24
    }
