# ÆONIX PRISM // Release Candidate 1 (RC-1) Verification Report (Final)

**Document ID:** `AEONIX-QA-RC1-FINAL-SIGNOFF-VERIFIED`  
**Execution Context:** Verification Attempt 3 of 3 (Final Release Sign-Off Audit)  
**Release Sign-Off Verdict:** **CONDITIONALLY CERTIFIED FOR RELEASE CANDIDATE 1 (RC-1)**  
*(Conditional upon adherence to English speech-fixture validation scope and local two-device network topology)*  
**Audit Date:** 2026-11-09  

---

## 1. Hardware Architecture & System Baseline

- **Primary Controller (POCO M4 Pro 5G):**  
  - Hardware: MediaTek Dimensity 810 SoC (2x ARM Cortex-A76 performance cores @ 2.4 GHz + 6x ARM Cortex-A55 efficiency cores @ 2.0 GHz), 6 GB RAM, UFS 2.2 storage.
  - OS / Runtime: Android 12 / Termux Linux environment (`10.18.167.168` / `10.116.23.168`).
  - System Roles: Core Mind daemon, encrypted SQLite storage vault, Sentinel deterministic authorization authority, Chronos event journal, burst-only local intelligence kernel (whisper.cpp + llama.cpp). Sole approval and signing authority.
- **Display Terminal (Amazon Fire TV Stick Lite):**  
  - Hardware: MediaTek MT8695D Quad-core ARM Cortex-A53 @ 1.7 GHz, 1 GB RAM, IMG GE8300 GPU.
  - OS / Model: Fire OS 7 (Android 9 API 28), Product: `sheldon`, Model: `AFTSS` (`10.18.167.179:5555`).
  - System Roles: PRISM Living Surface display surface, native Leanback view hierarchy, unprivileged input viewport. Zero authorization authority.
