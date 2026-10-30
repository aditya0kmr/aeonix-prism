import os
import json
import time
import subprocess
import httpx
from typing import Optional, Dict, Any, List
from aeonix.core.ram_guard import check_ram_guard

MODEL_FAST = os.path.expanduser("~/aeonix/models/qwen2.5-0.5b-instruct-q4_k_m.gguf")
MODEL_DEEP = os.path.expanduser("~/aeonix/models/qwen2.5-1.5b-instruct-q4_k_m.gguf")

SERVER_PORT = 8081
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"

class LlamaRunner:
    def __init__(self, port: int = SERVER_PORT):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.current_model: Optional[str] = None

    def is_running(self) -> bool:
        try:
            with httpx.Client(timeout=1.0) as client:
                res = client.get(f"{SERVER_URL}/health")
                return res.status_code == 200
        except Exception:
            return False

    def start_server(self, model_mode: str = "fast") -> bool:
        """
        Starts llama-server for either 'fast' (0.5B) or 'deep' (1.5B) model.
        Includes automatic RAM threshold adaptation.
        """
        target_model = MODEL_DEEP if model_mode == "deep" else MODEL_FAST
        required_ram_kb = 1200000 if model_mode == "deep" else 600000

        # If already running with the requested model, reuse it
        if self.is_running() and self.current_model == target_model:
            return True

        # If running with a different model, stop first
        if self.is_running():
            self.stop_server()

        # Pre-inference RAM guard
        ram = check_ram_guard(threshold_kb=required_ram_kb)
        if not ram["is_safe"]:
            # If 1.5B requested but RAM < 1.2GB, fallback to 0.5B
            if model_mode == "deep":
                print(f"[LlamaRunner] Insufficient RAM for 1.5B ({ram['available_mb']}MB). Falling back to 0.5B.")
                return self.start_server(model_mode="fast")
            else:
                print(f"[LlamaRunner] Aborting start: RAM guard triggered ({ram['available_mb']}MB available)")
                return False

        cmd = [
            "llama-server",
            "-m", target_model,
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "-c", "2048",
            "-t", "4",
            "--no-warmup"
        ]

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        self.current_model = target_model

        for _ in range(25):
            time.sleep(0.4)
            if self.is_running():
                return True

        return False

    def stop_server(self):
        """Unloads model immediately to obey burst-execution memory rule."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
            self.current_model = None

    def generate(
        self,
        messages: List[Dict[str, str]],
        mode: str = "fast",
        max_tokens: int = 60,
        temperature: float = 0.6
    ) -> Optional[str]:
        """Generates completion via OpenAI-compatible endpoint."""
        ok = self.start_server(model_mode=mode)
        if not ok:
            return None

        try:
            with httpx.Client(timeout=45.0) as client:
                payload = {
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False
                }
                res = client.post(f"{SERVER_URL}/v1/chat/completions", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[LlamaRunner] Error during generation: {e}")
        return None

# Global instance
llama_runner = LlamaRunner()
