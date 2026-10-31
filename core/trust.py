"""
TRUST & CONTROL — POCO Root of Trust & Cryptographic Execution Orders
Implements:
- POCO Root of Trust attestation with persistent state
- Cryptographic Signed Execution Orders (HMAC-SHA256 signature verification & payload integrity)
- Replay attack prevention via order nonces
- Emergency Sovereign Kill Switch (persisted across restarts, halts executors)
"""

import hmac
import hashlib
import time
import json
import secrets
from typing import Dict, Any, Optional, Tuple, List

from aeonix.core.db import (
    log_audit_event, 
    get_system_state, 
    set_system_state, 
    record_order_nonce
)
from aeonix.core.auth import get_master_key, ROLE_POCO_CORE

class VerificationResult:
    """Supports both boolean evaluation self.assertTrue(res) and tuple unpacking is_valid, reason = res."""
    def __init__(self, is_valid: bool, reason: str):
        self.is_valid = bool(is_valid)
        self.reason = reason

    def __bool__(self):
        return self.is_valid

    def __iter__(self):
        return iter((self.is_valid, self.reason))

    def __getitem__(self, idx):
        return (self.is_valid, self.reason)[idx]

    def __repr__(self):
        return f"VerificationResult(is_valid={self.is_valid}, reason={self.reason!r})"

class KillSwitchResult(dict):
    """Supports both dict access (res['kill_switch']) and tuple unpacking (ok, res = ...)."""
    def __init__(self, success: bool, payload: Dict[str, Any]):
        super().__init__(payload)
        self.success = bool(success)

    def __iter__(self):
        yield self.success
        yield dict(self)

    def __bool__(self):
        return self.success

