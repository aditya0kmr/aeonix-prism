# ÆONIX PRISM // Sovereign Intelligence & Living-Room OS
**POCO M4 Pro 5G Core Mind + Fire TV Stick Lite Glass Terminal**
**Author:** Aditya (User: Aadi) | **Architecture:** Local-First, Zero-Cloud, Sovereign Distributed Intelligence

---

## 1. System Vision & Architecture

ÆONIX PRISM is a two-device, zero-cost, privacy-first sovereign intelligence operating system designed from the **Complete A–Z Master Document** and **Master Coding Guidelines v2.0**:

- **Device 1: POCO M4 Pro 5G (Dimensity 810, Android Termux, `10.116.23.168`)**
  - **The Mind & Vault**: Houses the local LLM inference engines, persistent memory heart, cryptographic hash-chained audit vault, Zeroconf mDNS broadcaster, and asynchronous ASGI daemon.
  - **100% Offline & Free**: Operates using quantized local models (`Qwen2.5-0.5B` & `Qwen2.5-1.5B`) and native `whisper.cpp` ARM NEON speech-to-text with zero cloud APIs.
- **Device 2: Amazon Fire TV Stick Lite (Android 9 / API 28, `10.116.23.179`)**
  - **The Living Surface & Dumb Glass**: Custom Leanback Android TV launcher with an active RAM footprint under **70MB**, 0 WebViews, and real-time WebSocket telemetry.
  - **Human Authority**: The Sentinel Gate intercepts all consequential actions, presenting modal alerts that strictly default to `DENY (SAFE)` on remote input.

```mermaid
flowchart LR
    subgraph FireTV ["Fire TV Stick Lite (Glass)"]
        UI["Living Surface UI<br/>(aether-launcher)"]
        Mic["Remote Mic<br/>(PTT 16kHz PCM)"]
        Sentinel["Sentinel Modal<br/>(Default: DENY SAFE)"]
    end

    subgraph POCO ["POCO M4 Pro 5G (Mind)"]
        WS["WebSocket Server<br/>(:8080/ws)"]
        STT["whisper.cpp (tiny.en)<br/>(ARM NEON)"]
        Router["Fast-Path Router<br/>(<0.05ms)"]
        LLM["Dual-Tier LlamaRunner<br/>(0.5B / 1.5B)"]
        Vault["SQLite WAL Vault<br/>(SHA-256 Chained)"]
        Memory["AADYA Memory Heart"]
    end

    Mic -->|WebSocket Stream| WS
    WS --> STT
    STT --> Router
    Router -->|Hit| WS
    Router -->|Miss| LLM
    LLM --> WS
    WS --> UI
    POCO -.->|Sentinel Alert| Sentinel
    Sentinel -->|Auth Response| Vault
```

---

## 2. Directory Structure

```
~/aeonix/
├── core/
│   ├── db.py            # SQLite WAL vault, hash-chained audit_log, sentinel queue
│   ├── discovery.py     # Zeroconf mDNS (_aeonix._tcp.local) broadcaster
│   ├── fast_path.py     # Sub-millisecond router for weather, sentinel, media, sanctuary
│   ├── llama_runner.py  # Multi-tier dual model LLM runner (0.5B Fast / 1.5B Deep)
│   ├── memory.py        # AADYA Memory Heart (FTS token search, daily briefing)
│   ├── ram_guard.py     # RAM Guard (>800MB threshold, <16 child processes)
│   ├── server.py        # Starlette ASGI Daemon with WebSockets and REST APIs
│   └── stt.py           # Whisper STT engine with ARM NEON / Dotprod acceleration
├── scripts/
│   └── start-core.sh    # Wake-lock acquisition, vault integrity verify & Uvicorn startup
├── models/              # (Git-ignored) GGUF & GGML model weights
└── data/                # (Git-ignored) SQLite WAL databases
```

---

## 3. Implemented & Verified Capabilities

### Phase 1: The Core Loop (100% Verified)
- [x] **SQLite WAL Vault**: `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`, `PRAGMA integrity_check` passing.
- [x] **RAM Guard**: Active memory protection enforcing $>800\text{MB}$ free memory (current: $>3,100\text{MB}$) and process caps.
- [x] **Fast-Path Router**: Executes known commands (weather, sentinel, media, sanctuary, status) in $<0.05\text{ms}$.
- [x] **Fire TV Sideload**: Ultra-lightweight Leanback launcher verified at **68.2 MB** active PSS with **0 WebViews**.
- [x] **mDNS Discovery**: Zero-configuration discovery over `_aeonix._tcp.local:8080`.

### Phase 2: Intelligence, Voice & Sentinel Deck (100% Verified)
- [x] **Multi-Tier LLM Inference**: Fast Mode (Qwen2.5-0.5B, 469MB) & Deep Mode (Qwen2.5-1.5B, 1.04GB) with auto-unload.
- [x] **Offline Speech-To-Text**: Native `whisper.cpp` with `ggml-tiny.en.bin` transcribing 11s audio in **2.38s** offline.
- [x] **Push-to-Talk (PTT)**: 16-bit 16kHz mono PCM streaming from Fire TV remote microphone directly to POCO.
- [x] **Fail-Safe Sentinel Living Deck**:
  - Leanback dialog with synthetic acoustic cues (`CyberSoundSynth`).
  - **Fail-Safe Default**: Primary focus strictly locked to `DENY (SAFE)` to eliminate accidental execution.
  - Deliberate approval path (`DPAD_RIGHT` $\rightarrow$ `APPROVE`) verified live.
  - 300-second auto-timeout auto-denial.
- [x] **Tamper-Evident Audit Trail**: SHA-256 hash-chained cryptographic provenance across all actions, intent resolutions, and voice commands.

---

## 4. API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/status` | `GET` | Core Mind health, RAM guard telemetry & connected Glass terminals |
| `/api/sentinel/create` | `POST` | Dispatches consequential action card to Fire TV Living Surface |
| `/api/sentinel/resolve` | `POST` | Resolves Sentinel Gate approval / denial |
| `/api/memory/remember` | `POST` | Stores persistent memory in AADYA memory heart |
| `/api/memory/recall` | `GET` | Full-text token search and category memory retrieval |
| `/api/briefing` | `GET` | Daily briefing synthesis combining memories, sentinel logs & status |
| `/api/intent` | `POST` | Fast-path routed intent execution with fallback to Qwen2.5 |
| `/api/voice/transcribe` | `POST` | Direct offline WAV/PCM speech transcription endpoint |
| `/ws` | `WS` | Real-time Living Surface synchronization, PTT audio streaming, and Sentinel Gate events |

---

## 5. Quickstart

### Launching the Core Mind on POCO:
```bash
bash ~/aeonix/scripts/start-core.sh
```

### Verifying System Status:
```bash
curl -s http://127.0.0.1:8080/api/status | jq .
```
