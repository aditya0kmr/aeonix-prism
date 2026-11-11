# P1-2 Physical End-to-End Voice Loop Demonstration Report

**Evaluation Date:** 2026-11-11  
**Status:** `PHYSICAL_END_TO_END_VOICE_LOOP_PASSED`  
**Production Readiness:** `NOT_FINALIZED`  
**Scope:** Bounded Demonstration Only (Not a claim of general free-form speech reliability)

---

## 1. Executive Summary

This report documents the verification of the complete physical end-to-end voice loop:
$$\text{POCO Physical Microphone (/ui/ptt)} \longrightarrow \text{Local Whisper STT} \longrightarrow \text{Deterministic Fast Path} \longrightarrow \text{Approved Indian English TTS} \longrightarrow \text{Fire TV In-App Playback}$$

Human listening evaluation confirmed successful reception and playback on the Fire TV:
> **Human Verdict:** *"The audio was good and perfect."*

---

## 2. Audio Capture & STT Ingestion

- **Capture Method:** Sovereign POCO tactile PTT console (`/ui/ptt`), WebAudio `ScriptProcessorNode` at 16,000 Hz 16-bit mono PCM.
- **Hardware Lifecycle:** Hardware microphone track requested strictly on explicit user gesture and immediately stopped/released upon touch end.
- **Disk Retention:** Zero disk retention; captured audio buffered ephemerally in RAM.
- **Ingested Audio:** 7.168 seconds (229,376 PCM bytes / 229,420 WAV bytes).
- **Audio Hash (SHA-256):** `c2fc8c413c78f56201bce0f571bac21b537b5eb3dd97f2cb291ce386a8135125`.
- **Voice Activity Detection:** RMS Energy `3219.66` (`has_speech: True`).
- **STT Engine:** Local `whisper.cpp` using `ggml-tiny.bin` on Dimensity 810 ARM NEON.
- **STT Inference Time:** 2.247 seconds.
- **Expected Command:** `"What is the system status?"`
- **Raw Whisper Transcript:** `"what is the system of status?"` (Extraneous preposition `"of"` detected during inter-word pause; Attempt 1 word-order transposition was not repeated).

---

## 3. Intent Matching & Deterministic Fast-Path

- **Equivalence Method:** Explicit deterministic intent matching based on recognized keywords `"system"` and `"status"`.
- **Matched Intent:** `system_health` (evaluated in 0.030 ms).
- **Match Decision:** Accepted by human operator for this bounded demonstration only; does **not** establish general free-form speech reliability.
- **Deterministic Response:** `"Living surface online. The phone and television are connected."`
- **LLM Usage:** 0 tokens (zero cloud dependencies, zero generative hallucination risk).

---

## 4. Speech Synthesis (Approved Voice Profile)

- **Voice Profile:** `en_IN-spicor-medium` (VITS architecture).
- **Synthesized Audio:** 4.145 seconds, 22,050 Hz mono 16-bit PCM (`182,784` bytes).
- **Output WAV SHA-256:** `cbbbfe38712fd6156b77e1ec9d4d906e37430e52bb952934a58d1553faf21b9a`.
- **Approved Parameters:** `speed = 0.90`, `silence_scale = 0.20`, `noise_scale = 0.667`, `noise_scale_w = 0.800`, `length_scale = 1.0`, `threads = 2`.
- **Synthesis Timings:**
  - Phonemization (`espeak-ng -v en-us --ipa`): 0.203s (202.93 ms)
  - Model Load (`sherpa-onnx`): 3.354s
  - Neural Synthesis: 0.912s (912 ms)
  - Serialization: 0.016s

---

## 5. Fire TV Transport & Playback

- **Protocol:** `VoiceAudioProtocol` v1 over authenticated TLS WebSocket (`active_connections = 1`).
- **Message ID:** `physical-ptt-attempt2-intent-match-firetv`.
- **Transmission Duration:** 3.63 ms (`182,784` bytes in 16 KiB binary frames).
- **Playback Sink:** `AndroidAudioTrackSink` (`STREAM_MUSIC`, 22,050 Hz, 16-bit mono).
- **Drain Window:** 5.34 seconds.
- **Human Verification:** Confirmed audible, clear, and complete with no distortion, clipping, or premature cutoff.

---

## 6. System Safety & Memory Audit

- **Resident Set Size (`VmRSS` via `/proc/self/status`):**
  - Ephemeral Server Start: 48.26 MB (`49,420 kB`)
  - Post-TTS Peak: 233.11 MB (`238,708 kB`)
  - Post-Drain Completion: 235.78 MB (`241,436 kB`)
  - Physical RAM Delta: +187.52 MB (fully reclaimed on process exit)
- **Available System Memory:** 1,810.71 MB baseline $\rightarrow$ 1,694.36 MB post-drain (RAM guard threshold > 800 MB strictly respected).
- **Static Heap Baseline (`ru_maxrss`):** 1,024.85 MB (Android Bionic dynamic linker / page-table static preallocation).
- **Server Shutdown:** PRISM stopped immediately after playback drain; port 8443 confirmed `CLOSED`.
