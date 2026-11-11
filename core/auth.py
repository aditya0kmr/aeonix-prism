"""
ÆONIX PRISM // Authentication & Sovereign Device Identity Engine
Role-based cryptographic authentication for REST endpoints and WebSockets.
Eliminates unverified client-supplied identity claims.
"""

import os
import json
import time
import hmac
import hashlib
import base64
import secrets
from typing import Dict, Any, Optional, Tuple

SECRETS_DIR = os.getenv("AEONIX_SECRETS_DIR", os.path.expanduser("~/.aeonix/secrets"))
PROD_SECRETS_DIR = os.path.realpath(os.path.expanduser("~/.aeonix/secrets"))

def get_secrets_dir() -> str:
    """Returns dynamic secrets directory respecting test isolation environment variables. Refuses production paths in test mode."""
    s_dir = os.getenv("AEONIX_SECRETS_DIR", SECRETS_DIR)
    if os.getenv("AEONIX_TEST_MODE") == "1":
        real = os.path.realpath(os.path.abspath(s_dir))
        if real == PROD_SECRETS_DIR or real.startswith(PROD_SECRETS_DIR + os.sep):
            raise PermissionError(
                f"PRODUCTION_ACCESS_REFUSED_IN_TEST_MODE: Secret path '{s_dir}' resolves to production secrets directory during test execution."
            )
    return s_dir

KEY_FILE = os.path.join(SECRETS_DIR, "master_key.json")

# Role definitions
ROLE_POCO_CORE = "POCO_CORE"
ROLE_FIRETV_GLASS = "FIRETV_GLASS"
ROLE_AGENT_EXECUTOR = "AGENT_EXECUTOR"
ROLE_PTT_OPERATOR = "PTT_OPERATOR"
VALID_ROLES = {ROLE_POCO_CORE, ROLE_FIRETV_GLASS, ROLE_AGENT_EXECUTOR, ROLE_PTT_OPERATOR}

def _ensure_secrets_storage(secrets_dir: Optional[str] = None) -> bytes:
    """Ensures secret storage directory exists with strict 0o700/0o600 permissions and loads/creates master key."""
    s_dir = secrets_dir or get_secrets_dir()
    if not os.path.exists(s_dir):
        os.makedirs(s_dir, mode=0o700, exist_ok=True)
    
    key_file = os.path.join(s_dir, "master_key.json")
    if os.path.exists(key_file):
        try:
            with open(key_file, "r") as f:
                data = json.load(f)
                return base64.b64decode(data["master_secret"])
        except Exception:
            pass # Regenerate if corrupt

    # Generate fresh cryptographically secure 256-bit key
    master_secret = secrets.token_bytes(32)
    with open(key_file, "w") as f:
        json.dump({
            "created_at": time.time(),
            "master_secret": base64.b64encode(master_secret).decode("ascii"),
            "version": 1
        }, f)
    try:
        os.chmod(key_file, 0o600)
    except Exception:
        pass
    return master_secret

_MASTER_KEY = _ensure_secrets_storage()

def get_master_key(secrets_dir: Optional[str] = None) -> bytes:
    s_dir = secrets_dir or get_secrets_dir()
    if s_dir == SECRETS_DIR and _MASTER_KEY:
        return _MASTER_KEY
    return _ensure_secrets_storage(s_dir)

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

def _b64url_decode(s: str) -> bytes:
    rem = len(s) % 4
    if rem > 0:
        s += "=" * (4 - rem)
    return base64.urlsafe_b64decode(s.encode("ascii"))

def issue_device_token(device_id: str, role: str, ttl_seconds: int = 86400 * 30, secrets_dir: Optional[str] = None) -> str:
    """
    Issues a tamper-proof cryptographic bearer token bound to a verified device_id and role.
    """
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}")

    now = time.time()
    payload = {
        "device_id": device_id,
        "role": role,
        "nonce": secrets.token_hex(12),
        "issued_at": round(now, 2),
        "expires_at": round(now + ttl_seconds, 2)
    }
    raw_payload = json.dumps(payload, sort_keys=True).encode("utf-8")
    sig = hmac.new(get_master_key(secrets_dir), raw_payload, hashlib.sha256).digest()
    
    return f"{_b64url_encode(raw_payload)}.{_b64url_encode(sig)}"

