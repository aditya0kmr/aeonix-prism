"""
ÆONIX PRISM // Sovereign Local Model Queue Manager
Enforces strict model-specific RAM guards, bounded FIFO queuing, and Sentinel security invariants:
- Bounded capacity: Max 10 queued requests.
- Bounded TTL: Requests older than 10 minutes (600s) automatically expire.
- Oldest-drop eviction when capacity is reached.
- Rejection of consequential or sensitive actions (no automatic deferred execution of approvals).
- Single-model lifecycle: pre-load check, burst execution, immediate unload.
- Explicit fallback labeling: 'qwen2.5-0.5b-fallback' only when allow_fallback=True.
- Cryptographic audit trail logging for all lifecycle events.
"""

import os
import time
import uuid
from typing import Dict, Any, List, Optional, Callable
from collections import deque

from aeonix.core.ram_guard import check_model_ram_guard, MODEL_RAM_THRESHOLDS_KB
from aeonix.core.sanctuary import is_sanctuary_active
from aeonix.core.db import log_audit_event
from aeonix.core.llama_runner import llama_runner

MAX_QUEUE_SIZE = 10
MAX_REQUEST_AGE_SECONDS = 600.0  # 10 minutes

CONSEQUENTIAL_KEYWORDS = {
    "approve", "approved", "authorization", "authorize",
    "delete", "format", "wipe", "destroy", "drop",
    "export_keys", "export keys", "reset", "shutdown",
    "lockdown override", "grant_root"
}


def is_query_consequential(text: str) -> bool:
    """Scans query text for sensitive or consequential action keywords."""
    clean = text.lower().strip()
    words = clean.split()
    for kw in CONSEQUENTIAL_KEYWORDS:
        if kw in clean:
            return True
    return False


