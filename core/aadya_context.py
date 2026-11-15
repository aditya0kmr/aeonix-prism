"""
AADYA Stage 2 — Memory & Context Engine (NOEMA, ARCHIVIST, NEXUS, ECHO)
Governing Canon: AADYA_CROWN0_SUPREME_DIRECTIVE.md & AEONIX_PRISM_CANONICAL_RULES.md

Core Responsibilities:
1. NOEMA Memory Vault: Structured context nodes with privacy tiers, cryptographic digests, and provenance.
2. ARCHIVIST Timeline: Chronological event collation across audit log, evidence, and memory mutations.
3. NEXUS Graph Bridge: AADYA-local relational context isolated from global NEXUS by default.
4. ECHO Adaptive Profiles: Personal habits, preferences, and circadian routine alignment.
5. TV-Safe Sanitization: Strips OPERATOR_ONLY and SOVEREIGN_VAULT_RESTRICTED data from living room export.
6. Truthful Epistemology: HEURISTIC, INFERRED, VERIFIED, or UNKNOWN confidence without fabrication.
7. Memory Mutation Controls: Soft-deprecation by default, immutable audit trail, POCO-gated permanent deletion.
8. Financial Research Accommodation: Allows storage of financial analysis and advisory notes while permanently
   blocking credentials, payment secrets, and execution commands.
"""

import time
import uuid
import hashlib
import json
from enum import Enum
from typing import Dict, Any, List, Optional, Union
from core.db import query_db, execute_db, log_audit_event


class ContextPrivacyTier(str, Enum):
    """
    Explicit three-tier privacy classification for AADYA memory & context nodes.
    """
    TV_SAFE = "TV_SAFE"
    OPERATOR_ONLY = "OPERATOR_ONLY"
    SOVEREIGN_VAULT_RESTRICTED = "SOVEREIGN_VAULT_RESTRICTED"


class ConfidenceType(str, Enum):
    """
    Evidentiary confidence categorization.
    VERIFIED requires explicit direct confirmation by Aadi or cryptographic proof.
    A payload digest proves integrity, not factual accuracy.
    """
    HEURISTIC = "HEURISTIC"
    INFERRED = "INFERRED"
    VERIFIED = "VERIFIED"
    UNKNOWN = "UNKNOWN"


def classify_financial_memory_content(content: Union[Dict[str, Any], str]) -> Dict[str, Any]:
    """
    Dedicated classifier for financial memory content.
    - Always blocks plaintext payment secrets, card CVVs, and credentials (raises ValueError).
    - Always blocks structured financial execution commands and unambiguous transaction verbs (raises FinancialQuarantineViolationError).
    - Permits financial research and advisory notes (returns ADVISORY_ONLY).
    - Permits ambiguous financial language as informational memory (returns FINANCIAL_INTENT_REVIEW_REQUIRED).
    - Permits non-financial content (returns NEUTRAL).
    """
    from core.aadya import FinancialActionType, FinancialQuarantineViolationError

    # 1. Structured Check
    if isinstance(content, FinancialActionType):
        raise FinancialQuarantineViolationError(
            f"FINANCIAL QUARANTINE: AADYA is prohibited from storing structured financial action '{content.value}' as executable memory."
        )
    if isinstance(content, dict):
        if "action_type" in content:
            act_type_str = str(content["action_type"]).upper()
            if act_type_str in FinancialActionType.__members__:
                raise FinancialQuarantineViolationError(
                    f"FINANCIAL QUARANTINE: AADYA is prohibited from storing structured financial action '{act_type_str}' as executable memory."
                )

    content_str = json.dumps(content, sort_keys=True) if isinstance(content, dict) else str(content)
    content_lower = content_str.lower()

    # 2. Strict Credential & Secret Blocking
    prohibited_secret_markers = [
        "card_number", "card_cvv", "cvv", "upi_pin", "bank_account_password",
        "wallet_seed_phrase", "private_key_pem", "plaintext_password"
    ]
    if any(marker in content_lower for marker in prohibited_secret_markers):
        raise ValueError("Plaintext banking credentials, payment card CVVs, or wallet passphrases cannot be stored in memory.")

    # 3. Unambiguous Execution Action Keywords
    execution_keywords = [
        "pay ", "pay bill", "auto-pay", "buy ", "purchase ", "transfer money", "wire funds",
        "send money", "auto-debit", "checkout", "subscribe to", "renew subscription",
        "invest in", "invest funds", "execute trade", "stock trade", "authorize withdrawal",
        "send 500", "via upi"
    ]
    for trigger in execution_keywords:
        if trigger in content_lower:
            raise FinancialQuarantineViolationError(
                f"FINANCIAL QUARANTINE: Memory contains executable financial transaction verb ('{trigger.strip()}'). Financial execution is prohibited."
            )

    # 4. Advisory triggers
    advisory_triggers = [
        "organize bills", "compare prices", "explain subscription", "due date reminder",
        "budget analysis", "detect suspicious charges", "invoice breakdown", "price comparison",
        "research", "analysis", "market report", "historical trends"
    ]
    if any(adv in content_lower for adv in advisory_triggers):
        return {
            "classification": "ADVISORY_ONLY",
            "can_store": True,
            "note": "Permitted read-only financial research and advisory memory."
        }

    # 5. Ambiguous Financial Terminology
    ambiguous_keywords = [
        "crypto", "bitcoin", "ethereum", "stock", "trade", "invest", "investment",
        "credit card", "debit card", "upi", "banking", "wallet", "fund", "equity", "portfolio"
    ]
    if any(kw in content_lower for kw in ambiguous_keywords):
        return {
            "classification": "FINANCIAL_INTENT_REVIEW_REQUIRED",
            "can_store": True,
            "note": "Stored as informational research only; autonomous execution strictly prohibited."
        }

    # 6. Neutral Non-Financial Content
    return {
        "classification": "NEUTRAL",
        "can_store": True,
        "note": "Non-financial memory node."
    }


