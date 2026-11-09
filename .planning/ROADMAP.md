# ÆTHERION / ÆONIX PRISM // Master Roadmap (G0–G10)

**Reference:** Consolidated Two-Device Engineering Specification (4 November 2026, Section 22)

---

## Phases & Gates

### Phase 0: Gate G0 — Physical & Repository Baseline Audit
* [x] Task 0.1: Run and document hardware properties of POCO controller (`22031116AI`, Android 13, 5.5 GiB RAM, 77 GiB free storage).
* [x] Task 0.2: Run and document Fire TV Stick Lite properties over ADB (subnet shift documented, target `10.18.167.X` dynamic discovery).
* [x] Task 0.3: Verify stock home launcher recovery script and fallback availability (`restore.sh`).
* [x] Task 0.4: Reconcile working tree in `aeonix-prism`, run portable test suite (151/151 passed), and commit (`d297a4a`).
* **Exit Gate:** Device properties locked, test suite 100% pass, working stock fallback confirmed. [VERIFIED]

### Phase 1: Gate G1 — Build & Deploy Spike (TV APK)
* [x] Task 1.1: Audit Gradle / Android build toolchain feasibility directly on Termux/ARM (Java 17 OpenJDK + Gradle 8.9 verified).
* [x] Task 1.2: Establish minimal signed TV APK compilation path (Path A phone-only on-device verified: 36s build time).
* [x] Task 1.3: Verify APK package name continuity (`com.gathin.tvhome`), signature digest, and APK size (3.2 MB vs < 30 MB ceiling).
* **Exit Gate:** Reproducible TV APK built directly on phone in Termux. [VERIFIED]

### Phase 2: Gate G2 — Security Spine & POCO Approval Interface
* [x] Task 2.1: Enforce loopback/private IP binding and strict authentication headers.
* [x] Task 2.2: Implement POCO Mobile Operator Console web UI for single-tap R3/R4 mission approval/denial (`core/operator_ui.py`, `/operator` and `/console` routes).
* [x] Task 2.3: Verify append-only cryptographic audit chain and fail-closed rate-limiting (155/155 test suites passed).
* **Exit Gate:** Operator approval flow verified in browser; unapproved R3/R4 actions strictly rejected. [VERIFIED]

### Phase 3: Gate G3 — Core Transport, Certificate Pinning & State Resync
* [x] Task 3.1: Generate self-signed CA and device certificate with dynamic subnet SAN coverage (`core/tls_cert.py`).
* [x] Task 3.2: Verify Fire TV Java client certificate pinning handshake (`AeonixWebSocketClientTest`: 7/7 JUnit passed).
* [x] Task 3.3: Implement sequence-based state resynchronization cursor, 32 KiB safety frame bounding, and heartbeat watchdog (`tests/test_gate3_transport_and_sync.py`: 6/6 passed).
* **Exit Gate:** Encrypted WebSocket link established; reconnects resync lost state without duplication. [VERIFIED]

### Phase 4: Gate G4 — Chronos Context, Durable Events & Integrity Proofs
* [ ] Task 4.1: Durable SQLite event envelope schema validation and WAL checkpointing.
* [ ] Task 4.2: Audit entry chaining: `hash(versioned record + previous hash)`.
* [ ] Task 4.3: Weather and external cache provenance with honest staleness indicator.
* **Exit Gate:** Event journal replay verified; tamper detection flags corrupted events.

### Phase 5: Gate G5 — PRISM TV Living Surface (Command Deck & D-Pad)
* [ ] Task 5.1: Implement Command Deck, App Matrix, Sentinel, Chronos views in Leanback/RecyclerView.
* [ ] Task 5.2: Focus stability test: zero focus traps, consistent Back key behavior across all rows.
* [ ] Task 5.3: Memory soak test: TV PSS verified below 180 MB during continuous rapid navigation.
* **Exit Gate:** Fluid 60fps TV navigation on Fire TV Stick Lite under 180 MB RAM.

### Phase 6: Gate G6 — Local Intelligence (Burst-Only Inference)
* [ ] Task 6.1: Fast deterministic intent router for system commands, app launches, and cached cards.
* [ ] Task 6.2: Lightweight quantized model admission (0.5B GGUF via llama.cpp) for burst execution.
* [ ] Task 6.3: Strict memory lifecycle: allocate on query, stream response, unload model immediately.
* **Exit Gate:** Deterministic queries < 50ms; burst inference completes without tripping controller RAM guard.

### Phase 7: Gate G7 — VOX Push-to-Talk Audio
* [ ] Task 7.1: POCO push-to-talk audio capture and local VAD.
* [ ] Task 7.2: Offline ASR pipeline using `sherpa-onnx` lightweight model.
* [ ] Task 7.3: Feasibility assessment of Fire TV remote mic input (gated).
* **Exit Gate:** Spoken command on POCO transcribes offline and triggers deterministic intent.

### Phase 8: Gate G8 — First Governed Mission
* [ ] Task 8.1: Construct end-to-end mission (Storage Diagnostic or APK Preflight).
* [ ] Task 8.2: Simulate and evaluate policy -> request POCO approval -> single-use token claim.
* [ ] Task 8.3: Execute bounded action and record cryptographic audit verification entry.
* **Exit Gate:** Live mission executed with verified audit receipt.

### Phase 9: Gate G9 — Forensic & Telemetry Expansion
* [ ] Task 9.1: Bounded network topology telemetry and local device inventory.
* [ ] Task 9.2: Topic monitoring and source-linked markdown note ingestion.
* **Exit Gate:** Passive observations ingested without background battery drain.

### Phase 10: Gate G10 — Release Hardening, Restore Drill & Verification Audit
* [ ] Task 10.1: Full disaster recovery drill: simulate database wipe and restore from verified backup.
* [ ] Task 10.2: Security regression test run across all 151+ test cases.
* [ ] Task 10.3: Final evidence package and user handbook generation.
* **Exit Gate:** Clean disaster restore pass, 0 security warnings, production sign-off.
