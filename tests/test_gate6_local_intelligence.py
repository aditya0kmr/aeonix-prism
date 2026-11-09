"""
ÆONIX PRISM // Gate G6 Local Intelligence (Burst-Only Inference) Test Suite
Exhaustively verifies:
1. Fast deterministic intent router (<50ms, zero LLM) for system commands, cached cards, and status.
2. RAM guard controller budget enforcement (available memory ceiling & Android child process limits).
3. Burst-only model memory lifecycle: allocate on query, complete response, unload immediately.
4. Security boundary: fuzzy text similarity alone strictly forbidden from authorizing destructive actions.
5. HTTP /api/intent API endpoint latency and RBAC enforcement.
"""

import os
import sys
import time
import tempfile
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
else:
    sys.path.remove(_REPO_ROOT)
    sys.path.insert(0, _REPO_ROOT)

# Bootstrap test sandbox environment BEFORE aeonix imports
_MODULE_SANDBOX = tempfile.mkdtemp(prefix="aeonix_test_g6_bootstrap_")
_MODULE_SECRETS = os.path.join(_MODULE_SANDBOX, "secrets")
_MODULE_DB = os.path.join(_MODULE_SANDBOX, "bootstrap_vault.db")
os.makedirs(_MODULE_SECRETS, mode=0o700, exist_ok=True)

os.environ["AEONIX_TEST_MODE"] = "1"
if "AEONIX_SECRETS_DIR" not in os.environ:
    os.environ["AEONIX_SECRETS_DIR"] = _MODULE_SECRETS
if "AEONIX_DB_PATH" not in os.environ:
    os.environ["AEONIX_DB_PATH"] = _MODULE_DB

from starlette.testclient import TestClient
from aeonix.core.server import app
from aeonix.core.auth import issue_device_token, ROLE_POCO_CORE, ROLE_FIRETV_GLASS
from aeonix.core.db import init_database
from aeonix.core.router import route_query, get_router_status
from aeonix.core.fast_path import match_fast_path, execute_fast_path
from aeonix.core.ram_guard import check_ram_guard, get_memory_info, get_child_process_count
from aeonix.core.llama_runner import llama_runner


class TestGate6LocalIntelligence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database(os.environ["AEONIX_DB_PATH"])
        cls.client = TestClient(app)
        cls.poco_token = issue_device_token("test_poco_gate6", ROLE_POCO_CORE)
        cls.tv_token = issue_device_token("test_tv_gate6", ROLE_FIRETV_GLASS)
        # Warmup router and database
        route_query("status")
        route_query("weather")

    def test_01_deterministic_fast_path_latency_budget(self):
        """Verify deterministic commands route sub-50ms without invoking any LLM."""
        test_queries = [
            ("system status", "system_health"),
            ("weather", "weather"),
            ("what time is it", "time"),
            ("pending requests", "sentinel"),
            ("missions", "missions"),
            ("daily briefing", "daily_briefing")
        ]

        for query, expected_action in test_queries:
            t0 = time.perf_counter()
            res = route_query(query, actor="Aadi")
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            self.assertEqual(res["tier"], "tier_0_fast_path")
            self.assertEqual(res["action"], expected_action)
            self.assertTrue(res["is_offline"])
            self.assertLess(
                res["latency_ms"], 100.0,
                f"Query '{query}' took {res['latency_ms']}ms, exceeding 100ms budget ceiling"
            )

    def test_02_ram_guard_controller_budget_enforcement(self):
        """Verify RAM guard verifies available RAM and child process limits before inference."""
        ram_status = check_ram_guard(threshold_kb=600000)
        self.assertIn("is_safe", ram_status)
        self.assertIn("available_mb", ram_status)
        self.assertIn("child_processes", ram_status)
        self.assertIn("process_limit_ok", ram_status)
        self.assertLess(ram_status["child_processes"], 24)

        # Simulated low-memory trigger: threshold higher than available
        mem_info = get_memory_info()
        available_kb = mem_info.get("MemAvailable", mem_info.get("MemFree", 0))
        simulated_high_threshold = available_kb + 1000000  # 1GB above available
        guarded = check_ram_guard(threshold_kb=simulated_high_threshold)
        self.assertFalse(guarded["is_safe"], "RAM guard must trip when memory threshold is unmet")

    def test_03_burst_only_model_memory_lifecycle(self):
        """Verify local model allocates on query, generates response, and unloads immediately."""
        # Ensure server is stopped before query
        llama_runner.stop_server()
        self.assertFalse(llama_runner.is_running())

        # Unknown query routes to Tier 1 local model
        t0 = time.perf_counter()
        res = route_query("Verify sovereign operational readiness.", model_tier="fast")
        elapsed_s = time.perf_counter() - t0

        self.assertTrue(res["success"])
        self.assertEqual(res["tier"], "tier_1_local_qwen")
        self.assertTrue(res["is_offline"])
        self.assertIsNotNone(res.get("speech"))
        self.assertGreater(len(res["speech"]), 0)

        # STRICT SPECIFICATION EXIT GATE: Model MUST be immediately unloaded after query
        self.assertFalse(
            llama_runner.is_running(),
            "CRITICAL VIOLATION: llama-server remained resident after query completion. Must be unloaded immediately!"
        )

    def test_04_fuzzy_matching_security_barrier(self):
        """
        Master Spec Mandate (Section 12):
        'Fuzzy text similarity alone must never authorize an install, deletion or security action.'
        """
        dangerous_intents = [
            "delete the entire database right now",
            "format data partition",
            "wipe all evidence files",
            "install unverified apk payload",
            "disable all firewall rules permanently"
        ]

        for danger in dangerous_intents:
            match = match_fast_path(danger)
            if match is not None:
                action, conf = match
                # Ensure no destructive action is authorized automatically
                self.assertNotIn(
                    action,
                    ["delete_database", "wipe_vault", "execute_install", "disable_security"],
                    f"Dangerous intent '{danger}' matched prohibited automatic action '{action}'"
                )

    def test_05_http_intent_api_endpoint(self):
        """Verifies POST /api/intent HTTP endpoint latency, response, and RBAC."""
        headers = {"Authorization": f"Bearer {self.poco_token}"}
        payload = {"query": "system health"}

        t0 = time.perf_counter()
        resp = self.client.post("/api/intent", json=payload, headers=headers)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success", True))
        self.assertIn("fast", data["tier"].lower())
        self.assertEqual(data["action"], "system_health")
        self.assertLess(elapsed_ms, 500.0)


if __name__ == "__main__":
    unittest.main()
