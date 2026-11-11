"""
ÆONIX PRISM // Approved Local TTS Adapter Subsystem (Section 10 / P1-2 Voice Loop).
Synthesizes speech using the approved Indian English voice profile (en_IN-spicor-medium).
Guarantees 100% offline execution, 1:1 parameter mapping, zero generative hallucination,
and zero persistent audio file retention.
"""

import io
import os
import resource
import subprocess
import time
import wave
from typing import Dict, Any, Tuple, Optional, List, Callable

from aeonix.core.voice_profile_registry import (
    PRISM_PRIMARY_VOICE_PROFILE_APPROVED,
    VoiceProfile,
    VOICE_PROFILES
)

# Optional mock synthesizer hook for isolated testing
_mock_tts_synthesizer: Optional[Callable[[str, VoiceProfile], Tuple[bool, str, bytes, Dict[str, Any]]]] = None


def set_mock_tts_synthesizer(hook: Optional[Callable]):
    """Sets or clears the mock TTS synthesizer hook for tests."""
    global _mock_tts_synthesizer
    _mock_tts_synthesizer = hook


def get_tts_parameters(profile_name: str = "prism_primary") -> Dict[str, Any]:
    """Returns the verified declarative tuning parameters for a voice profile."""
    profile = VOICE_PROFILES.get(profile_name, PRISM_PRIMARY_VOICE_PROFILE_APPROVED)
    return {
        "profile_identity": profile.identity,
        "model_name": profile.model.name,
        "speed": profile.parameters.speed,
        "silence_scale": profile.parameters.silence_scale,
        "noise_scale": profile.parameters.noise_scale,
        "noise_scale_w": profile.parameters.noise_scale_w,
        "length_scale": profile.parameters.length_scale,
        "threads": profile.parameters.threads,
        "sample_rate": profile.audio.sample_rate,
        "channels": profile.audio.channels,
        "encoding": profile.audio.encoding
    }


def resolve_model_assets(profile_name: str = "prism_primary") -> Tuple[str, str, str]:
    """
    Resolves the paths to the ONNX model, tokens.txt, and espeak-ng-data directory.
    Returns (model_path, tokens_path, data_dir).
    Raises FileNotFoundError if assets are missing.
    """
    custom_dir = os.getenv("AEONIX_TTS_MODEL_DIR")
    candidate_model_dirs = [
        custom_dir,
        "/data/data/com.termux/files/home/.gemini/antigravity-cli/brain/7277f13d-e50c-4810-8794-5b8db9a44160/scratch/p1_2_tts/model/vits-piper-en_IN-spicor-medium",
        os.path.expanduser("~/.aeonix/models/vits-piper-en_IN-spicor-medium")
    ]
    resolved_model_dir = ""
    for d in candidate_model_dirs:
        if d and os.path.isdir(d):
            resolved_model_dir = d
            break

    if not resolved_model_dir:
        raise FileNotFoundError(f"TTS model directory not found. Candidates checked: {candidate_model_dirs}")

    model_path = os.path.join(resolved_model_dir, "en_IN-spicor-medium-sherpa.onnx")
    tokens_path = os.path.join(resolved_model_dir, "tokens.txt")

    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"Adapted Sherpa ONNX model not found: {model_path}")
    if not os.path.isfile(tokens_path):
        raise FileNotFoundError(f"TTS tokens file not found: {tokens_path}")

    custom_data_dir = os.getenv("AEONIX_ESPEAK_DATA_DIR")
    candidate_data_dirs = [
        custom_data_dir,
        "/data/data/com.termux/files/home/.gemini/antigravity-cli/brain/7277f13d-e50c-4810-8794-5b8db9a44160/scratch/p1_2_tts/model/vits-piper-en_US-amy-medium/espeak-ng-data",
        "/data/data/com.termux/files/usr/share/espeak-ng-data"
    ]
    resolved_data_dir = ""
    for dd in candidate_data_dirs:
        if dd and os.path.isdir(dd):
            resolved_data_dir = dd
            break

    if not resolved_data_dir:
        raise FileNotFoundError(f"espeak-ng-data directory not found. Candidates checked: {candidate_data_dirs}")

    return model_path, tokens_path, resolved_data_dir


def phonemize_text(text: str, voice: str = "en-us", timeout_s: float = 5.0) -> List[str]:
    """Phonemizes input text using local espeak-ng binary."""
    espeak_bin = os.getenv("AEONIX_ESPEAK_BIN", "/data/data/com.termux/files/usr/bin/espeak-ng")
    if not os.path.isfile(espeak_bin):
        raise FileNotFoundError(f"espeak-ng binary not found at {espeak_bin}")

    cmd = [espeak_bin, "-q", "-v", voice, "--ipa", text]
    proc = subprocess.run(
        cmd,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=True
    )
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"Phonemization returned empty output for text: '{text}'")
    return lines


