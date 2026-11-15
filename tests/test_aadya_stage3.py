"""
AADYA Stage 3 — Autonomous Operations & Mission Engine Test Suite
Tests DAG decomposition, topological cycle detection, low-risk autonomous execution,
POCO escalation binding, failure & bounded retry policies, RAM pressure deferral,
recovery snapshot restoration, audit chaining, and permanent financial quarantine enforcement.
"""

import os
import time
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from core.aadya import AadyaCrownZero, FinancialQuarantineViolationError
from core.aadya_missions import AadyaMissionEngine, AUTONOMOUS_LOW_RISK_ALLOWLIST
from core.db import get_connection, verify_audit_chain, init_database


class TestAadyaStage3Missions(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "aadya_stage3_test.db")
        init_database(self.db_path)
        self.aadya = AadyaCrownZero(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Mission Creation & DAG Validation
    # -------------------------------------------------------------------------
    def test_mission_creation_and_dag_validation(self):
        tasks = [
            {"id": "t1", "action_type": "read_system_telemetry", "target": "ram"},
            {"id": "t2", "action_type": "query_local_knowledge", "target": "storage", "dependencies": ["t1"]},
            {"id": "t3", "action_type": "synthesize_briefing", "target": "summary", "dependencies": ["t2"]}
        ]
        mission = self.aadya.create_mission(
            title="System Status Mission",
            objective="Inspect system telemetry and synthesize briefing",
            tasks=tasks
        )

        self.assertIsNotNone(mission)
        self.assertEqual(mission["status"], "READY")
        self.assertEqual(mission["total_tasks"], 3)
        self.assertEqual(mission["completed_tasks"], 0)
        self.assertEqual(mission["progress_pct"], 0.0)
        self.assertEqual(len(mission["tasks"]), 3)
        self.assertEqual(mission["tasks"][0]["status"], "READY")
        self.assertEqual(mission["tasks"][1]["status"], "PENDING")
        self.assertEqual(mission["tasks"][2]["status"], "PENDING")

    def test_dag_cycle_detection(self):
        # Circular dependency: t1 -> t2 -> t3 -> t1
        cyclic_tasks = [
            {"id": "t1", "action_type": "read_system_telemetry", "target": "ram", "dependencies": ["t3"]},
            {"id": "t2", "action_type": "query_local_knowledge", "target": "storage", "dependencies": ["t1"]},
            {"id": "t3", "action_type": "synthesize_briefing", "target": "summary", "dependencies": ["t2"]}
        ]
        with self.assertRaises(ValueError) as ctx:
            self.aadya.create_mission(
                title="Cyclic Mission",
                objective="Should fail cycle detection",
                tasks=cyclic_tasks
            )
        self.assertIn("DAG_CYCLE_DETECTED", str(ctx.exception))

    def test_dag_invalid_or_self_dependencies(self):
        # Non-existent dependency
        invalid_tasks = [
            {"id": "t1", "action_type": "read_system_telemetry", "target": "ram", "dependencies": ["non_existent"]}
        ]
        with self.assertRaises(ValueError) as ctx:
            self.aadya.create_mission(title="Invalid", objective="Invalid", tasks=invalid_tasks)
        self.assertIn("INVALID_DEPENDENCY", str(ctx.exception))

        # Self-dependency
        self_tasks = [
            {"id": "t1", "action_type": "read_system_telemetry", "target": "ram", "dependencies": ["t1"]}
        ]
        with self.assertRaises(ValueError) as ctx:
            self.aadya.create_mission(title="Self", objective="Self", tasks=self_tasks)
        self.assertIn("SELF_DEPENDENCY", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 2. DAG Dependency Ordering & Wave Execution
    # -------------------------------------------------------------------------
    def test_dag_dependency_ordering_and_wave_execution(self):
        # t1 and t2 run in parallel; t3 waits for both
        tasks = [
            {"id": "t1", "action_type": "read_system_telemetry", "target": "ram"},
            {"id": "t2", "action_type": "storage_diagnostic", "target": "disk"},
            {"id": "t3", "action_type": "synthesize_briefing", "target": "summary", "dependencies": ["t1", "t2"]}
        ]
        mission = self.aadya.create_mission(title="Wave Mission", objective="Test wave execution", tasks=tasks)
        mid = mission["id"]

        # Step 1: Executes t1
        s1 = self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
        self.assertTrue(s1["success"])
        self.assertEqual(s1["task_id"], "t1")
        self.assertIn("result_digest", s1)

        m_state = self.aadya.get_mission(mid)
        t3_state = next(t for t in m_state["tasks"] if t["id"] == "t3")
        self.assertEqual(t3_state["status"], "PENDING", "t3 must remain PENDING while t2 is not done")

        # Step 2: Executes t2
        s2 = self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
        self.assertTrue(s2["success"])
        self.assertEqual(s2["task_id"], "t2")

        # Step 3: Now t3 should be unblocked and execute
        s3 = self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
        self.assertTrue(s3["success"])
        self.assertEqual(s3["task_id"], "t3")

        # Step 4: Mission marks COMPLETED
        s4 = self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
        self.assertTrue(s4["success"])
        self.assertEqual(s4["status"], "COMPLETED")

        final_mission = self.aadya.get_mission(mid)
        self.assertEqual(final_mission["status"], "COMPLETED")
        self.assertEqual(final_mission["completed_tasks"], 3)
        self.assertEqual(final_mission["progress_pct"], 100.0)

    # -------------------------------------------------------------------------
    # 3. Low-Risk Autonomous Execution
    # -------------------------------------------------------------------------
    def test_low_risk_autonomous_execution_to_completion(self):
        tasks = [
            {"id": "t1", "action_type": "read_system_telemetry", "target": "system"},
            {"id": "t2", "action_type": "scan_network_passive", "target": "wlan0", "dependencies": ["t1"]},
            {"id": "t3", "action_type": "query_weather", "target": "Bengaluru", "dependencies": ["t2"]},
            {"id": "t4", "action_type": "storage_diagnostic", "target": "vault", "dependencies": ["t3"]}
        ]
        mission = self.aadya.create_mission(title="Low Risk Batch", objective="Test autonomous allowlist", tasks=tasks)
        mid = mission["id"]

        run_res = self.aadya.run_mission_to_completion(mid, max_steps=10, mock_free_ram_kb=2500000)
        final_m = run_res["mission"]

        self.assertEqual(final_m["status"], "COMPLETED")
        self.assertEqual(final_m["completed_tasks"], 4)
        self.assertEqual(final_m["progress_pct"], 100.0)

        # Confirm every task has an authentic SHA-256 result digest
        for t in final_m["tasks"]:
            self.assertEqual(t["status"], "COMPLETED")
            self.assertIsNotNone(t["result_digest"])
            self.assertEqual(len(t["result_digest"]), 64)

    # -------------------------------------------------------------------------
    # 4. High-Risk Task & POCO Escalation
    # -------------------------------------------------------------------------
    def test_high_risk_task_requires_poco_escalation(self):
        tasks = [
            {"id": "t1", "action_type": "read_system_telemetry", "target": "system"},
            {"id": "t2", "action_type": "delete_private_memory", "target": "vault_node_99", "dependencies": ["t1"]}
        ]
        mission = self.aadya.create_mission(title="Privileged Mission", objective="Test high-risk escalation", tasks=tasks)
        mid = mission["id"]

        # Step 1: t1 executes autonomously (low risk)
        s1 = self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
        self.assertTrue(s1["success"])
        self.assertEqual(s1["task_id"], "t1")

        # Step 2: t2 is high risk -> Triggers POCO escalation
        s2 = self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
        self.assertTrue(s2["success"])
        self.assertEqual(s2["status"], "AWAITING_ESCALATION")
        self.assertEqual(s2["task_id"], "t2")
        escalation_id = s2["escalation_id"]
        self.assertIsNotNone(escalation_id)

        m_state = self.aadya.get_mission(mid)
        self.assertEqual(m_state["status"], "AWAITING_ESCALATION")
        t2_state = next(t for t in m_state["tasks"] if t["id"] == "t2")
        self.assertEqual(t2_state["status"], "AWAITING_ESCALATION")

        # Step 3: Resolve POCO escalation with valid APPROVE
        res = self.aadya.missions.resolve_and_execute_task_escalation(
            mission_id=mid,
            task_id="t2",
            decision="APPROVE",
            verification_token="SOVEREIGN_POCO_ROOT_TOKEN_2026",
            nonce="nonce_stage3_approval_1",
            approver="Aadi"
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "COMPLETED")
        self.assertIn("result_digest", res)

        # Verify mission is now fully completed
        final_m = self.aadya.get_mission(mid)
        self.assertEqual(final_m["completed_tasks"], 2)
        self.assertEqual(final_m["progress_pct"], 100.0)

    # -------------------------------------------------------------------------
    # 5. Financial Quarantine Non-Bypass
    # -------------------------------------------------------------------------
    def test_financial_quarantine_blocks_mission_creation(self):
        # Any task attempting financial execution must raise FinancialQuarantineViolationError
        financial_tasks = [
            {"id": "t1", "action_type": "transfer_funds", "target": "bank_account", "params": {"amount": 1000}}
        ]
        with self.assertRaises(FinancialQuarantineViolationError):
            self.aadya.create_mission(
                title="Illegal Wire",
                objective="Attempt financial transfer in mission",
                tasks=financial_tasks
            )

        crypto_tasks = [
            {"id": "t1", "action_type": "execute_order", "target": "binance_spot_trade"}
        ]
        with self.assertRaises(FinancialQuarantineViolationError):
            self.aadya.create_mission(
                title="Illegal Trade",
                objective="Attempt crypto trade in mission",
                tasks=crypto_tasks
            )

        # Confirm zero missions created in DB
        missions = self.aadya.list_missions()
        self.assertEqual(len(missions), 0)

    # -------------------------------------------------------------------------
    # 6. Pause & Resume Behavior
    # -------------------------------------------------------------------------
    def test_pause_and_resume_mission(self):
        tasks = [
            {"id": "t1", "action_type": "read_system_telemetry", "target": "system"},
            {"id": "t2", "action_type": "query_local_knowledge", "target": "context", "dependencies": ["t1"]},
            {"id": "t3", "action_type": "synthesize_briefing", "target": "summary", "dependencies": ["t2"]}
        ]
        mission = self.aadya.create_mission(title="Pause Test", objective="Test pause and resume", tasks=tasks)
        mid = mission["id"]

        # Step 1: Run t1
        self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)

        # Pause mission
        p_res = self.aadya.pause_mission(mid, actor="Aadi", reason="User inspection")
        self.assertTrue(p_res["success"])
        self.assertEqual(p_res["status"], "PAUSED")

        # Subsequent step fails because mission is paused
        step_during_pause = self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
        self.assertFalse(step_during_pause["success"])
        self.assertEqual(step_during_pause["status"], "PAUSED")

        # Resume mission
        r_res = self.aadya.resume_mission(mid, actor="Aadi")
        self.assertTrue(r_res["success"])
        self.assertEqual(r_res["status"], "READY")

        # Complete remaining steps
        run_res = self.aadya.run_mission_to_completion(mid, max_steps=10, mock_free_ram_kb=2000000)
        self.assertEqual(run_res["mission"]["status"], "COMPLETED")
        self.assertEqual(run_res["mission"]["completed_tasks"], 3)

    # -------------------------------------------------------------------------
    # 7. Cancel Mission Behavior
    # -------------------------------------------------------------------------
    def test_cancel_mission_stops_all_further_execution(self):
        tasks = [
            {"id": "t1", "action_type": "read_system_telemetry", "target": "system"},
            {"id": "t2", "action_type": "query_local_knowledge", "target": "context", "dependencies": ["t1"]}
        ]
        mission = self.aadya.create_mission(title="Cancel Test", objective="Test cancellation", tasks=tasks)
        mid = mission["id"]

        c_res = self.aadya.cancel_mission(mid, actor="Aadi", reason="Operator abort")
        self.assertTrue(c_res["success"])
        self.assertEqual(c_res["status"], "CANCELLED")

        m = self.aadya.get_mission(mid)
        self.assertEqual(m["status"], "CANCELLED")
        for t in m["tasks"]:
            self.assertEqual(t["status"], "CANCELLED")

        step_after_cancel = self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
        self.assertFalse(step_after_cancel["success"])
        self.assertEqual(step_after_cancel["status"], "CANCELLED")

    # -------------------------------------------------------------------------
    # 8. Failure & Retry Policy (Corrections 1 & 2)
    # -------------------------------------------------------------------------
    def test_failure_and_retry_exhaustion_for_idempotent_task(self):
        tasks = [
            {"id": "t1", "action_type": "read_system_telemetry", "target": "fail_target", "max_retries": 2}
        ]
        mission = self.aadya.create_mission(title="Retry Test", objective="Test idempotent retry", tasks=tasks)
        mid = mission["id"]

        # Mock action runner to simulate transient failure
        with patch.object(self.aadya.missions, "_run_action_handler", side_effect=RuntimeError("Transient timeout")):
            # Step 1: Fails, retry_count -> 1, status remains READY for retry
            s1 = self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
            self.assertFalse(s1["success"])
            self.assertEqual(s1["status"], "RETRYING")
            self.assertEqual(s1["retry_count"], 1)

            # Step 2: Fails, retry_count -> 2, status remains READY
            s2 = self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
            self.assertFalse(s2["success"])
            self.assertEqual(s2["status"], "RETRYING")
            self.assertEqual(s2["retry_count"], 2)

            # Step 3: Fails, retries exhausted -> Terminal FAILED
            s3 = self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
            self.assertFalse(s3["success"])
            self.assertEqual(s3["status"], "FAILED")

        m = self.aadya.get_mission(mid)
        self.assertEqual(m["status"], "FAILED")
        self.assertEqual(m["failed_tasks"], 1)

    def test_non_idempotent_and_high_risk_tasks_never_auto_retry(self):
        # A non-idempotent or high-risk task must fail immediately on failure
        tasks = [
            {"id": "t1", "action_type": "privileged_patch", "target": "subsystem", "max_retries": 3}
        ]
        mission = self.aadya.create_mission(title="Non-Idempotent Test", objective="Zero auto-retry", tasks=tasks)
        mid = mission["id"]

        # Elevate to POCO, then simulate failure
        t1 = mission["tasks"][0]
        self.assertEqual(t1["is_idempotent"], 0, "High risk task must not be marked idempotent")

        # Attempt manual retry of non-idempotent task
        # First set it to FAILED in DB
        conn = get_connection(self.db_path, allow_maintenance=True)
        with conn:
            conn.execute("UPDATE aadya_tasks SET status = 'FAILED' WHERE id = 't1';")
            conn.execute("UPDATE aadya_missions SET status = 'FAILED' WHERE id = ?;", (mid,))
        conn.close()

        retry_res = self.aadya.retry_failed_task(mid, "t1")
        self.assertFalse(retry_res["success"])
        self.assertIn("NON_IDEMPOTENT_RETRY_FORBIDDEN", retry_res["error"])

    # -------------------------------------------------------------------------
    # 9. Recovery Snapshot Creation & Restoration (Corrections 7 & 8)
    # -------------------------------------------------------------------------
    def test_recovery_snapshot_creation_and_restoration(self):
        tasks = [
            {"id": "t1", "action_type": "read_system_telemetry", "target": "ram"},
            {"id": "t2", "action_type": "storage_diagnostic", "target": "disk", "dependencies": ["t1"]},
            {"id": "t3", "action_type": "synthesize_briefing", "target": "summary", "dependencies": ["t2"]}
        ]
        mission = self.aadya.create_mission(title="Snapshot Test", objective="Test recovery snapshot", tasks=tasks)
        mid = mission["id"]

        # Run t1
        self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)

        # Create checkpoint snapshot after t1
        snap = self.aadya.create_mission_recovery_snapshot(mid, reason="AFTER_T1_SUCCESS")
        self.assertIsNotNone(snap["snapshot_id"])
        self.assertEqual(len(snap["snapshot_digest"]), 64)

        # Simulate a crash/interruption during t2
        conn = get_connection(self.db_path, allow_maintenance=True)
        with conn:
            conn.execute("UPDATE aadya_tasks SET status = 'RUNNING' WHERE id = 't2';")
            conn.execute("UPDATE aadya_missions SET status = 'NEEDS_RECONCILIATION' WHERE id = ?;", (mid,))
        conn.close()

        # Recover mission from snapshot
        rec = self.aadya.recover_mission_from_snapshot(mid, snapshot_id=snap["snapshot_id"])
        self.assertTrue(rec["success"])

        # Verification: t1 remains COMPLETED (Correction 8: never overwrite completed work)
        m = self.aadya.get_mission(mid)
        self.assertEqual(m["status"], "READY")
        t1_state = next(t for t in m["tasks"] if t["id"] == "t1")
        self.assertEqual(t1_state["status"], "COMPLETED")
        self.assertIsNotNone(t1_state["result_digest"])

        # t2 was restored to READY
        t2_state = next(t for t in m["tasks"] if t["id"] == "t2")
        self.assertEqual(t2_state["status"], "READY")

    def test_recovery_snapshot_tamper_detection(self):
        tasks = [{"id": "t1", "action_type": "read_system_telemetry", "target": "ram"}]
        mission = self.aadya.create_mission(title="Tamper Test", objective="Test tamper check", tasks=tasks)
        mid = mission["id"]

        snap = self.aadya.create_mission_recovery_snapshot(mid, reason="CHECKPOINT")
        snap_id = snap["snapshot_id"]

        # Tamper payload in DB
        conn = get_connection(self.db_path, allow_maintenance=True)
        with conn:
            conn.execute(
                "UPDATE aadya_mission_snapshots SET state_payload_json = '{\"tampered\": true}' WHERE id = ?;",
                (snap_id,)
            )
        conn.close()

        rec = self.aadya.recover_mission_from_snapshot(mid, snapshot_id=snap_id)
        self.assertFalse(rec["success"])
        self.assertIn("SNAPSHOT_TAMPER_DETECTED", rec["error"])

    # -------------------------------------------------------------------------
    # 10. RAM Pressure Deferral
    # -------------------------------------------------------------------------
    def test_ram_pressure_deferral(self):
        tasks = [{"id": "t1", "action_type": "read_system_telemetry", "target": "ram"}]
        mission = self.aadya.create_mission(title="RAM Test", objective="Test RAM guard", tasks=tasks)
        mid = mission["id"]

        # Simulate low free RAM: 400 MB (< 800 MB threshold)
        res = self.aadya.execute_mission_step(mid, ram_threshold_kb=800000, mock_free_ram_kb=400000)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "DEFERRED_RAM")

        m = self.aadya.get_mission(mid)
        self.assertEqual(m["status"], "DEFERRED_RAM")
        t1 = m["tasks"][0]
        # Task remains READY (not failed)
        self.assertEqual(t1["status"], "READY")

        # Resume after RAM pressure clears: 1.5 GB (> 800 MB threshold)
        res_after = self.aadya.execute_mission_step(mid, ram_threshold_kb=800000, mock_free_ram_kb=1500000)
        self.assertTrue(res_after["success"])
        self.assertEqual(res_after["status"], "COMPLETED")

    # -------------------------------------------------------------------------
    # 11. Truthful Progress & Audit Chaining
    # -------------------------------------------------------------------------
    def test_truthful_progress_and_audit_chain_integrity(self):
        tasks = [
            {"id": "t1", "action_type": "read_system_telemetry", "target": "ram"},
            {"id": "t2", "action_type": "storage_diagnostic", "target": "disk", "dependencies": ["t1"]}
        ]
        mission = self.aadya.create_mission(title="Audit Test", objective="Test audit chain", tasks=tasks)
        mid = mission["id"]

        # 0% at start
        m0 = self.aadya.get_mission(mid)
        self.assertEqual(m0["progress_pct"], 0.0)

        # 50% after t1
        self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
        m1 = self.aadya.get_mission(mid)
        self.assertEqual(m1["progress_pct"], 50.0)

        # 100% after t2
        self.aadya.execute_mission_step(mid, mock_free_ram_kb=2000000)
        m2 = self.aadya.get_mission(mid)
        self.assertEqual(m2["progress_pct"], 100.0)

        # Verify audit chain integrity across all transitions
        audit_res = verify_audit_chain(self.db_path)
        self.assertTrue(audit_res["is_valid"], f"Audit chain verification failed: {audit_res}")
        self.assertGreater(audit_res["total_events"], 5)

    # -------------------------------------------------------------------------
    # 12. Engine Degraded State Handling
    # -------------------------------------------------------------------------
    def test_missions_engine_degraded_state(self):
        bad_aadya = AadyaCrownZero(db_path="/proc/read_only_fake/bad.db")
        self.assertEqual(bad_aadya.missions_initialization_status, "INITIALIZATION_FAILED")

        with self.assertRaises(RuntimeError) as ctx:
            bad_aadya.create_mission("Title", "Objective", [])
        self.assertIn("degraded state", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
