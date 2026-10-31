# ÆONIX PRISM // Operator Console & Sovereign Security Architecture

**Document Version:** 1.0.0  
**Governing Baseline:** Decision D01–D18 (v4.0 Architecture Specification)  
**Date:** October 31, 2026  
**Status:** IMPLEMENTED & VERIFIED  

---

## 1. Sovereign POCO Operator Console

The Operator Review Console (`core/operator_console.py`) serves as the physical local gate authority on the POCO M4 Pro 5G (`22031116AI`). It is strictly local-only and provides the operator approval mechanism for consequential operations before execution.

### 1.1 Zero Default / Agent-Selected Credentials
- **No Default PIN:** The console explicitly prohibits hardcoding, generating, or defaulting to predictable credentials (e.g., PIN 8421 or any other default).
- **First-Run Setup:** On first execution, the operator must set up their own private passphrase interactively.
- **Double Confirmation:** Input is masked using `getpass.getpass()` and must be entered twice and match.
- **Length Constraint:** Passphrase requires a minimum length of 8 characters.

### 1.2 Password Hashing & KDF Parameters
- **Algorithm:** PBKDF2-HMAC-SHA256.
- **Work Factor:** 600,000 iterations (measured optimal for Dimensity 810 without thermal throttling).
- **Salt:** 32 cryptographically random bytes generated via `secrets.token_bytes(32)`.
- **Storage:** Persisted in `~/.aeonix/secrets/operator_pin.json` with strict `0600` Linux permissions (`0700` parent directory). Contains version, iteration count, salt hex, and hash hex.

### 1.3 Persistent Lockout & Anti-Brute-Force
- **Persistent State:** Failed attempts and lockout timestamps are persisted to `~/.aeonix/secrets/operator_lockout.json` (`0600`).
- **Process Restart Immunity:** Because state is read from disk before any attempt, restarting the console or killing the process does NOT reset or bypass the active lockout window.
- **Exponential Backoff:**
  - 3 failed attempts: 30-second lockout.
  - 5 failed attempts: 60-second lockout.
  - 7+ failed attempts: 300-second (5-minute) lockout.
- **Reset on Success:** A successful passphrase authentication immediately resets the failed attempt counter to zero.

### 1.4 Deterministic Action Digest & Review Cards
Before presenting an approval decision, the console computes a deterministic cryptographic SHA-256 **Action Digest**:
$$\text{Action Digest} = \text{SHA-256}(\text{request\_id} \parallel \text{agent} \parallel \text{action\_type} \parallel \text{target} \parallel \text{canonical\_scope\_json})$$

The terminal review card displays:
- Request ID & Requesting Agent
- Action Class & Risk Level
- Exact Target & Working Directory (`cwd`)
- Exact Command Arguments
- External Egress Status
- Expiry / TTL countdown
- Cryptographic Action Digest (SHA-256)

### 1.5 Recovery & Reset Procedure
If an operator forgets their passphrase or requires credential rotation:
1. **Deliberate Local Physical Action:** Operator must access the local Termux shell on the POCO device directly. Remote reset via API or network is strictly impossible.
2. **State Invalidation:** Execute `rm ~/.aeonix/secrets/operator_pin.json ~/.aeonix/secrets/operator_lockout.json`.
3. **Session Invalidation:** Deleting the pin file invalidates all active console review authorizations immediately.
4. **Re-Initialization:** Launching `python3 core/operator_console.py` immediately initiates the first-run masked setup flow.

### 1.6 Stated Security Limitation (Termux UID Boundary)
> [!IMPORTANT]
> **Application-Level Security Barrier Only:**
> The POCO Operator Console is an application-level control executing within Termux (`UID: u0_a283`). It prevents accidental network triggers, rogue subagents, or unauthorized remote actions. Because all processes running within Termux share the identical Linux UID, any code with execute privileges under `u0_a283` can inspect process memory or read user-owned files directly.
> 
> This CLI console **does not** constitute a hardware-backed Trusted Execution Environment (TEE) or SELinux boundary. Full hardware-backed operator biometric authentication is slated for the native Android companion app.

---

## 2. Token Provisioning & Hardening

### 2.1 Revocation of Exposed Credential
- The previously committed debug token with nonce `1a2f3b38438e040f23f1692b` was permanently revoked and inserted into the `revoked_tokens` table in SQLite.
- `verify_token()` actively checks `is_token_revoked()`; any request using this revoked nonce is immediately rejected.

### 2.2 App-Private Secure Storage Provisioning
- The debuggable Fire TV APK (`com.aether.launcher`) was provisioned using `adb shell run-as com.aether.launcher`.
- Credential file path: `/data/data/com.aether.launcher/files/auth/glass_token.json`.
- File ownership: UID `u0_a11`, permissions: `0600` (`-rw-------`).
- Ordinary ADB push was avoided; app sandbox boundary was strictly maintained.

### 2.3 Elimination of Query String Credentials
- Hardcoded `DEFAULT_AUTH_TOKEN` string constant was completely expunged from `AeonixWebSocketClient.java`.
- `AeonixWebSocketClient` reads from `loadProvisionedToken()` at runtime.
- The URL query string `?token=...` parameter was removed from the WebSocket handshake request. Handshake transmits `Authorization: Bearer <token>` in the RFC 6455 HTTP upgrade header.
- The backend `websocket_endpoint` strictly rejects any handshake containing `token` in query parameters with WebSocket close code `4401`.