- **Git Provenance:**  
  - Candidate Commit: [`d765d2b3a1922834396fa961fe808da7e4474428`](file:///data/data/com.termux/files/home/aeonix-prism) (`HEAD -> main`, `origin/main`).
  - Tested Source Revision: [`b1c0bead57e44221707277690253923f03f0e9ea`](file:///data/data/com.termux/files/home/aeonix-prism) (Verified Ancestor: `git merge-base --is-ancestor b1c0bea d765d2b` = `TRUE`).
  - Diff against Tested Revision: Exactly 2 test inventory metadata artifacts (`docs/test_inventory.json`, `docs/test_run_artifact.json`); zero functional, configuration, test, or dependency files changed. Working tree is completely clean.

---

## 2. Capability Status Classification

Capabilities are strictly partitioned into Verified, Deferred, Blocked, and Unsupported:

### 2.1 Physically Verified Capabilities (Certified for RC-1)
- **Local Two-Device Network Pairing & Dynamic TLS:** Mutual IP pairing between POCO and Fire TV with sovereign X.509 certificates and SHA-256 certificate pinning on Android.
- **Cryptographic RBAC & Bearer Token Security:** Strict header-based bearer authentication; 100% rejection across 11 sensitive endpoints for unauthenticated or Glass-role requests.
- **Deterministic Sentinel Gate:** Consequential actions held pending operator PBKDF2 passphrase verification and reviewed action digest binding.
- **Governed Mission Full Lifecycle:** Request &rarr; Collect &rarr; Plan &rarr; Precondition Simulation &rarr; Policy Check &rarr; Operator Passphrase Approval &rarr; Single-Use Claim &rarr; Execute &rarr; Receipt Verification &rarr; Completion Journaling.
- **Single-Use Authorization & Replay Protection:** Re-executing an approved or completed mission is deterministically rejected (`INVALID_MISSION_STATUS`).
- **Mission Crash Reconciliation:** Interrupted missions persist in `EXECUTING`, recover to `NEEDS_RECONCILIATION` on reboot, and refuse automated retry without operator intervention.
- **English Speech-Fixture Validation:** Real 16kHz speech fixture (`jfk.wav`) verified through `whisper-cli` on POCO Cortex-A76 cores using `ggml-tiny.en.bin` (2.26s latency, 0.20x RTF) and `ggml-tiny.bin` (2.57s latency, 0.23x RTF).
- **Burst-Only Local LLM Kernel:** Qwen2.5-0.5B-Instruct executed locally at 8.38 tokens/sec; full RAM release upon unload.
- **Encrypted Local Disaster Recovery:** AES-256-GCM encrypted backup creation (52.28ms) and isolated restore (87.94ms); 100% logical table row parity; tampered archive rejection.
- **Native Fire TV Living Surface UI:** Native Leanback view hierarchy (147 native views, 0 WebViews), active PSS 97.8 MB (below 180 MB ceiling).

### 2.2 Explicitly Deferred Capabilities (Post-RC-1 Roadmap)
- **Spoken Hindi and Hinglish Recognition:** Synthetically tested via 440Hz sine wave parameters (`-l hi`); spoken recognition of natural Hindi and Hinglish is **DEFERRED** until consented native speech training corpora are collected and benchmarked.
- **Physical Fire TV Remote Microphone Capture:** **DEFERRED** due to Amazon Fire OS reserving the remote microphone exclusively for Alexa. Audio input is certified via the POCO smartphone microphone.
- **Multi-Speaker Conversational Voice:** Conversational multi-turn acoustic diarization is **DEFERRED**.
- **Public-Data Gateway & External Investigations:** Shodan, AlienVault OTX, and external OSINT integrations are **DEFERRED** to preserve zero-cloud boundaries for RC-1.
- **Conditional Smart-Home & Media Integrations:** Home Assistant, Plex, and media integrations are **DEFERRED**.

### 2.3 Blocked Capabilities
- **Active Subnet / LAN Port Scanning:** Panoptes active port scanning is **BLOCKED** at Sentinel Gate without explicit operator authorization and CIDR definition. Only passive local ARP inspection is operational.

### 2.4 Unsupported Architectural Scope
- **Universal Offline Autonomous Operations:** RC-1 is not certified for unbounded general-purpose autonomy; execution is strictly bounded to pre-simulated, white-listed mission types (`storage_diagnostic`, `apk_preflight`).
- **Third Compute Hosts & Cloud AI:** Cloud LLM backends (OpenAI, Anthropic, Gemini API) are explicitly unsupported in this sovereign deployment.

---

## 3. Transport Security, Certificate Pinning & Rotation

Evidence file: [`03_live_transport_security_audit.json`](file:///data/data/com.termux/files/home/aeonix-verification/rc1/evidence/03_live_transport_security_audit.json)

1. **TLS Mode & Cryptographic Specification:**  
   The transport layer operates over encrypted WebSockets (`wss://`) and HTTPS using sovereign self-signed X.509 certificates generated via `cryptography.x509`. The certificate uses a 2048-bit RSA key signed with SHA-256 and has a 10-year validity period.
2. **Subject Alternative Name (SAN) Coverage:**  
   The certificate strictly asserts SAN entries for `localhost`, `aeonix-core.local`, `127.0.0.1`, and the active LAN IP (`10.18.167.168` / `10.116.23.168`).
3. **Android SHA-256 Certificate Pinning Flow:**  
   The Fire TV Stick Lite client ([`AeonixWebSocketClient.java`](file:///data/data/com.termux/files/home/aether-launcher/app/src/main/java/com/gathin/tvhome/net/AeonixWebSocketClient.java)) enforces explicit SHA-256 certificate pinning. Its `createPinnedTrustManager` extracts the leaf certificate from the TLS peer chain and compares `SHA-256(leaf_cert.getEncoded())` against the pre-shared hex fingerprint in `cert_fingerprint.json`.
   - Missing pin configuration throws `IllegalArgumentException`.
   - Fingerprint mismatch throws `CertificateException` and immediately terminates the socket.
   - Zero `TrustAll` or unpinned fallback verifiers exist in the codebase.
4. **Certificate Rotation Procedure:**  
   To rotate the sovereign certificate:
   - On POCO: Remove `~/.aeonix/secrets/aeonix_cert.pem`, `aeonix_key.pem`, and `cert_fingerprint.json`, then re-run `ensure_sovereign_tls_credentials()` in Python.
   - On Fire TV: Update the `pinnedFingerprint` parameter in the client configuration matching the new fingerprint, then restart `com.aether.launcher`.

---

## 4. UI, Rendering Performance & Memory Leak Reality

Evidence files: [`08_firetv_gfxinfo_live_attempt3.txt`](file:///data/data/com.termux/files/home/aeonix-verification/rc1/evidence/08_firetv_gfxinfo_live_attempt3.txt), [`08_firetv_meminfo.txt`](file:///data/data/com.termux/files/home/aeonix-verification/rc1/evidence/08_firetv_meminfo.txt)

### 4.1 Display Rendering Metrics
Testing was conducted on physical Fire TV Stick Lite (`sheldon`, Android 9 API 28) running package `com.aether.launcher` (PID 17510):
- **Display Mode:** 1920x1080 @ 60.0 Hz (16.6ms frame deadline).
- **Steady-State Rendering:** Static and ambient HUD display renders with 0 missed VSYNCs.
- **Measured Startup Jank:** Broad "0% jank" or "universal 60 fps" claims are false. During cold start, layout inflation of 147 native Leanback views exceeded the 16.6ms display deadline:
  - **Measured Frames Over Deadline:** 20 out of 26 initial frames missed deadline (76.9% initial janky frames).
  - **Missed VSYNCs:** 9 missed VSYNCs during layout creation.
  - **50th Percentile Frame Time:** 46ms
  - **90th Percentile Frame Time:** 300ms
  - **95th Percentile Frame Time:** 750ms
  - **99th Percentile Frame Time:** 750ms
  - **Root Cause:** Android ViewRootImpl cold-start view tree inflation and bitmap texture uploads onto the MediaTek MT8695 GPU pipeline. Once initialized, steady-state display renders at 16.6ms intervals.

### 4.2 Memory Consumption & Leak Qualification
- **Process Memory (com.aether.launcher):** Active Total PSS is **97.8 MB** (Private Dirty: 72.9 MB, Native Heap: 29.5 MB, Graphics: 24.2 MB), safely within the 180 MB device ceiling.
- **WebViews:** **0** (strictly verified via `dumpsys meminfo 17510 | grep WebViews: 0`).
- **Memory Leak Qualification:** Zero memory leaks cannot be inferred solely from host-wide free RAM (~2.5 GB available on POCO). Process-level PSS on POCO server remained stable at 15.6 MB across the test cycle, but long-term memory leak immunity requires continuous multi-hour soak telemetry.

---

## 5. APK Artifact Provenance: Debug vs Release

| Attribute | Debug APK (Installed & Verified) | Release APK (Built Artifact) |
| :--- | :--- | :--- |
| **Artifact Path** | `/data/data/com.termux/files/home/aether-launcher/app/build/outputs/apk/debug/app-debug.apk` | `/data/data/com.termux/files/home/aether-launcher/app/build/outputs/apk/release/app-release.apk` |
| **File Size** | 3,259,101 bytes (~3.1 MB) | 1,478,810 bytes (~1.4 MB) |
| **SHA-256 Digest** | `cd7b883f6640f0d1fbe90a42e90899194e9fb2195eec98036d8ca4474eac5483` | `ea493cdf59e64141ae8d7dff66fdbf7d3edfba5f08329a58b9155c6d7bd27c70` |
| **Package Name** | `com.aether.launcher` | `com.aether.launcher` |
| **versionName / versionCode** | `2.0-hybrid` / `20` | `2.0-hybrid` / `20` |
| **minSdk / targetSdk** | `26` (Android 8.0) / `34` (Android 14) | `26` (Android 8.0) / `34` (Android 14) |
| **Signing Scheme** | Android APK Signature Scheme v2 | Android APK Signature Scheme v2 |
| **Signing Fingerprint** | `signatures=[5671f3e0]` (PackageSignatures v2) | N/A (Unsigned / Release Key Staged) |
| **Installed on Fire TV?** | **YES** (`/data/app/com.aether.launcher-Jor2bz1DGWtBxAvxG6AYTQ==/base.apk`) | NO |
| **Launched & Tested?** | **YES** (PID 17510 physically tested on `sheldon`) | NO |
| **RC-1 Status** | **CERTIFIED RC-1 PHYSICAL ARTIFACT** | **RELEASE APK BUILT BUT NOT PHYSICALLY VERIFIED; RC-1 uses the installed debug APK.** |

---

## 6. Test Suite Fidelity: Fakes vs Integration Mocks

- **Test Suite Execution:** `199 PASS / 0 FAIL / 0 ERROR / 0 SKIP` across 27 suites in 80.904s (real exit code 0).
- **Zero Integration Mocks:** Previous `unittest.mock.patch` in `test_phase4_panoptes_guardian.py` was replaced with a real loopback `http.server.HTTPServer` socket. All integration tests execute against real sockets, real SQLite files, and real cryptography.
- **Unit Test Fakes:** Unit test suites utilize ephemeral, in-memory SQLite sandbox paths and temporary files (`AEONIX_DB_PATH=/tmp/...`) to ensure that test execution has zero read/write side-effects on the production database (`~/aeonix/data/aeonix_vault.db`).

---

## 7. Verified Gate 8 Mission Lifecycle Receipt

Evidence file: [`g8_attempt3_full_receipt.json`](file:///data/data/com.termux/files/home/aeonix-verification/rc1/evidence/g8_attempt3_full_receipt.json)

```json
{
  "mission_id": "mission_1794236885065_edf5ce",
  "mission_version": "1.0-governed",
  "approval_id": "sentinel_1794236885098_d0d646",
  "sentinel_request_id": "sentinel_1794236885098_d0d646",
  "operator_identity_ref": "poco_m4_pro_core (POCO_CORE)",
  "action_type": "storage_diagnostic",
  "target": "system_storage",
  "normalized_parameters": {
    "target_path": "/data/data/com.termux/files/home"
  },
  "action_digest": "30d7833cad00d46d7f4cc56a5252a5eac51d8dc9b03189fd4d2e5844e93127dc",
  "policy_version": "sentinel-v2-rc1",
  "requested_at": 1794236885.0653522,
  "approved_at": 1794237203.1545324,
  "executed_at": 1794237226.330363,
  "verified_at": 1794237226.3689513,
  "completed_at": 1794237226.369807,
  "final_status": "COMPLETED",
  "verification_result": {
    "receipt_verified": true,
    "status": "NOMINAL",
    "total_bytes": 114988908544,
    "used_bytes": 32217411584,
    "free_bytes": 82547507200,
    "percent_used": 28.0
  },
  "evidence_references": [
    "g8_attempt3_after_approval.json",
    "g8_attempt3_verification_receipt.json",
    "g8_attempt3_approval_reuse_rejection.json"
  ],
  "audit_chain_reference": {
    "audit_log_id": 5457,
    "current_hash": "c9fb0abb375b26d212447255e9999c6063394215c88317884214d0bf58cfbcd8",
    "previous_hash": "91111afad29b30be2568b9b5a41478794f2891d59949a8645049816242ffa367"
  },
  "recovery_limitations": "Bounded read-only diagnostic. Zero disk writes executed in target directory. Crash recoverable via NEEDS_RECONCILIATION sentinel governor protocol.",
  "expiry_status": "APPROVED_PRIOR_TO_EXPIRY (TTL 600s, elapsed 318.06s)"
}
```

---

## 8. Official Release Verdict

**CONDITIONALLY CERTIFIED FOR RELEASE CANDIDATE 1 (RC-1)**  
*This candidate is certified strictly for local two-device operations with English speech-fixture validation, deterministic Sentinel gate approval on POCO M4 Pro 5G, and native Leanback display on Fire TV Stick Lite using the physically verified debug APK (`app-debug.apk`). Universal autonomy, spoken Hindi/Hinglish speech, and Fire TV remote microphone capture remain uncertified and explicitly deferred.*
