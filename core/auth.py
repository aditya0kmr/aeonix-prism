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

SECRETS_DIR = os.path.expanduser("~/.aeonix/secrets")
KEY_FILE = os.path.join(SECRETS_DIR, "master_key.json")

# Role definitions
ROLE_POCO_CORE = "POCO_CORE"
ROLE_FIRETV_GLASS = "FIRETV_GLASS"
ROLE_AGENT_EXECUTOR = "AGENT_EXECUTOR"
VALID_ROLES = {ROLE_POCO_CORE, ROLE_FIRETV_GLASS, ROLE_AGENT_EXECUTOR}

def _ensure_secrets_storage() -> bytes:
    """Ensures secret storage directory exists with strict 0o700/0o600 permissions and loads/creates master key."""
    if not os.path.exists(SECRETS_DIR):
        os.makedirs(SECRETS_DIR, mode=0o700, exist_ok=True)
    
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE, "r") as f:
                data = json.load(f)
                return base64.b64decode(data["master_secret"])
        except Exception:
            pass # Regenerate if corrupt

    # Generate fresh cryptographically secure 256-bit key
    master_secret = secrets.token_bytes(32)
    with open(KEY_FILE, "w") as f:
        json.dump({
            "created_at": time.time(),
            "master_secret": base64.b64encode(master_secret).decode("ascii"),
            "version": 1
        }, f)
    try:
        os.chmod(KEY_FILE, 0o600)
    except Exception:
        pass
    return master_secret

_MASTER_KEY = _ensure_secrets_storage()

def get_master_key() -> bytes:
    return _MASTER_KEY

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

def _b64url_decode(s: str) -> bytes:
    rem = len(s) % 4
    if rem > 0:
        s += "=" * (4 - rem)
    return base64.urlsafe_b64decode(s.encode("ascii"))

def issue_device_token(device_id: str, role: str, ttl_seconds: int = 86400 * 30) -> str:
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
    sig = hmac.new(_MASTER_KEY, raw_payload, hashlib.sha256).digest()
    
    return f"{_b64url_encode(raw_payload)}.{_b64url_encode(sig)}"

def verify_token(token_str: str) -> Optional[Dict[str, Any]]:
    """
    Cryptographically verifies a bearer token. Returns payload dict if valid, None if invalid or expired.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not token_str or "." not in token_str:
        return None

    try:
        payload_b64, sig_b64 = token_str.strip().split(".", 1)
        raw_payload = _b64url_decode(payload_b64)
        expected_sig = hmac.new(_MASTER_KEY, raw_payload, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload = json.loads(raw_payload.decode("utf-8"))
        now = time.time()
        if now > payload.get("expires_at", 0):
            return None # Expired

        # Check token revocation
        from aeonix.core.db import is_token_revoked
        if is_token_revoked(payload.get("nonce", "")):
            return None

        return payload
    except Exception:
        return None

def get_or_create_device_token(device_id: str, role: str) -> str:
    """Retrieves or issues a durable pairing token for standard sovereign infrastructure."""
    token_file = os.path.join(SECRETS_DIR, f"token_{device_id}.json")
    if os.path.exists(token_file):
        try:
            with open(token_file, "r") as f:
                data = json.load(f)
                token = data.get("token", "")
                if verify_token(token):
                    return token
        except Exception:
            pass

    token = issue_device_token(device_id, role, ttl_seconds=86400 * 365)
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
