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
from typing import Dict, Any, Optional, Tuple, List

from aeonix.core.db import (
    DB_PATH, 
    get_connection, 
    resolve_sentinel_request, 
    log_audit_event
)
from aeonix.core.auth import SECRETS_DIR, ROLE_POCO_CORE

OPERATOR_PIN_FILE = os.path.join(SECRETS_DIR, "operator_pin.json")
OPERATOR_LOCKOUT_FILE = os.path.join(SECRETS_DIR, "operator_lockout.json")

# KDF Parameters: measured appropriate for Dimensity 810
PBKDF2_ITERATIONS = 600_000
MIN_PASSPHRASE_LEN = 8


def _ensure_secrets_dir(secrets_dir: str = SECRETS_DIR):
    os.makedirs(secrets_dir, mode=0o700, exist_ok=True)


def is_operator_setup(secrets_dir: str = SECRETS_DIR) -> bool:
    """Returns True if operator passphrase has been configured."""
    pin_file = os.path.join(secrets_dir, "operator_pin.json")
    return os.path.exists(pin_file) and os.path.getsize(pin_file) > 0


def is_operator_locked(secrets_dir: str = SECRETS_DIR) -> Tuple[bool, float, int]:
    """
    Checks persistent lockout state.
    Returns (is_locked: bool, remaining_seconds: float, failed_attempts: int).
    """
    lock_file = os.path.join(secrets_dir, "operator_lockout.json")
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
        return False, 0.0, 0


def record_failed_attempt(secrets_dir: str = SECRETS_DIR) -> Tuple[bool, float, int]:
    """
    Records a failed passphrase attempt and updates persistent lockout state.
    """
    _ensure_secrets_dir(secrets_dir)
    lock_file = os.path.join(secrets_dir, "operator_lockout.json")
    now = time.time()
    failed_attempts = 1
    lockout_duration = 0.0

    if os.path.exists(lock_file):
        try:
            with open(lock_file, "r") as f:
                data = json.load(f)
            failed_attempts = data.get("failed_attempts", 0) + 1
        except Exception:
            pass

    # Exponential lockout schedule: 3 attempts -> 30s, 5 attempts -> 60s, 7+ attempts -> 300s
    if failed_attempts >= 7:
        lockout_duration = 300.0
    elif failed_attempts >= 5:
        lockout_duration = 60.0
    elif failed_attempts >= 3:
        lockout_duration = 30.0

    lockout_until = now + lockout_duration if lockout_duration > 0 else 0.0

    with open(lock_file, "w") as f:
        json.dump({
            "failed_attempts": failed_attempts,
            "lockout_until": lockout_until,
            "last_attempt_at": now
        }, f)
    try:
        os.chmod(lock_file, 0o600)
    except Exception:
        pass

    return (lockout_duration > 0), lockout_duration, failed_attempts


def reset_lockout_state(secrets_dir: str = SECRETS_DIR):
    """Resets persistent lockout counter upon successful authentication."""
    lock_file = os.path.join(secrets_dir, "operator_lockout.json")
    if os.path.exists(lock_file):
        try:
            with open(lock_file, "w") as f:
                json.dump({"failed_attempts": 0, "lockout_until": 0.0, "last_attempt_at": time.time()}, f)
            os.chmod(lock_file, 0o600)
        except Exception:
            pass


def setup_operator_secret(passphrase: str, secrets_dir: str = SECRETS_DIR) -> Tuple[bool, str]:
    """
    Sets up the sovereign operator passphrase on first run.
    Mandates minimum length and generates fresh random 32-byte salt with PBKDF2-HMAC-SHA256.
    """
    if len(passphrase) < MIN_PASSPHRASE_LEN:
        return False, f"Passphrase too short: minimum {MIN_PASSPHRASE_LEN} characters required"

    _ensure_secrets_dir(secrets_dir)
    pin_file = os.path.join(secrets_dir, "operator_pin.json")
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
    with open(pin_file, "w") as f:
        json.dump(payload, f, indent=2)
    try:
        os.chmod(pin_file, 0o600)
    except Exception:
        pass

    log_audit_event("OPERATOR", "setup_secret", "operator_console", "ok", {"iterations": PBKDF2_ITERATIONS})
    return True, "Operator passphrase initialized successfully"


def verify_operator_secret(passphrase: str, secrets_dir: str = SECRETS_DIR) -> Tuple[bool, str]:
    """
    Verifies operator passphrase against stored PBKDF2 hash.
    Enforces persistent lockout check and rate limiting.
    """
    pin_file = os.path.join(secrets_dir, "operator_pin.json")
    if not os.path.exists(pin_file):
        return False, "NOT_INITIALIZED: Operator passphrase has not been set up"

    is_locked, remaining_s, attempts = is_operator_locked(secrets_dir)
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
            reset_lockout_state(secrets_dir)
            return True, "AUTHENTICATED"
        else:
            is_now_locked, lock_dur, total_attempts = record_failed_attempt(secrets_dir)
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


def get_pending_sentinel_requests(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Fetches currently pending unexpired Sentinel requests."""
    conn = get_connection(db_path)
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
    secrets_dir: str = SECRETS_DIR,
    db_path: str = DB_PATH
) -> Tuple[bool, str]:
    """
    Validates operator passphrase and resolves the Sentinel request.
    Approved=True strictly requires successful passphrase validation.
    """
    if approved:
        if not passphrase:
            return False, "PASSPHRASE_REQUIRED: Approval requires operator passphrase"
        is_valid, msg = verify_operator_secret(passphrase, secrets_dir=secrets_dir)
        if not is_valid:
            return False, f"OPERATOR_AUTH_FAILED: {msg}"

    ok, reason = resolve_sentinel_request(
        req_id=req_id,
        approved=approved,
        resolver="Sovereign_Operator_Console",
        resolver_role=ROLE_POCO_CORE,
        db_path=db_path
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
            ok, reason = review_and_resolve_order(req["id"], approved=True, passphrase=pwd)
            if ok:
                print(f"[+] Order {req['id']} Approved successfully: {reason}")
            else:
                print(f"[-] Approval rejected: {reason}")
        elif choice == "S":
            print(f"[*] Order {req['id']} skipped.")


if __name__ == "__main__":
    run_interactive_console()