class TrustEngine:
    def __init__(self):
        pass

    def is_kill_switch_active(self) -> bool:
        """Returns True if the persistent emergency kill switch is engaged."""
        return bool(get_system_state("emergency_kill_switch", False))

    def trigger_kill_switch(self, rationale: str = "Operator emergency stop", actor_role: str = ROLE_POCO_CORE) -> Dict[str, Any]:
        """
        Emergency Sovereign Kill Switch:
        Persistently halts all background inference, cancels active orders, and locks executors.
        Persisted in SQLite database to survive process restarts.
        """
        set_system_state("emergency_kill_switch", {
            "engaged": True,
            "engaged_at": time.time(),
            "rationale": rationale,
            "role": actor_role
        })
        log_audit_event("TrustEngine", "emergency_kill_switch", "ALL_SYSTEMS", "ENGAGED", {
            "rationale": rationale,
            "actor_role": actor_role
        })
        return {
            "kill_switch": "ENGAGED",
            "state": "ALL_AGENTS_SUSPENDED",
            "rationale": rationale,
            "timestamp": time.time(),
        }

    def reset_kill_switch(self, actor_role: str = ROLE_POCO_CORE) -> KillSwitchResult:
        """
        Disengages emergency kill switch. Authorized only from POCO_CORE.
        """
        if actor_role != ROLE_POCO_CORE:
            log_audit_event("TrustEngine", "unauthorized_kill_switch_reset", "ALL_SYSTEMS", "REJECTED", {
                "actor_role": actor_role
            })
            return KillSwitchResult(False, {
                "success": False, 
                "kill_switch": "ENGAGED", 
                "error": "POCO_AUTHORITY_REQUIRED: Recovery restricted to POCO Core Mind"
            })

        set_system_state("emergency_kill_switch", False)
        log_audit_event("TrustEngine", "reset_kill_switch", "ALL_SYSTEMS", "RESTORED", {
            "actor_role": actor_role
        })
        return KillSwitchResult(True, {
            "success": True, 
            "kill_switch": "DISENGAGED", 
            "state": "NORMAL_OPERATIONS"
        })

    def generate_signed_order(
        self, 
        mission_name: str, 
        scope: List[Any], 
        target: str = "local_system",
        model: str = "NOVA_LOCAL", 
        user_verified: bool = False,
        actor_role: str = ROLE_POCO_CORE,
        ttl_seconds: int = 600
    ) -> Dict[str, Any]:
        """
        Generates an immutable POCO-signed execution order with cryptographic HMAC-SHA256.
        MANDATE: user_verified can ONLY be True if actor_role is POCO_CORE and explicit approval was obtained.
        """
        if self.is_kill_switch_active():
            raise RuntimeError("Cannot issue execution order: Emergency Kill Switch is ENGAGED")

        # Explicit verification check
        verified_flag = bool(user_verified and actor_role == ROLE_POCO_CORE)
        now = time.time()
        nonce = secrets.token_hex(16)
        params_digest = hashlib.sha256(json.dumps(scope, sort_keys=True).encode("utf-8")).hexdigest()

        payload = {
            "mission": mission_name,
            "target": target,
            "model": model,
            "user_verified": verified_flag,
            "scope": scope,
            "params_digest": params_digest,
            "nonce": nonce,
            "issued_at": round(now, 2),
            "expires_at": round(now + ttl_seconds, 2),
            "issuer": "POCO_CORE",
        }
        
        # Canonical serialization
        serialized = json.dumps(payload, sort_keys=True).encode("utf-8")
        master_key = get_master_key()
        sig = hmac.new(master_key, serialized, hashlib.sha256).hexdigest()
        payload["signature"] = f"POCO_SIGNED_HMAC_SHA256_{sig}"

        log_audit_event("TrustEngine", "issue_signed_order", mission_name, "ISSUED", {
            "nonce": nonce,
            "verified": verified_flag,
            "expires_at": payload["expires_at"]
        })
        return payload

    def verify_order(self, order: Dict[str, Any]) -> VerificationResult:
        """
        Full cryptographic verification of an execution order:
        - Validates HMAC-SHA256 signature
        - Validates issuer == 'POCO_CORE'
        - Verifies parameters digest integrity
        - Checks expiration time
        - Checks nonce for replay attack prevention
        - Checks emergency kill switch state
        """
        if self.is_kill_switch_active():
            return VerificationResult(False, "REJECTED: Emergency Kill Switch is ENGAGED")

        if not isinstance(order, dict):
            return VerificationResult(False, "INVALID_FORMAT: Order must be a dictionary")

        sig = order.get("signature", "")
        if sig.startswith("POCO_SIGNED_HMAC_SHA256_"):
            actual_sig_hex = sig.replace("POCO_SIGNED_HMAC_SHA256_", "")
        elif sig.startswith("HMAC_SHA256_"):
            actual_sig_hex = sig.replace("HMAC_SHA256_", "")
        else:
            return VerificationResult(False, "INVALID_SIGNATURE_FORMAT: Missing valid HMAC_SHA256 signature prefix")

        # Check issuer
        if order.get("issuer") != "POCO_CORE":
            return VerificationResult(False, "UNAUTHORIZED_ISSUER: Issuer must be POCO_CORE")

        now = time.time()
        if now > order.get("expires_at", 0):
            return VerificationResult(False, "ORDER_EXPIRED: Execution order TTL has expired")

        # Verify parameter digest integrity
        expected_digest = hashlib.sha256(json.dumps(order.get("scope", []), sort_keys=True).encode("utf-8")).hexdigest()
        if order.get("params_digest") != expected_digest:
            return VerificationResult(False, "TAMPERING_DETECTED: Parameters digest mismatch")

        # Construct unsigned canonical payload
        payload_copy = {k: v for k, v in order.items() if k != "signature"}
        serialized = json.dumps(payload_copy, sort_keys=True).encode("utf-8")
        master_key = get_master_key()
        expected_sig_hex = hmac.new(master_key, serialized, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(actual_sig_hex, expected_sig_hex):
            return VerificationResult(False, "CRYPTOGRAPHIC_VERIFICATION_FAILED: Signature invalid")

        # Replay prevention: check and record nonce
        nonce = order.get("nonce", "")
        if not record_order_nonce(nonce, order.get("mission", "unknown")):
            return VerificationResult(False, "REPLAY_ATTACK_DETECTED: Nonce has already been consumed")

        return VerificationResult(True, "VERIFIED_VALID")


trust = TrustEngine()
