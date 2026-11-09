# ÆTHERION / ÆONIX PRISM // Project State

**Active Milestone:** Milestone 1 (Gates G0–G3: Foundation & Core Connection)  
**Active Phase:** Phase 3 (Gate G3: Core Transport, Certificate Pinning & State Resync)  
**Last Updated:** November 9, 2026

---

## Current Progress
* [x] **Phase 0: Gate G0 (Audit & Baseline):**
  - POCO M4 Pro 5G (`22031116AI`, Android 13, 5.5 GiB RAM, 77 GiB storage) audited.
  - Subnet change tracked (`10.18.167.X`) with dynamic ADB detection.
  - Stock launcher fallback script verified (`restore.sh`).
  - Standalone portable test suite 100% pass (151/151 tests, 68s).
  - Committed and pushed to GitHub `origin/main` (`d297a4a`).
* [x] **Phase 1: Gate G1 (Build & Deploy Spike):**
  - Path A (On-device phone build via Termux) verified.
  - OpenJDK 17 + Gradle 8.9 + Termux `aapt2` override confirmed.
  - Pinned TLS Java tests passed (7/7 tests in 0.395s).
  - Standalone debug APK built in `aether-launcher`:
    - Path: `app/build/outputs/apk/debug/app-debug.apk`
    - Size: **3.2 MB** (Limit: < 30 MB)
    - SHA-256: `d03d9cf79111202366cc6168e088b72f9bd0b85f4de2c70ce252c412e06a2682`
* [x] **Phase 2: Gate G2 (Security Spine & POCO Approval Interface):**
  - Implemented standalone mobile browser Operator Console (`core/operator_ui.py`) served on `/operator` and `/console`.
  - Zero-external-CDN UI with live Sentinel review deck, Action Digest display, modal passphrase challenge, and emergency Sanctuary killswitch.
  - Added `tests/test_operator_ui.py` (4 tests) verifying HTML delivery, public allowlisting, passphrase requirement, and Fire TV approval rejection.
  - Updated inventory to 155 tests across 19 suites.
  - Full portable test suite 100% passed (155/155 in 57.3s) with bit-for-bit production isolation verified.
* [ ] **Phase 3: Gate G3 (Core Transport, Certificate Pinning & State Resync):** Next in queue.

---

## Blockers / Risks
* None. Gate G0, G1, and G2 verified and passing.

---

## Next Step
Proceed to Gate G3: Verify and harden the WSS/HTTPS certificate rotation, pairing flow, bounded message sizes (32 KiB), sequence-based state resync cursors, and heartbeat watchdog.
