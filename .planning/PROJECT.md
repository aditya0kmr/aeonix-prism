# ÆTHERION / ÆONIX PRISM // Project Specification

**Governing Baseline:** Consolidated Two-Device Engineering Specification (4 November 2026)  
**Topology:** Strict Two-Device Sovereign Intelligence Architecture  
* **Controller / Sovereign Mind:** POCO M4 Pro 5G (`22031116AI`, Termux/Android 13)
* **Living Surface Glass:** Fire TV Stick Lite (`AFTSS`, product `sheldon`, Android 9 / Fire OS 7)
* **Third Compute Host:** None (0 external cloud servers, 0 Docker dependencies)
* **Cost / Subscription Boundary:** Zero monetary cost, zero paid commercial AI subscriptions, offline-first operation.

---

## Architecture Boundaries
1. **POCO + Termux Controller:**
   - Single-worker Uvicorn / FastAPI ASGI daemon bound to loopback/private Wi-Fi.
   - Authoritative SQLite event and state store with WAL mode and continuous quiescence backup API.
   - Deterministic Sentinel execution engine with cryptographically bound single-use action tokens.
   - Burst-only local model intelligence (0.5B GGUF via llama.cpp or pure deterministic router).
   - High-risk approval authority strictly held by POCO.

2. **Fire TV Glass (`com.gathin.tvhome`):**
   - Native Android Leanback launcher with RecyclerView and focus-stable D-pad navigation.
   - Pinned TLS WebSocket client (`AeonixWebSocketClient`) rejecting plaintext or mismatched fingerprints.
   - Bounded memory footprint (PSS < 180 MB under continuous test soak).
   - APK size bounded under 30 MB.
   - No continuous TV wake-word listener (voice is push-to-talk on POCO).

3. **Repositories:**
   - [`aditya0kmr/aeonix-prism`](https://github.com/aditya0kmr/aeonix-prism): Backend daemon, policies, test suite, and audit tooling.
   - [`aditya0kmr/cleanyourtv`](https://github.com/aditya0kmr/cleanyourtv) (`feature/cleanyourtv-hybrid-base` / `aether-launcher`): Living surface launcher.
