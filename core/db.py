import sqlite3
import os
import time
import json
import hashlib
from typing import Optional, Dict, Any, List

DB_PATH = os.getenv("AEONIX_DB_PATH", os.path.expanduser("~/aeonix/data/aeonix_vault.db"))

def get_db_path() -> str:
    """Returns dynamic database path respecting test isolation environment variables."""
    return os.getenv("AEONIX_DB_PATH", DB_PATH)

def get_connection(db_path: Optional[str] = None, allow_maintenance: bool = False) -> sqlite3.Connection:
    actual_db = db_path or get_db_path()
    if not allow_maintenance:
        maint = False
        try:
            from aeonix.core.backup import is_maintenance_mode
            maint = is_maintenance_mode()
        except ImportError:
            pass
        if maint:
            raise sqlite3.OperationalError("DATABASE_LOCKED: System is in disaster recovery maintenance mode")

    dir_name = os.path.dirname(actual_db)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    conn = sqlite3.connect(actual_db, timeout=5.0)
    conn.row_factory = sqlite3.Row
    # Anti-Corruption & High-Performance Hardening Mandates
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn

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

def get_sentinel_request_digest(req_id: str, db_path: Optional[str] = None) -> Optional[str]:
    """Retrieves the cryptographic action digest for a queued Sentinel request."""
    actual_db = db_path or get_db_path()
    conn = get_connection(actual_db, allow_maintenance=True)
    cur = conn.cursor()
    cur.execute("SELECT action_digest FROM sentinel_requests WHERE id = ?;", (req_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return row["action_digest"]
    return None

def init_database(db_path: Optional[str] = None) -> bool:
    """Initializes tables and performs integrity checks."""
    conn = get_connection(db_path, allow_maintenance=True)
    cur = conn.cursor()
    
    # Verify DB integrity first
    cur.execute("PRAGMA integrity_check;")
    check = cur.fetchone()[0]
    if check != "ok":
        raise RuntimeError(f"Database integrity check failed: {check}")

    cur.executescript("""
    -- Users table
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'sovereign',
        created_at REAL NOT NULL
    );

    -- Devices table
    CREATE TABLE IF NOT EXISTS devices (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        ip_address TEXT,
        mac_address TEXT,
        trust_level TEXT NOT NULL DEFAULT 'standard',
        last_seen REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'active'
    );

    -- NOEMA & AADYA Memory Vault
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        tags TEXT,
        created_at REAL NOT NULL,
        expires_at REAL,
        source TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    -- Tasks table
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT,
        due_date REAL,
        priority TEXT NOT NULL DEFAULT 'medium',
        status TEXT NOT NULL DEFAULT 'pending',
        project_id TEXT,
        created_at REAL NOT NULL
    );

    -- SENTINEL Authorization Queue
    CREATE TABLE IF NOT EXISTS sentinel_requests (
        id TEXT PRIMARY KEY,
        agent TEXT NOT NULL,
        action_class TEXT NOT NULL,
        action_type TEXT NOT NULL,
        target TEXT NOT NULL,
        scope_json TEXT NOT NULL,
        risk_level TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        approved_by TEXT,
        approved_at REAL,
        audit_hash TEXT,
        action_digest TEXT NOT NULL DEFAULT '',
        claimed_by TEXT,
        claimed_at REAL,
        completed_at REAL,
        output_summary TEXT,
        error_msg TEXT
    );

    -- Cryptographic Hash-Chained Audit Trail
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT NOT NULL,
        result TEXT NOT NULL,
        details_json TEXT NOT NULL,
        previous_hash TEXT NOT NULL,
        current_hash TEXT NOT NULL
    );

    -- VERITAS Cases & Evidence
    CREATE TABLE IF NOT EXISTS cases (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        legal_basis TEXT,
        created_by TEXT NOT NULL,
        created_at REAL NOT NULL,
        closed_at REAL
    );

    CREATE TABLE IF NOT EXISTS evidence (
        id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        mime_type TEXT,
        metadata_json TEXT,
        collected_at REAL NOT NULL,
        collected_by TEXT NOT NULL,
        chain_of_custody TEXT NOT NULL,
        FOREIGN KEY(case_id) REFERENCES cases(id)
    );

    -- PANOPTES Entity-Relation Graph
    CREATE TABLE IF NOT EXISTS entities (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        attributes_json TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS entity_relations (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        confidence REAL DEFAULT 1.0,
        metadata_json TEXT,
        created_at REAL NOT NULL,
        FOREIGN KEY(source_id) REFERENCES entities(id),
        FOREIGN KEY(target_id) REFERENCES entities(id)
    );

    CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
    CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
    CREATE INDEX IF NOT EXISTS idx_rel_source ON entity_relations(source_id);
    CREATE INDEX IF NOT EXISTS idx_rel_target ON entity_relations(target_id);

    -- Sovereign System State Persistence (survives process restart)
    CREATE TABLE IF NOT EXISTS system_state (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at REAL NOT NULL
    );

    -- Cryptographic Token Revocation
    CREATE TABLE IF NOT EXISTS revoked_tokens (
        nonce TEXT PRIMARY KEY,
        revoked_at REAL NOT NULL,
        reason TEXT
    );

    -- Execution Order Nonces (Replay Attack Prevention)
    CREATE TABLE IF NOT EXISTS execution_order_nonces (
        nonce TEXT PRIMARY KEY,
        mission_id TEXT NOT NULL,
        used_at REAL NOT NULL
    );

    -- Missions Persistence & State Machine
    CREATE TABLE IF NOT EXISTS missions (
        id TEXT PRIMARY KEY,
        objective TEXT NOT NULL,
        target TEXT,
        status TEXT NOT NULL DEFAULT 'running',
        current_phase INTEGER NOT NULL DEFAULT 0,
        total_phases INTEGER NOT NULL DEFAULT 0,
        plan_json TEXT NOT NULL,
        execution_log_json TEXT NOT NULL,
        report_json TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );

    -- Oracle Research & Prediction Ledger
    CREATE TABLE IF NOT EXISTS research_ledger (
        id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        confidence REAL NOT NULL,
        sources_json TEXT NOT NULL,
        findings_json TEXT NOT NULL,
        contradictions_json TEXT NOT NULL,
        prediction_json TEXT,
        created_at REAL NOT NULL
    );
    """)

    # Seed Sovereign User (Aadi) if not present
    cur.execute("SELECT id FROM users WHERE id = 'user_aadi';")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (id, name, role, created_at) VALUES (?, ?, ?, ?);",
            ("user_aadi", "Aadi", "sovereign_master", time.time())
        )

    # Seed Fire TV Device if not present
    cur.execute("SELECT id FROM devices WHERE id = 'firetv_glass';")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO devices (id, name, type, ip_address, trust_level, last_seen, status) VALUES (?, ?, ?, ?, ?, ?, ?);",
            ("firetv_glass", "Fire TV Stick Lite", "glass_terminal", "10.116.23.179", "sovereign_terminal", time.time(), "paired")
        )

    # Dynamic column migration for sentinel_requests schema
    cur.execute("PRAGMA table_info(sentinel_requests);")
    existing_cols = {row["name"] for row in cur.fetchall()}
    columns_to_add = [
        ("action_digest", "TEXT NOT NULL DEFAULT ''"),
        ("claimed_by", "TEXT"),
        ("claimed_at", "REAL"),
        ("completed_at", "REAL"),
        ("output_summary", "TEXT"),
        ("error_msg", "TEXT")
    ]
    for col_name, col_def in columns_to_add:
        if col_name not in existing_cols:
            try:
                cur.execute(f"ALTER TABLE sentinel_requests ADD COLUMN {col_name} {col_def};")
            except Exception:
                pass

    conn.commit()
    conn.close()
    return True

