"""
ÆONIX PRISM // FORGE Typed Developer Engine
Sandboxed execution, typed allowlisted operations (zero shell=True),
Git telemetry, output bounding, and Sentinel-gated risk control.
Zero Cloud Dependencies.
"""

import os
import time
import subprocess
from typing import Dict, Any, List, Optional

from aeonix.core.db import (
    log_audit_event, 
    queue_sentinel_request, 
    check_sentinel_authorization,
    consume_sentinel_authorization
)
from aeonix.core.trust import trust
from aeonix.core.sanctuary import is_sanctuary_active

# Allowed safe working directories
ALLOWED_BASE_DIRS = [
    "/data/data/com.termux/files/home/aeonix",
    "/data/data/com.termux/files/home"
]

# Typed Operations Catalog
TYPED_OPERATIONS = {
    "git_status": {
        "binary": "git",
        "fixed_args": ["status", "--short"],
        "risk_level": "R0_SAFE",
        "is_consequential": False,
        "description": "Inspect Git repository working tree status"
    },
    "git_log": {
        "binary": "git",
        "fixed_args": ["log", "-n", "5", "--oneline"],
        "risk_level": "R0_SAFE",
        "is_consequential": False,
        "description": "View recent Git commit log"
    },
    "git_diff": {
        "binary": "git",
        "fixed_args": ["diff", "--stat"],
        "risk_level": "R0_SAFE",
        "is_consequential": False,
        "description": "Show statistics of unstaged file modifications"
    },
    "git_branch": {
        "binary": "git",
        "fixed_args": ["branch", "-a"],
        "risk_level": "R0_SAFE",
        "is_consequential": False,
        "description": "List repository branches"
    },
    "disk_usage": {
        "binary": "df",
        "fixed_args": ["-h", "."],
        "risk_level": "R0_SAFE",
        "is_consequential": False,
        "description": "Check local storage usage"
    },
    "memory_usage": {
        "binary": "free",
        "fixed_args": ["-m"],
        "risk_level": "R0_SAFE",
        "is_consequential": False,
        "description": "Inspect memory telemetry"
    },
    "system_uptime": {
        "binary": "uptime",
        "fixed_args": [],
        "risk_level": "R0_SAFE",
        "is_consequential": False,
        "description": "Check device uptime and load"
    },
    "file_list": {
        "binary": "ls",
        "fixed_args": ["-la"],
        "risk_level": "R0_SAFE",
        "is_consequential": False,
        "description": "List directory contents"
    },
    "echo": {
        "binary": "echo",
        "fixed_args": [],
        "risk_level": "R0_SAFE",
        "is_consequential": False,
        "description": "Safe text echo output"
    },
    "file_remove": {
        "binary": "rm",
        "fixed_args": ["-f"],
        "risk_level": "R3_HIGH",
        "is_consequential": True,
        "description": "Remove a specific target file"
    }
}

def _validate_path(target_path: Optional[str]) -> str:
    """Ensures working directory is within allowed boundaries."""
    if not target_path:
        return ALLOWED_BASE_DIRS[0]
    
    real_path = os.path.realpath(os.path.expanduser(target_path))
    for allowed in ALLOWED_BASE_DIRS:
        if real_path == allowed or real_path.startswith(allowed + "/"):
            return real_path
            
    raise PermissionError(f"Path access outside allowed boundaries: {target_path}")

def assess_command_risk(command: str) -> Dict[str, Any]:
    """Evaluates consequential risk of a command/operation."""
    clean = command.strip().lower()
    if "-rf" in clean or "format" in clean or "drop" in clean or "reboot" in clean:
        return {
            "risk_level": "R4_CRITICAL",
            "is_consequential": True,
            "reason": "Destructive or recursive system action"
        }
    if clean.startswith("rm") or "delete" in clean or "remove" in clean:
        return {
            "risk_level": "R3_HIGH",
            "is_consequential": True,
            "reason": "Deletes or modifies persistent filesystem artifacts"
        }
    return {
        "risk_level": "R0_SAFE",
        "is_consequential": False,
        "reason": "Read-only inspection or standard build operation"
    }

