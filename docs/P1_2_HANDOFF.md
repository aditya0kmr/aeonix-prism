# ÆONIX PRISM // Milestone P1-2 Voice Loop Hand-off & Preservation Checkpoint

## 1. Executive Summary & Current Operational Status
This document records the end-of-day state, architectural changes, evidence qualifications, and pending physical verification for Milestone P1-2 (Push-to-Talk to Indian English Neural TTS to Fire TV Voice Loop).

- **Current State:** Work frozen for the day due to a residential power cut ("light cut").
- **Server / Listener:** PRISM port `8443` is **CLOSED** (`ECONNREFUSED`). Uvicorn is completely stopped; zero test workers remain.
- **Background / Supporting Services:** Lumina Hub remains running untouched on port `8080`.
- **ADB Session:** Terminated and disconnected (`adb devices` list empty).
- **Physical Verification Status:** The normal-application physical Trial 1 was halted and remains **INCONCLUSIVE / PENDING** due to loss of television power. Earlier attempts are classified strictly as **INCOMPLETE / PREFLIGHT-ONLY** where no fresh physical capture and confirmed playback occurred.
- **Earlier Listening Demonstration Distinction:** The earlier successful listening demonstration achieved on the Fire TV utilized a staged test runner script (`scripts/test_firetv_voice_delivery.py`), which remains distinct from the production application route (`aeonix.core.server:app`).

---

## 2. Completed Architecture & Code Changes

### 2.1 Authentication & Security Remediation
- **Credential-Free UI Shell (`ui/ptt_console.py`, `core/server.py`):**
  - Eliminated embedded tokens, JWTs, and default credentials from `GET /ui/ptt`.
  - Added volatile memory retention: tokens live strictly in JavaScript closures and are never persisted to `localStorage`, `sessionStorage`, or cookies.
  - Eliminated token exposure via URL query parameters (`?token=...`) across all endpoints.
  - Enforced single-use 128-bit bootstrap secret exchange (`POST /api/ptt/bootstrap`) requiring an interactive local CLI run (`scripts/bootstrap_ptt_operator.py`).
  - Added explicit origin validation on `POST /api/ptt/bootstrap` via `AEONIX_BOOTSTRAP_ALLOWED_ORIGINS`.
- **Session Lifetime & Revocation:**
  - `ROLE_PTT_OPERATOR` session token TTL is capped at 900 seconds (15 minutes).
  - Explicit logout via the **EXIT** button immediately posts to `POST /api/ptt/logout`, inserting the token nonce into `revoked_tokens` in the database.
  - Qualified browser-usability checkpoint recorded: Session 1 timed out before bootstrap completion; Session 2 successfully authenticated and logged out.

### 2.2 Normal-Application Voice Integration
- **Normal Path Integration (`core/server.py`, `core/voice_pipeline.py`):**
  - Integrated the complete chain into `post_api_ptt_stop`:
    `Browser PTT -> VAD -> Whisper STT -> system_health Match -> Local Piper TTS -> Pinned TLS WebSocket Delivery -> Fire TV Playback`.
  - Confinement: Non-`system_health` intents trigger zero TTS synthesis, zero audio dispatch, zero LLM calls, and zero Sentinel queue writes.
  - Fixed Response: *"Living surface online. The phone and television are connected."*

### 2.3 Concurrency & Worker-Ownership Mechanism
- **Encapsulated Ownership (`core/voice_pipeline.py`):**
  - Implemented `VoiceResponseOwnership` and `VoiceResponseSession` to enforce strictly one response at a time across async orchestration, queued tasks, and orphaned worker threads.
  - Concurrent requests receive `HTTP 409 Conflict` (`VOICE_PIPELINE_BUSY`).
  - Cancelled/timed-out requests release ownership only after both async orchestration and submitted worker threads complete, preventing late audio dispatch or overlapping responses.

---

## 3. Test Verification & Code Health

- **Full Test Suite:** 340 tests ran and passed (`Ran 340 tests ... OK`, exit code `0`).
- **Targeted Integration Tests (`tests/test_ptt_voice_loop_integration.py`):** 16 dedicated tests covering timeout boundaries, worker ownership, executor exception handling, and 900-second session TTL enforcement.
- **Security Boundary Tests (`tests/test_ptt_security_remediation.py`):** 12 tests covering origin validation, CSRF resistance, replay rejection, and query parameter token rejection.

---

## 4. Known Limitations & Technical Debt

1. **Local Scratch-Path Fallback (`core/tts.py`):**
   - Lines 167–176 contain an `ImportError` fallback adding the scratch venv site-packages path to `sys.path`.
   - Recorded as temporary portability debt; runtime launches must set `PYTHONPATH` explicitly so runtime does not depend on the fallback.
2. **Uvicorn Graceful Shutdown Discrepancy:**
   - Under `timeout -k 5s 175s`, Uvicorn acknowledges `SIGTERM` (`Waiting for application shutdown`), but does not cleanly exit within the 5-second window, receiving `SIGKILL` (exit code `137`). Cause is currently UNKNOWN (unclosed background threads or event handles).
3. **Fire TV Target Network Address:**
   - The Fire TV active endpoint file (`files/auth/endpoint.json`) was verified via read-only ADB as pointing to `10.110.118.168:8443`.
   - Because IP addresses on dynamic LANs may change across router reboots or power cycles, network addresses must be rechecked before running trials tomorrow.
4. **Cinematic UI References:**
   - Recorded strictly as future backlog work; not implemented in this phase.

---

## 5. Resumption Checklist for Tomorrow

- [ ] Confirm power restoration and verify POCO LAN IP (`wlan0`) and Fire TV IP reachability.
- [ ] Perform read-only preflight check (module resolution, model assets, TLS certificates).
- [ ] Wait for operator to confirm **"browser ready"** with Chrome pre-opened to `https://127.0.0.1:8443/ui/ptt`.
- [ ] Operator generates fresh bootstrap secret via `python3 scripts/bootstrap_ptt_operator.py`.
- [ ] Launch bounded 175s server session.
- [ ] Verify Fire TV auto-connects to `https://<lan-ip>:8443/ws`.
- [ ] Operator completes single physical capture for **Trial 1**.
- [ ] Capture listening verdict from human operator before advancing.
- [ ] Do **NOT** automatically restart or advance to Trials 2/3.
