# ÆONIX PRISM // Release Candidate 1 (RC-1) Operator & User Handbook

**Document ID:** `AEONIX-DOC-RC1-USER-HANDBOOK`  
**Target Release:** Release Candidate 1 (RC-1)  
**System Architecture:** Two-Device Sovereign Topology (POCO M4 Pro 5G Controller + Fire TV Stick Lite Living Surface)  
**Date:** 2026-11-09  

---

## 1. What RC-1 Does and Does Not Do

### What RC-1 Does
- Operates 100% locally on your local home Wi-Fi network without external cloud AI dependencies.
- Runs the primary intelligence core, encrypted database vault, and approval authority on the **POCO M4 Pro 5G**.
- Renders an ambient, native Leanback HUD on the **Amazon Fire TV Stick Lite** without WebViews.
- Validates offline English voice commands via local `whisper.cpp` processing on the phone.
- Enforces deterministic Sentinel Gate authorization: consequential actions require human operator passphrase entry and action digest confirmation on POCO.
- Executes safe, bounded governed missions (`storage_diagnostic`, `apk_preflight`) with immutable cryptographic receipts.
- Automatically captures and reconciles mid-mission crashes into a `NEEDS_RECONCILIATION` state on reboot, prohibiting blind automated retries.
- Provides authenticated, encrypted local backups (`AES-256-GCM`) with isolated verification drill capabilities.

### What RC-1 Does NOT Do
- Does **not** recognize spoken Hindi, Hinglish, or mixed-language voice commands (speech parameter verification tested only; natural spoken corpora deferred).
- Does **not** capture audio from the Amazon Fire TV remote microphone (Fire OS reserves the remote mic exclusively for Alexa; audio input is handled on the POCO phone).
- Does **not** perform unconstrained or arbitrary autonomous shell execution.
- Does **not** connect to external third-party cloud LLMs (OpenAI, Anthropic, Google Cloud).
- Does **not** conduct active subnet or port scanning across your home network.
- Does **not** guarantee multi-hour UI frame consistency without initial cold-start view inflation jank.

---

## 2. POCO Setup & Service Startup

### Prerequisites on POCO M4 Pro 5G
1. Install **Termux** (F-Droid build) and **Termux:API**.
2. Ensure Python 3.11+ is installed (`pkg install python`).
3. Ensure model weights are located in `~/aeonix/models/`:
   - Whisper: `ggml-tiny.en.bin` (or `ggml-tiny.bin`)
   - LLM: `qwen2.5-0.5b-instruct-q4_k_m.gguf`

### Service Startup
To start the sovereign Core Mind daemon:
```bash
# 1. Acquire Android wake-lock to prevent CPU throttling
termux-wake-lock

# 2. Start the daemon with default loopback binding (or set AEONIX_BIND_HOST=0.0.0.0 for LAN access)
cd ~/aeonix-prism
bash scripts/start-core.sh
```
The server will bind to `http://127.0.0.1:8080` (or your LAN IP if `AEONIX_BIND_HOST=0.0.0.0` is exported).

---

## 3. Fire TV Installation & Pairing

### Installation via ADB
1. Enable **Developer Options** and **ADB Debugging** on your Fire TV Stick Lite (`Settings -> My Fire TV -> Developer Options`).
2. Connect from POCO via ADB over LAN:
   ```bash
   adb connect <FIRE_TV_IP>:5555
   ```
3. Install the native AETHER launcher APK:
   ```bash
   adb -s <FIRE_TV_IP>:5555 install -r ~/aether-launcher/app/build/outputs/apk/debug/app-debug.apk
   ```
4. Launch the application:
   ```bash
   adb -s <FIRE_TV_IP>:5555 shell am start -n com.aether.launcher/com.gathin.tvhome.MainActivity
   ```

### Pairing Handshake
- The Fire TV client connects via secure WebSocket (`wss://<POCO_IP>:8080/ws`).
- The client validates the server's X.509 certificate against the pre-configured SHA-256 certificate fingerprint. If the fingerprint does not match, connection is refused.
- Authentication utilizes the provisioned `ROLE_FIRETV_GLASS` token located at `~/.aeonix/secrets/token_firetv_stick_glass.json`.

---

## 4. Operator Console Approval Flow

High-risk or consequential actions are held at the Sentinel Gate and will not execute without operator authorization.

1. Open the Operator Console in a browser on POCO:
   ```text
   http://127.0.0.1:8080/operator
   ```
2. Inspect the pending Sentinel Request:
   - **Request ID:** e.g., `sentinel_1794236885098_d0d646`
   - **Action Class / Type:** e.g., `governed_mission / storage_diagnostic`
   - **Target & Parameters:** Path and bounds.
   - **Action Digest:** SHA-256 cryptographic binding of all parameters.
3. Review the parameters and enter your **Operator Passphrase**.
4. Click **Approve** (or **Deny**).
5. Once approved, the governor claims the authorization token and executes the bounded action, publishing an audit receipt.

---

## 5. Emergency Pause & System Kill Switch

In case of abnormal behavior or if you wish to instantly halt all autonomous agents:

### Engaging the Kill Switch
- **Via Operator Console:** Click the red **Emergency Pause / Kill Switch** button on the console header.
- **Via Terminal Command:**
  ```bash
  curl -X POST http://127.0.0.1:8080/api/trust/killswitch \
    -H "Authorization: Bearer <POCO_BEARER_TOKEN>" \
    -H "Content-Type: application/json" \
    -d '{"action": "engage", "rationale": "Operator emergency intervention"}'
  ```
- **System Impact:**
  - Active missions are immediately halted.
  - The Sentinel Gate refuses all new proposals.
  - The Fire TV Living Surface displays an amber **EMERGENCY PAUSE ACTIVE** HUD banner.

