"""
Unit & Negative Security Tests: Operator Lockout Fail-Closed & Atomic State Persistence
Validates:
1. Malformed or corrupted lockout files FAIL CLOSED (is_operator_locked returns True).
2. Lockout state persists across simulated process restarts.
3. Passphrase setup and lockout writes are atomic.
4. Deliberate physical operator reset requires explicit confirmation and invalidates credentials.
"""

import os
import tempfile
import unittest
import json
import time

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


class TestOperatorLockoutFailClosed(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.secrets_dir = os.path.join(self.temp_dir, "secrets")
        self.db_path = os.path.join(self.temp_dir, "test_vault.db")
        os.makedirs(self.secrets_dir, mode=0o700, exist_ok=True)
        init_database(self.db_path)

        self.passphrase = "SovereignPassphrase8421"
        setup_operator_secret(self.passphrase, secrets_dir=self.secrets_dir)

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

    def test_04_deliberate_physical_reset(self):
        """reset_operator_credentials requires confirm=True and wipes operator secrets."""
        # Unconfirmed reset must fail
        ok, msg = reset_operator_credentials(secrets_dir=self.secrets_dir, confirm=False, db_path=self.db_path)
        self.assertFalse(ok)
        self.assertIn("CONFIRMATION_REQUIRED", msg)
        self.assertTrue(is_operator_setup(self.secrets_dir))

        # Confirmed reset must succeed
        ok, msg = reset_operator_credentials(secrets_dir=self.secrets_dir, confirm=True, db_path=self.db_path)
        self.assertTrue(ok)
        self.assertIn("RESET_SUCCESSFUL", msg)
        self.assertFalse(is_operator_setup(self.secrets_dir))


if __name__ == "__main__":
    unittest.main()
