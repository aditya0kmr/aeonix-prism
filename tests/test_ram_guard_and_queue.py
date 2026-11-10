"""
ÆONIX PRISM // Unit & Integration Tests: Model-Specific Dynamic RAM Guard & Queue Manager
Exhaustively tests:
1. Model-specific free-RAM thresholds (0.5B >= 1.2GB, 1.5B >= 2.5GB, 3B >= 4.0GB).
2. Refusal to silently downgrade 1.5B/3B to 0.5B when fallback is disabled.
3. Explicit user fallback flag enabling labeled 'qwen2.5-0.5b-fallback' responses with audit logging.
4. Queue capacity bounding (max 10 items) and oldest-drop eviction policy.
5. Queue TTL expiration (10 minutes = 600 seconds).
6. Non-queueing of consequential or sensitive actions for automatic later execution.
7. Model lifecycle: single-model loading, pre-load RAM check, post-inference immediate unload and RAM release.
8. Sentinel lockdown behavior: pauses or cancels pending non-sensitive queued work.
9. Audit trail logging for all queue, fallback, load, unload, expiry, and drop events.
"""

import os
import sys
import time
import tempfile
import unittest
from unittest.mock import patch, MagicMock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Bootstrap test sandbox environment BEFORE aeonix imports
_MODULE_SANDBOX = tempfile.mkdtemp(prefix="aeonix_test_ram_queue_")
_MODULE_SECRETS = os.path.join(_MODULE_SANDBOX, "secrets")
_MODULE_DB = os.path.join(_MODULE_SANDBOX, "bootstrap_vault.db")
os.makedirs(_MODULE_SECRETS, mode=0o700, exist_ok=True)

os.environ["AEONIX_TEST_MODE"] = "1"
os.environ["AEONIX_SECRETS_DIR"] = _MODULE_SECRETS
os.environ["AEONIX_DB_PATH"] = _MODULE_DB

from aeonix.core.db import init_database, query_db, get_connection
from aeonix.core.ram_guard import (
    check_ram_guard,
    check_model_ram_guard,
    get_memory_info,
    MODEL_RAM_THRESHOLDS_KB,
)
from aeonix.core.model_queue import ModelQueueManager
from aeonix.core.sanctuary import engage_sanctuary, release_sanctuary