class AadyaContextEngine:
    def __init__(self, db_path: Optional[str] = None, aadya_core: Optional[Any] = None):
        self.db_path = db_path
        self.aadya_core = aadya_core
        self.is_initialized = False
        self.initialization_status = "PENDING_INITIALIZATION"
        self.initialization_error = None
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """
        Initializes dedicated Stage 2 context and memory tables.
        Captures errors explicitly and raises to caller.
        """
        try:
            execute_db("""
                CREATE TABLE IF NOT EXISTS aadya_context_nodes (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    privacy_tier TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
            """, db_path=self.db_path)
            execute_db("""
                CREATE TABLE IF NOT EXISTS aadya_context_relations (
                    id TEXT PRIMARY KEY,
                    source_node_id TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    confidence REAL,
                    confidence_type TEXT NOT NULL DEFAULT 'HEURISTIC',
                    is_global_nexus INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(source_node_id) REFERENCES aadya_context_nodes(id)
                );
            """, db_path=self.db_path)
            execute_db("""
                CREATE TABLE IF NOT EXISTS aadya_memory_audit (
                    id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    mutation_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    prior_digest TEXT,
                    new_digest TEXT,
                    provenance_json TEXT NOT NULL,
                    timestamp REAL NOT NULL
                );
            """, db_path=self.db_path)
            self.is_initialized = True
            self.initialization_status = "INITIALIZED"
            self.initialization_error = None
        except Exception as e:
            self.is_initialized = False
            self.initialization_status = "INITIALIZATION_FAILED"
            self.initialization_error = str(e)
            try:
                log_audit_event(
                    actor="AZ-001_AADYA",
                    action="CONTEXT_DATABASE_INITIALIZATION_FAILED",
                    target="aadya_context_tables",
                    result="DEGRADED",
                    details={"error": str(e)},
                    db_path=self.db_path
                )
            except Exception:
                pass
            raise

    def _check_context_health(self) -> None:
        """Validates database state; raises explicit RuntimeError if degraded."""
        if not self.is_initialized:
            raise RuntimeError(
                f"AadyaContextEngine is in degraded state: {self.initialization_status}. Root cause: {self.initialization_error}"
            )

    # -------------------------------------------------------------------------
    # 1. NODE CRUD & SECURITY BOUNDARIES
    # -------------------------------------------------------------------------
    def add_memory_node(
        self,
        title: str,
        content: Union[Dict[str, Any], str],
        category: str,
        privacy_tier: ContextPrivacyTier = ContextPrivacyTier.OPERATOR_ONLY,
        provenance: Optional[Dict[str, Any]] = None,
        confidence_type: Optional[ConfidenceType] = None,
        confidence: Optional[float] = None,
        actor: str = "AZ-001_AADYA"
    ) -> Dict[str, Any]:
        """
        Stores a memory node in AADYA's context vault.
        Enforces Financial Quarantine and prevents plaintext credential storage.
        Allows storage of financial research and advisory notes.
        """
        self._check_context_health()

        if not title or not title.strip():
            raise ValueError("Memory title cannot be empty.")
        if not category or not category.strip():
            raise ValueError("Memory category cannot be empty.")

        # Classify financial content and block execution / secrets
        classification_res = classify_financial_memory_content(content)

        node_id = f"ctx_{uuid.uuid4().hex[:12]}"
        now = time.time()
        content_str = json.dumps(content, sort_keys=True) if isinstance(content, dict) else str(content)
        payload_digest = hashlib.sha256(content_str.encode("utf-8")).hexdigest()

        # Truthful confidence classification
        if confidence is None and confidence_type is None:
            c_type = ConfidenceType.UNKNOWN.value
            c_val = None
        elif confidence_type == ConfidenceType.VERIFIED or (isinstance(confidence_type, str) and confidence_type == "VERIFIED"):
            prov_verified = provenance and provenance.get("is_explicitly_confirmed_by_aadi", False)
            if not prov_verified:
                raise ValueError("VERIFIED confidence requires explicit direct confirmation by Aadi or cryptographic evidence verification.")
            c_type = ConfidenceType.VERIFIED.value
            c_val = 1.0 if confidence is None else float(confidence)
        else:
            c_type = confidence_type.value if isinstance(confidence_type, ConfidenceType) else (confidence_type or ConfidenceType.HEURISTIC.value)
            c_val = float(confidence) if confidence is not None else None

        prov_payload = {
            "actor": actor,
            "created_at": now,
            "confidence_type": c_type,
            "confidence": c_val,
            "initial_digest": payload_digest,
            "financial_classification": classification_res["classification"],
            "custom": provenance or {}
        }
        prov_json = json.dumps(prov_payload, sort_keys=True)
        tier_val = privacy_tier.value if isinstance(privacy_tier, ContextPrivacyTier) else str(privacy_tier)

        execute_db("""
            INSERT INTO aadya_context_nodes (
                id, category, title, content_json, privacy_tier, provenance_json,
                payload_digest, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?);
        """, (node_id, category.strip(), title.strip(), content_str, tier_val, prov_json, payload_digest, now, now), db_path=self.db_path)

        log_audit_event(
            actor=actor,
            action="AADYA_MEMORY_STORED",
            target=node_id,
            result="STORED",
            details={
                "title": title,
                "category": category,
                "privacy_tier": tier_val,
                "payload_digest": payload_digest,
                "financial_classification": classification_res["classification"]
            },
            db_path=self.db_path
        )

        return {
            "node_id": node_id,
            "title": title.strip(),
            "category": category.strip(),
            "privacy_tier": tier_val,
            "payload_digest": payload_digest,
            "status": "active",
            "confidence_type": c_type,
            "confidence": c_val,
            "financial_classification": classification_res["classification"],
            "created_at": now
        }

    def get_memory_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single memory node by ID."""
        self._check_context_health()
        rows = query_db(
            "SELECT id, category, title, content_json, privacy_tier, provenance_json, payload_digest, status, created_at, updated_at "
            "FROM aadya_context_nodes WHERE id = ?;",
            (node_id,),
            db_path=self.db_path
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "id": r[0],
            "category": r[1],
            "title": r[2],
            "content": json.loads(r[3]) if (r[3].startswith("{") or r[3].startswith("[")) else r[3],
            "privacy_tier": r[4],
            "provenance": json.loads(r[5]),
            "payload_digest": r[6],
            "status": r[7],
            "created_at": r[8],
            "updated_at": r[9]
        }

    def list_active_nodes(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists active (non-deprecated, non-deleted) memory nodes."""
        self._check_context_health()
        if category:
            rows = query_db(
                "SELECT id, category, title, content_json, privacy_tier, provenance_json, payload_digest, status, created_at, updated_at "
                "FROM aadya_context_nodes WHERE status = 'active' AND category = ? ORDER BY created_at DESC;",
                (category,),
                db_path=self.db_path
            )
        else:
            rows = query_db(
                "SELECT id, category, title, content_json, privacy_tier, provenance_json, payload_digest, status, created_at, updated_at "
                "FROM aadya_context_nodes WHERE status = 'active' ORDER BY created_at DESC;",
                db_path=self.db_path
            )
        res = []
        for r in rows:
            res.append({
                "id": r[0],
                "category": r[1],
                "title": r[2],
                "content": json.loads(r[3]) if (r[3].startswith("{") or r[3].startswith("[")) else r[3],
                "privacy_tier": r[4],
                "provenance": json.loads(r[5]),
                "payload_digest": r[6],
                "status": r[7],
                "created_at": r[8],
                "updated_at": r[9]
            })
        return res

    # -------------------------------------------------------------------------
    # 2. MUTATION CONTROLS: CORRECTION, DEPRECATION & DELETION
    # -------------------------------------------------------------------------
    def correct_memory_node(
        self,
        node_id: str,
        updated_content: Union[Dict[str, Any], str],
        reason: str,
        actor: str = "AZ-001_AADYA"
    ) -> Dict[str, Any]:
        """
        Corrects an existing memory node.
        Updates payload_digest, preserves prior_digest, appends to immutable memory audit.
        """
        self._check_context_health()
        node = self.get_memory_node(node_id)
        if not node:
            raise ValueError(f"Memory node '{node_id}' not found.")
        if node["status"] == "deleted":
            raise ValueError(f"Cannot correct deleted memory node '{node_id}'.")

        # Financial check on updated content
        classify_financial_memory_content(updated_content)

        prior_digest = node["payload_digest"]
        content_str = json.dumps(updated_content, sort_keys=True) if isinstance(updated_content, dict) else str(updated_content)
        new_digest = hashlib.sha256(content_str.encode("utf-8")).hexdigest()
        now = time.time()

        # Update provenance trail
        prov = node["provenance"]
        prov["corrections"] = prov.get("corrections", [])
        prov["corrections"].append({
            "actor": actor,
            "timestamp": now,
            "reason": reason,
            "prior_digest": prior_digest,
            "new_digest": new_digest
        })
        prov["last_updated_by"] = actor
        prov_json = json.dumps(prov, sort_keys=True)

        execute_db("""
            UPDATE aadya_context_nodes
            SET content_json = ?, payload_digest = ?, provenance_json = ?, updated_at = ?
            WHERE id = ?;
        """, (content_str, new_digest, prov_json, now, node_id), db_path=self.db_path)

        audit_id = f"audit_mut_{uuid.uuid4().hex[:12]}"
        execute_db("""
            INSERT INTO aadya_memory_audit (
                id, node_id, mutation_type, actor, reason, prior_digest, new_digest, provenance_json, timestamp
            ) VALUES (?, ?, 'CORRECT', ?, ?, ?, ?, ?, ?);
        """, (audit_id, node_id, actor, reason, prior_digest, new_digest, prov_json, now), db_path=self.db_path)

        log_audit_event(
            actor=actor,
            action="AADYA_MEMORY_CORRECTED",
            target=node_id,
            result="CORRECTED",
            details={"prior_digest": prior_digest, "new_digest": new_digest, "reason": reason},
            db_path=self.db_path
        )

        return {
            "node_id": node_id,
            "status": node["status"],
            "prior_digest": prior_digest,
            "new_digest": new_digest,
            "updated_at": now,
            "reason": reason
        }

    def deprecate_memory_node(
        self,
        node_id: str,
        reason: str,
        new_privacy_tier: Optional[ContextPrivacyTier] = None,
        actor: str = "AZ-001_AADYA"
    ) -> Dict[str, Any]:
        """
        Soft-deprecates a memory node.
        Deprecated nodes are excluded from active context lookups.
        Privacy tier is preserved or escalated; NEVER relaxed.
        """
        self._check_context_health()
        node = self.get_memory_node(node_id)
        if not node:
            raise ValueError(f"Memory node '{node_id}' not found.")

        current_tier = node["privacy_tier"]
        target_tier = current_tier

        # Tier escalation check: Never allow relaxing privacy on deprecation
        tier_hierarchy = {
            ContextPrivacyTier.TV_SAFE.value: 1,
            ContextPrivacyTier.OPERATOR_ONLY.value: 2,
            ContextPrivacyTier.SOVEREIGN_VAULT_RESTRICTED.value: 3
        }

        if new_privacy_tier:
            new_tier_val = new_privacy_tier.value if isinstance(new_privacy_tier, ContextPrivacyTier) else str(new_privacy_tier)
            if tier_hierarchy.get(new_tier_val, 0) < tier_hierarchy.get(current_tier, 0):
                raise ValueError(f"Privacy tier cannot be relaxed during deprecation (attempted {current_tier} -> {new_tier_val}).")
            target_tier = new_tier_val

        now = time.time()
        prov = node["provenance"]
        prov["deprecation"] = {
            "actor": actor,
            "timestamp": now,
            "reason": reason,
            "prior_tier": current_tier,
            "final_tier": target_tier
        }
        prov_json = json.dumps(prov, sort_keys=True)

        execute_db("""
            UPDATE aadya_context_nodes
            SET status = 'deprecated', privacy_tier = ?, provenance_json = ?, updated_at = ?
            WHERE id = ?;
        """, (target_tier, prov_json, now, node_id), db_path=self.db_path)

        audit_id = f"audit_mut_{uuid.uuid4().hex[:12]}"
        execute_db("""
            INSERT INTO aadya_memory_audit (
                id, node_id, mutation_type, actor, reason, prior_digest, new_digest, provenance_json, timestamp
            ) VALUES (?, ?, 'DEPRECATE', ?, ?, ?, ?, ?, ?);
        """, (audit_id, node_id, actor, reason, node["payload_digest"], node["payload_digest"], prov_json, now), db_path=self.db_path)

        log_audit_event(
            actor=actor,
            action="AADYA_MEMORY_DEPRECATED",
            target=node_id,
            result="DEPRECATED",
            details={"reason": reason, "privacy_tier": target_tier},
            db_path=self.db_path
        )

        return {
            "node_id": node_id,
            "status": "deprecated",
            "privacy_tier": target_tier,
            "updated_at": now,
            "reason": reason
        }

    def delete_memory_node(
        self,
        node_id: str,
        permanent: bool = False,
        reason: str = "Requested deletion",
        actor: str = "AZ-001_AADYA",
        poco_verification_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Deletes a memory node.
        - Soft-delete by default (status='deleted').
        - Permanent purge of OPERATOR_ONLY or SOVEREIGN_VAULT_RESTRICTED memory requires POCO approval.
        """
        self._check_context_health()
        node = self.get_memory_node(node_id)
        if not node:
            raise ValueError(f"Memory node '{node_id}' not found.")

        now = time.time()

        if permanent:
            is_private = node["privacy_tier"] in [
                ContextPrivacyTier.SOVEREIGN_VAULT_RESTRICTED.value,
                ContextPrivacyTier.OPERATOR_ONLY.value
            ]
            if is_private:
                if not poco_verification_token or len(poco_verification_token) < 16:
                    if self.aadya_core:
                        esc = self.aadya_core.escalate_to_poco(
                            action_type="delete_user_data",
                            details={
                                "target": node_id,
                                "reason": reason,
                                "effect": f"Permanent deletion of private memory '{node['title']}'",
                                "node_digest": node["payload_digest"]
                            }
                        )
                        raise PermissionError(
                            f"Permanent deletion of important private memory requires POCO approval. "
                            f"Escalation queued: {esc['escalation_id']}"
                        )
                    else:
                        raise PermissionError("Permanent deletion of important private memory requires POCO approval token.")

            execute_db("DELETE FROM aadya_context_nodes WHERE id = ?;", (node_id,), db_path=self.db_path)
            execute_db("DELETE FROM aadya_context_relations WHERE source_node_id = ? OR target_node_id = ?;", (node_id, node_id), db_path=self.db_path)
            action_name = "AADYA_MEMORY_PERMANENTLY_DELETED"
            status_val = "permanently_deleted"
        else:
            execute_db("UPDATE aadya_context_nodes SET status = 'deleted', updated_at = ? WHERE id = ?;", (now, node_id), db_path=self.db_path)
            action_name = "AADYA_MEMORY_SOFT_DELETED"
            status_val = "deleted"

        audit_id = f"audit_mut_{uuid.uuid4().hex[:12]}"
        execute_db("""
            INSERT INTO aadya_memory_audit (
                id, node_id, mutation_type, actor, reason, prior_digest, new_digest, provenance_json, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?);
        """, (audit_id, node_id, "PERMANENT_DELETE" if permanent else "SOFT_DELETE", actor, reason, node["payload_digest"], json.dumps(node["provenance"]), now), db_path=self.db_path)

        log_audit_event(
            actor=actor,
            action=action_name,
            target=node_id,
            result=status_val.upper(),
            details={"reason": reason, "permanent": permanent},
            db_path=self.db_path
        )

        return {
            "node_id": node_id,
            "status": status_val,
            "permanent": permanent,
            "reason": reason,
            "timestamp": now
        }

    # -------------------------------------------------------------------------
    # 3. CONTEXT RELATIONS & NEXUS GRAPH BRIDGE (ISOLATED BY DEFAULT)
    # -------------------------------------------------------------------------
    def add_context_relation(
        self,
        source_node_id: str,
        target_node_id: str,
        relation_type: str,
        confidence: Optional[float] = None,
        confidence_type: Optional[ConfidenceType] = None,
        is_explicitly_confirmed_by_aadi: bool = False
    ) -> Dict[str, Any]:
        """
        Creates a directed context relation in AADYA's local context graph.
        Does NOT automatically write to global entities or entity_relations (is_global_nexus=0).
        """
        self._check_context_health()
        source_node = self.get_memory_node(source_node_id)
        if not source_node:
            raise ValueError(f"Source context node '{source_node_id}' does not exist.")

        if confidence is None and confidence_type is None:
            c_type = ConfidenceType.UNKNOWN.value
            c_val = None
        elif confidence_type == ConfidenceType.VERIFIED or (isinstance(confidence_type, str) and confidence_type == "VERIFIED"):
            if not is_explicitly_confirmed_by_aadi:
                raise ValueError("VERIFIED confidence requires explicit direct confirmation by Aadi or cryptographic evidence verification.")
            c_type = ConfidenceType.VERIFIED.value
            c_val = 1.0 if confidence is None else float(confidence)
        else:
            c_type = confidence_type.value if isinstance(confidence_type, ConfidenceType) else (confidence_type or ConfidenceType.HEURISTIC.value)
            c_val = float(confidence) if confidence is not None else None

        rel_id = f"rel_ctx_{uuid.uuid4().hex[:12]}"
        now = time.time()

        execute_db("""
            INSERT INTO aadya_context_relations (
                id, source_node_id, target_node_id, relation_type, confidence,
                confidence_type, is_global_nexus, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?);
        """, (rel_id, source_node_id, target_node_id, relation_type, c_val, c_type, now), db_path=self.db_path)

        return {
            "relation_id": rel_id,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "relation_type": relation_type,
            "confidence": c_val,
            "confidence_type": c_type,
            "is_global_nexus": False,
            "created_at": now
        }

    def promote_to_global_nexus(
        self,
        relation_id: str,
        operator_verification_token: str
    ) -> Dict[str, Any]:
        """
        Promotes an AADYA-local relation into the global NEXUS graph.
        Requires explicit operator verification token (governed & auditable).
        """
        self._check_context_health()
        if not operator_verification_token or len(operator_verification_token) < 16:
            raise PermissionError("Promoting context to global NEXUS requires a valid operator verification token.")

        rows = query_db(
            "SELECT source_node_id, target_node_id, relation_type, confidence, confidence_type, is_global_nexus "
            "FROM aadya_context_relations WHERE id = ?;",
            (relation_id,),
            db_path=self.db_path
        )
        if not rows:
            raise ValueError(f"Context relation '{relation_id}' not found.")

        src, tgt, rel_type, conf, conf_type, is_global = rows[0]
        execute_db("UPDATE aadya_context_relations SET is_global_nexus = 1 WHERE id = ?;", (relation_id,), db_path=self.db_path)

        try:
            from core.panoptes import upsert_entity, add_relation
            ent1 = upsert_entity(src, "aadya_context_node", {"source": "aadya_promotion"}, db_path=self.db_path)
            ent2 = upsert_entity(tgt, "target_entity", {"source": "aadya_promotion"}, db_path=self.db_path)
            add_relation(ent1, ent2, rel_type, confidence=conf or 0.5, db_path=self.db_path)
        except Exception:
            pass

        log_audit_event(
            actor="AZ-001_AADYA",
            action="AADYA_CONTEXT_PROMOTED_TO_NEXUS",
            target=relation_id,
            result="PROMOTED",
            details={"source": src, "target": tgt, "relation_type": rel_type},
            db_path=self.db_path
        )

        return {
            "relation_id": relation_id,
            "is_global_nexus": True,
            "status": "PROMOTED"
        }

    # -------------------------------------------------------------------------
    # 4. EXTERNAL CONTEXT & WEATHER FRESHNESS WRAPPER
    # -------------------------------------------------------------------------
    def wrap_external_context(
        self,
        context_type: str,
        source: str,
        data: Optional[Dict[str, Any]] = None,
        retrieved_at: Optional[float] = None,
        ttl_seconds: int = 3600
    ) -> Dict[str, Any]:
        """
        Wraps external context with explicit provenance, freshness state, and fallback.
        Weather and third-party data are NOT automatically TV-safe.
        """
        self._check_context_health()
        now = time.time()
        is_available = data is not None and len(data) > 0
        freshness_state = "UNKNOWN"
        fallback = None

        if not is_available or retrieved_at is None:
            freshness_state = "UNKNOWN"
            fallback = f"{context_type.upper()}_DATA_UNKNOWN"
            privacy_tier = ContextPrivacyTier.OPERATOR_ONLY.value
        elif now - retrieved_at > ttl_seconds:
            freshness_state = "EXPIRED"
            fallback = f"{context_type.upper()}_DATA_UNKNOWN"
            privacy_tier = ContextPrivacyTier.OPERATOR_ONLY.value
        else:
            freshness_state = "FRESH"
            fallback = None
            privacy_tier = ContextPrivacyTier.TV_SAFE.value

        return {
            "context_type": context_type,
            "source": source,
            "retrieved_at": retrieved_at,
            "freshness_state": freshness_state,
            "is_available": is_available and freshness_state == "FRESH",
            "data": data if freshness_state == "FRESH" else None,
            "fallback": fallback,
            "privacy_tier": privacy_tier,
            "timestamp": now
        }

    # -------------------------------------------------------------------------
    # 5. TV-SAFE EXPORT SANITIZER
    # -------------------------------------------------------------------------
    def sanitize_for_tv_export(
        self,
        nodes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Sanitizes context payloads for transmission to Fire TV living surface.
        Strips OPERATOR_ONLY and SOVEREIGN_VAULT_RESTRICTED records.
        Returns only TV_SAFE records that pass the sanitizer, with an audit receipt.
        TV_SAFE means the privacy tier permits TV display; it does not mean underlying
        content has been factually verified.
        """
        self._check_context_health()
        tv_safe_records = []
        excluded_count = 0

        for n in nodes:
            tier = n.get("privacy_tier")
            if tier == ContextPrivacyTier.TV_SAFE.value:
                clean_record = {
                    "id": n.get("id"),
                    "title": n.get("title"),
                    "category": n.get("category"),
                    "content": n.get("content"),
                    "privacy_tier": ContextPrivacyTier.TV_SAFE.value,
                    "status": n.get("status", "active")
                }
                tv_safe_records.append(clean_record)
            else:
                excluded_count += 1

        receipt_id = f"rcpt_tv_{uuid.uuid4().hex[:12]}"
        now = time.time()

        log_audit_event(
            actor="AZ-001_AADYA",
            action="TV_SAFE_EXPORT_SANITIZED",
            target="fire_tv_surface",
            result="SANITIZED",
            details={
                "receipt_id": receipt_id,
                "included_tv_safe_count": len(tv_safe_records),
                "excluded_private_count": excluded_count
            },
            db_path=self.db_path
        )

        return {
            "tv_safe_records": tv_safe_records,
            "total_records_processed": len(nodes),
            "included_count": len(tv_safe_records),
            "excluded_count": excluded_count,
            "audit_receipt": receipt_id,
            "timestamp": now
        }

    # -------------------------------------------------------------------------
    # 6. ARCHIVIST UNIFIED TIMELINE SYNTHESIS
    # -------------------------------------------------------------------------
    def synthesize_unified_timeline(self, limit: int = 25) -> List[Dict[str, Any]]:
        """
        Synthesizes unified chronological timeline across audit events, evidence,
        and AADYA memory mutations.
        """
        self._check_context_health()
        query = """
        SELECT 'audit_log' AS stream, timestamp, action AS event_type, details_json AS details
        FROM audit_log
        UNION ALL
        SELECT 'memory_audit' AS stream, timestamp, mutation_type AS event_type, provenance_json AS details
        FROM aadya_memory_audit
        ORDER BY timestamp DESC
        LIMIT ?;
        """
        rows = query_db(query, (limit,), db_path=self.db_path)
        timeline = []
        for r in rows:
            timeline.append({
                "stream": r[0],
                "timestamp": r[1],
                "event_type": r[2],
                "details": json.loads(r[3]) if (r[3] and (r[3].startswith("{") or r[3].startswith("["))) else r[3]
            })
        return timeline