def log_audit_event(
    actor: str, 
    action: str, 
    target: str, 
    result: str, 
    details: Dict[str, Any], 
    db_path: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    allow_maintenance: bool = False
) -> str:
    """Appends an event to audit_log with cryptographic SHA-256 hash chaining."""
    if not allow_maintenance:
        try:
            from aeonix.core.backup import is_maintenance_mode
            if is_maintenance_mode():
                raise sqlite3.OperationalError("DATABASE_LOCKED: System is in disaster recovery maintenance mode")
        except ImportError:
            pass

    should_close = False
    if conn is None:
        conn = get_connection(db_path, allow_maintenance=allow_maintenance)
        should_close = True
        
    cur = conn.cursor()
    
    cur.execute("SELECT current_hash FROM audit_log ORDER BY id DESC LIMIT 1;")
    row = cur.fetchone()
    prev_hash = row["current_hash"] if row else "GENESIS_BLOCK_AEONIX_PRISM_v2.0"

    now = time.time()
    details_str = json.dumps(details, sort_keys=True)
    hash_payload = f"{prev_hash}|{now}|{actor}|{action}|{target}|{result}|{details_str}"
    current_hash = hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()

    cur.execute("""
        INSERT INTO audit_log (timestamp, actor, action, target, result, details_json, previous_hash, current_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, (now, actor, action, target, result, details_str, prev_hash, current_hash))

    if should_close:
        conn.commit()
        conn.close()
    return current_hash

def queue_sentinel_request(agent: str, action_class: str, action_type: str, target: str, scope: Dict[str, Any], risk_level: str, ttl_seconds: int = 300, db_path: Optional[str] = None, timeout_seconds: Optional[int] = None) -> str:
    """Enqueues a pending action for human verification (Sentinel Gate)."""
    if timeout_seconds is not None:
        ttl_seconds = int(timeout_seconds)
    conn = get_connection(db_path)
    cur = conn.cursor()
    
    req_id = f"sentinel_{int(time.time()*1000)}_{os.urandom(3).hex()}"
    now = time.time()
    expires_at = now + ttl_seconds
    scope_str = json.dumps(scope, sort_keys=True)
    action_digest = compute_action_digest(req_id, agent, action_type, target, scope)
    
    cur.execute("""
        INSERT INTO sentinel_requests (id, agent, action_class, action_type, target, scope_json, risk_level, status, created_at, expires_at, action_digest)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?);
    """, (req_id, agent, action_class, action_type, target, scope_str, risk_level, now, expires_at, action_digest))

    conn.commit()
    conn.close()

    log_audit_event(
        actor=agent,
        action="sentinel_request_created",
        target=target,
        result="queued",
        details={"request_id": req_id, "risk_level": risk_level, "action_type": action_type, "action_digest": action_digest},
        db_path=db_path
    )
    return req_id

create_sentinel_request = queue_sentinel_request

def query_db(query: str, args: tuple = (), db_path: Optional[str] = None) -> list:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(query, args)
    rows = cur.fetchall()
    conn.close()
    return rows

def execute_db(query: str, args: tuple = (), db_path: Optional[str] = None) -> int:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(query, args)
    conn.commit()
    lastrowid = cur.lastrowid
    conn.close()
    return lastrowid

def get_system_state(key: str, default: Any = None, db_path: Optional[str] = None) -> Any:
    """Retrieves persisted sovereign system state across reboots."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT value_json FROM system_state WHERE key = ?;", (key,))
    row = cur.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["value_json"])
        except Exception:
            return row["value_json"]
    return default

