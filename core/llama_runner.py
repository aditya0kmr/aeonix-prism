import os
import json
import time
import hashlib
import subprocess
import httpx
from typing import Optional, Dict, Any, List
from aeonix.core.ram_guard import check_ram_guard

MODEL_FAST = os.path.expanduser("~/aeonix/models/qwen2.5-0.5b-instruct-q4_k_m.gguf")
MODEL_DEEP = os.path.expanduser("~/aeonix/models/qwen2.5-1.5b-instruct-q4_k_m.gguf")
LOG_DIR = os.path.expanduser("~/aeonix/data/logs")
LOG_FILE = os.path.join(LOG_DIR, "llama_runner.log")

SERVER_PORT = 8081
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"

def compute_file_sha256(path: str) -> str:
    """Computes SHA-256 hash of a model file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1048576): # 1MB chunks
            sha.update(chunk)
    return sha.hexdigest()

class LlamaRunner:
    def __init__(self, port: int = SERVER_PORT):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.current_model: Optional[str] = None
        self._log_fd = None
        os.makedirs(LOG_DIR, exist_ok=True)

    def is_running(self) -> bool:
        try:
            with httpx.Client(timeout=1.0) as client:
                res = client.get(f"{SERVER_URL}/health")
                return res.status_code == 200
        except Exception:
            return False

    def get_last_logs(self, max_lines: int = 30) -> List[str]:
        """Returns the most recent lines from the llama_runner log file."""
        if not os.path.exists(LOG_FILE):
            return []
        try:
            with open(LOG_FILE, "r", errors="replace") as f:
                lines = f.readlines()
                return [l.strip() for l in lines[-max_lines:]]
        except Exception as e:
            return [f"Log read error: {e}"]

    def get_model_metadata(self, model_mode: str = "fast") -> Dict[str, Any]:
        """Returns verification and license metadata for the installed model."""
        target_path = MODEL_DEEP if model_mode == "deep" else MODEL_FAST
        exists = os.path.exists(target_path)
        size_mb = round(os.path.getsize(target_path) / (1024 * 1024), 2) if exists else 0
        sha256_hash = compute_file_sha256(target_path) if exists else "NOT_FOUND"

        return {
            "mode": model_mode,
            "model_path": target_path,
            "installed": exists,
            "size_mb": size_mb,
            "architecture": "Qwen2.5",
            "parameter_count": "1.5B" if model_mode == "deep" else "0.5B",
            "quantization": "Q4_K_M",
            "license": "Apache-2.0",
            "sha256": sha256_hash
        }

    def start_server(self, model_mode: str = "fast") -> bool:
        """
        Starts llama-server for either 'fast' (0.5B) or 'deep' (1.5B) model.
        Preserves process logs and validates RAM guard thresholds.
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

        # Open log file to preserve process logs
        self._log_fd = open(LOG_FILE, "a")
        self._log_fd.write(f"\n--- [START {time.strftime('%Y-%m-%d %H:%M:%S')}] {cmd} ---\n")
        self._log_fd.flush()

        self.process = subprocess.Popen(
            cmd,
            stdout=self._log_fd,
            stderr=self._log_fd,
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

        if self._log_fd:
            try:
                self._log_fd.write(f"--- [STOP {time.strftime('%Y-%m-%d %H:%M:%S')}] ---\n")
                self._log_fd.flush()
                self._log_fd.close()
            except Exception:
                pass
            self._log_fd = None

    def benchmark(
        self, 
        model_mode: str = "fast", 
        prompt: str = "Explain sovereign computation in one concise sentence."
    ) -> Dict[str, Any]:
        """
        Executes a rigorous benchmark of local model performance on Dimensity 810.
        Measures startup latency, generation time, tokens per second, and RAM consumption.
        """
        ram_before = check_ram_guard()
        t_start = time.perf_counter()
        
        ok = self.start_server(model_mode=model_mode)
        startup_ms = round((time.perf_counter() - t_start) * 1000, 2)
        if not ok:
            return {
                "success": False,
                "error": "Failed to start llama-server",
                "logs": self.get_last_logs(10)
            }
            
        t_gen_start = time.perf_counter()
        messages = [{"role": "user", "content": prompt}]
        output = None
        prompt_tokens = 0
        completion_tokens = 0
        
        try:
            with httpx.Client(timeout=45.0) as client:
                payload = {
                    "messages": messages,
                    "max_tokens": 50,
                    "temperature": 0.6,
                    "stream": False
                }
                res = client.post(f"{SERVER_URL}/v1/chat/completions", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    output = data["choices"][0]["message"]["content"].strip()
                    usage = data.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", len(prompt.split()))
                    completion_tokens = usage.get("completion_tokens", len(output.split()) if output else 0)
        except Exception as e:
            output = f"Generation error: {e}"
        finally:
            gen_ms = round((time.perf_counter() - t_gen_start) * 1000, 2)
            self.stop_server()
            ram_after = check_ram_guard()
            
        tokens_per_sec = round((completion_tokens / (gen_ms / 1000.0)), 2) if gen_ms > 0 else 0
        
        return {
            "success": True,
            "model_mode": model_mode,
            "metadata": self.get_model_metadata(model_mode),
            "startup_latency_ms": startup_ms,
            "generation_latency_ms": gen_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tokens_per_second": tokens_per_sec,
            "ram_before_mb": ram_before["available_mb"],
            "ram_after_mb": ram_after["available_mb"],
            "prompt": prompt,
            "output": output
        }


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