def draft_command_from_prompt(prompt: str) -> Dict[str, Any]:
    """Translates natural language directive into a typed, verified operation."""
    p = prompt.strip().lower()

    if p.startswith("echo"):
        op_name = "echo"
    elif "git status" in p or "repo status" in p:
        op_name = "git_status"
    elif "git log" in p or "recent commit" in p or "commit history" in p:
        op_name = "git_log"
    elif "git diff" in p or "show changes" in p:
        op_name = "git_diff"
    elif "git branch" in p:
        op_name = "git_branch"
    elif "disk" in p or "storage" in p or "free space" in p:
        op_name = "disk_usage"
    elif "uptime" in p or "system running" in p:
        op_name = "system_uptime"
    elif "memory" in p or "free ram" in p:
        op_name = "memory_usage"
    elif "list file" in p or "directory" in p:
        op_name = "file_list"
    elif "delete" in p or "remove" in p or p.startswith("rm"):
        op_name = "file_remove"
    else:
        op_name = "git_status"

    op = TYPED_OPERATIONS[op_name]
    cmd_str = f"{op['binary']} {' '.join(op['fixed_args'])}".strip()
    risk_dict = {
        "risk_level": op["risk_level"],
        "risk_tier": op["risk_level"].split("_")[0],
        "is_consequential": op["is_consequential"],
        "reason": op["description"],
        "rationale": op["description"]
    }
    return {
        "operation": op_name,
        "command": cmd_str,
        "drafted_command": cmd_str,
        "description": op["description"],
        "risk": risk_dict,
        "risk_assessment": risk_dict
    }

def execute_typed_operation(
    operation_name: str,
    extra_args: Optional[List[str]] = None,
    cwd: Optional[str] = None,
    sentinel_request_id: Optional[str] = None,
    actor: str = "Aadi",
    actor_role: str = "POCO_CORE"
) -> Dict[str, Any]:
    """
    Executes a typed allowlisted operation WITHOUT shell=True.
    Consequential operations require valid, non-expired Sentinel approval.
    """
    if trust.is_kill_switch_active():
        return {
            "success": False,
            "error": "EXECUTION_BLOCKED: Emergency Kill Switch is ENGAGED",
            "status": "kill_switch_hold"
        }

    if is_sanctuary_active():
        return {
            "success": False,
            "error": "EXECUTION_BLOCKED: Sanctuary Privacy Lockdown is ACTIVE",
            "status": "sanctuary_hold"
        }

    if operation_name not in TYPED_OPERATIONS:
        return {
            "success": False,
            "error": f"UNKNOWN_OPERATION: Operation '{operation_name}' is not in the typed catalog",
            "status": "denied"
        }

    op = TYPED_OPERATIONS[operation_name]
    safe_cwd = _validate_path(cwd)

    # Consequential Gate
    if op["is_consequential"]:
        if not sentinel_request_id:
            # Enqueue Sentinel request
            req_id = queue_sentinel_request(
                agent="FORGE",
                action_class="DEVELOPER_EXECUTION",
                action_type=f"TYPED_OP_{operation_name.upper()}",
                target=f"{op['binary']} {operation_name}",
                scope={"cwd": safe_cwd, "extra_args": extra_args or []},
                risk_level=op["risk_level"],
                ttl_seconds=300
            )
            return {
                "success": False,
                "status": "sentinel_gate_hold",
                "request_id": req_id,
                "operation": operation_name,
                "message": f"Consequential operation '{operation_name}' halted at Sentinel Gate. Approval required on POCO Core Mind."
            }

        # Atomically verify and consume authorization: binds to this single execution
        expected_target = f"{op['binary']} {operation_name}"
        expected_action = f"TYPED_OP_{operation_name.upper()}"
        is_auth, req_data, auth_reason = consume_sentinel_authorization(
            sentinel_request_id,
            expected_target=expected_target,
            expected_action=expected_action
        )
        if not is_auth:
            return {
                "success": False,
                "status": "authorization_rejected",
                "reason": auth_reason,
                "error": f"Execution rejected: {auth_reason}"
            }

    # Construct strict argument list
    arg_list = [op["binary"]] + list(op["fixed_args"])
    if extra_args:
        # Sanitize extra args: ensure no semicolons or pipe symbols
        for a in extra_args:
            clean_arg = str(a).strip()
            if any(char in clean_arg for char in [";", "|", "&", "$", "`", "\n"]):
                return {
                    "success": False,
                    "error": f"ILLEGAL_ARGUMENT: Shell metacharacters are prohibited: {clean_arg}",
                    "status": "denied"
                }
            if operation_name == "file_remove":
                base_name = os.path.basename(clean_arg)
                if base_name in [".git", ".ssh", "aeonix_vault.db", "vault.db", "models", "bin", "data"]:
                    return {
                        "success": False,
                        "error": f"PROTECTED_RESOURCE: Removal of critical system artifact '{base_name}' is strictly prohibited.",
                        "status": "denied"
                    }
            arg_list.append(clean_arg)

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            arg_list,
            shell=False, # STRICTLY FALSE
            cwd=safe_cwd,
            text=True,
            capture_output=True,
            timeout=10.0
        )
        dt = round((time.perf_counter() - t0) * 1000, 2)
        raw_output = (proc.stdout if proc.returncode == 0 else proc.stderr).strip()
        
        # Enforce output bounds (max 64KB)
        bounded_output = raw_output[:65536]
        is_truncated = len(raw_output) > 65536

        log_audit_event(
            actor=f"{actor} ({actor_role})",
            action="forge_typed_executed",
            target=operation_name,
            result="success" if proc.returncode == 0 else "error",
            details={
                "exit_code": proc.returncode,
                "latency_ms": dt,
                "truncated": is_truncated
            }
        )

        return {
            "success": proc.returncode == 0,
            "status": "completed" if proc.returncode == 0 else "error",
            "operation": operation_name,
            "exit_code": proc.returncode,
            "output": bounded_output,
            "truncated": is_truncated,
            "latency_ms": dt
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "status": "timeout",
            "error": "EXECUTION_TIMEOUT: Operation exceeded 10.0s time limit"
        }
    except Exception as e:
        return {
            "success": False,
            "status": "error",
            "error": str(e)
        }

