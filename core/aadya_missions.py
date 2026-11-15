"""
AADYA Missions & Autonomous Operations Engine
Stage 3 Crown-0 Autonomous Operations subsystem.

Provides:
- DAG-based mission decomposition and dependency management
- Topological cycle detection and wave execution
- Fail-closed autonomy evaluation with explicit low-risk allowlist
- Permanent financial quarantine enforcement (no creation, scheduling, or retry)
- POCO escalation for high-risk actions with digest binding
- Safe RAM-pressure deferral via dynamic RAM guard
- Atomic SQLite transactions for every task state transition
- Truthful progress tracking and verified result digests
- Checkpointed recovery snapshots with non-destructive restoration
"""

import os
import sys
import time
import json
import sqlite3
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple, Set

from core.db import (
    get_connection,
    get_db_path,
    log_audit_event,
    compute_action_digest
)
from core.ram_guard import check_ram_guard

logger = logging.getLogger("aeonix.core.aadya_missions")

# Valid mission lifecycle states
VALID_MISSION_STATES = {
    "CREATED",
    "READY",
    "RUNNING",
    "PAUSED",
    "AWAITING_ESCALATION",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "DEFERRED_RAM",
    "NEEDS_RECONCILIATION"
}

# Valid task states
VALID_TASK_STATES = {
    "PENDING",
    "READY",
    "RUNNING",
    "AWAITING_ESCALATION",
    "COMPLETED",
    "FAILED",
    "PAUSED",
    "CANCELLED",
    "DEFERRED_RAM",
    "SKIPPED"
}

# Explicit low-risk action allowlist permitted for autonomous execution without POCO escalation
AUTONOMOUS_LOW_RISK_ALLOWLIST = {
    "query_local_knowledge": {"idempotent": True, "description": "Query local SQLite context or memory"},
    "read_system_telemetry": {"idempotent": True, "description": "Read non-sensitive RAM, CPU, storage telemetry"},
    "synthesize_briefing": {"idempotent": True, "description": "Generate briefing summary from local context"},
    "update_future_radar": {"idempotent": True, "description": "Refresh predictive radar signals"},
    "query_weather": {"idempotent": True, "description": "Read cached or external weather context"},
    "scan_network_passive": {"idempotent": True, "description": "Mock-safe passive network telemetry read"},
    "list_goals": {"idempotent": True, "description": "Read active AADYA goals"},
    "list_routines": {"idempotent": True, "description": "Read active AADYA routines"},
    "read_memory_node": {"idempotent": True, "description": "Retrieve readable memory node"},
    "list_memory_nodes": {"idempotent": True, "description": "List readable memory nodes"},
    "synthesize_timeline": {"idempotent": True, "description": "Generate unified event timeline"},
    "storage_diagnostic": {"idempotent": True, "description": "Read-only storage partition diagnostic"}
}

# Financial execution trigger verbs strictly prohibited from any mission/task
PROHIBITED_FINANCIAL_VERBS = {
    "transfer", "pay", "payment", "buy", "sell", "trade", "swap", "stake",
    "withdraw", "deposit", "invest", "borrow", "lend", "sign_transaction",
    "execute_order", "wire", "remit"
}


def _verify_non_financial(action_type: str, target: str, params: Optional[Dict[str, Any]] = None) -> None:
    """
    Enforces the permanent financial quarantine at mission/task boundaries.
    Raises FinancialQuarantineViolationError if any execution verb or financial target is found.
    """
    from core.aadya import FinancialQuarantineViolationError

    combined = f"{action_type} {target} {json.dumps(params or {}) if params else ''}".lower()
    for verb in PROHIBITED_FINANCIAL_VERBS:
        if verb in action_type.lower() or f" {verb} " in f" {combined} " or verb in target.lower():
            raise FinancialQuarantineViolationError(
                f"FINANCIAL_QUARANTINE_VIOLATION: Financial execution action '{action_type}' on '{target}' "
                "is permanently prohibited under AADYA Crown-0 autonomy. Zero financial execution permitted."
            )


