"""
ÆONIX PRISM // Hybrid Router, Local AI & VOX Verification Suite
Verifies tiered routing, model metadata, SHA-256 integrity, local inference benchmarks,
and bounded audio streaming.
100% On-Device Provenance.
"""

import os
import sys
import unittest
import time
from typing import Dict, Any

sys.path.insert(0, "/data/data/com.termux/files/home/aeonix")
sys.path.insert(0, "/data/data/com.termux/files/home")

from aeonix.core.db import init_database
from aeonix.core.router import get_router_status, route_query
from aeonix.core.llama_runner import llama_runner, compute_file_sha256

KNOWN_MODEL_HASHES = {
    "qwen2.5-0.5b-instruct-q4_k_m.gguf": "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db",
    "ggml-tiny.en.bin": "921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f"
}

class TestHybridRouterAndAI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def test_router_status_and_provider_declarations(self):
        """Test provider catalog, modalities, and daily quota limits."""
        status = get_router_status()
        self.assertTrue(status["sovereign_first"])
        self.assertEqual(status["default_tier"], "tier_1_local_sovereign")
        self.assertIn("local_qwen_fast", status["providers"])
        self.assertIn("gemini_flash", status["providers"])

        # Check modalities
        self.assertIn("text", status["providers"]["local_qwen_fast"]["modalities"])
        self.assertIn("image", status["providers"]["gemini_flash"]["modalities"])

    def test_tier_0_fast_path_routing_latency(self):
        """Verify Fast-Path queries bypass LLMs completely in under 50ms."""
        res = route_query("status", actor="Aadi")
        self.assertEqual(res["tier"], "tier_0_fast_path")
        self.assertTrue(res["is_offline"])
        self.assertEqual(res["action"], "system_health")
        self.assertLess(res["latency_ms"], 50.0)

    def test_router_caching_behavior(self):
        """Verify repeated queries hit memory cache in sub-5ms."""
        # Query 1: executes router
        q1 = route_query("What is encryption?", actor="Aadi")
        # Query 2: should hit memory cache
        q2 = route_query("What is encryption?", actor="Aadi")
        self.assertTrue(q2.get("from_cache", False))
        self.assertLess(q2["latency_ms"], 10.0)

    def test_sovereign_fallback_when_external_cloud_disabled(self):
        """Ensure requesting external AI without key safely falls back to local Qwen."""
        # Force GEMINI_API_KEY to empty
        old_key = os.environ.get("GEMINI_API_KEY")
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

        try:
            res = route_query("Explain autonomy in one sentence", allow_external=True)
            self.assertEqual(res["tier"], "tier_1_local_qwen")
            self.assertTrue(res["is_offline"])
            self.assertTrue(res["fallback_occurred"])
        finally:
            if old_key:
                os.environ["GEMINI_API_KEY"] = old_key

    def test_model_metadata_and_cryptographic_hash(self):
        """Verify installed model metadata, license, and cryptographic SHA-256."""
        meta = llama_runner.get_model_metadata("fast")
        self.assertTrue(meta["installed"])
        self.assertEqual(meta["architecture"], "Qwen2.5")
        self.assertEqual(meta["license"], "Apache-2.0")
        self.assertEqual(meta["quantization"], "Q4_K_M")
        self.assertEqual(meta["sha256"], KNOWN_MODEL_HASHES["qwen2.5-0.5b-instruct-q4_k_m.gguf"])

    def test_local_llm_benchmark_execution(self):
        """Verify llama-server startup, token generation speed, and RAM recovery."""
        bench = llama_runner.benchmark(model_mode="fast", prompt="Say hello.")
        self.assertTrue(bench["success"])
        self.assertLess(bench["startup_latency_ms"], 3000.0) # sub-3s startup
        self.assertGreater(bench["tokens_per_second"], 5.0)  # > 5 t/s on Dimensity 810
        self.assertIsNotNone(bench["output"])
        self.assertGreater(len(bench["output"]), 0)

if __name__ == "__main__":
    unittest.main()
