#!/usr/bin/env python3
"""
Runs full test discovery in an isolated environment and produces portable test run artifacts.
Verifies production isolation, reconciles discovered vs executed cases, records git provenance
and dirty digest, and exits nonzero on any discrepancy or failure.
Outputs docs/test_run_artifact.json.
"""

import os
import sys
import time
import json
import hashlib
import tempfile
import shutil
import platform
import unittest
import subprocess
from typing import Dict, List, Set, Any, Optional

PROD_SECRETS_DIR = "/data/data/com.termux/files/home/.aeonix/secrets"
PROD_DB_PATH = "/data/data/com.termux/files/home/aeonix/data/aeonix_vault.db"
TESTS_DIR = "/data/data/com.termux/files/home/aeonix/tests"
OUTPUT_PATH = "/data/data/com.termux/files/home/aeonix/docs/test_run_artifact.json"
INVENTORY_PATH = "/data/data/com.termux/files/home/aeonix/docs/test_inventory.json"


def compute_file_hash(filepath: str) -> Optional[str]:
    """Compute SHA-256 hash of a file if it exists."""
    if not os.path.exists(filepath):
        return None
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def snapshot_production_paths() -> Dict[str, Optional[str]]:
    """Capture exact cryptographic hashes of all production state files."""
    manifest = {}
    if os.path.isdir(PROD_SECRETS_DIR):
        for fname in sorted(os.listdir(PROD_SECRETS_DIR)):
            fpath = os.path.join(PROD_SECRETS_DIR, fname)
            if os.path.isfile(fpath):
                manifest[fpath] = compute_file_hash(fpath)
    manifest[PROD_DB_PATH] = compute_file_hash(PROD_DB_PATH)
    return manifest


# Capture pre-run production snapshot BEFORE any test sandbox or imports
_PRE_RUN_SNAPSHOT = snapshot_production_paths()

# Bootstrap test isolation environment BEFORE any aeonix imports
_SANDBOX_DIR = tempfile.mkdtemp(prefix="aeonix_test_portable_sandbox_")
_SANDBOX_SECRETS_DIR = os.path.join(_SANDBOX_DIR, "secrets")
_SANDBOX_DB_PATH = os.path.join(_SANDBOX_DIR, "test_vault.db")
os.makedirs(_SANDBOX_SECRETS_DIR, mode=0o700, exist_ok=True)

os.environ["AEONIX_TEST_MODE"] = "1"
os.environ["AEONIX_SECRETS_DIR"] = _SANDBOX_SECRETS_DIR
os.environ["AEONIX_DB_PATH"] = _SANDBOX_DB_PATH

sys.path.insert(0, "/data/data/com.termux/files/home")
sys.path.insert(0, "/data/data/com.termux/files/home/aeonix")

from aeonix.core.db import init_database
from aeonix.core.operator_console import setup_operator_secret

init_database(_SANDBOX_DB_PATH)
try:
    setup_operator_secret("TestSovereignSandboxPassphrase123!", secrets_dir=_SANDBOX_SECRETS_DIR)
except Exception:
    pass


