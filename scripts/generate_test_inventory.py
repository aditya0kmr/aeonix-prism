#!/usr/bin/env python3
"""
Generates machine-readable test inventory for ÆONIX PRISM test suites.
Extracts module, class, method, docstring, and security categorization.
Outputs docs/test_inventory.json.
"""

import os
import sys
import json
import inspect
import unittest
import importlib

sys.path.insert(0, "/data/data/com.termux/files/home")
sys.path.insert(0, "/data/data/com.termux/files/home/aeonix")

TESTS_DIR = "/data/data/com.termux/files/home/aeonix/tests"
OUTPUT_PATH = "/data/data/com.termux/files/home/aeonix/docs/test_inventory.json"


def generate_inventory():
    loader = unittest.defaultTestLoader
    discovered = loader.discover(TESTS_DIR, pattern="test_*.py")

    inventory = {
        "generated_at": os.popen("date -u +%Y-%m-%dT%H:%M:%SZ").read().strip(),
        "total_test_suites": 0,
        "total_test_cases": 0,
        "suites": []
    }

    suite_map = {}

    def extract_tests(suite):
        for item in suite:
            if isinstance(item, unittest.TestCase):
                cls_name = item.__class__.__name__
                mod_name = item.__class__.__module__
                method_name = item._testMethodName
                method_obj = getattr(item, method_name, None)
                doc = inspect.getdoc(method_obj) or ""

                if mod_name not in suite_map:
                    suite_map[mod_name] = {
                        "module": mod_name,
                        "class": cls_name,
                        "file_path": inspect.getfile(item.__class__),
                        "tests": []
                    }

                is_negative = any(kw in method_name.lower() or kw in doc.lower() for kw in [
                    "negative", "reject", "block", "fail", "prohibit", "tamper", "corrupt", "unauthorized", "bypass", "mismatch"
                ])

                suite_map[mod_name]["tests"].append({
                    "test_name": method_name,
                    "docstring": doc.split("\n")[0] if doc else "",
                    "full_docstring": doc,
                    "is_negative_security_test": is_negative
                })
            elif isinstance(item, unittest.TestSuite):
                extract_tests(item)

    extract_tests(discovered)

    total_tests = 0
    for mod_name in sorted(suite_map.keys()):
        suite_info = suite_map[mod_name]
        suite_info["test_count"] = len(suite_info["tests"])
        total_tests += suite_info["test_count"]
        inventory["suites"].append(suite_info)

    inventory["total_test_suites"] = len(inventory["suites"])
    inventory["total_test_cases"] = total_tests

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(inventory, f, indent=2)

    print(f"Generated test inventory with {total_tests} test cases across {len(inventory['suites'])} suites.")
    print(f"Output saved to {OUTPUT_PATH}")
    return inventory


if __name__ == "__main__":
    generate_inventory()
