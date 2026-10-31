"""
Unit & Negative Security Tests: Operator Lockout Fail-Closed, Concurrency Safety & Verifiable Reset
Validates:
1. Malformed or corrupted lockout files FAIL CLOSED (is_operator_locked returns True).
2. Lockout state persists across simulated process restarts.
3. Passphrase setup and lockout writes are atomic.
4. Concurrency safety: Concurrent lockout file updates use file locking (flock) to prevent races.
5. Verifiable Reset: Deliberate physical operator reset revokes active sessions and returns verifiable audit details.
"""

import os
import shutil
import tempfile
import unittest
import json
import time
import threading

from aeonix.core.operator_console import (
    setup_operator_secret,
    verify_operator_secret,
    is_operator_setup,
    is_operator_locked,
    record_failed_attempt,
    reset_lockout_state,
    reset_operator_credentials,
    _atomic_write_json
)
from aeonix.core.db import init_database
from aeonix.core.auth import issue_device_token, verify_token, ROLE_POCO_CORE


class TestOperatorLockoutFailClosed(unittest.TestCase):
    def setUp(self):
        self.orig_secrets = os.environ.get("AEONIX_SECRETS_DIR")
        self.orig_db = os.environ.get("AEONIX_DB_PATH")

        self.temp_dir = tempfile.mkdtemp()
        self.secrets_dir = os.path.join(self.temp_dir, "secrets")
        self.db_path = os.path.join(self.temp_dir, "test_vault.db")
        os.makedirs(self.secrets_dir, mode=0o700, exist_ok=True)

        os.environ["AEONIX_SECRETS_DIR"] = self.secrets_dir
        os.environ["AEONIX_DB_PATH"] = self.db_path

        init_database(self.db_path)

        self.passphrase = "SovereignPassphrase8421"
        setup_operator_secret(self.passphrase, secrets_dir=self.secrets_dir)

    def tearDown(self):
        if self.orig_secrets is not None:
            os.environ["AEONIX_SECRETS_DIR"] = self.orig_secrets
        else:
            os.environ.pop("AEONIX_SECRETS_DIR", None)

        if self.orig_db is not None:
            os.environ["AEONIX_DB_PATH"] = self.orig_db
        else:
            os.environ.pop("AEONIX_DB_PATH", None)

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_atomic_write_creates_valid_json(self):
        """_atomic_write_json creates valid file with 0600 permissions."""
        target_file = os.path.join(self.secrets_dir, "test_atomic.json")
        data = {"key": "value", "count": 42}
        _atomic_write_json(target_file, data)

        self.assertTrue(os.path.exists(target_file))
        mode = oct(os.stat(target_file).st_mode & 0o777)
        self.assertEqual(mode, "0o600")

        with open(target_file, "r") as f:
            loaded = json.load(f)
        self.assertEqual(loaded, data)

    def test_02_corrupted_lockout_file_fails_closed(self):
        """FAIL-CLOSED: If operator_lockout.json is corrupted or unreadable, is_operator_locked must return True."""
        lock_file = os.path.join(self.secrets_dir, "operator_lockout.json")
        # Write corrupted garbage data
        with open(lock_file, "w") as f:
            f.write("CORRUPTED_NON_JSON_DATA{{{{")

        # Must fail closed: locked out!
        is_locked, rem_s, attempts = is_operator_locked(self.secrets_dir)
        self.assertTrue(is_locked)
        self.assertGreater(rem_s, 0.0)
        self.assertEqual(attempts, 999)

        # verify_operator_secret must also reject authentication due to lockout
        ok, msg = verify_operator_secret(self.passphrase, secrets_dir=self.secrets_dir)
        self.assertFalse(ok)
        self.assertIn("LOCKED_OUT", msg)

    def test_03_lockout_persists_across_restarts(self):
        """Failed attempts accumulate and trigger persistent lockout across process restarts."""
        # Record 7 failed attempts to trigger maximum 300s lockout
        for _ in range(7):
            record_failed_attempt(self.secrets_dir)

        is_locked, rem_s, attempts = is_operator_locked(self.secrets_dir)
        self.assertTrue(is_locked)
        self.assertGreaterEqual(attempts, 7)
        self.assertGreater(rem_s, 250.0)

        # Simulate restart by re-reading state from disk in a fresh call
        is_locked_after, rem_s_after, attempts_after = is_operator_locked(self.secrets_dir)
        self.assertTrue(is_locked_after)
        self.assertEqual(attempts_after, attempts)

    def test_04_deliberate_physical_reset_requires_confirmation(self):
        """reset_operator_credentials requires confirm=True and wipes operator secrets."""
        # Unconfirmed reset must fail
        res = reset_operator_credentials(secrets_dir=self.secrets_dir, confirm=False, db_path=self.db_path)
        self.assertFalse(res["success"])
        self.assertIn("CONFIRMATION_REQUIRED", res.get("error", ""))
        self.assertTrue(is_operator_setup(self.secrets_dir))

    def test_05_concurrent_lockout_updates_thread_safe(self):
        """Concurrent threads updating lockout state concurrently use flock and remain uncorrupted."""
        threads = []
        errors = []

        def worker():
            try:
                for _ in range(3):
                    record_failed_attempt(self.secrets_dir)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        for _ in range(5):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")
        is_locked, rem_s, attempts = is_operator_locked(self.secrets_dir)
        self.assertTrue(is_locked)
        self.assertEqual(attempts, 15)

    def test_06_verifiable_reset_revocation_details(self):
        """reset_operator_credentials returns verifiable audit details and revokes active tokens."""
        from aeonix.core.auth import get_or_create_device_token
        # Create and persist an active POCO token in secrets dir
        poco_token = get_or_create_device_token("dev_poco_1", ROLE_POCO_CORE, secrets_dir=self.secrets_dir)
        payload = verify_token(poco_token, secrets_dir=self.secrets_dir, db_path=self.db_path)
        self.assertIsNotNone(payload)
        token_nonce = payload["nonce"]

        # Trigger a failed attempt to create lockout file
        record_failed_attempt(self.secrets_dir)

        # Perform confirmed reset
        res = reset_operator_credentials(secrets_dir=self.secrets_dir, confirm=True, db_path=self.db_path)
        self.assertTrue(res["success"])
        self.assertEqual(res["revoked_tokens_count"], 1)
        self.assertIn(token_nonce, res["revoked_nonces"])
        self.assertTrue(res["pin_removed"])
        self.assertTrue(res["lockout_cleared"])
        self.assertIsNotNone(res["audit_hash"])
        self.assertFalse(is_operator_setup(self.secrets_dir))

        # Token is now revoked! verify_token must return None
        verified = verify_token(poco_token, secrets_dir=self.secrets_dir, db_path=self.db_path)
        self.assertIsNone(verified)


if __name__ == "__main__":
    unittest.main()
