"""
ÆONIX PRISM // Sovereign POCO Operator Review Console & Local Gate Authority
Local-only terminal review interface for POCO Core Mind.
Enforces:
1. First-run local operator passphrase setup (no default or agent-selected credentials).
2. PBKDF2-HMAC-SHA256 password hashing with 600,000 iterations & 32-byte salt.
3. Persistent rate-limiting and exponential lockout state across process restarts.
4. Transparent review card display (exact action, target, arguments, cwd, action digest, expiry).
5. Cryptographic Action Digest binding before approval resolution.
6. Zero generic network endpoints: approval requires physical local operator review.

SECURITY NOTICE & STATED LIMITATION:
This PIN/passphrase challenge is an application-level control running within Termux to prevent
accidental remote triggers or unauthorized hands on an unlocked phone. Because all processes within
Termux share the identical Linux UID, processes in the same UID can read memory or files directly.
It does NOT constitute a hardware-backed TEE or SELinux boundary. Hardware-backed operator
authentication is slated for the native Android companion app.
"""

import os
import sys
import json
import time
import hmac
import hashlib
import secrets
import getpass
import sqlite3
import fcntl
from typing import Dict, Any, Optional, Tuple, List

from aeonix.core.db import (
    DB_PATH,
    get_db_path,
    get_connection, 
    resolve_sentinel_request, 
    log_audit_event,
    revoke_token
)
from aeonix.core.auth import SECRETS_DIR, get_secrets_dir, ROLE_POCO_CORE

def _s_dir(secrets_dir: Optional[str] = None) -> str:
    return secrets_dir or get_secrets_dir()

def _d_path(db_path: Optional[str] = None) -> str:
    return db_path or get_db_path()

OPERATOR_PIN_FILE = os.path.join(SECRETS_DIR, "operator_pin.json")
OPERATOR_LOCKOUT_FILE = os.path.join(SECRETS_DIR, "operator_lockout.json")

# KDF Parameters: measured appropriate for Dimensity 810
PBKDF2_ITERATIONS = 600_000
MIN_PASSPHRASE_LEN = 8


def _ensure_secrets_dir(secrets_dir: Optional[str] = None):
    os.makedirs(_s_dir(secrets_dir), mode=0o700, exist_ok=True)


def _atomic_write_json(file_path: str, data: Dict[str, Any]):
    """Atomically writes JSON payload using temporary file replacement and fsync."""
    dir_name = os.path.dirname(file_path)
    if dir_name:
        os.makedirs(dir_name, mode=0o700, exist_ok=True)
    tmp_path = f"{file_path}.tmp_{os.getpid()}_{secrets.token_hex(4)}"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, file_path)


def is_operator_setup(secrets_dir: Optional[str] = None) -> bool:
    """Returns True if operator passphrase has been configured."""
    s_dir = _s_dir(secrets_dir)
    pin_file = os.path.join(s_dir, "operator_pin.json")
    return os.path.exists(pin_file) and os.path.getsize(pin_file) > 0


def is_operator_locked(secrets_dir: Optional[str] = None) -> Tuple[bool, float, int]:
    """
    Checks persistent lockout state.
    FAIL-CLOSED: If the lockout file exists but cannot be parsed or read,
    locks out the console by default (300s, 999 attempts).
    Returns (is_locked: bool, remaining_seconds: float, failed_attempts: int).
    """
    s_dir = _s_dir(secrets_dir)
    lock_file = os.path.join(s_dir, "operator_lockout.json")
    if not os.path.exists(lock_file):
        return False, 0.0, 0

    try:
        with open(lock_file, "r") as f:
            data = json.load(f)
        now = time.time()
        lockout_until = data.get("lockout_until", 0.0)
        failed_attempts = data.get("failed_attempts", 0)

        if now < lockout_until:
            return True, round(lockout_until - now, 1), failed_attempts
        return False, 0.0, failed_attempts
    except Exception:
        # FAIL-CLOSED: Malformed, corrupted, or unreadable lock file must enforce lockout
        return True, 300.0, 999


class ResetResult(dict):
    """Verifiable structured reset result supporting both dict access and tuple unpacking."""
    @property
    def success(self) -> bool:
        return bool(self.get("success", False))

    def __iter__(self):
        yield self.get("success", False)
        yield self.get("message") or self.get("error", "")