def verify_token(token_str: str, secrets_dir: Optional[str] = None, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Cryptographically verifies a bearer token. Returns payload dict if valid, None if invalid or expired.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not token_str or "." not in token_str:
        return None

    try:
        payload_b64, sig_b64 = token_str.strip().split(".", 1)
        raw_payload = _b64url_decode(payload_b64)
        expected_sig = hmac.new(get_master_key(secrets_dir), raw_payload, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload = json.loads(raw_payload.decode("utf-8"))
        now = time.time()
        if now > payload.get("expires_at", 0):
            return None # Expired

        # Check token and device revocation
        from aeonix.core.db import is_token_revoked, is_device_revoked
        if is_token_revoked(payload.get("nonce", ""), db_path=db_path):
            return None
        if is_device_revoked(payload.get("device_id", ""), db_path=db_path):
            return None

        return payload
    except Exception:
        return None

def get_or_create_device_token(device_id: str, role: str, secrets_dir: Optional[str] = None) -> str:
    """Retrieves or issues a durable pairing token for standard sovereign infrastructure."""
    s_dir = secrets_dir or get_secrets_dir()
    token_file = os.path.join(s_dir, f"token_{device_id}.json")
    if os.path.exists(token_file):
        try:
            with open(token_file, "r") as f:
                data = json.load(f)
                token = data.get("token", "")
                if verify_token(token, secrets_dir=s_dir):
                    return token
        except Exception:
            pass

    token = issue_device_token(device_id, role, ttl_seconds=86400 * 365, secrets_dir=s_dir)
    with open(token_file, "w") as f:
        json.dump({"device_id": device_id, "role": role, "token": token, "created_at": time.time()}, f)
    try:
        os.chmod(token_file, 0o600)
    except Exception:
        pass
    return token

# Pre-generate durable sovereign tokens
POCO_CORE_TOKEN = get_or_create_device_token("poco_m4_pro_core", ROLE_POCO_CORE)
FIRETV_GLASS_TOKEN = get_or_create_device_token("firetv_stick_glass", ROLE_FIRETV_GLASS)

def generate_bootstrap_secret(ttl_seconds: int = 300, db_path: Optional[str] = None) -> Tuple[str, str]:
    """
    Generates a cryptographically random, 128-bit single-use bootstrap secret.
    Stores only the SHA-256 hash in the shared sovereign database.
    Invalidates any previously active bootstrap secrets.
    """
    secret = secrets.token_hex(16) # 128 bits of entropy
    code_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()

    from aeonix.core.db import create_bootstrap_record
    create_bootstrap_record(code_hash, ttl_seconds=min(ttl_seconds, 300), db_path=db_path)
    return secret, code_hash

def exchange_bootstrap_secret(secret: str, db_path: Optional[str] = None, secrets_dir: Optional[str] = None) -> Optional[str]:
    """
    Atomically exchanges a valid, unexpired single-use bootstrap secret for a short-lived ROLE_PTT_OPERATOR session token.
    Uses database-level atomic test-and-set consumption.
    Rejects missing, expired, replayed, or invalid secrets with None.
    """
    if not secret or len(secret) < 16:
        return None

    code_hash = hashlib.sha256(secret.strip().encode("utf-8")).hexdigest()

    from aeonix.core.db import consume_bootstrap_code_atomic
    consumed = consume_bootstrap_code_atomic(code_hash, db_path=db_path)
    if not consumed:
        return None

    # Issue strictly short-lived (15-min / 900s) ROLE_PTT_OPERATOR session token
    session_token = issue_device_token(
        device_id="poco_ptt_operator",
        role=ROLE_PTT_OPERATOR,
        ttl_seconds=900,
        secrets_dir=secrets_dir
    )
    return session_token

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "bootstrap":
        secret, code_hash = generate_bootstrap_secret()
        print("\n" + "=" * 60)
        print("ÆONIX PRISM // Sovereign PTT Operator Bootstrap")
        print("=" * 60)
        print(f"One-Time Bootstrap Secret: {secret}")
        print("Validity: 5 minutes (single use)")
        print("Role: PTT_OPERATOR (strictly limited to PTT endpoints)")
        print("=" * 60 + "\n")
