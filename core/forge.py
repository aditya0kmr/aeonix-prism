"""
ÆONIX PRISM // FORGE Autonomous Developer Engine
Natural-language terminal assistant, sandboxed execution, git telemetry, and Sentinel-gated risk control.
Zero Cloud Dependencies.
"""

import os
import re
import time
import subprocess
from typing import Dict, Any, List, Optional

from aeonix.core.db import get_connection, log_audit_event, queue_sentinel_request

# Consequential / Destructive command patterns
CRITICAL_PATTERNS = [
    r"\brm\s+-[rf]{1,2}\b",
    r"\bdd\b",
    r"\bmkfs\b",
    r"\breboot\b",
    r"\bshutdown\b",
    r"\bformat\b",
    r"\bchmod\s+-R\s+777\b"
]

HIGH_RISK_PATTERNS = [
    r"\brm\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+push\s+.*--force\b",
    r"\bgit\s+clean\s+-[xfd]{1,3}\b",
    r"\biptables\b",
    r"\bpkill\b",
    r"\bkill\s+-9\b"
]

SAFE_COMMANDS = [
    "git status", "git log", "git diff", "git branch",
    "ls", "pwd", "uname", "df", "free", "uptime", "ps", "cat", "whoami"
]

def assess_command_risk(command: str) -> Dict[str, Any]:
    """Evaluates the consequential risk level of a shell command."""
    clean = command.strip()
    
    # Check critical patterns
    for pat in CRITICAL_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE):
            return {
                "risk_level": "R4_CRITICAL",
                "is_consequential": True,
                "reason": "Potentially destructive or system-altering operation"
            }
            
    # Check high risk patterns
    for pat in HIGH_RISK_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE):
            return {
                "risk_level": "R3_HIGH",
                "is_consequential": True,
                "reason": "Alters files, process state, or git history"
            }

    # Safe read-only commands
    first_word = clean.split()[0] if clean else ""
    if any(clean.startswith(safe) for safe in SAFE_COMMANDS) or first_word in ("ls", "cat", "echo", "pwd", "git"):
        if not any(re.search(p, clean) for p in HIGH_RISK_PATTERNS):
            return {
                "risk_level": "R0_SAFE",
                "is_consequential": False,
                "reason": "Read-only inspection or standard build operation"
            }

    return {
        "risk_level": "R1_MODERATE",
        "is_consequential": False,
        "reason": "Standard non-destructive command"
    }

def draft_command_from_prompt(prompt: str) -> Dict[str, Any]:
    """Translates natural language directive into an exact shell command."""
    p = prompt.strip().lower()

    if "git status" in p or "repo status" in p:
        cmd = "git status --short"
        desc = "Inspect current Git repository working tree status"
    elif "git log" in p or "recent commit" in p or "commit history" in p:
        cmd = "git log -n 5 --oneline"
        desc = "View 5 most recent Git commits"
    elif "git diff" in p or "show changes" in p:
        cmd = "git diff --stat"
        desc = "Show statistics of unstaged file modifications"
    elif "disk" in p or "storage" in p or "free space" in p:
        cmd = "df -h ."
        desc = "Check disk storage usage and available space"
    elif "uptime" in p or "system running" in p:
        cmd = "uptime"
        desc = "Check device uptime and load averages"
    elif "memory" in p or "free ram" in p:
        cmd = "free -m"
        desc = "Inspect memory buffer and swap telemetry"
    elif "rebuild launcher" in p or "compile apk" in p:
        cmd = "cd /data/data/com.termux/files/home/aether-launcher && ./gradlew assembleDebug"
        desc = "Compile debug APK for Fire TV Living Surface"
    elif "delete" in p or "remove" in p:
        target = p.split()[-1]
        cmd = f"rm -i {target}"
        desc = f"Safely remove file {target}"
    elif "kill server" in p or "restart server" in p:
        cmd = "pkill -f uvicorn"
        desc = "Terminate running ASGI server daemon"
    else:
        cmd = f"echo 'Unrecognized directive: {prompt}'"
        desc = "Echo unmapped command"

    risk = assess_command_risk(cmd)
    return {
        "prompt": prompt,
        "drafted_command": cmd,
        "description": desc,
        "risk": risk
    }

def execute_sandboxed_command(command: str, actor: str = "Aadi", cwd: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes a shell command after verifying Sentinel risk guardrails.
    Commands with risk >= R3 CANNOT execute without explicit Sentinel authorization!
    """
    risk_info = assess_command_risk(command)
    
    if risk_info["is_consequential"] and risk_info["risk_level"] in ("R3_HIGH", "R4_CRITICAL"):
        # MUST halt at Sentinel Gate
        req_id = queue_sentinel_request(
            agent="FORGE",
            action_class="DEVELOPER_EXECUTION",
            action_type="SHELL_COMMAND",
            target=command,
            scope={"cwd": cwd or os.getcwd(), "reason": risk_info["reason"]},
            risk_level=risk_info["risk_level"],
            ttl_seconds=300
        )
        return {
            "status": "sentinel_gate_hold",
            "request_id": req_id,
            "command": command,
            "risk": risk_info,
            "message": "Destructive or consequential command halted at Sentinel Gate. Approval required on Living Surface."
        }

    # Execute safe command
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd or "/data/data/com.termux/files/home/aeonix",
            text=True,
            capture_output=True,
            timeout=15.0
        )
        dt = round((time.perf_counter() - t0) * 1000, 2)
        output = proc.stdout if proc.returncode == 0 else proc.stderr

        log_audit_event(
            actor=actor,
            action="forge_command_executed",
            target=command,
            result="success" if proc.returncode == 0 else "error",
            details={"exit_code": proc.returncode, "latency_ms": dt}
        )

        return {
            "status": "executed",
            "command": command,
            "exit_code": proc.returncode,
            "output": output.strip(),
            "latency_ms": dt,
            "risk": risk_info
        }
    except Exception as e:
        return {
            "status": "error",
            "command": command,
            "error": str(e),
            "risk": risk_info
        }

def get_git_telemetry(repo_dir: str = "/data/data/com.termux/files/home/aeonix") -> Dict[str, Any]:
    """Fetches Git repository status and branch telemetry."""
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=repo_dir, text=True, timeout=3.0
        ).strip()
        last_commit = subprocess.check_output(
            ["git", "log", "-n", "1", "--format=%h - %s (%cr)"], cwd=repo_dir, text=True, timeout=3.0
        ).strip()
        diff_stat = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo_dir, text=True, timeout=3.0
        ).strip()
        modified_count = len(diff_stat.splitlines()) if diff_stat else 0

        return {
            "success": True,
            "repository": os.path.basename(repo_dir),
            "branch": branch,
            "latest_commit": last_commit,
            "modified_files": modified_count,
            "is_clean": modified_count == 0
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

draft_command = draft_command_from_prompt
get_git_status = get_git_telemetry
