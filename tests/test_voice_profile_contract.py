"""
Unit tests for Voice Profile Registry Contract & Evidence Artifacts (P1-2).

Verifies:
- Profile fields, audio contract (22050 Hz, mono, 16-bit PCM), approved tuning values.
- Fallback profile references LJSpeech baseline.
- Zero import side effects (no model loading, zero network requests).
- Zero secret, token, IP address, or private path leakage in repository artifacts.
"""

import json
import os
import re
import unittest


class TestVoiceProfileContract(unittest.TestCase):

    def test_registry_import_has_no_side_effects(self):
        """Verifies importing the registry does not load models or initiate network calls."""
        import aeonix.core.voice_profile_registry as reg
        self.assertTrue(hasattr(reg, "PRISM_PRIMARY_VOICE_PROFILE_APPROVED"))
        self.assertTrue(hasattr(reg, "PRISM_FALLBACK_VOICE_PROFILE"))
        self.assertTrue(hasattr(reg, "VOICE_PROFILES"))

    def test_primary_profile_invariants(self):
        """Verifies approved primary voice profile fields and values."""
        from aeonix.core.voice_profile_registry import PRISM_PRIMARY_VOICE_PROFILE_APPROVED as prof

        self.assertEqual(prof.identity, "prism_primary")
        self.assertEqual(prof.status, "APPROVED_PRIMARY_EVALUATION")
        self.assertFalse(prof.governance.production_release_ready)
        self.assertFalse(prof.governance.distribution_ready)
        self.assertEqual(prof.governance.evaluation_scope, "local_private_research")

        # Audio contract
        self.assertEqual(prof.audio.sample_rate, 22050)
        self.assertEqual(prof.audio.channels, 1)
        self.assertEqual(prof.audio.sample_width_bytes, 2)
        self.assertEqual(prof.audio.encoding, "pcm_s16le")

        # Approved tuning parameters
        self.assertEqual(prof.parameters.speed, 0.90)
        self.assertEqual(prof.parameters.silence_scale, 0.20)
        self.assertEqual(prof.parameters.noise_scale, 0.667)
        self.assertEqual(prof.parameters.noise_scale_w, 0.800)
        self.assertEqual(prof.parameters.length_scale, 1.000)
        self.assertEqual(prof.parameters.threads, 2)

        # Model provenance
        self.assertEqual(prof.model.name, "en_IN-spicor-medium")
        self.assertEqual(prof.model.upstream_revision, "a4ff93ef95684b5dafc3800b99fb78a6b4c30235")
        self.assertEqual(prof.model.original_onnx_sha256, "e19debae94b70ecc9d22603820373c4dc9bfceb4de8675e1138d2072fca11494")
        self.assertEqual(prof.model.original_onnx_size_bytes, 63516050)
        self.assertEqual(prof.model.adapted_sherpa_onnx_sha256, "84732bfb9668b20f31c28e7fecf33c93498dbcbaac5c50069d8754a04b5ed4a7")
        self.assertEqual(prof.model.adapted_sherpa_onnx_size_bytes, 63516183)
        self.assertEqual(prof.model.tokens_txt_sha256, "e8a50ae0c75612d18cfcf3f90800dca79f961e3ed97f9574f3535194469187fd")
        self.assertEqual(prof.model.tokens_count, 161)

        # Phonemizer
        self.assertEqual(prof.phonemizer.engine, "espeak-ng")
        self.assertEqual(prof.phonemizer.voice, "en-us")
        self.assertEqual(prof.phonemizer.supported_symbols_count, 161)

        # Fallback reference
        self.assertEqual(prof.fallback_profile_name, "prism_fallback_ljspeech")

    def test_fallback_profile_invariants(self):
        """Verifies declarative fallback profile references LJSpeech baseline."""
        from aeonix.core.voice_profile_registry import PRISM_FALLBACK_VOICE_PROFILE as fb

        self.assertEqual(fb.identity, "prism_fallback_ljspeech")
        self.assertIn("ljspeech", fb.model.name.lower())
        self.assertEqual(fb.audio.sample_rate, 22050)
        self.assertEqual(fb.audio.channels, 1)
        self.assertEqual(fb.audio.encoding, "pcm_s16le")

    def test_evidence_json_integrity_and_hygiene(self):
        """Verifies p1_2_voice_profile_evidence.json matches specification and contains zero leaks."""
        evidence_path = os.path.join(
            os.path.dirname(__file__), "..", "docs", "evidence", "p1_2_voice_profile_evidence.json"
        )
        self.assertTrue(os.path.isfile(evidence_path))

        with open(evidence_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["milestone"], "P1-2")
        self.assertEqual(data["status"], "APPROVED_PRIMARY_EVALUATION")
        self.assertFalse(data["production_release_ready"])
        self.assertFalse(data["distribution_ready"])

        # Check tests A, B, C recorded
        tests = data["test_evidence"]
        self.assertEqual(len(tests), 3)
        test_ids = [t["test_id"] for t in tests]
        self.assertIn("Test A", test_ids)
        self.assertIn("Test B", test_ids)
        self.assertIn("Test C", test_ids)

        for t in tests:
            self.assertIn("PASS", t["human_listening_verdict"])
            self.assertEqual(len(t["wav_sha256"]), 64)

        # Check hygiene: zero private conversation paths, zero IP addresses, zero bearer tokens
        with open(evidence_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("10.110.", content)
        self.assertNotIn("192.168.", content)
        self.assertNotIn("Bearer ", content)
        self.assertNotIn("brain/7277f", content)

    def test_repository_files_hygiene(self):
        """Scans voice profile registry, spec, and evidence docs for secret/IP leaks."""
        base_dir = os.path.join(os.path.dirname(__file__), "..")
        target_files = [
            os.path.join(base_dir, "core", "voice_profile_registry.py"),
            os.path.join(base_dir, "docs", "evidence", "P1_2_VOICE_PROFILE_SPEC.md"),
            os.path.join(base_dir, "docs", "evidence", "p1_2_voice_profile_evidence.json"),
        ]

        ip_pattern = re.compile(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
        token_pattern = re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}")

        for path in target_files:
            self.assertTrue(os.path.isfile(path), f"Missing target file: {path}")
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertFalse(ip_pattern.search(content), f"Private IP found in {path}")
            self.assertFalse(token_pattern.search(content), f"Bearer token pattern found in {path}")
            self.assertNotIn("brain/7277f", content, f"Internal conversation path found in {path}")


if __name__ == "__main__":
    unittest.main()
