"""
Voice Profile Registry (P1-2 Configuration & Audit Contract).

Defines immutable, declarative voice profile structures for ÆONIX PRISM AI agents.
Pure configuration module: zero runtime model loading, zero network calls,
zero side-effects at import time.

Status: APPROVED_PRIMARY_EVALUATION (Evaluation only; not finalized for distribution).
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass(frozen=True)
class ModelIdentity:
    name: str
    architecture: str
    upstream_repository: str
    upstream_revision: str
    original_onnx_sha256: str
    original_onnx_size_bytes: int
    adapted_sherpa_onnx_sha256: str
    adapted_sherpa_onnx_size_bytes: int
    tokens_txt_sha256: str
    tokens_count: int


@dataclass(frozen=True)
class PhonemizerContract:
    engine: str
    voice: str
    command_template: List[str]
    supported_symbols_count: int


@dataclass(frozen=True)
class TuningParameters:
    speed: float
    silence_scale: float
    noise_scale: float
    noise_scale_w: float
    length_scale: float
    threads: int


@dataclass(frozen=True)
class AudioContract:
    sample_rate: int
    channels: int
    sample_width_bytes: int
    encoding: str


@dataclass(frozen=True)
class GovernanceInfo:
    license_model: str
    corpus_provenance: str
    evaluation_scope: str
    distribution_ready: bool
    production_release_ready: bool


@dataclass(frozen=True)
class VoiceProfile:
    identity: str
    display_name: str
    status: str
    model: ModelIdentity
    phonemizer: PhonemizerContract
    parameters: TuningParameters
    audio: AudioContract
    governance: GovernanceInfo
    fallback_profile_name: Optional[str] = None


# --- Approved PRISM Primary Voice Profile (Evaluation Only) ---

PRISM_PRIMARY_VOICE_PROFILE_APPROVED = VoiceProfile(
    identity="prism_primary",
    display_name="PRISM Primary Voice (Indian English)",
    status="APPROVED_PRIMARY_EVALUATION",
    model=ModelIdentity(
        name="en_IN-spicor-medium",
        architecture="VITS (Piper medium, single-speaker)",
        upstream_repository="navgurukul-ai-labs/text-to-speech-en-IN-piper",
        upstream_revision="a4ff93ef95684b5dafc3800b99fb78a6b4c30235",
        original_onnx_sha256="e19debae94b70ecc9d22603820373c4dc9bfceb4de8675e1138d2072fca11494",
        original_onnx_size_bytes=63516050,
        adapted_sherpa_onnx_sha256="84732bfb9668b20f31c28e7fecf33c93498dbcbaac5c50069d8754a04b5ed4a7",
        adapted_sherpa_onnx_size_bytes=63516183,
        tokens_txt_sha256="e8a50ae0c75612d18cfcf3f90800dca79f961e3ed97f9574f3535194469187fd",
        tokens_count=161
    ),
    phonemizer=PhonemizerContract(
        engine="espeak-ng",
        voice="en-us",
        command_template=["espeak-ng", "-q", "-v", "en-us", "--ipa", "{text}"],
        supported_symbols_count=161
    ),
    parameters=TuningParameters(
        speed=0.90,
        silence_scale=0.20,
        noise_scale=0.667,
        noise_scale_w=0.800,
        length_scale=1.000,
        threads=2
    ),
    audio=AudioContract(
        sample_rate=22050,
        channels=1,
        sample_width_bytes=2,
        encoding="pcm_s16le"
    ),
    governance=GovernanceInfo(
        license_model="AGPL-3.0 (NavGurukul wrapper)",
        corpus_provenance="IISc SPICOR English TTS Corpus (SPIRE Lab, IISc Bangalore)",
        evaluation_scope="local_private_research",
        distribution_ready=False,
        production_release_ready=False
    ),
    fallback_profile_name="prism_fallback_ljspeech"
)


# --- Declarative Fallback Profile Baseline ---

PRISM_FALLBACK_VOICE_PROFILE = VoiceProfile(
    identity="prism_fallback_ljspeech",
    display_name="PRISM Fallback Voice (US English LJSpeech)",
    status="BASELINE_FALLBACK",
    model=ModelIdentity(
        name="vits-piper-en_US-ljspeech-medium",
        architecture="VITS (Piper medium, single-speaker)",
        upstream_repository="k2-fsa/sherpa-onnx",
        upstream_revision="v1.10.15",
        original_onnx_sha256="prepackaged_k2_fsa_release",
        original_onnx_size_bytes=63516050,
        adapted_sherpa_onnx_sha256="prepackaged_k2_fsa_release",
        adapted_sherpa_onnx_size_bytes=63516050,
        tokens_txt_sha256="prepackaged_k2_fsa_tokens",
        tokens_count=161
    ),
    phonemizer=PhonemizerContract(
        engine="espeak-ng",
        voice="en-us",
        command_template=["espeak-ng", "-q", "-v", "en-us", "--ipa", "{text}"],
        supported_symbols_count=161
    ),
    parameters=TuningParameters(
        speed=1.00,
        silence_scale=0.20,
        noise_scale=0.667,
        noise_scale_w=0.800,
        length_scale=1.000,
        threads=2
    ),
    audio=AudioContract(
        sample_rate=22050,
        channels=1,
        sample_width_bytes=2,
        encoding="pcm_s16le"
    ),
    governance=GovernanceInfo(
        license_model="Public Domain (LJSpeech) / MIT (Piper/Sherpa)",
        corpus_provenance="LJSpeech-1.1",
        evaluation_scope="baseline_reference",
        distribution_ready=True,
        production_release_ready=True
    ),
    fallback_profile_name=None
)


VOICE_PROFILES: Dict[str, VoiceProfile] = {
    PRISM_PRIMARY_VOICE_PROFILE_APPROVED.identity: PRISM_PRIMARY_VOICE_PROFILE_APPROVED,
    PRISM_FALLBACK_VOICE_PROFILE.identity: PRISM_FALLBACK_VOICE_PROFILE,
}