def record_failed_attempt(secrets_dir: Optional[str] = None) -> Tuple[bool, float, int]:
    """
    Records a failed passphrase attempt and updates persistent lockout state atomically and concurrency-safely.
    """
    s_dir = _s_dir(secrets_dir)
    _ensure_secrets_dir(s_dir)
    lock_file = os.path.join(s_dir, "operator_lockout.json")
    mutex_file = os.path.join(s_dir, ".lockout.lock")
    now = time.time()
    failed_attempts = 1
    lockout_duration = 0.0

    with open(mutex_file, "a") as m_fd:
        fcntl.flock(m_fd.fileno(), fcntl.LOCK_EX)
        try:
            if os.path.exists(lock_file):
                try:
                    with open(lock_file, "r") as f:
                        data = json.load(f)
                    failed_attempts = data.get("failed_attempts", 0) + 1
                except Exception:
                    # If corrupted, jump to maximum lockout
                    failed_attempts = 7

            # Exponential lockout schedule: 3 attempts -> 30s, 5 attempts -> 60s, 7+ attempts -> 300s
            if failed_attempts >= 7:
                lockout_duration = 300.0
            elif failed_attempts >= 5:
                lockout_duration = 60.0
            elif failed_attempts >= 3:
                lockout_duration = 30.0

            lockout_until = now + lockout_duration if lockout_duration > 0 else 0.0

            _atomic_write_json(lock_file, {
                "failed_attempts": failed_attempts,
                "lockout_until": lockout_until,
                "last_attempt_at": now
            })
        finally:
            fcntl.flock(m_fd.fileno(), fcntl.LOCK_UN)

    return (lockout_duration > 0), lockout_duration, failed_attempts


def reset_lockout_state(secrets_dir: Optional[str] = None):
    """Resets persistent lockout counter upon successful authentication concurrency-safely."""
    s_dir = _s_dir(secrets_dir)
    lock_file = os.path.join(s_dir, "operator_lockout.json")
    mutex_file = os.path.join(s_dir, ".lockout.lock")
    if os.path.exists(lock_file):
        try:
            with open(mutex_file, "a") as m_fd:
                fcntl.flock(m_fd.fileno(), fcntl.LOCK_EX)
                try:
                    _atomic_write_json(lock_file, {
                        "failed_attempts": 0, 
                        "lockout_until": 0.0, 
                        "last_attempt_at": time.time()
                    })
                finally:
                    fcntl.flock(m_fd.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass


def reset_operator_credentials(
    secrets_dir: Optional[str] = None, 
    confirm: bool = False, 
    db_path: Optional[str] = None
) -> ResetResult:
    """
    Deliberate physical operator reset procedure.
    Requires explicit confirm=True.
    Invalidates stored PIN/hash, resets lockout state, and revokes operator sessions.
    Returns verifiable ResetResult with revoked nonces list, count, and audit event hash.
    """
    if not confirm:
        return ResetResult({
            "success": False,
            "error": "CONFIRMATION_REQUIRED: Deliberate local operator action required (confirm=True)."
        })

    s_dir = _s_dir(secrets_dir)
    d_path = _d_path(db_path)
    pin_file = os.path.join(s_dir, "operator_pin.json")
    lock_file = os.path.join(s_dir, "operator_lockout.json")

    pin_removed = False
    lockout_cleared = False

    if os.path.exists(pin_file):
        try:
            os.remove(pin_file)
            pin_removed = True
        except Exception as e:
            return ResetResult({"success": False, "error": f"FAILED_TO_REMOVE_PIN: {str(e)}"})

    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
            lockout_cleared = True
        except Exception:
            pass

    # Revoke operator and pairing tokens in DB and collect nonces
    revoked_nonces = []
    try:
        import base64
        for f in os.listdir(s_dir):
            if f.startswith("token_") and f.endswith(".json"):
                t_path = os.path.join(s_dir, f)
                try:
                    with open(t_path, "r") as tf:
                        data = json.load(tf)
                    token_str = data.get("token", "")
                    if token_str and "." in token_str:
                        payload_b64 = token_str.split(".", 1)[0]
                        rem = len(payload_b64) % 4
                        if rem > 0:
                            payload_b64 += "=" * (4 - rem)
                        raw_payload = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
                        payload = json.loads(raw_payload.decode("utf-8"))
                        nonce = payload.get("nonce")
                        if nonce:
                            revoke_token(nonce, reason="operator_credentials_reset", db_path=d_path)
                            revoked_nonces.append(nonce)
                    os.remove(t_path)
                except Exception:
                    pass
    except Exception:
        pass

    audit_hash = log_audit_event(
        actor="OPERATOR",
        action="reset_operator_credentials",
        target="operator_console",
        result="ok",
        details={
            "reason": "deliberate_physical_reset",
            "revoked_tokens_count": len(revoked_nonces),
            "revoked_nonces": revoked_nonces
        },
        db_path=d_path,
        allow_maintenance=True
    )

    return ResetResult({
        "success": True,
        "message": "RESET_SUCCESSFUL: Operator credentials reset. Console returned to first-run setup state.",
        "revoked_tokens_count": len(revoked_nonces),
        "revoked_nonces": revoked_nonces,
        "audit_hash": audit_hash,
        "pin_removed": pin_removed,
        "lockout_cleared": lockout_cleared
    })


def setup_operator_secret(passphrase: str, secrets_dir: Optional[str] = None) -> Tuple[bool, str]:
    """
    Sets up the sovereign operator passphrase on first run.
    Mandates minimum length and generates fresh random 32-byte salt with PBKDF2-HMAC-SHA256.
    """
    if len(passphrase) < MIN_PASSPHRASE_LEN:
        return False, f"Passphrase too short: minimum {MIN_PASSPHRASE_LEN} characters required"

    s_dir = _s_dir(secrets_dir)
    _ensure_secrets_dir(s_dir)
    pin_file = os.path.join(s_dir, "operator_pin.json")
    if os.path.exists(pin_file):
        return False, "Operator passphrase already configured. Use reset procedure with recovery key to modify."

    salt = secrets.token_bytes(32)
    h = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, PBKDF2_ITERATIONS)

    payload = {
        "version": 1,
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": PBKDF2_ITERATIONS,
        "salt_hex": salt.hex(),
        "hash_hex": h.hex(),
        "created_at": time.time()
    }
    _atomic_write_json(pin_file, payload)

    log_audit_event("OPERATOR", "setup_secret", "operator_console", "ok", {"iterations": PBKDF2_ITERATIONS})
    return True, "Operator passphrase initialized successfully"