def synthesize_speech(
    text: str,
    profile_name: str = "prism_primary"
) -> Tuple[bool, str, bytes, Dict[str, Any]]:
    """
    Synthesizes speech using the approved local TTS adapter.

    Parameters map 1:1 to sherpa-onnx:
      - speed: 0.90 -> GenerationConfig.speed
      - silence_scale: 0.20 -> GenerationConfig.silence_scale
      - noise_scale: 0.667 -> OfflineTtsVitsModelConfig.noise_scale
      - noise_scale_w: 0.800 -> OfflineTtsVitsModelConfig.noise_scale_w
      - length_scale: 1.0 -> OfflineTtsVitsModelConfig.length_scale
      - threads: 2 -> OfflineTtsModelConfig.num_threads

    Returns:
      (success: bool, error_message: str, wav_bytes: bytes, metrics: Dict[str, Any])
    """
    profile = VOICE_PROFILES.get(profile_name, PRISM_PRIMARY_VOICE_PROFILE_APPROVED)

    # Check mock hook first (for isolated unit/integration tests)
    if _mock_tts_synthesizer is not None:
        return _mock_tts_synthesizer(text, profile)

    t0_overall = time.perf_counter()
    metrics: Dict[str, Any] = {
        "profile": profile.identity,
        "model_name": profile.model.name,
        "sample_rate": profile.audio.sample_rate,
        "channels": profile.audio.channels,
        "speed": profile.parameters.speed,
        "silence_scale": profile.parameters.silence_scale,
        "noise_scale": profile.parameters.noise_scale,
        "noise_scale_w": profile.parameters.noise_scale_w,
        "length_scale": profile.parameters.length_scale,
        "threads": profile.parameters.threads,
    }

    try:
        # Step 1: Phonemization
        t0_phone = time.perf_counter()
        phoneme_lines = phonemize_text(text, voice=profile.phonemizer.voice)
        t_phone = time.perf_counter() - t0_phone
        metrics["phonemization_ms"] = round(t_phone * 1000, 2)

        # Step 2: Model Asset Resolution
        model_path, tokens_path, data_dir = resolve_model_assets(profile_name)

        # Step 3: Lazy sherpa_onnx import
        try:
            import sherpa_onnx
        except ImportError:
            candidate_sites = [
                "/data/data/com.termux/files/home/.gemini/antigravity-cli/brain/7277f13d-e50c-4810-8794-5b8db9a44160/scratch/p1_2_tts/venv/lib/python3.14/site-packages",
            ]
            for cs in candidate_sites:
                if os.path.isdir(cs) and cs not in sys.path:
                    sys.path.insert(0, cs)
            import sherpa_onnx

        # Step 4: Model Configuration
        t0_model = time.perf_counter()
        vits_config = sherpa_onnx.OfflineTtsVitsModelConfig(
            model=model_path,
            tokens=tokens_path,
            data_dir=data_dir,
            noise_scale=profile.parameters.noise_scale,
            noise_scale_w=profile.parameters.noise_scale_w,
            length_scale=profile.parameters.length_scale
        )
        model_config = sherpa_onnx.OfflineTtsModelConfig(
            vits=vits_config,
            num_threads=profile.parameters.threads,
            debug=False,
            provider="cpu"
        )
        tts_config = sherpa_onnx.OfflineTtsConfig(
            model=model_config,
            max_num_sentences=2
        )
        tts = sherpa_onnx.OfflineTts(tts_config)
        t_model = time.perf_counter() - t0_model
        metrics["model_load_ms"] = round(t_model * 1000, 2)

        # Step 5: Neural Synthesis
        t0_synth = time.perf_counter()
        gc = sherpa_onnx.GenerationConfig()
        gc.phoneme_codepoints = [[ord(c) for c in l] for l in phoneme_lines]
        gc.speed = profile.parameters.speed
        gc.silence_scale = profile.parameters.silence_scale
        audio = tts.generate(text="", config=gc)
        t_synth = time.perf_counter() - t0_synth
        metrics["neural_synthesis_ms"] = round(t_synth * 1000, 2)

        # Step 6: In-Memory WAV Serialization
        buf = io.BytesIO()
        save_ok = sherpa_onnx.write_wave(buf, audio.samples, audio.sample_rate)
        if not save_ok:
            # Fallback to standard wave writer
            buf.seek(0)
            buf.truncate()
            import struct
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(audio.sample_rate)
                # Float samples in [-1.0, 1.0] to int16
                int16_samples = [max(-32768, min(32767, int(s * 32767))) for s in audio.samples]
                w.writeframes(struct.pack(f"<{len(int16_samples)}h", *int16_samples))

        wav_bytes = buf.getvalue()
        pcm_bytes_count = len(audio.samples) * 2
        audio_duration_s = round(pcm_bytes_count / (profile.audio.sample_rate * 2), 3)

        metrics["pcm_bytes"] = pcm_bytes_count
        metrics["total_wav_bytes"] = len(wav_bytes)
        metrics["audio_duration_seconds"] = audio_duration_s
        metrics["total_latency_ms"] = round((time.perf_counter() - t0_overall) * 1000, 2)

        return True, "", wav_bytes, metrics

    except Exception as e:
        metrics["total_latency_ms"] = round((time.perf_counter() - t0_overall) * 1000, 2)
        return False, str(e), b"", metrics