def execute_sandboxed_command(command: str, actor: str = "Aadi", cwd: Optional[str] = None) -> Dict[str, Any]:
    """Compatibility adapter: maps shell requests to typed operations."""
    draft = draft_command_from_prompt(command)
    op_name = draft["operation"]
    extra_args = None
    if op_name == "echo":
        cmd_str = command.strip()
        if cmd_str.startswith("echo"):
            arg = cmd_str[4:].strip().strip("'\"")
            extra_args = [arg]
    res = execute_typed_operation(op_name, extra_args=extra_args, cwd=cwd, actor=actor)
    if res.get("status") == "completed":
        res["status"] = "executed"
    return res

def get_git_telemetry(repo_path: str = "/data/data/com.termux/files/home/aeonix") -> Dict[str, Any]:
    """Extracts local Git telemetry via typed operations."""
    safe_path = _validate_path(repo_path)
    if not os.path.exists(os.path.join(safe_path, ".git")):
        return {"success": False, "error": "Not a git repository"}

    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], 
            cwd=safe_path, text=True, stderr=subprocess.DEVNULL
        ).strip()

        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], 
            cwd=safe_path, text=True, stderr=subprocess.DEVNULL
        ).strip()

        status_raw = subprocess.check_output(
            ["git", "status", "--porcelain"], 
            cwd=safe_path, text=True, stderr=subprocess.DEVNULL
        ).strip()

        modified_count = len(status_raw.splitlines()) if status_raw else 0

        return {
            "success": True,
            "repository": os.path.basename(safe_path),
            "branch": branch,
            "latest_commit": commit,
            "modified_files": modified_count,
            "is_clean": modified_count == 0
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# Backward compatibility alias
get_git_status = get_git_telemetry
draft_command = draft_command_from_prompt