def get_git_provenance() -> Dict[str, Any]:
    """Capture source commit, dirty diff digest, and git status."""
    try:
        commit_res = subprocess.run(
            ["git", "-C", "/data/data/com.termux/files/home/aeonix", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        )
        commit = commit_res.stdout.strip()
    except Exception as e:
        commit = f"ERROR: {e}"

    try:
        diff_res = subprocess.run(
            ["git", "-C", "/data/data/com.termux/files/home/aeonix", "diff", "HEAD"],
            capture_output=True, check=True
        )
        diff_bytes = diff_res.stdout
        if diff_bytes:
            dirty_digest = hashlib.sha256(diff_bytes).hexdigest()
        else:
            dirty_digest = "CLEAN"
    except Exception as e:
        dirty_digest = f"ERROR: {e}"

    try:
        status_res = subprocess.run(
            ["git", "-C", "/data/data/com.termux/files/home/aeonix", "status", "--short"],
            capture_output=True, text=True, check=True
        )
        git_status = status_res.stdout.strip()
    except Exception as e:
        git_status = f"ERROR: {e}"

    return {
        "source_commit": commit,
        "dirty_digest": dirty_digest,
        "git_status": git_status
    }


class ReconcilingTestResult(unittest.TestResult):
    """TestResult that records all outcomes and durations."""
    def __init__(self):
        super().__init__()
        self.results: List[Dict[str, Any]] = []
        self.executed_ids: Set[str] = set()
        self._start_time: Optional[float] = None

    def startTest(self, test: unittest.TestCase):
        super().startTest(test)
        self.executed_ids.add(test.id())
        self._start_time = time.time()

    def addSuccess(self, test: unittest.TestCase):
        super().addSuccess(test)
        elapsed = time.time() - (self._start_time or time.time())
        self.results.append({
            "test_id": test.id(),
            "status": "PASS",
            "duration_seconds": round(elapsed, 4),
            "error": None
        })

    def addFailure(self, test: unittest.TestCase, err):
        super().addFailure(test, err)
        elapsed = time.time() - (self._start_time or time.time())
        self.results.append({
            "test_id": test.id(),
            "status": "FAIL",
            "duration_seconds": round(elapsed, 4),
            "error": self._exc_info_to_string(err, test)
        })

    def addError(self, test: unittest.TestCase, err):
        super().addError(test, err)
        elapsed = time.time() - (self._start_time or time.time())
        self.results.append({
            "test_id": test.id(),
            "status": "ERROR",
            "duration_seconds": round(elapsed, 4),
            "error": self._exc_info_to_string(err, test)
        })

    def addSkip(self, test: unittest.TestCase, reason: str):
        super().addSkip(test, reason)
        elapsed = time.time() - (self._start_time or time.time())
        self.results.append({
            "test_id": test.id(),
            "status": "SKIP",
            "duration_seconds": round(elapsed, 4),
            "error": reason
        })


def collect_discovered_ids(suite) -> Set[str]:
    """Recursively extract all test IDs from a TestSuite."""
    ids = set()
    for item in suite:
        if isinstance(item, unittest.TestCase):
            ids.add(item.id())
        elif isinstance(item, unittest.TestSuite):
            ids.update(collect_discovered_ids(item))
    return ids


def run_portable_test_suite() -> int:
    """Execute the full test suite with production isolation and reconciliation."""
    exact_command = f"{sys.executable} {' '.join(sys.argv)}"
    runtime_info = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "exact_command": exact_command,
        "cwd": os.getcwd(),
        "pid": os.getpid()
    }

    # Step 1: Discovery
    loader = unittest.defaultTestLoader
    discovered = loader.discover(TESTS_DIR, pattern="test_*.py")
    discovered_ids = collect_discovered_ids(discovered)
    discovered_count = len(discovered_ids)

    # Step 2: Run execution
    start_wall = time.time()
    t_start_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_wall))

    result = ReconcilingTestResult()
    discovered.run(result)

    end_wall = time.time()
    t_end_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_wall))
    total_duration = round(end_wall - start_wall, 3)

    # Cleanup test sandbox
    shutil.rmtree(_SANDBOX_DIR, ignore_errors=True)

    # Step 3: Post-run production snapshot & proof verification
    post_snapshot = snapshot_production_paths()
    production_mutated = False
    mutation_details = []

    for path, pre_hash in _PRE_RUN_SNAPSHOT.items():
        post_hash = post_snapshot.get(path)
        if pre_hash != post_hash:
            production_mutated = True
            mutation_details.append(f"MUTATED: {path} pre={pre_hash} post={post_hash}")

    for path, post_hash in post_snapshot.items():
        if path not in _PRE_RUN_SNAPSHOT:
            production_mutated = True
            mutation_details.append(f"CREATED_IN_PROD: {path} hash={post_hash}")

    production_isolation_proof = {
        "verified_unchanged": not production_mutated,
        "production_secrets_dir": PROD_SECRETS_DIR,
        "production_db_path": PROD_DB_PATH,
        "pre_hashes": _PRE_RUN_SNAPSHOT,
        "post_hashes": post_snapshot,
        "mutations": mutation_details
    }

    # Step 4: Reconciliation of discovered vs executed cases
    executed_ids = result.executed_ids
    executed_count = len(result.results)
    missing_from_execution = sorted(list(discovered_ids - executed_ids))
    unexpected_executed = sorted(list(executed_ids - discovered_ids))
    reconciled = (len(missing_from_execution) == 0 and len(unexpected_executed) == 0 and discovered_count == executed_count)

    passed_count = sum(1 for r in result.results if r["status"] == "PASS")
    failed_count = sum(1 for r in result.results if r["status"] == "FAIL")
    error_count = sum(1 for r in result.results if r["status"] == "ERROR")
    skipped_count = sum(1 for r in result.results if r["status"] == "SKIP")

    pass_rate = round((passed_count / executed_count * 100), 2) if executed_count > 0 else 0.0

    # Step 5: Inventory reconciliation
    inventory_reconciled = True
    inventory_count = None
    if os.path.exists(INVENTORY_PATH):
        try:
            with open(INVENTORY_PATH, "r") as f:
                inv_data = json.load(f)
                inventory_count = inv_data.get("total_test_cases")
                if inventory_count != executed_count:
                    inventory_reconciled = False
        except Exception:
            inventory_reconciled = False

    git_prov = get_git_provenance()

    artifact = {
        "metadata": {
            "environment": "POCO M4 Pro 5G (Termux Linux)",
            "two_device_topology": "POCO M4 Pro 5G Core Mind (10.116.23.168) + Fire TV Stick Lite Glass Terminal (10.116.23.179)",
            "source_commit": git_prov["source_commit"],
            "dirty_digest": git_prov["dirty_digest"],
            "git_status": git_prov["git_status"],
            "runtime": runtime_info,
            "start_time": t_start_iso,
            "end_time": t_end_iso,
            "total_duration_seconds": total_duration,
            "discovered_tests": discovered_count,
            "executed_tests": executed_count,
            "reconciliation": {
                "reconciled": reconciled,
                "missing_from_execution": missing_from_execution,
                "unexpected_executed": unexpected_executed,
                "inventory_total": inventory_count,
                "inventory_reconciled": inventory_reconciled
            },
            "passed": passed_count,
            "failed": failed_count,
            "errors": error_count,
            "skipped": skipped_count,
            "pass_rate_percent": pass_rate,
            "production_isolation": production_isolation_proof
        },
        "test_results": result.results
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(artifact, f, indent=2)

    print("=" * 70)
    print("ÆONIX PRISM Portable Test Execution Summary")
    print(f"Source Commit: {git_prov['source_commit']}")
    print(f"Dirty Digest:  {git_prov['dirty_digest']}")
    print(f"Discovered:    {discovered_count} | Executed: {executed_count} | Reconciled: {reconciled}")
    print(f"Inventory:     {inventory_count} (Reconciled: {inventory_reconciled})")
    print(f"Results:       {passed_count} PASS | {failed_count} FAIL | {error_count} ERROR | {skipped_count} SKIP")
    print(f"Pass Rate:     {pass_rate}% in {total_duration}s")
    print(f"Prod Isolation Verified: {production_isolation_proof['verified_unchanged']}")
    print(f"Artifact:      {OUTPUT_PATH}")
    print("=" * 70)

    # Determine exit code
    success = (
        failed_count == 0 and
        error_count == 0 and
        reconciled and
        inventory_reconciled and
        production_isolation_proof["verified_unchanged"]
    )

    if not success:
        if production_mutated:
            print("FAILURE: Production path isolation violated!")
            for m in mutation_details:
                print(f"  {m}")
        if not reconciled:
            print(f"FAILURE: Discovery vs execution mismatch! Missing: {missing_from_execution}, Unexpected: {unexpected_executed}")
        if not inventory_reconciled:
            print(f"FAILURE: Inventory mismatch! Inventory has {inventory_count}, executed has {executed_count}")
        if failed_count > 0 or error_count > 0:
            print(f"FAILURE: {failed_count} tests failed, {error_count} errors occurred.")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = run_portable_test_suite()
    sys.exit(exit_code)