def verify_operator_secret(passphrase: str, secrets_dir: Optional[str] = None) -> Tuple[bool, str]:
    """
    Verifies operator passphrase against stored PBKDF2 hash.
    Enforces persistent lockout check and rate limiting.
    """
    s_dir = _s_dir(secrets_dir)
    pin_file = os.path.join(s_dir, "operator_pin.json")
    if not os.path.exists(pin_file):
        return False, "NOT_INITIALIZED: Operator passphrase has not been set up"

    is_locked, remaining_s, attempts = is_operator_locked(s_dir)
    if is_locked:
        return False, f"LOCKED_OUT: Operator console locked for remaining {remaining_s}s (Restarting console does not bypass lockout)"

    try:
        with open(pin_file, "r") as f:
            data = json.load(f)

        salt = bytes.fromhex(data["salt_hex"])
        expected_hash = bytes.fromhex(data["hash_hex"])
        iterations = data.get("iterations", PBKDF2_ITERATIONS)

        actual_hash = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations)

        if hmac.compare_digest(expected_hash, actual_hash):
            reset_lockout_state(s_dir)
            return True, "AUTHENTICATED"
        else:
            is_now_locked, lock_dur, total_attempts = record_failed_attempt(s_dir)
            if is_now_locked:
                return False, f"INCORRECT_SECRET: Account locked out for {lock_dur}s ({total_attempts} failed attempts)"
            return False, f"INCORRECT_SECRET: Authentication failed ({total_attempts} failed attempts)"
    except Exception as e:
        return False, f"INTERNAL_ERROR: {str(e)}"