def set_system_state(key: str, value: Any, db_path: Optional[str] = None):
    """Persists sovereign system state across reboots."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    val_json = json.dumps(value)
    cur.execute("""
        INSERT INTO system_state (key, value_json, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at;
    """, (key, val_json, time.time()))
    conn.commit()
    conn.close()

def is_token_revoked(nonce: str, db_path: Optional[str] = None) -> bool:
    """Checks if a cryptographic token nonce has been revoked."""
    if not nonce:
        return True
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT nonce FROM revoked_tokens WHERE nonce = ?;", (nonce,))
    revoked = cur.fetchone() is not None
    conn.close()
    return revoked

def revoke_token(nonce: str, reason: str = "Operator Revocation", db_path: Optional[str] = None) -> bool:
    """Revokes a cryptographic token nonce permanently."""
    if not nonce:
        return False
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO revoked_tokens (nonce, revoked_at, reason) VALUES (?, ?, ?);",
                (nonce, time.time(), reason))
    conn.commit()
    conn.close()
    log_audit_event("SECURITY", "revoke_token", nonce, "revoked", {"reason": reason}, db_path=db_path)
    return True

def record_order_nonce(nonce: str, mission_id: str, db_path: Optional[str] = None) -> bool:
    """
    Records an execution order nonce. Returns True if recorded (nonce fresh),
    or False if nonce was already used (prevents replay attacks).
    """
    if not nonce:
        return False
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT nonce FROM execution_order_nonces WHERE nonce = ?;", (nonce,))
    if cur.fetchone():
        conn.close()
        return False # Replay detected!
    
    cur.execute("INSERT INTO execution_order_nonces (nonce, mission_id, used_at) VALUES (?, ?, ?);",
                (nonce, mission_id, time.time()))
    conn.commit()
    conn.close()
    return True

def check_sentinel_authorization(req_id: str, db_path: Optional[str] = None) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Checks authorization state immediately before execution.
    Returns (is_authorized: bool, request_dict: Optional[dict], reason: str).
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM sentinel_requests WHERE id = ?;", (req_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False, None, "REQUEST_NOT_FOUND"

    req_dict = dict(row)
    now = time.time()
    if req_dict["status"] != "approved":
        return False, req_dict, f"NOT_APPROVED (current status: {req_dict['status']})"

    if now > req_dict["expires_at"]:
        return False, req_dict, "AUTHORIZATION_EXPIRED"

    return True, req_dict, "AUTHORIZED"

def claim_sentinel_authorization(
    req_id: str,
    expected_target: Optional[str] = None,
    expected_action: Optional[str] = None,
    expected_scope: Optional[Dict[str, Any]] = None,
    expected_digest: Optional[str] = None,
    claimer: str = "FORGE",
    db_path: Optional[str] = None
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Atomically verifies and claims an approved Sentinel authorization order.
    Lifecycle: transitions status from 'approved' -> 'claimed'.
    Validates:
    - Must be in 'approved' state.
    - Must not be expired.
    - If expected_target is specified, must match row['target'].
    - If expected_action is specified, must match row['action_type'] or row['action_class'].
    - If expected_scope is specified, validates exact scope_json matching (cwd, extra_args).
    - If expected_digest is specified or record contains action_digest, validates Action Digest.
    - Single-use only: Rejects replay attempts with ALREADY_CONSUMED.
    Returns (is_claimed: bool, request_dict: Optional[dict], reason: str).
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    now = time.time()
    try:
        cur.execute("BEGIN IMMEDIATE;")
        cur.execute("SELECT * FROM sentinel_requests WHERE id = ?;", (req_id,))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            conn.close()
            return False, None, "REQUEST_NOT_FOUND"

        req_dict = dict(row)
        current_status = req_dict["status"]
        if current_status in ("claimed", "completed", "executed", "failed", "indeterminate"):
            conn.rollback()
            conn.close()
            return False, req_dict, f"ALREADY_CONSUMED: Sentinel authorization has already been {current_status}"

        if current_status != "approved":
            conn.rollback()
            conn.close()
            return False, req_dict, f"NOT_APPROVED: Current status is '{current_status}'"

        if now > req_dict["expires_at"]:
            cur.execute("UPDATE sentinel_requests SET status = 'expired' WHERE id = ?;", (req_id,))
            conn.commit()
            conn.close()
            return False, req_dict, "AUTHORIZATION_EXPIRED: TTL has elapsed"

        if expected_target and req_dict["target"] != expected_target:
            conn.rollback()
            conn.close()
            return False, req_dict, f"TARGET_MISMATCH: Expected target '{expected_target}', got '{req_dict['target']}'"

        if expected_action and expected_action not in (req_dict["action_type"], req_dict["action_class"]):
            conn.rollback()
            conn.close()
            return False, req_dict, f"ACTION_MISMATCH: Expected action '{expected_action}', got '{req_dict['action_type']}'"

        if expected_scope is not None:
            try:
                stored_scope = json.loads(req_dict["scope_json"])
                # Compare cwd if specified
                if "cwd" in expected_scope and stored_scope.get("cwd") != expected_scope["cwd"]:
                    conn.rollback()
                    conn.close()
                    return False, req_dict, f"SCOPE_MISMATCH: Approved working directory '{stored_scope.get('cwd')}' does not match execution directory '{expected_scope['cwd']}'"

                # Compare extra_args if specified
                if "extra_args" in expected_scope:
                    approved_args = stored_scope.get("extra_args", [])
                    exec_args = expected_scope["extra_args"]
                    if approved_args != exec_args:
                        conn.rollback()
                        conn.close()
                        return False, req_dict, f"SCOPE_MISMATCH: Approved arguments {approved_args} do not match execution arguments {exec_args}"
            except Exception as e:
                conn.rollback()
                conn.close()
                return False, req_dict, f"SCOPE_PARSE_ERROR: {str(e)}"

        # Validate Action Digest Binding
        stored_digest = req_dict.get("action_digest")
        if stored_digest:
            stored_scope_obj = json.loads(req_dict["scope_json"]) if req_dict.get("scope_json") else {}
            recalc_digest = compute_action_digest(
                req_dict["id"], req_dict["agent"], req_dict["action_type"], req_dict["target"], stored_scope_obj
            )
            if stored_digest != recalc_digest:
                conn.rollback()
                conn.close()
                return False, req_dict, "DIGEST_MISMATCH: Stored action digest does not match record parameters"

            if expected_digest and expected_digest != stored_digest:
                conn.rollback()
                conn.close()
                return False, req_dict, f"DIGEST_MISMATCH: Expected digest '{expected_digest}' does not match record digest '{stored_digest}'"

        # Atomically transition to 'claimed' with metadata
        cur.execute("""
            UPDATE sentinel_requests 
            SET status = 'claimed', claimed_by = ?, claimed_at = ? 
            WHERE id = ?;
        """, (claimer, now, req_id))

        log_audit_event(
            actor="SENTINEL_GATE",
            action="authorization_claimed",
            target=req_dict["target"],
            result="claimed",
            details={"request_id": req_id, "action_type": req_dict["action_type"], "claimed_by": claimer, "claimed_at": now},
            db_path=db_path,
            conn=conn
        )
        conn.commit()
        conn.close()
        req_dict["status"] = "claimed"
        req_dict["claimed_by"] = claimer
        req_dict["claimed_at"] = now
        return True, req_dict, "CLAIMED_SUCCESS"
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, None, f"DATABASE_ERROR: {str(e)}"

def complete_sentinel_execution(
    req_id: str,
    success: bool,
    output_summary: str = "",
    error_msg: Optional[str] = None,
    db_path: Optional[str] = None
) -> bool:
    """
    Finalizes execution lifecycle: transitions status from 'claimed' to 'completed' or 'failed'.
    Strictly enforces that starting status must be 'claimed'.
    Rejects transition from 'pending', 'approved', 'expired', or already finalized states.
    Persists completion timestamp, output summary, and error message for claim finalization.
    """
    conn = get_connection(db_path, allow_maintenance=True)
    cur = conn.cursor()
    now = time.time()
    new_status = "completed" if success else "failed"
    try:
        cur.execute("BEGIN IMMEDIATE;")
        cur.execute("SELECT status, target, action_type FROM sentinel_requests WHERE id = ?;", (req_id,))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            conn.close()
            return False

        current_status = row["status"] if isinstance(row, sqlite3.Row) else row[0]
        # Starting status MUST be 'claimed'
        if current_status != "claimed":
            conn.rollback()
            conn.close()
            return False

        target = row["target"] if isinstance(row, sqlite3.Row) else row[1]
        action = row["action_type"] if isinstance(row, sqlite3.Row) else row[2]

        cur.execute("""
            UPDATE sentinel_requests 
            SET status = ?, completed_at = ?, output_summary = ?, error_msg = ? 
            WHERE id = ?;
        """, (new_status, now, (output_summary or "")[:512], error_msg, req_id))

        log_audit_event(
            actor="SENTINEL_GATE",
            action=f"execution_{new_status}",
            target=target,
            result=new_status,
            details={"request_id": req_id, "action": action, "output": (output_summary or "")[:256], "error": error_msg, "completed_at": now},
            db_path=db_path,
            conn=conn,
            allow_maintenance=True
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.rollback()
        conn.close()
        return False

def consume_sentinel_authorization(
    req_id: str,
    expected_target: Optional[str] = None,
    expected_action: Optional[str] = None,
    expected_scope: Optional[Dict[str, Any]] = None,
    expected_digest: Optional[str] = None,
    db_path: Optional[str] = None
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Atomically verifies and consumes (claims) an approved Sentinel authorization order.
    Transitions status: 'approved' -> 'claimed'.
    Does NOT fabricate execution completion without actual execution.
    """
    is_claimed, req_dict, reason = claim_sentinel_authorization(
        req_id=req_id,
        expected_target=expected_target,
        expected_action=expected_action,
        expected_scope=expected_scope,
        expected_digest=expected_digest,
        claimer="SENTINEL_CONSUME",
        db_path=db_path
    )
    if is_claimed:
        return True, req_dict, "CONSUMED_SUCCESS"
    return False, req_dict, reason

def resolve_sentinel_request(
    req_id: str, 
    approved: bool, 
    resolver: str = "Aadi", 
    resolver_role: str = "POCO_CORE",
    passphrase_verified: bool = False,
    expected_action_digest: Optional[str] = None,
    db_path: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Atomically resolves a pending Sentinel request (Approved or Denied).
    Mandates:
    - Only POCO_CORE role can grant approval.
    - Consequential approval strictly requires passphrase_verified=True (eliminating bearer token bypass).
    - Enforces displayed-digest-to-approved-record binding.
    - FIRETV_GLASS can deny/cancel, but cannot approve consequential actions.
    - Strict boolean validation.
    - Rejects expired and already-resolved requests.
    Returns (success: bool, status_reason: str).
    """
    if not isinstance(approved, bool):
        return False, "INVALID_INPUT: approved must be a strict boolean"

    conn = get_connection(db_path)
    cur = conn.cursor()
    now = time.time()

    try:
        # Atomic lock
        cur.execute("BEGIN IMMEDIATE;")
        cur.execute("SELECT * FROM sentinel_requests WHERE id = ?;", (req_id,))
        row = cur.fetchone()

        if not row:
            conn.rollback()
            conn.close()
            return False, "REQUEST_NOT_FOUND"

        if row["status"] != "pending":
            conn.rollback()
            conn.close()
            return False, f"ALREADY_RESOLVED: Status is already '{row['status']}'"

        if now > row["expires_at"]:
            # Auto-expire
            cur.execute("UPDATE sentinel_requests SET status = 'expired' WHERE id = ?;", (req_id,))
            log_audit_event("SENTINEL", "auto_expire", req_id, "expired", {"expired_at": now}, db_path=db_path, conn=conn)
            conn.commit()
            conn.close()
            return False, "EXPIRED: Request TTL has elapsed"

        if approved is True:
            # 1. Authority Check: POCO Core only
            if resolver_role != "POCO_CORE":
                log_audit_event(
                    actor=resolver,
                    action="unauthorized_approval_attempt",
                    target=row["target"],
                    result="rejected",
                    details={"request_id": req_id, "resolver_role": resolver_role, "reason": "POCO-only approval authority mandate"},
                    db_path=db_path,
                    conn=conn
                )
                conn.commit()
                conn.close()
                return False, "POCO_AUTHORITY_REQUIRED: Approval restricted strictly to POCO Core Mind"

            # 2. Operator Passphrase Verification Mandate (Item 1)
            if not passphrase_verified:
                log_audit_event(
                    actor=resolver,
                    action="unauthenticated_approval_attempt",
                    target=row["target"],
                    result="rejected",
                    details={"request_id": req_id, "reason": "Bearer token alone cannot approve without operator passphrase verification"},
                    db_path=db_path,
                    conn=conn
                )
                conn.commit()
                conn.close()
                return False, "OPERATOR_PASSPHRASE_REQUIRED: Approval of consequential actions strictly requires operator passphrase verification"

            # 3. Action Digest Binding Mandate (Item 2)
            if not expected_action_digest or not str(expected_action_digest).strip():
                log_audit_event(
                    actor=resolver,
                    action="undigested_approval_attempt",
                    target=row["target"],
                    result="rejected",
                    details={"request_id": req_id, "reason": "Protected approval strictly mandates reviewed action digest"},
                    db_path=db_path,
                    conn=conn
                )
                conn.commit()
                conn.close()
                return False, "ACTION_DIGEST_REQUIRED: Approval of consequential actions strictly requires the reviewed action digest"

            clean_expected_digest = str(expected_action_digest).strip()
            try:
                scope_dict = json.loads(row["scope_json"])
            except Exception:
                scope_dict = {}
            actual_digest = compute_action_digest(row["id"], row["agent"], row["action_type"], row["target"], scope_dict)
            
            stored_digest = row["action_digest"] if "action_digest" in row.keys() else ""
            if stored_digest and stored_digest != actual_digest:
                conn.rollback()
                conn.close()
                return False, "DATABASE_TAMPERING_DETECTED: Stored action digest does not match record parameters"

            if clean_expected_digest != actual_digest:
                conn.rollback()
                conn.close()
                return False, f"DIGEST_MISMATCH: Displayed digest '{clean_expected_digest}' does not match record digest '{actual_digest}'"

        status = "approved" if approved else "denied"
        audit_hash = log_audit_event(
            actor=f"{resolver} ({resolver_role})",
            action=f"sentinel_request_{status}",
            target=row["target"],
            result=status,
            details={
                "request_id": req_id, 
                "risk_level": row["risk_level"], 
                "role": resolver_role,
                "action_digest": expected_action_digest or (row["action_digest"] if "action_digest" in row.keys() else "")
            },
            db_path=db_path,
            conn=conn
        )

        cur.execute("""
            UPDATE sentinel_requests 
            SET status = ?, approved_by = ?, approved_at = ?, audit_hash = ?
            WHERE id = ?;
        """, (status, f"{resolver} ({resolver_role})", now, audit_hash, req_id))

        conn.commit()
        conn.close()
        return True, status
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"TRANSACTION_ERROR: {str(e)}"

def verify_audit_chain(db_path: Optional[str] = None, allow_maintenance: bool = False) -> Dict[str, Any]:
    """
    Cryptographically verifies the entire audit_log SHA-256 hash chain from genesis to tip.
    Detects any inserted, modified, or deleted records.
    """
    conn = get_connection(db_path, allow_maintenance=allow_maintenance)
    cur = conn.cursor()
    cur.execute("SELECT id, timestamp, actor, action, target, result, details_json, previous_hash, current_hash FROM audit_log ORDER BY id ASC;")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"is_valid": True, "total_events": 0, "status": "EMPTY_CHAIN"}

    expected_prev = "GENESIS_BLOCK_AEONIX_PRISM_v2.0"
    for i, row in enumerate(rows):
        # 1. Verify previous hash chaining
        if i == 0:
            if row["previous_hash"] != expected_prev:
                return {
                    "is_valid": False,
                    "error": f"Genesis block previous_hash mismatch at row {row['id']}",
                    "row_id": row["id"],
                    "expected": expected_prev,
                    "found": row["previous_hash"]
                }
        else:
            if row["previous_hash"] != expected_prev:
                return {
                    "is_valid": False,
                    "error": f"Hash chain broken at row {row['id']}: previous_hash does not match parent current_hash",
                    "row_id": row["id"],
                    "expected": expected_prev,
                    "found": row["previous_hash"]
                }

        # 2. Recompute current SHA-256 hash
        hash_payload = f"{row['previous_hash']}|{row['timestamp']}|{row['actor']}|{row['action']}|{row['target']}|{row['result']}|{row['details_json']}"
        computed_hash = hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()

        if computed_hash != row["current_hash"]:
            return {
                "is_valid": False,
                "error": f"Content tampering detected at row {row['id']}: computed hash != stored hash",
                "row_id": row["id"],
                "computed_hash": computed_hash,
                "stored_hash": row["current_hash"]
            }

        expected_prev = row["current_hash"]

    return {
        "is_valid": True,
        "total_events": len(rows),
        "status": "CRYPTOGRAPHICALLY_VERIFIED",
        "genesis_hash": rows[0]["current_hash"],
        "tip_hash": rows[-1]["current_hash"]
    }
