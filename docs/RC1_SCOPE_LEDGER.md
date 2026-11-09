# ÆONIX PRISM // Release Candidate 1 (RC-1) Scope Ledger

**Document ID:** `AEONIX-SPEC-RC1-SCOPE-LEDGER`  
**Baseline Commit:** `d765d2b3a1922834396fa961fe808da7e4474428`  
**Topology:** POCO M4 Pro 5G (Core Controller) + Amazon Fire TV Stick Lite (Living Surface Display)  
**Classification Rules:**
- `PHYSICALLY_VERIFIED`: Directly tested on POCO M4 Pro 5G or Fire TV Stick Lite hardware with verifiable artifact.
- `PARTIALLY_VERIFIED`: Core logic tested in portable suite or synthetic fixture; complete physical hardware flow contains deferred sub-components.
- `DEFERRED`: Formally planned capability intentionally postponed to post-RC-1 milestone.
- `BLOCKED`: Capability prohibited by security policy, missing permission, or architectural constraint.
- `NOT_IMPLEMENTED`: Architectural concept designed in specification but no executable code exists in RC-1.

---

## 1. Master Capability Matrix

| Capability Family | Requested Behavior | RC-1 Status | Evidence Artifact | Security Class | Approval Requirement | Deferred Reason | Post-RC-1 Next Action |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Core Identity & Health** | Sovereign device token issuance, HMAC-SHA256 signature, monotonic sequence, health telemetry | **PHYSICALLY_VERIFIED** | `02_security_static_scan.txt`, `07_security_rbac_matrix.json` | R0 (System) | None (Read-only status) | None | Add continuous daemon heartbeat monitor |
| **Chronos Journal** | Append-only SHA-256 hash-chained event journal, reconnect state resync | **PHYSICALLY_VERIFIED** | `09_performance_soak_telemetry.txt`, `test_gate3_transport_and_sync.py` | R1 (Audit) | None (Automatic journal) | None | Implement long-term snapshot & prune compaction |
| **Sentinel Gate** | Deterministic authorization, PBKDF2 operator verification, action digest binding, rate-limiting & lockout | **PHYSICALLY_VERIFIED** | `07_security_rbac_matrix.json`, `test_operator_lockout_failclosed.py` | R3 (Auth) | Sovereign POCO Passphrase Required | None | Add biometrics (fingerprint) authorization prompt |
| **AXIOM Missions** | Multi-phase governed mission lifecycle, simulation, crash reconciliation, single-use replay protection | **PHYSICALLY_VERIFIED** | `g8_attempt3_full_receipt.json`, `08_crash_reconciliation_live.json` | R3 (Governed) | Operator Passphrase & Digest Match | None | Expand declarative mission phase library |
| **VOX Speech Recognition** | Offline local speech-to-text via `whisper.cpp` | **PARTIALLY_VERIFIED** | `07_voice_multilingual_matrix.json` | R1 (Input) | None | Spoken Hindi/Hinglish recognition and Fire OS remote mic PTT deferred | Integrate consented native Hindi voice corpus; mobile mic PTT app |
| **Oracle Intelligence** | Burst-only local LLM kernel (llama.cpp / Qwen2.5-0.5B), fast-path regex router, memory guard | **PHYSICALLY_VERIFIED** | `test_gate6_local_intelligence.py` | R1 (Compute) | None | None | Benchmark quantized 1.5B model on Dimensity 810 |
| **Forge Execution** | Bounded execution of typed operations (`storage_diagnostic`, `apk_preflight`), fs isolation | **PHYSICALLY_VERIFIED** | `g8_attempt3_full_receipt.json`, `test_narrow_fs_allowlist.py` | R3 (Execution)| Sentinel Operator Approval | Arbitrary shell script execution forbidden | Add sandboxed container runner for user tools |
| **Echo Dispatcher** | Event broadcast over WebSocket, HUD card rendering on Fire TV | **PHYSICALLY_VERIFIED** | `test_gate3_transport_and_sync.py`, `08_firetv_logcat.txt` | R1 (Display) | None | None | Add audio chime notifications on Living Surface |
| **Lumen Context** | Local memory storage, tag retrieval, chronological context assembly | **PARTIALLY_VERIFIED** | `test_phase3_lumen_rag.py` | R1 (Storage) | None | High-dimensional embedding vector store deferred | Integrate on-device sqlite-vss or hnswlib index |
| **PRISM TV UI** | Native Leanback HUD display, D-pad navigation, zero WebViews, sub-180MB RAM | **PHYSICALLY_VERIFIED** | `08_firetv_gfxinfo_live_attempt3.txt`, `08_firetv_meminfo.txt` | R0 (Display) | None | None | Optimize cold-start layout view inflation |
| **Mesh Pairing & Sync** | Two-device local IP pairing, dynamic X.509 cert, Android SHA-256 cert pinning | **PARTIALLY_VERIFIED** | `03_live_transport_security_audit.json`, `AeonixWebSocketClient.java` | R2 (Network) | Initial Device Pairing PIN | Multi-hop mesh network routing deferred | Add mDNS / NSD automatic device discovery |
| **Guardian Network** | Passive ARP inspection, gateway verification, zero cloud outbound enforcement | **PHYSICALLY_VERIFIED** | `g9_guardian_network.json`, `test_phase4_panoptes_guardian.py` | R2 (Network) | None (Passive mode) | Active subnet port scanning held at Sentinel | Add Wi-Fi interface signal metrics |
| **Recovery Vault** | Online atomic SQLite backup, AES-256-GCM encryption, isolated restore drill | **PHYSICALLY_VERIFIED** | `10_disaster_recovery_isolated_audit.json`, `g10_backup_verify.json` | R3 (Storage) | Recovery Passphrase Required | None | Add automated off-device backup sync via SFTP/USB |
| **Briefing Service** | Morning / evening situational briefing synthesis from local events | **PARTIALLY_VERIFIED** | `test_orchestrator_scenarios.py` | R1 (Compute) | None | Multi-modal TTS audio briefing deferred | Connect local Piper TTS engine for audio output |
| **Gateway & Public Data** | External OSINT (Shodan, AlienVault OTX, domain queries) | **DEFERRED** | N/A | R2 (Network) | Operator Approval Required | Strict zero-cloud offline scope for RC-1 | Implement rate-limited outbound proxy with operator opt-in |
| **AETHER Build & Deploy** | Native Android compilation of `com.aether.launcher`, APK signing, ADB push | **PHYSICALLY_VERIFIED** | `08_firetv_meminfo.txt`, `app-debug.apk` | R2 (Tooling) | Operator USB Debugging | None | Automate release APK v3 signing pipeline |
| **Lawful Investigations** | Bounded APK static manifest and preflight inspection | **PARTIALLY_VERIFIED** | `test_gate8_governed_mission.py` | R3 (Analysis) | Operator Sentinel Approval | Remote binary reverse engineering deferred | Expand static Dex parser and permission audit |
| **Media & Watchlist** | Local media index, watchlist synchronization with TV playback | **DEFERRED** | N/A | R1 (Media) | None | Secondary priority for initial governance core | Connect local UPnP / DLNA media server |
| **Conditional Home Integration**| Home Assistant / Zigbee local smart home coordination | **DEFERRED** | N/A | R2 (IoT) | Operator Action Approval | Out of scope for two-device RC-1 baseline | Build local MQTT / WebSockets HA bridge |

---

## 2. Summary by Status Tier

- **PHYSICALLY_VERIFIED (10 Families):** Core Identity & Health, Chronos Journal, Sentinel Gate, AXIOM Missions, Oracle Intelligence, Forge Execution, Echo Dispatcher, PRISM TV UI, Guardian Network, Recovery Vault, AETHER Build & Deploy.
- **PARTIALLY_VERIFIED (5 Families):** VOX Speech Recognition (English certified; Hindi/remote mic deferred), Lumen Context, Mesh Pairing & Sync, Briefing Service, Lawful Investigations.
- **DEFERRED (4 Families):** Gateway & Public Data, Media & Watchlist, Conditional Home Integration, Multi-Device Mesh Routing.
- **BLOCKED (1 Capability):** Unbounded Active Network Scanning (held at Sentinel Gate).
- **NOT_IMPLEMENTED (0 Families):** All core architectural concepts have executable implementations in repository code.
