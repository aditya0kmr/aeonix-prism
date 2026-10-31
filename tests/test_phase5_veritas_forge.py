"""
ÆONIX PRISM // Phase 5 Verification Suite: VERITAS & FORGE
Verifies digital forensics vault, case management, immutable evidence hashing,
chronological timeline building, cryptographically verified report export,
typed developer engine, risk tier classification, and Sentinel holds.
Zero cloud API dependencies.
"""

import os
import sys
import tempfile
import unittest
import time
from typing import Dict, Any

sys.path.insert(0, "/data/data/com.termux/files/home/aeonix")
sys.path.insert(0, "/data/data/com.termux/files/home")

from aeonix.core.db import init_database
from aeonix.core.veritas import (
    create_case,
    ingest_evidence,
    verify_evidence,
    generate_case_manifest,
    build_case_timeline,
    export_case_report
)
from aeonix.core.forge import (
    assess_command_risk,
    draft_command_from_prompt,
    execute_sandboxed_command,
    execute_typed_operation,
    get_git_telemetry
)

class TestPhase5VeritasAndForge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def test_veritas_case_lifecycle_and_immutable_evidence(self):
        """Test case creation, SHA-256 evidence ingestion, and integrity verification."""
        case_id = create_case("Operation Phase 5 Verification", "Veritas Forensics Audit", "Authorized Sovereign Audit")
        self.assertTrue(case_id.startswith("case_"))

        # Create temporary evidence file
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        tmp.write(b"VERITAS_FORENSIC_ARTIFACT_STAGE5_100PCT_GENUINE\n")
        tmp.close()

        try:
            ing = ingest_evidence(case_id, tmp.name, mime_type="text/plain", metadata={"source": "test_phase5"})
            self.assertEqual(ing["status"], "secured")
            self.assertIn("sha256", ing)

            # Verify integrity
            ver = verify_evidence(ing["evidence_id"])
            self.assertTrue(ver["verified"])
            self.assertEqual(ver["status"], "intact")

            # Verify manifest
            manifest = generate_case_manifest(case_id)
            self.assertEqual(manifest["case_id"], case_id)
            self.assertTrue(manifest["all_evidence_intact"])
            self.assertEqual(manifest["total_evidence_items"], 1)
        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)

    def test_veritas_chronological_timeline_builder(self):
        """Test chronological timeline construction merging case, custody, and audit events."""
        case_id = create_case("Timeline Audit Case", "Testing chronological ordering")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".log")
        tmp.write(b"Audit log entry timestamp test\n")
        tmp.close()

        try:
            ingest_evidence(case_id, tmp.name, mime_type="text/plain")
            timeline = build_case_timeline(case_id)
            self.assertGreaterEqual(len(timeline), 2)

            # Verify strictly chronological ordering
            timestamps = [entry["timestamp"] for entry in timeline]
            self.assertEqual(timestamps, sorted(timestamps))

            # Verify event types present
            event_types = [entry["event_type"] for entry in timeline]
            self.assertIn("CASE_CREATED", event_types)
            self.assertIn("EVIDENCE_CUSTODY_STEP", event_types)
        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)

    def test_veritas_forensic_report_export(self):
        """Test generating and exporting an immutable case report with cryptographic digest."""
        case_id = create_case("Forensic Dossier Export Case", "Exporting examination report")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        tmp.write(b"FORENSIC_EVIDENCE_PAYLOAD_FOR_EXPORT\n")
        tmp.close()

        try:
            ingest_evidence(case_id, tmp.name)
            report = export_case_report(case_id)
            self.assertTrue(report["success"])
            self.assertIn("report_file", report)
            self.assertTrue(os.path.exists(report["report_file"]))
            self.assertIn("report_sha256", report)
            self.assertTrue(report["all_evidence_intact"])

            # Verify the exported file is read-only (mode 0o444)
            file_mode = oct(os.stat(report["report_file"]).st_mode & 0o777)
            self.assertEqual(file_mode, "0o444")
        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)

    def test_forge_natural_language_drafting_and_risk(self):
        """Test natural language translation into shell commands and risk assessment."""
        d1 = draft_command_from_prompt("check git branch")
        self.assertIn("git", d1["drafted_command"])
        self.assertEqual(d1["risk"]["risk_level"], "R0_SAFE")

        d2 = draft_command_from_prompt("remove temporary file")
        self.assertIn("rm", d2["drafted_command"])
        self.assertTrue(d2["risk"]["is_consequential"])

    def test_forge_sandboxed_safe_execution(self):
        """Test executing safe read-only operations via typed allowlist."""
        res = execute_typed_operation("echo", ["PHASE_5_FORGE_OK"])
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("PHASE_5_FORGE_OK", res["output"])

    def test_forge_sentinel_hold_on_consequential_operations(self):
        """Test that destructive operations halt at Sentinel Gate and return request ID."""
        res = execute_sandboxed_command("rm -rf /data/data/com.termux/files/usr/tmp/unauthorized.txt")
        self.assertEqual(res["status"], "sentinel_gate_hold")
        self.assertIn("sentinel_", res["request_id"])

    def test_forge_git_telemetry_live(self):
        """Test real Git branch, commit SHA, and remote introspection."""
        git_info = get_git_telemetry()
        self.assertTrue(git_info["success"])
        self.assertEqual(git_info["repository"], "aeonix")
        self.assertEqual(git_info["branch"], "main")
        self.assertIn("latest_commit", git_info)
        self.assertGreaterEqual(len(git_info["latest_commit"]), 7) # Valid Git commit hash


if __name__ == "__main__":
    unittest.main()