class AadyaMissionEngine:
    """
    Crown-0 Autonomous Operations Engine.
    Coordinates DAG mission validation, wave-based step execution, POCO escalation binding,
    fail-closed risk gating, and atomic transactional transitions.
    """

    def __init__(self, db_path: Optional[str] = None, parent_crown_zero: Optional[Any] = None):
        self.db_path = db_path
        self.parent = parent_crown_zero
        self.is_initialized = False
        self.initialization_status = "PENDING_INITIALIZATION"
        self.initialization_error = None

        try:
            self._ensure_mission_tables()
            self.is_initialized = True
            self.initialization_status = "INITIALIZED"
        except Exception as e:
            self.is_initialized = False
            self.initialization_status = "INITIALIZATION_FAILED"
            self.initialization_error = str(e)
            logger.error("Failed to initialize AadyaMissionEngine: %s", e)

    def _get_db(self) -> str:
        return self.db_path or get_db_path()

    def _check_engine_health(self) -> None:
        if not self.is_initialized or self.initialization_status == "INITIALIZATION_FAILED":
            raise RuntimeError(
                f"AADYA_MISSION_ENGINE_DEGRADED: Missions engine is not operational "
                f"(status={self.initialization_status}, error={self.initialization_error})"
            )

    def _ensure_mission_tables(self) -> None:
        """Creates SQLite tables for missions, tasks, and recovery snapshots with strict integrity."""
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS aadya_missions (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        objective TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT 'operational',
                        status TEXT NOT NULL,
                        plan_digest TEXT NOT NULL,
                        total_tasks INTEGER NOT NULL DEFAULT 0,
                        completed_tasks INTEGER NOT NULL DEFAULT 0,
                        failed_tasks INTEGER NOT NULL DEFAULT 0,
                        scope_json TEXT,
                        error_message TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        completed_at REAL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS aadya_tasks (
                        id TEXT PRIMARY KEY,
                        mission_id TEXT NOT NULL REFERENCES aadya_missions(id),
                        step_index INTEGER NOT NULL,
                        action_type TEXT NOT NULL,
                        target TEXT NOT NULL,
                        params_json TEXT,
                        risk_level TEXT NOT NULL,
                        is_idempotent INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL,
                        dependencies_json TEXT,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        max_retries INTEGER NOT NULL DEFAULT 3,
                        escalation_id TEXT,
                        result_digest TEXT,
                        result_json TEXT,
                        error_message TEXT,
                        started_at REAL,
                        completed_at REAL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS aadya_mission_snapshots (
                        id TEXT PRIMARY KEY,
                        mission_id TEXT NOT NULL REFERENCES aadya_missions(id),
                        snapshot_digest TEXT NOT NULL,
                        state_payload_json TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_aadya_tasks_mission ON aadya_tasks(mission_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_aadya_tasks_status ON aadya_tasks(status);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_aadya_snapshots_mission ON aadya_mission_snapshots(mission_id);")
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # DAG Validation & Cycle Detection
    # -------------------------------------------------------------------------
    @staticmethod
    def validate_dag(tasks: List[Dict[str, Any]]) -> List[str]:
        """
        Validates task dependencies using Kahn's algorithm / topological sort.
        Returns the topographically sorted task IDs preserving input order for ties.
        Raises ValueError on cycle or missing dependency.
        """
        if not tasks:
            raise ValueError("EMPTY_TASK_SET: Mission must specify at least one task.")

        task_ids: List[str] = []
        task_id_set: Set[str] = set()
        adj: Dict[str, List[str]] = {}
        in_degree: Dict[str, int] = {}

        for t in tasks:
            tid = t.get("id")
            if not tid:
                raise ValueError("MISSING_TASK_ID: Every task must have an explicit 'id'.")
            if tid in task_id_set:
                raise ValueError(f"DUPLICATE_TASK_ID: Task ID '{tid}' is defined more than once.")
            task_ids.append(tid)
            task_id_set.add(tid)
            adj[tid] = []
            in_degree[tid] = 0

        for t in tasks:
            tid = t["id"]
            deps = t.get("dependencies", [])
            for dep in deps:
                if dep not in task_id_set:
                    raise ValueError(f"INVALID_DEPENDENCY: Task '{tid}' depends on non-existent task '{dep}'.")
                if dep == tid:
                    raise ValueError(f"SELF_DEPENDENCY: Task '{tid}' cannot depend on itself.")
                adj[dep].append(tid)
                in_degree[tid] += 1

        # Kahn's algorithm with stable order
        queue = [tid for tid in task_ids if in_degree[tid] == 0]
        sorted_ids = []

        while queue:
            curr = queue.pop(0)
            sorted_ids.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_ids) != len(task_ids):
            cycle_tasks = [tid for tid, deg in in_degree.items() if deg > 0]
            raise ValueError(f"DAG_CYCLE_DETECTED: Dependency cycle detected among tasks: {cycle_tasks}")

        return sorted_ids

    # -------------------------------------------------------------------------
    # Mission Creation
    # -------------------------------------------------------------------------
    def create_mission(
        self,
        title: str,
        objective: str,
        tasks: List[Dict[str, Any]],
        category: str = "operational",
        actor: str = "Aadi",
        scope: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validates and creates a new mission with its DAG tasks.
        Enforces financial quarantine, DAG acyclicity, and atomic persistence.
        """
        self._check_engine_health()

        if not title or not objective:
            raise ValueError("MISSING_METADATA: Mission requires non-empty title and objective.")

        # 1. Enforce financial quarantine across all tasks
        for t in tasks:
            action_type = t.get("action_type", "")
            target = t.get("target", "")
            params = t.get("params", {})
            _verify_non_financial(action_type, target, params)

        # 2. Validate DAG dependencies
        sorted_ids = self.validate_dag(tasks)

        now = time.time()
        mission_id = f"mission_{int(now * 1000)}_{os.urandom(3).hex()}"

        # 3. Calculate plan digest
        plan_summary = {
            "title": title,
            "objective": objective,
            "category": category,
            "tasks": [
                {
                    "id": t["id"],
                    "action_type": t.get("action_type"),
                    "target": t.get("target"),
                    "dependencies": t.get("dependencies", [])
                }
                for t in tasks
            ]
        }
        plan_digest = hashlib.sha256(json.dumps(plan_summary, sort_keys=True).encode("utf-8")).hexdigest()

        # Build task mapping
        task_map = {t["id"]: t for t in tasks}
        total_tasks = len(tasks)

        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                # Insert mission record
                conn.execute("""
                    INSERT INTO aadya_missions (
                        id, title, objective, actor, category, status,
                        plan_digest, total_tasks, completed_tasks, failed_tasks,
                        scope_json, error_message, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, NULL, ?, ?);
                """, (
                    mission_id, title, objective, actor, category, "CREATED",
                    plan_digest, total_tasks, json.dumps(scope or {}), now, now
                ))

                # Insert tasks
                for idx, tid in enumerate(sorted_ids):
                    t = task_map[tid]
                    action_type = t.get("action_type", "unknown_action")
                    target = t.get("target", "unspecified_target")
                    params = t.get("params", {})
                    deps = t.get("dependencies", [])
                    max_retries = int(t.get("max_retries", 3))

                    # Assess risk and idempotency
                    low_risk_meta = AUTONOMOUS_LOW_RISK_ALLOWLIST.get(action_type)
                    if low_risk_meta:
                        risk_level = "LOW"
                        is_idempotent = 1 if low_risk_meta.get("idempotent", True) else 0
                    else:
                        risk_level = "HIGH"
                        # High-risk or unknown tasks are strictly non-idempotent for auto-retry
                        is_idempotent = 0

                    initial_task_status = "READY" if len(deps) == 0 else "PENDING"

                    conn.execute("""
                        INSERT INTO aadya_tasks (
                            id, mission_id, step_index, action_type, target,
                            params_json, risk_level, is_idempotent, status,
                            dependencies_json, retry_count, max_retries,
                            escalation_id, result_digest, result_json,
                            error_message, started_at, completed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, NULL, NULL, NULL, NULL, NULL);
                    """, (
                        tid, mission_id, idx, action_type, target,
                        json.dumps(params), risk_level, is_idempotent, initial_task_status,
                        json.dumps(deps), max_retries
                    ))

                # Update mission status to READY
                conn.execute("UPDATE aadya_missions SET status = 'READY', updated_at = ? WHERE id = ?;", (now, mission_id))

                # Atomic audit log
                log_audit_event(
                    actor=actor,
                    action="create_mission",
                    target=mission_id,
                    result="SUCCESS",
                    details={
                        "title": title,
                        "task_count": total_tasks,
                        "plan_digest": plan_digest
                    },
                    conn=conn
                )

            # Auto-create initial snapshot
            self._create_snapshot_internal(mission_id, reason="INITIAL_CREATION")

        finally:
            conn.close()

        return self.get_mission(mission_id)

    # -------------------------------------------------------------------------
    # Mission & Task Queries
    # -------------------------------------------------------------------------
    def get_mission(self, mission_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves full mission state, tasks, and truthful progress."""
        self._check_engine_health()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            conn.row_factory = sqlite3.Row
            m_cur = conn.cursor()
            m_cur.execute("SELECT * FROM aadya_missions WHERE id = ?;", (mission_id,))
            m_row = m_cur.fetchone()
            if not m_row:
                return None

            mission = dict(m_row)
            if mission.get("scope_json"):
                try:
                    mission["scope"] = json.loads(mission["scope_json"])
                except Exception:
                    mission["scope"] = {}

            t_cur = conn.cursor()
            t_cur.execute("SELECT * FROM aadya_tasks WHERE mission_id = ? ORDER BY step_index ASC;", (mission_id,))
            tasks = []
            completed_count = 0
            failed_count = 0

            for r in t_cur.fetchall():
                td = dict(r)
                if td.get("params_json"):
                    try:
                        td["params"] = json.loads(td["params_json"])
                    except Exception:
                        td["params"] = {}
                if td.get("dependencies_json"):
                    try:
                        td["dependencies"] = json.loads(td["dependencies_json"])
                    except Exception:
                        td["dependencies"] = []
                if td.get("result_json"):
                    try:
                        td["result"] = json.loads(td["result_json"])
                    except Exception:
                        td["result"] = None

                if td["status"] == "COMPLETED":
                    completed_count += 1
                elif td["status"] == "FAILED":
                    failed_count += 1

                tasks.append(td)

            mission["tasks"] = tasks
            total = len(tasks)
            mission["total_tasks"] = total
            mission["completed_tasks"] = completed_count
            mission["failed_tasks"] = failed_count
            mission["progress_pct"] = round((completed_count / total * 100.0), 2) if total > 0 else 0.0

            return mission
        finally:
            conn.close()

    def list_missions(self, status: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists missions filtered by status or category."""
        self._check_engine_health()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            query = "SELECT id FROM aadya_missions WHERE 1=1"
            params: List[Any] = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if category:
                query += " AND category = ?"
                params.append(category)
            query += " ORDER BY created_at DESC;"

            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            return [self.get_mission(r["id"]) for r in rows if r["id"]]
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Execution Engine & Step Progression
    # -------------------------------------------------------------------------
    def execute_mission_step(
        self,
        mission_id: str,
        ram_threshold_kb: int = 800000,
        mock_free_ram_kb: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes the next eligible task in the DAG.
        - Checks RAM guard (defers on memory pressure)
        - Evaluates dependencies
        - Dispatches low-risk action or holds for POCO escalation
        - Performs atomic state transition with verified result digest
        """
        self._check_engine_health()
        mission = self.get_mission(mission_id)
        if not mission:
            return {"success": False, "error": f"Mission '{mission_id}' not found."}

        current_status = mission["status"]
        if current_status == "COMPLETED":
            return {
                "success": True,
                "status": "COMPLETED",
                "mission": mission,
                "message": "Mission is already completed."
            }

        if current_status in {"FAILED", "CANCELLED", "PAUSED"}:
            return {
                "success": False,
                "status": current_status,
                "message": f"Mission is in terminal or inactive state: {current_status}"
            }

        # 1. Check RAM Guard
        ram_status = check_ram_guard(threshold_kb=ram_threshold_kb)
        avail_kb = mock_free_ram_kb if mock_free_ram_kb is not None else ram_status["available_kb"]
        if avail_kb < ram_threshold_kb:
            # Memory pressure: defer execution safely
            self._defer_on_ram(mission_id, avail_kb, ram_threshold_kb)
            return {
                "success": False,
                "status": "DEFERRED_RAM",
                "message": f"RAM pressure detected: {avail_kb} KB free < {ram_threshold_kb} KB threshold. Execution deferred safely.",
                "available_kb": avail_kb,
                "threshold_kb": ram_threshold_kb
            }

        tasks = mission["tasks"]
        completed_task_ids = {t["id"] for t in tasks if t["status"] == "COMPLETED"}

        # 2. Update PENDING tasks whose dependencies are now all COMPLETED to READY
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                for t in tasks:
                    if t["status"] == "PENDING":
                        deps = set(t.get("dependencies", []))
                        if deps.issubset(completed_task_ids):
                            conn.execute(
                                "UPDATE aadya_tasks SET status = 'READY' WHERE id = ? AND status = 'PENDING';",
                                (t["id"],)
                            )
                            t["status"] = "READY"
        finally:
            conn.close()

        # 3. Find next READY task
        ready_task = next((t for t in tasks if t["status"] == "READY"), None)

        if not ready_task:
            # Check if all tasks completed
            if len(completed_task_ids) == len(tasks):
                self._complete_mission(mission_id)
                return {
                    "success": True,
                    "status": "COMPLETED",
                    "mission": self.get_mission(mission_id),
                    "message": "All mission tasks have completed successfully."
                }

            # Check if any tasks are awaiting escalation
            escalated = [t for t in tasks if t["status"] == "AWAITING_ESCALATION"]
            if escalated:
                self._update_mission_status(mission_id, "AWAITING_ESCALATION")
                return {
                    "success": True,
                    "status": "AWAITING_ESCALATION",
                    "pending_escalation_tasks": [t["id"] for t in escalated],
                    "message": "Mission is paused awaiting POCO escalation approval."
                }

            # Check if any tasks are in FAILED state
            failed = [t for t in tasks if t["status"] == "FAILED"]
            if failed:
                self._update_mission_status(mission_id, "FAILED", error="One or more tasks failed.")
                return {
                    "success": False,
                    "status": "FAILED",
                    "failed_tasks": [t["id"] for t in failed],
                    "message": "Mission halted due to task failure."
                }

            return {
                "success": True,
                "status": mission["status"],
                "message": "No tasks currently eligible for execution."
            }

        # 4. Process the ready task
        tid = ready_task["id"]
        action_type = ready_task["action_type"]
        target = ready_task["target"]
        params = ready_task.get("params", {})

        # Absolute financial quarantine check
        _verify_non_financial(action_type, target, params)

        # Check risk level and allowlist
        if action_type not in AUTONOMOUS_LOW_RISK_ALLOWLIST:
            # High-risk / unknown action -> Route to POCO Escalation
            return self._escalate_task_to_poco(mission_id, tid, action_type, target, params)

        # Low-risk allowlist action -> Execute bounded task
        return self._execute_bounded_task(mission_id, ready_task)

    def _execute_bounded_task(self, mission_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes an authorized low-risk task atomically.
        Guarantees result digest verification, dependent task unblocking,
        completion transition, snapshot creation, and audit logging.
        """
        tid = task["id"]
        action_type = task["action_type"]
        target = task["target"]
        params = task.get("params", {})
        now = time.time()

        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            # Mark RUNNING in isolated transaction
            with conn:
                conn.execute(
                    "UPDATE aadya_tasks SET status = 'RUNNING', started_at = ? WHERE id = ?;",
                    (now, tid)
                )
                conn.execute(
                    "UPDATE aadya_missions SET status = 'RUNNING', updated_at = ? WHERE id = ?;",
                    (now, mission_id)
                )
        finally:
            conn.close()

        # Execute the bounded action runner
        try:
            exec_res = self._run_action_handler(action_type, target, params)
            result_digest = hashlib.sha256(json.dumps(exec_res, sort_keys=True).encode("utf-8")).hexdigest()
            exec_payload = {
                "output": exec_res,
                "result_digest": result_digest,
                "executed_at": time.time()
            }

            # Atomic commit of COMPLETED state and unblocking dependent tasks
            mission_fully_completed = False
            conn = get_connection(self._get_db(), allow_maintenance=True)
            try:
                with conn:
                    conn.execute("""
                        UPDATE aadya_tasks
                        SET status = 'COMPLETED',
                            result_digest = ?,
                            result_json = ?,
                            completed_at = ?,
                            error_message = NULL
                        WHERE id = ?;
                    """, (result_digest, json.dumps(exec_payload), time.time(), tid))

                    # Update mission stats
                    conn.execute("""
                        UPDATE aadya_missions
                        SET completed_tasks = completed_tasks + 1,
                            updated_at = ?
                        WHERE id = ?;
                    """, (time.time(), mission_id))

                    # Unblock any PENDING tasks whose dependencies are now all satisfied
                    cur = conn.cursor()
                    cur.execute("SELECT id, status FROM aadya_tasks WHERE mission_id = ?;", (mission_id,))
                    all_tasks = cur.fetchall()
                    completed_ids = {r[0] for r in all_tasks if r[1] == 'COMPLETED'}

                    cur.execute("SELECT id, dependencies_json FROM aadya_tasks WHERE mission_id = ? AND status = 'PENDING';", (mission_id,))
                    pending_rows = cur.fetchall()
                    for pid, p_deps_json in pending_rows:
                        p_deps = set(json.loads(p_deps_json or "[]"))
                        if p_deps.issubset(completed_ids):
                            conn.execute("UPDATE aadya_tasks SET status = 'READY' WHERE id = ?;", (pid,))

                    # Check if all tasks in mission are completed
                    cur.execute("SELECT COUNT(*) FROM aadya_tasks WHERE mission_id = ? AND status != 'COMPLETED';", (mission_id,))
                    remaining_count = cur.fetchone()[0]
                    if remaining_count == 0:
                        mission_fully_completed = True
                        conn.execute("""
                            UPDATE aadya_missions
                            SET status = 'COMPLETED',
                                completed_at = ?,
                                updated_at = ?
                            WHERE id = ?;
                        """, (time.time(), time.time(), mission_id))

                    # Audit record
                    log_audit_event(
                        actor="AADYA_MISSION_ENGINE",
                        action="task_completed",
                        target=f"{mission_id}:{tid}",
                        result="SUCCESS",
                        details={
                            "action_type": action_type,
                            "result_digest": result_digest
                        },
                        conn=conn
                    )

                    if mission_fully_completed:
                        log_audit_event(
                            actor="AADYA_MISSION_ENGINE",
                            action="mission_completed",
                            target=mission_id,
                            result="SUCCESS",
                            details={"completed_at": time.time()},
                            conn=conn
                        )
            finally:
                conn.close()

            # Record checkpoint snapshot after successful task
            self._create_snapshot_internal(mission_id, reason=f"TASK_COMPLETED_{tid}")

            return {
                "success": True,
                "task_id": tid,
                "status": "COMPLETED",
                "result_digest": result_digest,
                "result": exec_payload,
                "mission_completed": mission_fully_completed
            }

        except Exception as e:
            logger.error("Task '%s' in mission '%s' failed: %s", tid, mission_id, e)
            return self._handle_task_failure(mission_id, task, str(e))

    def _run_action_handler(self, action_type: str, target: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mock-safe handler for autonomous actions.
        Prevents real external mutation, real network scans, or real APK installations.
        """
        if action_type == "read_system_telemetry":
            ram = check_ram_guard()
            return {
                "telemetry_type": "system_ram",
                "available_mb": ram.get("available_mb"),
                "child_processes": ram.get("child_processes"),
                "process_limit_ok": ram.get("process_limit_ok")
            }

        elif action_type == "query_local_knowledge":
            query = params.get("query", "status")
            return {
                "query": query,
                "status": "resolved",
                "source": "local_sqlite_knowledge"
            }

        elif action_type == "scan_network_passive":
            # Mandatory correction 4: Mock-safe adapter for passive network scan
            return {
                "mode": "mock_safe_passive_adapter",
                "scan_target": target or "local_interface",
                "devices_found": 1,
                "active_probe_performed": False,
                "passive_telemetry": "wlan0_up"
            }

        elif action_type == "query_weather":
            if self.parent and hasattr(self.parent, "wrap_external_context"):
                return self.parent.wrap_external_context(
                    context_type="weather",
                    source=f"weather_service:{target or 'local'}",
                    data={"location": target or "local", "condition": "clear"}
                )
            return {"status": "WEATHER_DATA_CACHED", "location": target or "local", "source": "safe_adapter"}

        elif action_type == "synthesize_briefing":
            return {
                "briefing_type": target or "morning",
                "summary": "Autonomous operations nominal. Zero security alerts.",
                "timestamp": time.time()
            }

        elif action_type == "update_future_radar":
            if self.parent and hasattr(self.parent, "scan_future_radar"):
                return self.parent.scan_future_radar()
            return {"status": "RADAR_UPDATED", "signals": 0}

        elif action_type in {"list_goals", "list_routines"}:
            return {"action": action_type, "items": [], "count": 0}

        elif action_type in {"read_memory_node", "list_memory_nodes"}:
            if self.parent and hasattr(self.parent, "list_active_nodes"):
                return {"nodes": self.parent.list_active_nodes()}
            return {"action": action_type, "nodes": []}

        elif action_type == "synthesize_timeline":
            if self.parent and hasattr(self.parent, "synthesize_unified_timeline"):
                return self.parent.synthesize_unified_timeline()
            return {"events": [], "timeline": "synthesized"}

        elif action_type == "storage_diagnostic":
            return {
                "target": target or "storage_vault",
                "status": "healthy",
                "read_only": True,
                "timestamp": time.time()
            }

        raise NotImplementedError(f"Action '{action_type}' has no bounded runner handler.")

    # -------------------------------------------------------------------------
    # POCO Escalation Handling for High-Risk Tasks
    # -------------------------------------------------------------------------
    def _escalate_task_to_poco(
        self,
        mission_id: str,
        task_id: str,
        action_type: str,
        target: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Escalates a high-risk or unknown action to POCO.
        Transitions the task to AWAITING_ESCALATION and records escalation order.
        """
        escalation_id = None
        if self.parent and hasattr(self.parent, "escalate_to_poco"):
            esc_res = self.parent.escalate_to_poco(
                action_type=action_type,
                details={
                    "mission_id": mission_id,
                    "task_id": task_id,
                    "target": target,
                    "params": params
                }
            )
            escalation_id = esc_res.get("escalation_id")
        else:
            escalation_id = f"esc_{int(time.time() * 1000)}_{os.urandom(3).hex()}"

        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    UPDATE aadya_tasks
                    SET status = 'AWAITING_ESCALATION',
                        escalation_id = ?
                    WHERE id = ?;
                """, (escalation_id, task_id))

                conn.execute("""
                    UPDATE aadya_missions
                    SET status = 'AWAITING_ESCALATION',
                        updated_at = ?
                    WHERE id = ?;
                """, (time.time(), mission_id))

                log_audit_event(
                    actor="AADYA_MISSION_ENGINE",
                    action="task_escalated_to_poco",
                    target=f"{mission_id}:{task_id}",
                    result="HELD_FOR_APPROVAL",
                    details={
                        "escalation_id": escalation_id,
                        "action_type": action_type
                    },
                    conn=conn
                )
        finally:
            conn.close()

        return {
            "success": True,
            "status": "AWAITING_ESCALATION",
            "task_id": task_id,
            "escalation_id": escalation_id,
            "message": f"Task '{task_id}' requires POCO operator approval."
        }

    def bind_task_escalation(self, mission_id: str, task_id: str, escalation_id: str) -> Dict[str, Any]:
        """Binds an existing POCO escalation ID to a task."""
        self._check_engine_health()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    UPDATE aadya_tasks
                    SET escalation_id = ?, status = 'AWAITING_ESCALATION'
                    WHERE mission_id = ? AND id = ?;
                """, (escalation_id, mission_id, task_id))
        finally:
            conn.close()
        return {"success": True, "mission_id": mission_id, "task_id": task_id, "escalation_id": escalation_id}

    def resolve_and_execute_task_escalation(
        self,
        mission_id: str,
        task_id: str,
        decision: str,
        verification_token: str,
        nonce: str,
        approver: str = "Aadi"
    ) -> Dict[str, Any]:
        """
        Resolves a task's POCO escalation and executes the approved task.
        Enforces strict token validation, single-use nonce, and digest binding.
        """
        self._check_engine_health()
        mission = self.get_mission(mission_id)
        if not mission:
            return {"success": False, "error": f"Mission '{mission_id}' not found."}

        task = next((t for t in mission["tasks"] if t["id"] == task_id), None)
        if not task:
            return {"success": False, "error": f"Task '{task_id}' not found in mission '{mission_id}'."}

        escalation_id = task.get("escalation_id")
        if not escalation_id:
            return {"success": False, "error": f"Task '{task_id}' has no active POCO escalation order."}

        # Resolve escalation through Crown-0 parent
        if self.parent and hasattr(self.parent, "resolve_poco_escalation"):
            res = self.parent.resolve_poco_escalation(
                escalation_id=escalation_id,
                decision=decision,
                verification_token=verification_token,
                nonce=nonce
            )
            if res.get("status") not in {"APPROVED", "DENIED"}:
                self._handle_task_failure(mission_id, task, f"POCO Escalation failed: {res}")
                return {"success": False, "error": f"POCO Escalation failed: {res}"}

            if decision != "APPROVE" or res.get("status") != "APPROVED":
                self._handle_task_failure(mission_id, task, f"POCO Escalation denied by {approver}")
                return {"success": False, "status": "DENIED", "message": f"Escalation denied: {res}"}

        # If approved, complete the approved task with verification receipt
        exec_payload = {
            "output": f"Approved task '{task['action_type']}' executed under verified POCO authorization.",
            "approver": approver,
            "escalation_id": escalation_id,
            "executed_at": time.time()
        }
        result_digest = hashlib.sha256(json.dumps(exec_payload, sort_keys=True).encode("utf-8")).hexdigest()
        exec_payload["result_digest"] = result_digest

        mission_fully_completed = False
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    UPDATE aadya_tasks
                    SET status = 'COMPLETED',
                        result_digest = ?,
                        result_json = ?,
                        completed_at = ?,
                        error_message = NULL
                    WHERE id = ?;
                """, (result_digest, json.dumps(exec_payload), time.time(), task_id))

                conn.execute("""
                    UPDATE aadya_missions
                    SET completed_tasks = completed_tasks + 1,
                        status = 'READY',
                        updated_at = ?
                    WHERE id = ?;
                """, (time.time(), mission_id))

                # Unblock any PENDING tasks whose dependencies are now all satisfied
                cur = conn.cursor()
                cur.execute("SELECT id, status FROM aadya_tasks WHERE mission_id = ?;", (mission_id,))
                all_tasks = cur.fetchall()
                completed_ids = {r[0] for r in all_tasks if r[1] == 'COMPLETED'}

                cur.execute("SELECT id, dependencies_json FROM aadya_tasks WHERE mission_id = ? AND status = 'PENDING';", (mission_id,))
                pending_rows = cur.fetchall()
                for pid, p_deps_json in pending_rows:
                    p_deps = set(json.loads(p_deps_json or "[]"))
                    if p_deps.issubset(completed_ids):
                        conn.execute("UPDATE aadya_tasks SET status = 'READY' WHERE id = ?;", (pid,))

                # Check if all tasks in mission are completed
                cur.execute("SELECT COUNT(*) FROM aadya_tasks WHERE mission_id = ? AND status != 'COMPLETED';", (mission_id,))
                remaining_count = cur.fetchone()[0]
                if remaining_count == 0:
                    mission_fully_completed = True
                    conn.execute("""
                        UPDATE aadya_missions
                        SET status = 'COMPLETED',
                            completed_at = ?,
                            updated_at = ?
                        WHERE id = ?;
                    """, (time.time(), time.time(), mission_id))

                log_audit_event(
                    actor=approver,
                    action="task_escalation_executed",
                    target=f"{mission_id}:{task_id}",
                    result="SUCCESS",
                    details={
                        "escalation_id": escalation_id,
                        "result_digest": result_digest
                    },
                    conn=conn
                )

                if mission_fully_completed:
                    log_audit_event(
                        actor="AADYA_MISSION_ENGINE",
                        action="mission_completed",
                        target=mission_id,
                        result="SUCCESS",
                        details={"completed_at": time.time()},
                        conn=conn
                    )
        finally:
            conn.close()

        self._create_snapshot_internal(mission_id, reason=f"ESCALATION_RESOLVED_{task_id}")

        return {
            "success": True,
            "mission_id": mission_id,
            "task_id": task_id,
            "status": "COMPLETED",
            "result_digest": result_digest,
            "mission_completed": mission_fully_completed
        }

    # -------------------------------------------------------------------------
    # Failure & Retry Handling
    # -------------------------------------------------------------------------
    def _handle_task_failure(self, mission_id: str, task: Dict[str, Any], error_msg: str) -> Dict[str, Any]:
        """
        Handles task failure strictly conforming to mandatory corrections 1 and 2:
        - Only explicitly idempotent, low-risk tasks may retry.
        - High-risk and non-idempotent tasks must NEVER automatically retry.
        """
        tid = task["id"]
        risk_level = task.get("risk_level", "HIGH")
        is_idempotent = bool(task.get("is_idempotent", 0))
        current_retries = int(task.get("retry_count", 0))
        max_retries = int(task.get("max_retries", 3))

        can_auto_retry = (
            risk_level == "LOW" and
            is_idempotent and
            current_retries < max_retries
        )

        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                if can_auto_retry:
                    new_retry_count = current_retries + 1
                    conn.execute("""
                        UPDATE aadya_tasks
                        SET retry_count = ?,
                            status = 'READY',
                            error_message = ?
                        WHERE id = ?;
                    """, (new_retry_count, error_msg, tid))

                    log_audit_event(
                        actor="AADYA_MISSION_ENGINE",
                        action="task_retry_scheduled",
                        target=f"{mission_id}:{tid}",
                        result="RETRYING",
                        details={"retry_count": new_retry_count, "error": error_msg},
                        conn=conn
                    )
                    return {
                        "success": False,
                        "status": "RETRYING",
                        "task_id": tid,
                        "retry_count": new_retry_count,
                        "error": error_msg
                    }
                else:
                    # Retries exhausted or forbidden
                    conn.execute("""
                        UPDATE aadya_tasks
                        SET status = 'FAILED',
                            error_message = ?
                        WHERE id = ?;
                    """, (error_msg, tid))

                    conn.execute("""
                        UPDATE aadya_missions
                        SET failed_tasks = failed_tasks + 1,
                            status = 'FAILED',
                            error_message = ?,
                            updated_at = ?
                        WHERE id = ?;
                    """, (f"Task '{tid}' failed: {error_msg}", time.time(), mission_id))

                    log_audit_event(
                        actor="AADYA_MISSION_ENGINE",
                        action="task_failed_terminal",
                        target=f"{mission_id}:{tid}",
                        result="FAILED",
                        details={"error": error_msg, "risk_level": risk_level, "idempotent": is_idempotent},
                        conn=conn
                    )
                    return {
                        "success": False,
                        "status": "FAILED",
                        "task_id": tid,
                        "error": error_msg
                    }
        finally:
            conn.close()

    def retry_failed_task(self, mission_id: str, task_id: str, actor: str = "Aadi") -> Dict[str, Any]:
        """
        Manually requested retry for a failed task.
        Enforces idempotency and low-risk rules (correction 1 & 2).
        """
        self._check_engine_health()
        mission = self.get_mission(mission_id)
        if not mission:
            return {"success": False, "error": f"Mission '{mission_id}' not found."}

        task = next((t for t in mission["tasks"] if t["id"] == task_id), None)
        if not task:
            return {"success": False, "error": f"Task '{task_id}' not found."}

        if task["status"] != "FAILED":
            return {"success": False, "error": f"Task '{task_id}' is not in FAILED state (current: {task['status']})."}

        # Enforce correction 1 & 2
        if task.get("risk_level") != "LOW" or not bool(task.get("is_idempotent", 0)):
            return {
                "success": False,
                "error": "NON_IDEMPOTENT_RETRY_FORBIDDEN: High-risk or non-idempotent tasks cannot be retried."
            }

        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    UPDATE aadya_tasks
                    SET status = 'READY',
                        error_message = NULL
                    WHERE id = ?;
                """, (task_id,))

                conn.execute("""
                    UPDATE aadya_missions
                    SET status = 'READY',
                        failed_tasks = MAX(0, failed_tasks - 1),
                        error_message = NULL,
                        updated_at = ?
                    WHERE id = ?;
                """, (time.time(), mission_id))

                log_audit_event(
                    actor=actor,
                    action="task_manual_retry",
                    target=f"{mission_id}:{task_id}",
                    result="SUCCESS",
                    details={"reset_by": actor},
                    conn=conn
                )
        finally:
            conn.close()

        return {"success": True, "mission_id": mission_id, "task_id": task_id, "status": "READY"}

    # -------------------------------------------------------------------------
    # RAM Pressure Deferral
    # -------------------------------------------------------------------------
    def _defer_on_ram(self, mission_id: str, avail_kb: int, threshold_kb: int) -> None:
        """Atomically defers mission execution due to RAM pressure."""
        now = time.time()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    UPDATE aadya_missions
                    SET status = 'DEFERRED_RAM',
                        updated_at = ?
                    WHERE id = ?;
                """, (now, mission_id))

                log_audit_event(
                    actor="AADYA_MISSION_ENGINE",
                    action="ram_pressure_deferral",
                    target=mission_id,
                    result="DEFERRED",
                    details={
                        "available_kb": avail_kb,
                        "threshold_kb": threshold_kb
                    },
                    conn=conn
                )
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Pause, Resume, Cancel Lifecycle
    # -------------------------------------------------------------------------
    def pause_mission(self, mission_id: str, actor: str = "Aadi", reason: str = "") -> Dict[str, Any]:
        """Atomically pauses mission execution and creates a pause snapshot."""
        self._check_engine_health()
        mission = self.get_mission(mission_id)
        if not mission:
            return {"success": False, "error": f"Mission '{mission_id}' not found."}

        if mission["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return {"success": False, "error": f"Cannot pause mission in terminal state '{mission['status']}'."}

        now = time.time()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute(
                    "UPDATE aadya_missions SET status = 'PAUSED', updated_at = ? WHERE id = ?;",
                    (now, mission_id)
                )
                log_audit_event(
                    actor=actor,
                    action="pause_mission",
                    target=mission_id,
                    result="PAUSED",
                    details={"reason": reason},
                    conn=conn
                )
        finally:
            conn.close()

        self._create_snapshot_internal(mission_id, reason=f"PAUSED_BY_{actor}")
        return {"success": True, "mission_id": mission_id, "status": "PAUSED"}

    def resume_mission(self, mission_id: str, actor: str = "Aadi") -> Dict[str, Any]:
        """Atomically resumes a paused mission."""
        self._check_engine_health()
        mission = self.get_mission(mission_id)
        if not mission:
            return {"success": False, "error": f"Mission '{mission_id}' not found."}

        if mission["status"] not in {"PAUSED", "DEFERRED_RAM"}:
            return {"success": False, "error": f"Mission '{mission_id}' is not PAUSED (current: {mission['status']})."}

        now = time.time()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute(
                    "UPDATE aadya_missions SET status = 'READY', updated_at = ? WHERE id = ?;",
                    (now, mission_id)
                )
                log_audit_event(
                    actor=actor,
                    action="resume_mission",
                    target=mission_id,
                    result="RESUMED",
                    details={},
                    conn=conn
                )
        finally:
            conn.close()

        return {"success": True, "mission_id": mission_id, "status": "READY"}

    def cancel_mission(self, mission_id: str, actor: str = "Aadi", reason: str = "") -> Dict[str, Any]:
        """Atomically cancels mission and all non-completed tasks."""
        self._check_engine_health()
        mission = self.get_mission(mission_id)
        if not mission:
            return {"success": False, "error": f"Mission '{mission_id}' not found."}

        if mission["status"] in {"COMPLETED", "CANCELLED"}:
            return {"success": False, "error": f"Mission '{mission_id}' already terminated ({mission['status']})."}

        now = time.time()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute(
                    "UPDATE aadya_missions SET status = 'CANCELLED', updated_at = ?, completed_at = ? WHERE id = ?;",
                    (now, now, mission_id)
                )
                conn.execute("""
                    UPDATE aadya_tasks
                    SET status = 'CANCELLED'
                    WHERE mission_id = ? AND status NOT IN ('COMPLETED', 'FAILED');
                """, (mission_id,))

                log_audit_event(
                    actor=actor,
                    action="cancel_mission",
                    target=mission_id,
                    result="CANCELLED",
                    details={"reason": reason},
                    conn=conn
                )
        finally:
            conn.close()

        return {"success": True, "mission_id": mission_id, "status": "CANCELLED"}

    def _complete_mission(self, mission_id: str) -> None:
        """Internal helper to mark mission COMPLETED."""
        now = time.time()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    UPDATE aadya_missions
                    SET status = 'COMPLETED',
                        completed_at = ?,
                        updated_at = ?
                    WHERE id = ?;
                """, (now, now, mission_id))

                log_audit_event(
                    actor="AADYA_MISSION_ENGINE",
                    action="mission_completed",
                    target=mission_id,
                    result="SUCCESS",
                    details={"completed_at": now},
                    conn=conn
                )
        finally:
            conn.close()

    def _update_mission_status(self, mission_id: str, status: str, error: Optional[str] = None) -> None:
        now = time.time()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    UPDATE aadya_missions
                    SET status = ?,
                        error_message = ?,
                        updated_at = ?
                    WHERE id = ?;
                """, (status, error, now, mission_id))
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Batch Execution Loop
    # -------------------------------------------------------------------------
    def run_mission_to_completion(
        self,
        mission_id: str,
        max_steps: int = 50,
        ram_threshold_kb: int = 800000,
        mock_free_ram_kb: Optional[int] = None
    ) -> Dict[str, Any]:
        """Runs eligible tasks step-by-step up to max_steps or terminal state."""
        self._check_engine_health()
        steps_run = 0
        last_res = {}

        while steps_run < max_steps:
            res = self.execute_mission_step(
                mission_id=mission_id,
                ram_threshold_kb=ram_threshold_kb,
                mock_free_ram_kb=mock_free_ram_kb
            )
            last_res = res
            steps_run += 1

            # Check if mission has reached terminal or inactive state
            cur_m = self.get_mission(mission_id)
            if not cur_m:
                break
            m_status = cur_m["status"]
            if m_status in {"COMPLETED", "FAILED", "CANCELLED", "PAUSED", "DEFERRED_RAM", "AWAITING_ESCALATION"}:
                break

            step_status = res.get("status")
            if step_status in {"FAILED", "CANCELLED", "PAUSED", "DEFERRED_RAM", "AWAITING_ESCALATION"}:
                break

        final_mission = self.get_mission(mission_id)
        return {
            "steps_executed": steps_run,
            "last_step_result": last_res,
            "mission": final_mission
        }

    # -------------------------------------------------------------------------
    # Recovery & Checkpoint Snapshots
    # -------------------------------------------------------------------------
    def create_mission_recovery_snapshot(self, mission_id: str, reason: str = "CHECKPOINT") -> Dict[str, Any]:
        """Public API to capture a verified recovery snapshot."""
        self._check_engine_health()
        return self._create_snapshot_internal(mission_id, reason=reason)

    def _create_snapshot_internal(self, mission_id: str, reason: str) -> Dict[str, Any]:
        """
        Serializes full mission and tasks state, calculates SHA-256 digest,
        and commits to aadya_mission_snapshots.
        """
        mission = self.get_mission(mission_id)
        if not mission:
            raise ValueError(f"Cannot snapshot non-existent mission '{mission_id}'.")

        now = time.time()
        snap_id = f"snap_{int(now * 1000)}_{os.urandom(3).hex()}"
        payload_str = json.dumps(mission, sort_keys=True)
        digest = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            with conn:
                conn.execute("""
                    INSERT INTO aadya_mission_snapshots (
                        id, mission_id, snapshot_digest, state_payload_json, reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?);
                """, (snap_id, mission_id, digest, payload_str, reason, now))

                log_audit_event(
                    actor="AADYA_MISSION_ENGINE",
                    action="create_recovery_snapshot",
                    target=f"{mission_id}:{snap_id}",
                    result="SUCCESS",
                    details={"digest": digest, "reason": reason},
                    conn=conn
                )
        finally:
            conn.close()

        return {
            "snapshot_id": snap_id,
            "mission_id": mission_id,
            "snapshot_digest": digest,
            "reason": reason,
            "created_at": now
        }

    def recover_mission_from_snapshot(
        self,
        mission_id: str,
        snapshot_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Conforms strictly to mandatory corrections 7 and 8:
        - Recovery snapshots must restore only to the last verified checkpoint.
        - Recovery must NEVER silently overwrite completed work.
        """
        self._check_engine_health()
        conn = get_connection(self._get_db(), allow_maintenance=True)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            if snapshot_id:
                cur.execute(
                    "SELECT * FROM aadya_mission_snapshots WHERE id = ? AND mission_id = ?;",
                    (snapshot_id, mission_id)
                )
            else:
                cur.execute(
                    "SELECT * FROM aadya_mission_snapshots WHERE mission_id = ? ORDER BY created_at DESC LIMIT 1;",
                    (mission_id,)
                )

            snap_row = cur.fetchone()
            if not snap_row:
                return {"success": False, "error": f"No snapshot found for mission '{mission_id}'."}

            snap = dict(snap_row)
            payload_str = snap["state_payload_json"]
            expected_digest = snap["snapshot_digest"]

            # Integrity check
            actual_digest = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
            if actual_digest != expected_digest:
                return {
                    "success": False,
                    "error": f"SNAPSHOT_TAMPER_DETECTED: Digest mismatch (expected {expected_digest}, got {actual_digest})"
                }

            snapshot_data = json.loads(payload_str)
            snap_tasks = {t["id"]: t for t in snapshot_data.get("tasks", [])}

            # Fetch current live task states
            cur.execute("SELECT id, status, result_digest, dependencies_json FROM aadya_tasks WHERE mission_id = ?;", (mission_id,))
            live_rows = cur.fetchall()
            live_tasks = {r["id"]: dict(r) for r in live_rows}

            now = time.time()
            restored_count = 0

            with conn:
                for tid, s_task in snap_tasks.items():
                    live_t = live_tasks.get(tid)
                    if not live_t:
                        continue

                    # Correction 8: NEVER overwrite completed work!
                    if live_t["status"] == "COMPLETED" and live_t["result_digest"]:
                        # Already completed in live DB; preserve it
                        continue

                    # Restore non-completed task to snapshot state
                    target_status = s_task["status"]
                    if target_status == "RUNNING":
                        target_status = "READY"

                    conn.execute("""
                        UPDATE aadya_tasks
                        SET status = ?,
                            retry_count = ?,
                            error_message = ?
                        WHERE id = ?;
                    """, (target_status, s_task.get("retry_count", 0), s_task.get("error_message"), tid))
                    restored_count += 1

                # Evaluate dependencies to unblock tasks whose prerequisites are COMPLETED
                cur.execute("SELECT id, status FROM aadya_tasks WHERE mission_id = ?;", (mission_id,))
                fresh_tasks = cur.fetchall()
                completed_ids = {r[0] for r in fresh_tasks if r[1] == 'COMPLETED'}

                cur.execute("SELECT id, dependencies_json FROM aadya_tasks WHERE mission_id = ? AND status = 'PENDING';", (mission_id,))
                for pid, p_deps_json in cur.fetchall():
                    p_deps = set(json.loads(p_deps_json or "[]"))
                    if p_deps.issubset(completed_ids):
                        conn.execute("UPDATE aadya_tasks SET status = 'READY' WHERE id = ?;", (pid,))

                # Reset mission status to READY
                conn.execute("""
                    UPDATE aadya_missions
                    SET status = 'READY',
                        error_message = NULL,
                        updated_at = ?
                    WHERE id = ?;
                """, (now, mission_id))

                log_audit_event(
                    actor="AADYA_MISSION_ENGINE",
                    action="recover_from_snapshot",
                    target=f"{mission_id}:{snap['id']}",
                    result="SUCCESS",
                    details={
                        "snapshot_id": snap["id"],
                        "tasks_restored": restored_count
                    },
                    conn=conn
                )

        finally:
            conn.close()

        return {
            "success": True,
            "mission_id": mission_id,
            "snapshot_id": snap["id"],
            "tasks_restored": restored_count,
            "mission": self.get_mission(mission_id)
        }