def compute_action_digest(
    request_id: str,
    agent: str,
    action_type: str,
    target: str,
    scope: Dict[str, Any]
) -> str:
    """
    Derives deterministic cryptographic SHA-256 digest binding exact execution parameters.
    """
    scope_canonical = json.dumps(scope, sort_keys=True)
    canonical_payload = f"{request_id}|{agent}|{action_type}|{target}|{scope_canonical}"
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def get_pending_sentinel_requests(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches currently pending unexpired Sentinel requests."""
    conn = get_connection(_d_path(db_path))
    cur = conn.cursor()
    now = time.time()
    cur.execute("""
        SELECT * FROM sentinel_requests 
        WHERE status = 'pending' AND expires_at > ?
        ORDER BY created_at ASC;
    """, (now,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def format_sentinel_card(req: Dict[str, Any]) -> str:
    """Formats an exhaustive operator terminal review card."""
    now = time.time()
    ttl_remaining = max(0, int(req["expires_at"] - now))
    scope = {}
    try:
        scope = json.loads(req.get("scope_json", "{}"))
    except Exception:
        pass

    action_digest = compute_action_digest(
        req["id"],
        req["agent"],
        req["action_type"],
        req["target"],
        scope
    )

    card = [
        "=" * 76,
        "🛡️  ÆONIX PRISM // SOVEREIGN OPERATOR SENTINEL CONSOLE",
        "=" * 76,
        f"Request ID:        {req['id']}",
        f"Requesting Agent:  {req['agent']}",
        f"Action Class:      {req['action_class']}",
        f"Risk Level:        {req['risk_level']}",
        f"Action Type:       {req['action_type']}",
        f"Exact Target:      {req['target']}",
        f"Working Dir (cwd): {scope.get('cwd', 'N/A')}",
        f"Command Arguments: {scope.get('extra_args', [])}",
        f"Action Digest:     {action_digest} (SHA-256)",
        f"External Egress:   {scope.get('network_egress', 'NONE (Local Only)')}",
        f"Expiry / TTL:      Expires in {ttl_remaining}s (No automatic elevation)",
        f"Recovery Limits:   Pre-action snapshot required for persistent DB/file changes",
        "=" * 76,
        "Review Options:",
        "  [A] Approve action (requires sovereign operator passphrase confirmation)",
        "  [D] Deny / Cancel action permanently",
        "  [S] Skip for now",
        "  [Q] Quit console",
        "=" * 76
    ]
    return "\n".join(card)


def review_and_resolve_order(
    req_id: str,
    approved: bool,
    passphrase: Optional[str] = None,
    expected_action_digest: Optional[str] = None,
    secrets_dir: Optional[str] = None,
    db_path: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Validates operator passphrase and resolves the Sentinel request.
    Approved=True strictly requires successful passphrase validation.
    Enforces displayed-digest-to-approved-record binding.
    """
    s_dir = _s_dir(secrets_dir)
    d_path = _d_path(db_path)
    if approved:
        if not passphrase:
            return False, "PASSPHRASE_REQUIRED: Approval requires operator passphrase"
        is_valid, msg = verify_operator_secret(passphrase, secrets_dir=s_dir)
        if not is_valid:
            return False, f"OPERATOR_AUTH_FAILED: {msg}"

    ok, reason = resolve_sentinel_request(
        req_id=req_id,
        approved=approved,
        resolver="Sovereign_Operator_Console",
        resolver_role=ROLE_POCO_CORE,
        passphrase_verified=True if approved else False,
        expected_action_digest=expected_action_digest,
        db_path=d_path
    )
    return ok, reason


def run_interactive_console():
    """Interactive loop for POCO local terminal."""
    print("=" * 76)
    print("ÆONIX PRISM Sovereign Operator Review Console (Termux Local Gateway)")
    print("Security: Application-level review boundary for POCO Core Mind.")
    print("=" * 76)

    # First-run setup check
    if not is_operator_setup():
        print("\n[!] FIRST RUN: Operator Passphrase Setup Required")
        print("Please configure your private operator passphrase.")
        print(f"Minimum length: {MIN_PASSPHRASE_LEN} characters.")
        p1 = getpass.getpass("Enter new operator passphrase: ")
        p2 = getpass.getpass("Confirm operator passphrase: ")
        if p1 != p2:
            print("[-] Error: Passphrases do not match. Aborting.")
            sys.exit(1)
        ok, msg = setup_operator_secret(p1)
        if not ok:
            print(f"[-] Setup failed: {msg}")
            sys.exit(1)
        print("[+] Operator passphrase configured successfully.\n")

    # Lockout check
    is_locked, rem_s, attempts = is_operator_locked()
    if is_locked:
        print(f"[!] CONSOLE LOCKED: Too many failed attempts. Lockout active for {rem_s}s.")
        sys.exit(1)

    pending = get_pending_sentinel_requests()
    if not pending:
        print("[*] No pending Sentinel Gate requests awaiting approval.")
        print("[*] Listening for incoming mission execution orders. Press Ctrl+C to exit.")
        while True:
            time.sleep(2.0)
            pending = get_pending_sentinel_requests()
            if pending:
                break

    for req in pending:
        print("\n" + format_sentinel_card(req))
        choice = input("Select option [A/D/S/Q]: ").strip().upper()
        if choice == "Q":
            print("Exiting console.")
            break
        elif choice == "D":
            ok, reason = review_and_resolve_order(req["id"], approved=False)
            print(f"[*] Order {req['id']} Denied: {reason}")
        elif choice == "A":
            pwd = getpass.getpass("Enter operator passphrase to approve: ")
            req_digest = req.get("action_digest")
            if not req_digest:
                try:
                    sc = json.loads(req.get("scope_json", "{}"))
                except Exception:
                    sc = {}
                req_digest = compute_action_digest(req["id"], req["agent"], req["action_type"], req["target"], sc)
            ok, reason = review_and_resolve_order(req["id"], approved=True, passphrase=pwd, expected_action_digest=req_digest)
            if ok:
                print(f"[+] Order {req['id']} Approved successfully: {reason}")
            else:
                print(f"[-] Approval rejected: {reason}")
        elif choice == "S":
            print(f"[*] Order {req['id']} skipped.")


if __name__ == "__main__":
    run_interactive_console()