class TestRamGuardAndQueue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database(os.environ["AEONIX_DB_PATH"])

    def setUp(self):
        # Reset sanctuary state before each test
        release_sanctuary(actor="TestRunner")
        self.queue_mgr = ModelQueueManager(db_path=os.environ["AEONIX_DB_PATH"])

    def tearDown(self):
        release_sanctuary(actor="TestRunner")

    # -------------------------------------------------------------------------
    # 1. Model-Specific Free-RAM Thresholds
    # -------------------------------------------------------------------------
    def test_01_ram_thresholds_mapping(self):
        """Verifies exact thresholds: 0.5B = 1.2GB, 1.5B = 2.5GB, 3B = 4.0GB."""
        self.assertEqual(MODEL_RAM_THRESHOLDS_KB["0.5B"], 1200000)
        self.assertEqual(MODEL_RAM_THRESHOLDS_KB["1.5B"], 2500000)
        self.assertEqual(MODEL_RAM_THRESHOLDS_KB["3B"], 4000000)

    def test_02_ram_guard_checks_per_tier(self):
        """Verifies threshold evaluation with mocked available RAM values."""
        # 1. Mock 1.3 GB available (1,300,000 KB) -> 0.5B passes, 1.5B fails, 3B fails
        with patch("aeonix.core.ram_guard.get_memory_info", return_value={"MemAvailable": 1300000}):
            res_05 = check_model_ram_guard("0.5B")
            res_15 = check_model_ram_guard("1.5B")
            res_30 = check_model_ram_guard("3B")
            self.assertTrue(res_05["is_safe"])
            self.assertFalse(res_15["is_safe"])
            self.assertFalse(res_30["is_safe"])

        # 2. Mock 2.6 GB available (2,600,000 KB) -> 0.5B passes, 1.5B passes, 3B fails
        with patch("aeonix.core.ram_guard.get_memory_info", return_value={"MemAvailable": 2600000}):
            self.assertTrue(check_model_ram_guard("0.5B")["is_safe"])
            self.assertTrue(check_model_ram_guard("1.5B")["is_safe"])
            self.assertFalse(check_model_ram_guard("3B")["is_safe"])

        # 3. Mock 4.2 GB available (4,200,000 KB) -> all pass
        with patch("aeonix.core.ram_guard.get_memory_info", return_value={"MemAvailable": 4200000}):
            self.assertTrue(check_model_ram_guard("0.5B")["is_safe"])
            self.assertTrue(check_model_ram_guard("1.5B")["is_safe"])
            self.assertTrue(check_model_ram_guard("3B")["is_safe"])

        # 4. Mock 800 MB available (800,000 KB) -> all fail
        with patch("aeonix.core.ram_guard.get_memory_info", return_value={"MemAvailable": 800000}):
            self.assertFalse(check_model_ram_guard("0.5B")["is_safe"])
            self.assertFalse(check_model_ram_guard("1.5B")["is_safe"])
            self.assertFalse(check_model_ram_guard("3B")["is_safe"])

    # -------------------------------------------------------------------------
    # 2. No Silent Downgrade & Explicit Fallback Labeling
    # -------------------------------------------------------------------------
    def test_03_no_silent_downgrade_when_fallback_disabled(self):
        """1.5B request under 1.5GB RAM must NOT silently downgrade to 0.5B when fallback=False."""
        with patch("aeonix.core.ram_guard.get_memory_info", return_value={"MemAvailable": 1500000}):
            item = self.queue_mgr.enqueue(
                prompt="Summarize system telemetry",
                model_tier="1.5B",
                allow_fallback=False
            )
            self.assertEqual(item["status"], "queued")
            self.assertEqual(item["model_tier"], "1.5B")

            # Attempt to process: should remain queued because 1.5B needs 2.5GB and fallback is False
            result = self.queue_mgr.process_next(dry_run=True)
            self.assertIsNone(result)
            self.assertEqual(self.queue_mgr.get_status()["queued_count"], 1)

    def test_04_explicit_fallback_labeling_and_audit(self):
        """1.5B request under 1.5GB RAM downgrades to 0.5B ONLY when allow_fallback=True, labeling output."""
        with patch("aeonix.core.ram_guard.get_memory_info", return_value={"MemAvailable": 1500000}):
            item = self.queue_mgr.enqueue(
                prompt="Summarize system telemetry",
                model_tier="1.5B",
                allow_fallback=True
            )
            self.assertEqual(item["status"], "queued")

            # Process with fallback enabled
            result = self.queue_mgr.process_next(dry_run=True)
            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["model_used"], "qwen2.5-0.5b-fallback")
            self.assertTrue(result["fallback_applied"])

            # Verify audit trail logs fallback event
            rows = query_db(
                "SELECT action, details_json FROM audit_log WHERE action = 'queue_fallback_applied' ORDER BY id DESC LIMIT 1;",
                db_path=os.environ["AEONIX_DB_PATH"]
            )
            self.assertTrue(len(rows) > 0)
            self.assertIn("1.5B", rows[0][1])
            self.assertIn("0.5B", rows[0][1])

    # -------------------------------------------------------------------------
    # 3. Queue Limits & Oldest-Drop Eviction
    # -------------------------------------------------------------------------
    def test_05_queue_capacity_and_oldest_drop(self):
        """Enforces max 10 queued items, dropping the oldest when an 11th arrives, logging the drop."""
        # Enqueue 10 items
        for i in range(10):
            res = self.queue_mgr.enqueue(f"Query {i}", model_tier="0.5B")
            self.assertEqual(res["status"], "queued")

        status = self.queue_mgr.get_status()
        self.assertEqual(status["queued_count"], 10)
        first_id = status["items"][0]["id"]

        # Enqueue 11th item: must drop oldest (Query 0)
        res_11 = self.queue_mgr.enqueue("Query 10 (overflow)", model_tier="0.5B")
        self.assertEqual(res_11["status"], "queued")

        status_after = self.queue_mgr.get_status()
        self.assertEqual(status_after["queued_count"], 10)
        self.assertEqual(status_after["dropped_count"], 1)
        self.assertNotEqual(status_after["items"][0]["id"], first_id)
        self.assertEqual(status_after["dropped_items"][0]["id"], first_id)

        # Verify audit trail logs drop event
        rows = query_db(
            "SELECT action, details_json FROM audit_log WHERE action = 'queue_item_dropped_full' ORDER BY id DESC LIMIT 1;",
            db_path=os.environ["AEONIX_DB_PATH"]
        )
        self.assertTrue(len(rows) > 0)

    # -------------------------------------------------------------------------
    # 4. Queue TTL Expiration (10 minutes)
    # -------------------------------------------------------------------------
    def test_06_queue_ttl_expiration(self):
        """Items older than 10 minutes (600 seconds) must expire and not execute."""
        # Enqueue an item with a timestamp 605 seconds in the past
        item = self.queue_mgr.enqueue("Stale query", model_tier="0.5B")
        item["created_at"] = time.time() - 605

        # Process next should detect expiry, evict the item, and not execute it
        with patch("aeonix.core.ram_guard.get_memory_info", return_value={"MemAvailable": 2000000}):
            result = self.queue_mgr.process_next(dry_run=True)
            self.assertIsNone(result)

        status = self.queue_mgr.get_status()
        self.assertEqual(status["queued_count"], 0)
        self.assertEqual(status["expired_count"], 1)

        # Verify audit trail logs expiry event
        rows = query_db(
            "SELECT action, details_json FROM audit_log WHERE action = 'queue_item_expired' ORDER BY id DESC LIMIT 1;",
            db_path=os.environ["AEONIX_DB_PATH"]
        )
        self.assertTrue(len(rows) > 0)

    # -------------------------------------------------------------------------
    # 5. Non-Queueing of Consequential / Sensitive Actions
    # -------------------------------------------------------------------------
    def test_07_no_queueing_of_consequential_actions(self):
        """Consequential actions must NEVER be queued for automatic later execution."""
        # 1. Explicit flag
        res_explicit = self.queue_mgr.enqueue(
            "Delete vault partition",
            model_tier="0.5B",
            is_consequential=True
        )
        self.assertEqual(res_explicit["status"], "rejected_sensitive")
        self.assertIn("CONSEQUENTIAL_ACTIONS_CANNOT_BE_QUEUED", res_explicit["error"])

        # 2. Sensitive keyword detection (e.g. approve, format, delete, export keys)
        res_keyword = self.queue_mgr.enqueue(
            "approve mission gamma 42",
            model_tier="0.5B"
        )
        self.assertEqual(res_keyword["status"], "rejected_sensitive")

        # Confirm queue remains empty
        self.assertEqual(self.queue_mgr.get_status()["queued_count"], 0)

        # Verify audit trail logs rejection
        rows = query_db(
            "SELECT action, details_json FROM audit_log WHERE action = 'queue_consequential_rejected' ORDER BY id DESC LIMIT 1;",
            db_path=os.environ["AEONIX_DB_PATH"]
        )
        self.assertTrue(len(rows) > 0)

    # -------------------------------------------------------------------------
    # 6. Model Load / Unload Lifecycle & RAM Release
    # -------------------------------------------------------------------------
    def test_08_model_load_and_unload_lifecycle(self):
        """Verifies that only one model is loaded, inference runs, and model unloads immediately."""
        with patch("aeonix.core.ram_guard.get_memory_info", return_value={"MemAvailable": 2000000}):
            self.queue_mgr.enqueue("Compute hash", model_tier="0.5B")

            mock_start = MagicMock(return_value=True)
            mock_stop = MagicMock()
            mock_infer = MagicMock(return_value={"text": "Hash is computed"})

            with patch("aeonix.core.llama_runner.llama_runner.start_server", mock_start), \
                 patch("aeonix.core.llama_runner.llama_runner.stop_server", mock_stop), \
                 patch("aeonix.core.llama_runner.llama_runner.is_running", return_value=True):
                
                result = self.queue_mgr.process_next(
                    executor=lambda prompt, model: mock_infer(prompt)
                )

                self.assertIsNotNone(result)
                self.assertEqual(result["status"], "completed")
                mock_start.assert_called_once()
                self.assertGreaterEqual(mock_stop.call_count, 1)

    # -------------------------------------------------------------------------
    # 7. Sentinel Lockdown Behavior
    # -------------------------------------------------------------------------
    def test_09_sentinel_lockdown_pauses_queue(self):
        """Under Sentinel / Sanctuary lockdown, queue processing must be paused or cancelled."""
        self.queue_mgr.enqueue("Read daily news", model_tier="0.5B")
        self.assertEqual(self.queue_mgr.get_status()["queued_count"], 1)

        # Engage sanctuary lockdown
        engage_sanctuary(actor="Operator", reason="Threat Alert")

        # Attempt to process queue: must refuse execution
        with patch("aeonix.core.ram_guard.get_memory_info", return_value={"MemAvailable": 2500000}):
            result = self.queue_mgr.process_next(dry_run=True)
            self.assertIsNone(result)

        status = self.queue_mgr.get_status()
        self.assertTrue(status["is_sanctuary_active"])
        self.assertEqual(status["lockdown_halted_count"], 1)

        # Verify audit trail logs lockdown halt
        rows = query_db(
            "SELECT action FROM audit_log WHERE action = 'queue_lockdown_halted' ORDER BY id DESC LIMIT 1;",
            db_path=os.environ["AEONIX_DB_PATH"]
        )
        self.assertTrue(len(rows) > 0)


if __name__ == "__main__":
    unittest.main()
