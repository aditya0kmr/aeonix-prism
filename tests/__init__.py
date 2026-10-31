import os
import tempfile
import atexit
import shutil

# Guarantee test environment isolation from default operator secrets, lockout and live databases (Item 5)
_TEST_SANDBOX_DIR = tempfile.mkdtemp(prefix="aeonix_test_sandbox_")
_TEST_SECRETS_DIR = os.path.join(_TEST_SANDBOX_DIR, "secrets")
_TEST_DB_PATH = os.path.join(_TEST_SANDBOX_DIR, "test_vault.db")

os.makedirs(_TEST_SECRETS_DIR, mode=0o700, exist_ok=True)

# Bootstrap test mode and isolated paths BEFORE project imports (Requirement 2)
os.environ["AEONIX_TEST_MODE"] = "1"
if "AEONIX_SECRETS_DIR" not in os.environ:
    os.environ["AEONIX_SECRETS_DIR"] = _TEST_SECRETS_DIR

if "AEONIX_DB_PATH" not in os.environ:
    os.environ["AEONIX_DB_PATH"] = _TEST_DB_PATH

from aeonix.core.db import init_database
from aeonix.core.operator_console import setup_operator_secret

init_database(_TEST_DB_PATH)
try:
    setup_operator_secret("TestSovereignSandboxPassphrase123!", secrets_dir=_TEST_SECRETS_DIR)
except Exception:
    pass

def _cleanup():
    shutil.rmtree(_TEST_SANDBOX_DIR, ignore_errors=True)

atexit.register(_cleanup)
