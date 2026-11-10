"""
ÆONIX PRISM // Dynamic RAM Guard Subsystem
Guarantees safety before launching local LLM inference on Dimensity 810 ARM NEON.
Enforces model-specific free-RAM thresholds:
- Qwen2.5-0.5B: >= 1.2 GB (1,200,000 KB)
- Qwen2.5-1.5B: >= 2.5 GB (2,500,000 KB)
- Qwen2.5-3B:   >= 4.0 GB (4,000,000 KB)
Protects against the Android Low-Memory Killer (LMK) and Phantom Process limits.
"""

import os
import subprocess
from typing import Dict, Any, Optional

MODEL_RAM_THRESHOLDS_KB = {
    "0.5B": 1200000,
    "1.5B": 2500000,
    "3B": 4000000,
    "3.0B": 4000000,
    "fast": 1200000,
    "deep": 2500000,
    "qwen2.5-0.5b": 1200000,
    "qwen2.5-1.5b": 2500000,
    "qwen2.5-3b": 4000000,
}

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
    Default threshold: ~800MB available RAM for base system operations.
    """
    mem = get_memory_info()
    available_kb = mem.get("MemAvailable", mem.get("MemFree", 0))
    child_count = get_child_process_count()

    is_safe = available_kb >= threshold_kb

    return {
        "is_safe": is_safe,
        "available_mb": round(available_kb / 1024, 1),
        "threshold_mb": round(threshold_kb / 1024, 1),
        "available_kb": available_kb,
        "threshold_kb": threshold_kb,
        "child_processes": child_count,
        "process_limit_ok": child_count < 24
    }

def check_model_ram_guard(model_tier: str = "0.5B", mock_free_kb: Optional[int] = None) -> Dict[str, Any]:
    """
    Evaluates free RAM against model-specific requirements:
    - 0.5B: >= 1.2 GB (1,200,000 KB)
    - 1.5B: >= 2.5 GB (2,500,000 KB)
    - 3.0B: >= 4.0 GB (4,000,000 KB)
    """
    norm = str(model_tier).strip().lower()
    if "3" in norm:
        target_tier = "3B"
    elif "1.5" in norm or "deep" in norm:
        target_tier = "1.5B"
    else:
        target_tier = "0.5B"

    threshold_kb = MODEL_RAM_THRESHOLDS_KB.get(target_tier, 1200000)

    if mock_free_kb is not None:
        available_kb = mock_free_kb
        child_count = 1
    else:
        mem = get_memory_info()
        available_kb = mem.get("MemAvailable", mem.get("MemFree", 0))
        child_count = get_child_process_count()

    is_safe = available_kb >= threshold_kb

    return {
        "is_safe": is_safe,
        "model_tier": target_tier,
        "available_mb": round(available_kb / 1024, 1),
        "threshold_mb": round(threshold_kb / 1024, 1),
        "available_kb": available_kb,
        "threshold_kb": threshold_kb,
        "child_processes": child_count,
        "process_limit_ok": child_count < 24
    }

get_ram_status = check_ram_guard