### Disengaging the Kill Switch
Disengagement strictly requires POCO Core authentication:
```bash
curl -X POST http://127.0.0.1:8080/api/trust/killswitch \
  -H "Authorization: Bearer <POCO_BEARER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"action": "disengage", "rationale": "Operator cleared resume"}'
```

---

## 6. Guest Mode & Household Privacy

When guests or non-operators are in the room, Guest Mode prevents personal data leakage onto the shared television screen.

- **Activating Guest Mode:**  
  Toggle **Guest Mode** via the Operator Console or Fire TV settings.
- **Privacy Protections:**
  - Hides case investigations, audit logs, and system alerts from the Living Surface.
  - Prevents personal notifications from popping up on the TV screen.
  - Disables local in-memory event caching on the TV client.
  - Spoken responses containing personal data are directed solely to the POCO phone display, not spoken aloud on the television.

---

## 7. Voice Usage & Limitations

- **Certified Audio Path:** Speak commands into the **POCO smartphone microphone**.
- **Supported Language:** English speech is fully certified using real speech fixtures (`jfk.wav` baseline, RTF ~0.20x).
- **Voice Limitations:**
  - Natural spoken Hindi, Hinglish, or mixed-language phrases are **not certified** in RC-1.
  - The Amazon Fire TV Stick Lite remote microphone **cannot be used** due to Amazon OS security sandboxing.
  - Voice cannot be used to bypass Sentinel approvals: an operator passphrase must always be entered on POCO for consequential actions.

---

## 8. Offline Behavior & Local Network Boundaries

- **Zero Cloud Traffic:** ÆONIX PRISM operates completely offline without internet connectivity.
- **Network Isolation:** No external telemetry or cloud API calls are made. If your home router loses WAN connectivity, all core features (local missions, TV HUD, voice transcription, storage vault) remain 100% operational over the local Wi-Fi LAN.
- **Router Port Forwarding:** Never forward port 8080 on your home router. The system is engineered strictly for local LAN isolation.

---

## 9. Backup & Disaster Recovery

### Creating an Atomic Backup
Online backups are authenticated and encrypted using `AES-256-GCM`:
```bash
python3 -c "
from aeonix.core.backup import create_vault_backup
archive_path, checksum = create_vault_backup(note='Manual pre-update backup')
print(f'Backup archive created at {archive_path}')
"
```

### Performing an Isolated Restoration Drill
To verify backup recoverability without overwriting the live database:
```bash
python3 -c "
from aeonix.core.backup import verify_backup
res = verify_backup('<PATH_TO_ARCHIVE_TAR_GZ>', recovery_passphrase='<YOUR_PASSPHRASE>')
print('Integrity status:', res['valid'])
"
```

---

## 10. Recovery-Key Loss Warning

> [!CAUTION]
> **PERMANENT DATA LOSS RISK:**  
> The Recovery Vault uses military-grade **AES-256-GCM** encryption with PBKDF2 key derivation (100,000 iterations). There are **no backdoors, master resets, or cloud password recovery mechanisms**. If you lose your recovery passphrase, your encrypted backup archives are mathematically irrecoverable. Store your passphrase in a secure physical location.

---

## 11. Security Boundaries & Threat Model

1. **POCO Sovereign Authority:** Only the POCO device possesses write access to authorization tokens. The Fire TV is an unprivileged display client.
2. **Deterministic Sentinel Rule Engine:** Actions with risk classes R2 and R3 require human operator confirmation and cryptographic digest verification.
3. **Single-Use Authorization Nonces:** Approval tokens cannot be reused or replayed; each execution order nonce is invalidated immediately upon consumption.
4. **Rate-Limiting & Lockout:** 5 consecutive incorrect passphrase attempts lock the operator console for an exponentially increasing cooldown period (persistent across restarts).

---

## 12. Known Limitations

1. **Startup UI Jank:** During initial launch of `com.aether.launcher` on Fire TV, layout inflation of 147 native Leanback views takes 46ms–300ms per frame for the first 26 frames before settling to 60fps steady state.
2. **Single-Device POCO Storage Risk:** Local backups stored on the POCO filesystem protect against software corruption, but do not protect against physical destruction or loss of the phone handset without external off-device replication.
3. **Low-Memory Guarding:** Running large background apps alongside Termux on POCO may cause Android OOM-killer to terminate background processes; ensure Termux wake-lock is acquired.

---

## 13. Update & Maintenance Procedure

1. Before updating, create an encrypted backup using `create_vault_backup()`.
2. Inspect `git status` to ensure a clean working tree.
3. Fetch signed release tags:
   ```bash
   cd ~/aeonix-prism
   git pull --ff-only origin main
   ```
4. Run the portable test suite to verify baseline integrity:
   ```bash
   python3 scripts/run_portable_test_suite.py
   ```
5. Restart the daemon with `bash scripts/start-core.sh`.

---

## 14. Support & Diagnostic Bundle Redaction Rules

When collecting logs or diagnostics for support or GitHub issue reporting:

1. **Automated Redaction:** Never include `.aeonix/secrets/`, `*.pem`, `*.key`, or `master_key.json`.
2. **Bearer Token Scrubbing:** Ensure all HTTP headers in logs (`Authorization: Bearer ...`) are redacted.
3. **Database Privacy:** Do not share `aeonix_vault.db` or unencrypted `.db` snapshots; use only scrubbed statistical outputs (`test_run_artifact.json` or `sqlite3 .schema`).
4. **Network IP Redaction:** Redact external IP addresses, gateway MAC addresses, and Wi-Fi BSSIDs before posting diagnostic logs.
