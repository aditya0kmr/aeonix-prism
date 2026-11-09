# ÆONIX PRISM // Post-RC-1 Development & Engineering Roadmap

**Document ID:** `AEONIX-ROADMAP-POST-RC1`  
**Baseline Milestone:** Release Candidate 1 (RC-1)  
**Execution Sequence:** Prioritized P0 &rarr; P1 &rarr; P2  
**Date:** 2026-11-09  

---

## 1. P0 Priority: Critical Stabilization & Physical Hardware Hardening

These items address direct empirical gaps identified during RC-1 physical verification and must be completed before an unconditional general availability (GA) milestone.

### 1.1 Real TV Transport Test Matrix
- **Objective:** Exhaustively validate the WebSocket transport and reconnect state resynchronization across real-world Wi-Fi degradation conditions.
- **Deliverables:**
  - Automated soak harness on Fire TV testing packet loss (5%, 10%, 20%), Wi-Fi AP roaming, and physical power disconnects.
  - Verification of sequence replay buffer bounds (up to 500 events) upon reconnect.
  - Automated TLS certificate expiration and dynamic re-pinning renegotiation test.

### 1.2 Real Phone Microphone End-to-End Test Suite
- **Objective:** Bridge from static 16kHz WAV audio fixtures (`jfk.wav`) to real-time physical microphone streaming on the POCO M4 Pro 5G.
- **Deliverables:**
  - Native Termux:API audio capture wrapper (`termux-microphone-record`) with real-time VAD (Voice Activity Detection).
  - End-to-end physical pipeline: Spoken voice &rarr; POCO mic &rarr; local `whisper-cli` &rarr; intent extraction &rarr; Living Surface HUD confirmation card.
  - Real-world ambient noise benchmark (30dB quiet room vs 65dB TV background noise).

### 1.3 Extended 30–60 Minute Stability Soak
- **Objective:** Prove process memory leak immunity on both devices under active event broadcasting.
- **Deliverables:**
  - 60-minute continuous telemetry collector polling `dumpsys meminfo` on Fire TV and `smaps_rollup` on POCO.
  - Steady-state heap profiling to ensure zero unbounded object accumulation in `AeonixWebSocketClient` and `MainActivity`.
  - Battery thermal profile logging on POCO M4 Pro 5G under 1-hour sustained idle and burst workloads.

### 1.4 TV Startup & View Inflation Rendering Optimization
- **Objective:** Eliminate the initial 46ms–300ms layout inflation jank during `com.aether.launcher` cold-start.
- **Deliverables:**
  - Implement asynchronous view pre-inflation (`AsyncLayoutInflater`) for Leanback card rows.
  - Defer non-critical HUD widget binding until after the first VSYNC frame presentation.
  - Target: Sub-16.6ms frame time for 95% of startup frames on Fire TV Stick Lite (`sheldon`).

---

## 2. P1 Priority: Core Capability Expansion & Subsystem Polish

### 2.1 Hindi & Hinglish Voice Corpus and Accuracy Benchmark
- **Objective:** Transition Hindi/Hinglish speech recognition from synthetic parameter verification to genuine spoken accuracy.
- **Deliverables:**
  - Curate a consented 500-sample Hindi and mixed Hinglish audio command corpus.
  - Benchmark Word Error Rate (WER) and Character Error Rate (CER) on `ggml-tiny.bin` vs `ggml-base.bin`.
  - Evaluate POCO MediaTek Dimensity 810 CPU thermal and inference latency budgets when processing non-English vocabularies.

### 2.2 Fire TV Remote Microphone Feasibility Study
- **Objective:** Determine if native remote microphone access is viable under Fire OS or establish permanent smartphone PTT.
- **Deliverables:**
  - Low-level investigation of Fire OS Bluetooth HID audio profile (ALSA / AudioRecord permissions).
  - If OS-level sandboxing permanently reserves the remote mic for Alexa, develop an unprivileged push-to-talk companion UI on the POCO handset or a dedicated Bluetooth BLE remote.

### 2.3 Chronos Snapshot & Replay Polish
- **Objective:** Optimize long-term event journal growth and query latency.
- **Deliverables:**
  - Implement periodic cryptographic state checkpoints (snapshots) with verifiable Merkle proofs.
  - Implement verifiable pruning of historical raw events while preserving cryptographic tip continuity.

### 2.4 Lumen Retrieval & Memory Polish
- **Objective:** Elevate memory retrieval from regex/tag matching to semantic retrieval.
- **Deliverables:**
  - Integrate an embedded local vector database (`sqlite-vss` or lightweight `hnswlib`).
  - Deploy an ultra-compact local embedding model (`all-MiniLM-L6-v2` or `bge-small-en`) quantized for ARM NEON.

### 2.5 Forge Declarative Workflow Hardening
- **Objective:** Expand governed mission templates while strictly preserving Sentinel boundary guarantees.
- **Deliverables:**
  - Declarative YAML/JSON schema for composite multi-step missions with per-step precondition simulation.
  - Sandboxed execution isolating third-party diagnostic utilities from root system files.

---

## 3. P2 Priority: Ecosystem & Integration Expansion

### 3.1 Conditional Smart-Home Integration
- **Objective:** Enable local-only home automation coordination.
- **Deliverables:**
  - Local MQTT and WebSockets bridge for Home Assistant.
  - Sentinel policy templates for smart lights, switches, and environmental sensors with fail-closed physical safety boundaries.

### 3.2 External Media & Playback Coordination
- **Objective:** Connect Living Surface HUD to local media streaming.
- **Deliverables:**
  - Integration with local DLNA / UPnP or Plex media servers.
  - Living Surface metadata overlay and remote media playback control.

### 3.3 Public-Data Gateway Expansion
- **Objective:** Support operator-initiated external intelligence lookups without violating zero-cloud defaults.
- **Deliverables:**
  - Ephemeral outbound Tor / VPN proxy module for lawful external OSINT lookups (domain DNS, CVE databases).
  - Explicit per-query Sentinel Gate authorization for WAN egress.

### 3.4 Advanced Forensic & Investigation Workflows
- **Objective:** Deepen on-device forensic analysis capabilities.
- **Deliverables:**
  - Static Dex and ELF binary inspection engine for APK preflighting.
  - Evidence timeline graphing and cross-case entity correlation visualization on Fire TV HUD.