---

## 3. Central Authentication & Role-Based Access Control (RBAC)

### 3.1 Public Minimal Liveness Allowlist
- `GET /api/status` is the ONLY unauthenticated endpoint.
- Returns strictly:
  ```json
  {
    "status": "online",
    "system": "ÆONIX PRISM Core Mind v2.0",
    "timestamp": 1793448375.12
  }
  ```
- **Zero Information Leakage:** Absolutely zero sovereign usernames (`sovereign_user`), device counts (`connected_glass_clients`), pending counts (`sentinel_pending`), or memory metrics (`ram`) are leaked on this public route.
- Full operational telemetry is relocated to `GET /api/system/status`, requiring `ROLE_POCO_CORE`.

### 3.2 Central Default-Deny Middleware (`CentralAuthMiddleware`)
- Every HTTP route (outside `GET /api/status`) is guarded by Starlette `CentralAuthMiddleware`.
- Missing token $\to$ `401 UNAUTHENTICATED`.
- Forged signature or expired token $\to$ `401 UNAUTHENTICATED`.
- Revoked nonce $\to$ `401 UNAUTHENTICATED`.

### 3.3 RBAC Matrix
| Role | Permitted Routes | Forbidden Routes |
|---|---|---|
| `ROLE_POCO_CORE` | All 65 REST routes & WebSocket | None (Sovereign Authority) |
| `ROLE_FIRETV_GLASS` | `GET /api/status`<br>`GET /api/sentinel/pending`<br>`POST /api/sentinel/resolve` (Deny only)<br>`POST /api/intent`<br>`POST /api/voice/transcribe`<br>`GET /api/lumen/surface`<br>`GET /api/briefing`<br>`GET /api/media/*`<br>`GET /api/sanctuary/status` | `POST /api/forge/*`<br>`GET /api/backup/*`<br>`POST /api/backup/*`<br>`GET /api/veritas/*`<br>`GET /api/guardian/*`<br>`POST /api/sanctuary/activate`<br>`POST /api/sanctuary/deactivate`<br>`POST /api/trust/*`<br>`POST /api/ai/benchmark` (All return 403 FORBIDDEN) |
| `ROLE_AGENT_EXECUTOR` | `GET /api/status`<br>`POST /api/sentinel/create`<br>`POST /api/agents/dispatch`<br>`POST /api/memory/remember`<br>`GET /api/memory/recall` | System status, forge execution, backup operations, sanctuary (All return 403 FORBIDDEN) |

---

## 4. Execution Lifecycle & Protection Containment

### 4.1 Strict Lifecycle State Transitions
- Sentinel orders follow a strict multi-stage lifecycle:
  $$\text{pending} \xrightarrow{\text{resolve}} \text{approved} \xrightarrow{\text{claim}} \text{claimed} \xrightarrow{\text{complete}} \text{completed / failed}$$
- `complete_sentinel_execution` enforces that starting status **must be `claimed`**. Any attempt to complete directly from `pending`, `approved`, or already `completed` states returns `False`.
- `consume_sentinel_authorization` claims the authorization order (`approved` $\to$ `claimed`) without fabricating completion. Actual execution must complete before status transitions to `completed`.

### 4.2 File Protection & Path Containment
`core/forge.py` enforces multi-layer protection:
1. **Option Validation:** For `file_remove`, only explicit safe options `{"-f", "-r", "-rf", "-v"}` are allowed. Dangerous flags such as `--no-preserve-root` are rejected with `ILLEGAL_OPTION`.
2. **Canonical Path Resolution:** Target paths are resolved using `os.path.realpath(os.path.abspath(os.path.join(cwd, arg)))` to eliminate path traversal (`../`) and symlink escapes.
3. **Protected Tree Policy:** Rejects removal of:
   - Root `/`, `/system`, `/data/data/com.termux/files/usr`
   - User home directory root (`~`)
   - Secret storage `~/.aeonix/secrets`
   - Git repository trees (`.git`, `/.git/`)
   - SSH directories and keys (`.ssh`, `/.ssh/`)
   - SQLite databases and journal files (`*.db`, `*.db-wal`, `*.db-shm`)
   - Core codebase and data trees (`/aeonix/core`, `/aeonix/data`)
4. **Execution Failure Hook:** If an approved Sentinel request targets a protected resource, Forge marks the execution as `failed` in the audit log and Sentinel table before returning denied.

### 4.3 Disaster Recovery Maintenance Mode Lock
- When disaster recovery restore begins, `set_maintenance_mode(True)` is engaged.
- **Database Layer:** `get_connection()` raises `sqlite3.OperationalError: DATABASE_LOCKED: System is in disaster recovery maintenance mode` for non-recovery callers.
- **REST Layer:** `CentralAuthMiddleware` returns `503 MAINTENANCE_LOCKED` for all non-backup endpoints.
- **Recovery Isolation:** Only disaster recovery functions passing `allow_maintenance=True` can access and verify the database until restore completes and maintenance mode is safely released.
