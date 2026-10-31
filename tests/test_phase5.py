"""
ÆONIX PRISM // Phase 5 Test & Verification Suite
Verifies FORGE Developer Engine, Shell Sandboxing, Git Telemetry, and VISIA Visual Forensic OCR.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, "/data/data/com.termux/files/home")

from PIL import Image, ImageDraw
from aeonix.core.db import init_database
from aeonix.core.veritas import create_case
from aeonix.core.forge import (
    assess_command_risk,
    draft_command_from_prompt,
    execute_sandboxed_command,
    get_git_telemetry
)
from aeonix.core.visia import analyze_visual_artifact
from aeonix.core.fast_path import match_fast_path, execute_fast_path

class TestPhase5ForgeAndVisia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def test_forge_draft_and_risk_assessment(self):
        """Test natural language command drafting and risk tier classification."""
        draft1 = draft_command_from_prompt("check git status")
        self.assertIn("git status", draft1["drafted_command"])
        self.assertEqual(draft1["risk"]["risk_level"], "R0_SAFE")
        self.assertFalse(draft1["risk"]["is_consequential"])

        draft2 = draft_command_from_prompt("delete audit.log")
        self.assertIn("rm", draft2["drafted_command"])
        self.assertEqual(draft2["risk"]["risk_level"], "R3_HIGH")
        self.assertTrue(draft2["risk"]["is_consequential"])

        risk_crit = assess_command_risk("rm -rf /data/data/test")
        self.assertEqual(risk_crit["risk_level"], "R4_CRITICAL")
        self.assertTrue(risk_crit["is_consequential"])

    def test_forge_sandboxed_execution_and_sentinel_hold(self):
        """Test safe command execution vs Sentinel Gate hold on destructive directives."""
        # Safe command execution
        res_safe = execute_sandboxed_command("echo 'AEONIX_FORGE_OK'")
        self.assertEqual(res_safe["status"], "executed")
        self.assertEqual(res_safe["exit_code"], 0)
        self.assertEqual(res_safe["output"], "AEONIX_FORGE_OK")

        # Destructive command MUST pause at Sentinel Gate
        res_destruct = execute_sandboxed_command("rm -f /data/data/com.termux/files/usr/tmp/danger.txt")
        self.assertEqual(res_destruct["status"], "sentinel_gate_hold")
        self.assertIn("sentinel_", res_destruct["request_id"])

    def test_forge_git_telemetry(self):
        """Test live Git repository branch and commit introspection."""
        git_data = get_git_telemetry()
        self.assertTrue(git_data["success"])
        self.assertEqual(git_data["repository"], "aeonix")
        self.assertEqual(git_data["branch"], "main")
        self.assertIn("latest_commit", git_data)

    def test_visia_forensic_analysis_and_ocr(self):
        """Test image geometry, SHA-256, OCR text extraction, and VERITAS case integration."""
        # Create synthetic image with rendered text
        tmp_dir = tempfile.gettempdir()
        img_path = os.path.join(tmp_dir, "visia_test_doc.png")
        img = Image.new("RGB", (400, 150), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 60), "SOVEREIGN AGENT VERIFIED", fill=(0, 0, 0))
        img.save(img_path)

        # Create VERITAS case
        case_id = create_case("VISIA Forensic Document Case", "Automated OCR Verification")

        # Analyze
        analysis = analyze_visual_artifact(img_path, case_id=case_id, run_ocr=True)
        self.assertTrue(analysis["success"])
        self.assertEqual(analysis["format"], "PNG")
        self.assertEqual(analysis["dimensions"]["width"], 400)
        self.assertEqual(analysis["dimensions"]["height"], 150)
        self.assertIn("sha256", analysis)
        self.assertIn("case_link", analysis)
        self.assertEqual(analysis["case_link"]["status"], "secured")

        # OCR output
        ocr = analysis["ocr"]
        self.assertTrue(ocr["success"])
        self.assertIn("SOVEREIGN", ocr["text"].upper())

    def test_fast_path_forge_triggers(self):
        """Test sub-20ms intent matching for Git telemetry and developer status."""
        match = match_fast_path("git status")
        self.assertIsNotNone(match)
        action, conf = match
        self.assertEqual(action, "git_telemetry")

        res = execute_fast_path(action)
        self.assertIn("git", res)
        self.assertEqual(res["layout_intent"]["screen"], "focus")
        self.assertLess(res["latency_ms"], 500)

if __name__ == "__main__":
    unittest.main()