class ModelQueueManager:
    """
    Manages local burst LLM inference requests when available RAM is constrained.
    Ensures safe, bounded execution without triggering the Android Low-Memory Killer (LMK).
    """

    def __init__(self, max_size: int = MAX_QUEUE_SIZE, max_age_seconds: float = MAX_REQUEST_AGE_SECONDS, db_path: Optional[str] = None):
        self.max_size = max_size
        self.max_age_seconds = max_age_seconds
        self.db_path = db_path
        self.queue: deque = deque()
        self.dropped_history: List[Dict[str, Any]] = []
        self.expired_history: List[Dict[str, Any]] = []
        self.completed_history: List[Dict[str, Any]] = []
        self.lockdown_halted_count = 0

    def _cleanup_expired(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Evicts requests that have exceeded their 10-minute TTL."""
        current_time = now or time.time()
        expired = []
        valid = deque()

        while self.queue:
            item = self.queue.popleft()
            if (current_time - item["created_at"]) > self.max_age_seconds:
                item["status"] = "expired"
                item["expired_at"] = current_time
                self.expired_history.append(item)
                expired.append(item)
                try:
                    log_audit_event(
                        actor=item.get("actor", "CoreMind"),
                        action="queue_item_expired",
                        target="model_queue",
                        result="evicted",
                        details={"request_id": item["id"], "age_s": round(current_time - item["created_at"], 1)},
                        db_path=self.db_path
                    )
                except Exception:
                    pass
            else:
                valid.append(item)

        self.queue = valid
        return expired

    def enqueue(
        self,
        prompt: str,
        model_tier: str = "0.5B",
        allow_fallback: bool = False,
        is_consequential: bool = False,
        actor: str = "Aadi"
    ) -> Dict[str, Any]:
        """
        Enqueues an inference request.
        Strict Safety Rule: Consequential or sensitive actions are NEVER queued for automatic execution.
        """
        now = time.time()

        # 1. Clean up any expired requests first
        self._cleanup_expired(now)

        # 2. Check for consequential or sensitive intent
        if is_consequential or is_query_consequential(prompt):
            rejection = {
                "id": f"rej_{int(now*1000)}_{uuid.uuid4().hex[:6]}",
                "status": "rejected_sensitive",
                "prompt": prompt,
                "created_at": now,
                "error": "CONSEQUENTIAL_ACTIONS_CANNOT_BE_QUEUED: Consequential or sensitive actions cannot be queued for automatic later execution. Sentinel Gate requires fresh operator passphrase verification."
            }
            try:
                log_audit_event(
                    actor=actor,
                    action="queue_consequential_rejected",
                    target="sentinel_boundary",
                    result="blocked",
                    details={"prompt": prompt, "reason": "consequential_cannot_be_queued"},
                    db_path=self.db_path
                )
            except Exception:
                pass
            return rejection

        # 3. Check for Sanctuary / Sentinel lockdown
        if is_sanctuary_active():
            try:
                log_audit_event(
                    actor=actor,
                    action="queue_lockdown_halted",
                    target="model_queue",
                    result="halted",
                    details={"reason": "sanctuary_active_at_enqueue"},
                    db_path=self.db_path
                )
            except Exception:
                pass
            return {
                "id": f"lck_{int(now*1000)}_{uuid.uuid4().hex[:6]}",
                "status": "cancelled_lockdown",
                "error": "SENTINEL_LOCKDOWN: Sanctuary mode is active. Inference queueing is suspended."
            }

        # 4. Enforce capacity limit (max 10 items) — drop oldest if full
        if len(self.queue) >= self.max_size:
            dropped = self.queue.popleft()
            dropped["status"] = "dropped"
            dropped["dropped_at"] = now
            self.dropped_history.append(dropped)
            try:
                log_audit_event(
                    actor=dropped.get("actor", "CoreMind"),
                    action="queue_item_dropped_full",
                    target="model_queue",
                    result="dropped",
                    details={"dropped_id": dropped["id"], "queue_max": self.max_size},
                    db_path=self.db_path
                )
            except Exception:
                pass

        # 5. Append new item
        req_id = f"req_{int(now*1000)}_{uuid.uuid4().hex[:6]}"
        item = {
            "id": req_id,
            "prompt": prompt,
            "model_tier": model_tier,
            "allow_fallback": bool(allow_fallback),
            "actor": actor,
            "created_at": now,
            "status": "queued"
        }
        self.queue.append(item)

        try:
            log_audit_event(
                actor=actor,
                action="queue_item_enqueued",
                target="model_queue",
                result="queued",
                details={"request_id": req_id, "model_tier": model_tier, "allow_fallback": allow_fallback},
                db_path=self.db_path
            )
        except Exception:
            pass

        return item

    def process_next(
        self,
        dry_run: bool = False,
        executor: Optional[Callable[[str, str], Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Inspects the queue and executes the next eligible request if RAM allows.
        Handles:
        - Sentinel lockdown check (halts execution immediately).
        - TTL expiration.
        - Memory threshold check.
        - Explicit fallback to 0.5B with labeling.
        - Immediate model unload.
        """
        now = time.time()

        # 1. Sentinel lockdown check
        if is_sanctuary_active():
            self.lockdown_halted_count += 1
            try:
                log_audit_event(
                    actor="CoreMind",
                    action="queue_lockdown_halted",
                    target="model_queue",
                    result="halted",
                    details={"queued_items_halted": len(self.queue)},
                    db_path=self.db_path
                )
            except Exception:
                pass
            return None

        # 2. Evict expired
        self._cleanup_expired(now)
        if not self.queue:
            return None

        # 3. Check first queued item
        item = self.queue[0]
        requested_tier = item["model_tier"]
        allow_fallback = item["allow_fallback"]

        tier_check = check_model_ram_guard(requested_tier)
        target_model = requested_tier
        fallback_applied = False

        if tier_check["is_safe"]:
            target_model = requested_tier
        elif allow_fallback:
            # Check if 0.5B tier is safe
            fallback_check = check_model_ram_guard("0.5B")
            if fallback_check["is_safe"]:
                target_model = "0.5B"
                fallback_applied = True
            else:
                # Even 0.5B is unsafe; cannot process
                return None
        else:
            # Requested model unsafe and fallback is NOT allowed: remain queued
            return None

        # Remove item from queue as it is now being processed
        self.queue.popleft()
        item["status"] = "executing"
        item["started_at"] = time.time()

        # Audit fallback if applied
        if fallback_applied:
            try:
                log_audit_event(
                    actor=item.get("actor", "CoreMind"),
                    action="queue_fallback_applied",
                    target="model_queue",
                    result="fallback",
                    details={
                        "request_id": item["id"],
                        "original_tier": requested_tier,
                        "fallback_tier": "0.5B",
                        "available_mb": tier_check["available_mb"]
                    },
                    db_path=self.db_path
                )
            except Exception:
                pass

        model_label = "qwen2.5-0.5b-fallback" if fallback_applied else f"qwen2.5-{target_model.lower()}"

        # 4. Model lifecycle: load -> infer -> unload immediately
        result_payload = {}
        if not dry_run:
            model_mode = "deep" if ("1.5" in target_model or target_model == "1.5B") else "fast"
            try:
                # Ensure clean state: stop any running model first
                llama_runner.stop_server()

                # Start selected model
                started = llama_runner.start_server(model_mode=model_mode)
                if not started:
                    item["status"] = "error"
                    item["error"] = "MODEL_LOAD_FAILED"
                    return item

                # Perform inference
                if executor:
                    result_payload = executor(item["prompt"], target_model)
                else:
                    # Default in-process completion or mock
                    result_payload = {"text": f"Response generated by {model_label}"}

            finally:
                # Immediate unload to guarantee zero persistent RAM overhead
                llama_runner.stop_server()
        else:
            result_payload = {"text": f"[DryRun] Response generated by {model_label}"}

        item["status"] = "completed"
        item["completed_at"] = time.time()
        item["model_used"] = model_label
        item["fallback_applied"] = fallback_applied
        item["result"] = result_payload
        self.completed_history.append(item)

        try:
            log_audit_event(
                actor=item.get("actor", "CoreMind"),
                action="queue_item_completed",
                target="model_queue",
                result="success",
                details={"request_id": item["id"], "model_used": model_label},
                db_path=self.db_path
            )
        except Exception:
            pass

        return item

    def cancel_all(self, reason: str = "Sentinel Lockdown") -> int:
        """Cancels all pending queued requests."""
        now = time.time()
        cancelled_count = 0
        while self.queue:
            item = self.queue.popleft()
            item["status"] = "cancelled"
            item["cancel_reason"] = reason
            item["cancelled_at"] = now
            cancelled_count += 1
            try:
                log_audit_event(
                    actor="Sentinel",
                    action="queue_item_cancelled",
                    target="model_queue",
                    result="cancelled",
                    details={"request_id": item["id"], "reason": reason},
                    db_path=self.db_path
                )
            except Exception:
                pass
        return cancelled_count

    def get_status(self) -> Dict[str, Any]:
        """Returns the full runtime status of the model queue for UI rendering."""
        now = time.time()
        self._cleanup_expired(now)

        return {
            "queued_count": len(self.queue),
            "max_size": self.max_size,
            "max_age_seconds": self.max_age_seconds,
            "dropped_count": len(self.dropped_history),
            "expired_count": len(self.expired_history),
            "completed_count": len(self.completed_history),
            "lockdown_halted_count": self.lockdown_halted_count,
            "is_sanctuary_active": is_sanctuary_active(),
            "items": [
                {
                    "id": it["id"],
                    "model_tier": it["model_tier"],
                    "allow_fallback": it["allow_fallback"],
                    "age_seconds": round(now - it["created_at"], 1),
                    "status": it["status"]
                }
                for it in self.queue
            ],
            "dropped_items": [
                {"id": it["id"], "model_tier": it["model_tier"], "dropped_at": it.get("dropped_at")}
                for it in self.dropped_history[-5:]
            ],
            "expired_items": [
                {"id": it["id"], "model_tier": it["model_tier"], "expired_at": it.get("expired_at")}
                for it in self.expired_history[-5:]
            ]
        }
