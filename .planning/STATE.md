# ÆTHERION / ÆONIX PRISM // Project State

**Active Milestone:** Milestone 3 (Gates G7–G10: Voice, Governed Missions, Forensics & Production Hardening)  
**Active Phase:** Phase 7 (Gate G7: VOX Push-to-Talk Audio)  
**Last Updated:** November 9, 2026

---

## Completed Gates
* [x] **Phase 0: Gate G0 (Physical & Repository Baseline Audit):**
  - POCO M4 Pro 5G (`22031116AI`, Android 13, 5.5 GiB RAM, 77 GiB storage) audited.
  - Dynamic ADB target detection implemented in `core/atlas_watch.py`.
  - Stock launcher fallback script verified (`restore.sh`).
  - Standalone portable test runner established.
  - Committed and pushed to GitHub `origin/main` (`d297a4a`).
* [x] **Phase 1: Gate G1 (Build & Deploy Spike):**
  - Path A (On-device phone build via Termux) verified.
  - OpenJDK 17 + Gradle 8.9 + Termux `aapt2` override confirmed.
  - Pinned TLS Java tests passed (7/7 tests in 0.395s).
  - Standalone debug APK built in `aether-launcher`:
    - Size: **3.2 MB** (Limit: < 30 MB)
    - SHA-256: `d03d9cf79111202366cc6168e088b72f9bd0b85f4de2c70ce252c412e06a2682`
* [x] **Phase 2: Gate G2 (Security Spine & POCO Approval Interface):**
  - Standalone mobile Operator Console (`core/operator_ui.py`) served at `/operator` and `/console`.
  - Zero-external-CDN UI with Sentinel review deck, Action Digest display, passphrase modal, and emergency Sanctuary stop.
  - Role-segregated authorization (401 unauthenticated, 403 Fire TV Glass).
  - 4 new unit tests added in `tests/test_operator_ui.py`.
  - Committed and pushed to GitHub `origin/main` (`c3b0ec4`).
* [x] **Phase 3: Gate G3 (Core Transport, Certificate Pinning & State Resync):**
  - Enhanced `core/tls_cert.py` with dynamic subnet SAN resolution.
  - Enforced 32 KiB safety ceiling on WebSocket control frames.
  - Monotonic server sequence stamping (`_SERVER_SEQUENCE`) on broadcast messages.
  - Ring buffer and sequence-based resynchronization (`sync_request` / `sync_response`) replaying missed state on reconnect.
  - 6 new unit tests added in `tests/test_gate3_transport_and_sync.py`.
  - Committed and pushed to GitHub `origin/main` (`a3f5744`).
* [x] **Phase 4: Gate G4 (Chronos Context, Durable Events & Integrity Proofs):**
  - Implemented durable `events` table with schema versioning (`1.0.0`), monotonic server sequence, and 32 KiB payload ceiling bounding.
  - Created `record_durable_event` with anti-replay duplicate prevention and SHA-256 payload hashing.
  - Implemented deterministic `replay_event_journal` with automatic sequence monotonicity and payload tamper detection.
  - Added controlled SQLite WAL checkpointing (`checkpoint_wal` supporting PASSIVE, FULL, TRUNCATE) and database integrity checks (`verify_database_integrity` with quick_check & full_integrity_check).
  - Implemented Open-Meteo CC BY 4.0 weather cache provenance (`get_weather_with_provenance`) with honest staleness tracking and offline fallback.
  - Added `/gateway/weather`, `/chronos/timeline`, `/events`, and `/system/wal-checkpoint` endpoints with RBAC role enforcement.
  - 8 new unit tests in `tests/test_gate4_chronos.py`.
  - Committed and pushed to GitHub `origin/main` (`ed9f8dd`).
* [x] **Phase 5: Gate G5 (PRISM TV Living Surface — Command Deck & D-Pad):**
  - Verified TV launcher UI in `aether-launcher`: Command Deck, App Matrix, Sentinel HUD cards, and Chronos views.
  - Verified D-pad navigation, RTL/Hebrew boundary containment, and zero focus traps across all rows (`GridNavigationTest`, `RemoteKeysTest`, `DockSlotsTest`).
  - Verified memory trim policy (`onTrimMemory`) and PSS constraint (< 180 MB) with clean view and wallpaper player recycling (`MemoryTrimPolicyTest`).
  - Verified 302/302 plain JVM JUnit tests passed (100%) and APK size verified at 3.2 MB.
* [x] **Phase 6: Gate G6 (Local Intelligence — Burst-Only Inference):**
  - Verified deterministic fast-path intent router for system commands, weather, time, sentinel, missions, and daily briefing in sub-50ms (0.08ms – 38ms) with zero LLM invocation.
  - Verified POCO RAM guard budget enforcement: available RAM threshold check (> 600 MB) and Android Phantom Process limit (< 24 child processes).
  - Enforced burst-only model memory lifecycle: local Qwen2.5 0.5B GGUF model allocates on-demand and unloads immediately upon query completion via `stop_server()` (zero permanent resident memory footprint).
  - Enforced security barrier: fuzzy text similarity alone strictly prohibited from authorizing destructive commands.
  - 5 new unit tests added in `tests/test_gate6_local_intelligence.py`.
  - Test inventory expanded to **174 tests across 22 suites** (100% PASS in 82.9s with verified production isolation).

---

## Next Step
Proceed to Phase 7 (Gate G7): VOX Push-to-Talk Audio.
