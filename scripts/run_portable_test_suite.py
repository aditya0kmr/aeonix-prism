#!/usr/bin/env python3
"""
Runs full test discovery in an isolated environment and produces portable test run artifacts.
Outputs docs/test_run_artifact.json.
"""

import os
import sys
import time
import json
import unittest
import tempfile
import shutil

sys.path.insert(0, "/data/data/com.termux/files/home")
sys.path.insert(0, "/data/data/com.termux/files/home/aeonix")

TESTS_DIR = "/data/data/com.termux/files/home/aeonix/tests"
OUTPUT_PATH = "/data/data/com.termux/files/home/aeonix/docs/test_run_artifact.json"


class PortableTestResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.results = []
        self._start_time = None

    def startTest(self, test):
        super().startTest(test)
        self._start_time = time.time()

    def addSuccess(self, test):
        super().addSuccess(test)
        elapsed = time.time() - (self._start_time or time.time())
        self.results.append({
            "test_id": test.id(),
            "status": "PASS",
            "duration_seconds": round(elapsed, 4),
            "error": None
        })

    def addFailure(self, test, err):
        super().addFailure(test, err)
        elapsed = time.time() - (self._start_time or time.time())
        self.results.append({
            "test_id": test.id(),
            "status": "FAIL",
            "duration_seconds": round(elapsed, 4),
            "error": self._exc_info_to_string(err, test)
        })

    def addError(self, test, err):
        super().addError(test, err)
        elapsed = time.time() - (self._start_time or time.time())
        self.results.append({
            "test_id": test.id(),
            "status": "ERROR",
            "duration_seconds": round(elapsed, 4),
            "error": self._exc_info_to_string(err, test)
        })


def run_tests():
    start_wall = time.time()
    t_start_iso = os.popen("date -u +%Y-%m-%dT%H:%M:%SZ").read().strip()

    loader = unittest.defaultTestLoader
    discovered = loader.discover(TESTS_DIR, pattern="test_*.py")

    result = PortableTestResult()
    discovered.run(result)

    total_duration = round(time.time() - start_wall, 3)
    t_end_iso = os.popen("date -u +%Y-%m-%dT%H:%M:%SZ").read().strip()

    passed_count = sum(1 for r in result.results if r["status"] == "PASS")
    failed_count = sum(1 for r in result.results if r["status"] == "FAIL")
    error_count = sum(1 for r in result.results if r["status"] == "ERROR")

    artifact = {
        "metadata": {
            "environment": "POCO M4 Pro 5G (Termux Linux)",
            "start_time": t_start_iso,
            "end_time": t_end_iso,
            "total_duration_seconds": total_duration,
            "total_tests": len(result.results),
            "passed": passed_count,
            "failed": failed_count,
            "errors": error_count,
            "pass_rate_percent": round((passed_count / len(result.results) * 100), 2) if result.results else 0.0
        },
        "test_results": result.results
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(artifact, f, indent=2)

    print("=" * 60)
    print(f"ÆONIX PRISM Test Run Completed: {passed_count}/{len(result.results)} PASSED")
    print(f"Pass Rate: {artifact['metadata']['pass_rate_percent']}% | Total Time: {total_duration}s")
    print(f"Artifact written to {OUTPUT_PATH}")
    print("=" * 60)
    return artifact


if __name__ == "__main__":
    run_tests()
