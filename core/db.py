import sqlite3
import os
import time
import json
import hashlib
from typing import Optional, Dict, Any, List

DB_PATH = os.path.expanduser("~/aeonix/data/aeonix_vault.db")

def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    # Anti-Corruption & High-Performance Hardening Mandates
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn

def init_database(db_path: str = DB_PATH) -> bool:
    """Initializes tables and performs integrity checks."""
    conn = get_connection(db_path)
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
        audit_hash TEXT
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

    conn.commit()
    conn.close()
    return True

def log_audit_event(actor: str, action: str, target: str, result: str, details: Dict[str, Any], db_path: str = DB_PATH) -> str:
    """Appends an event to audit_log with cryptographic SHA-256 hash chaining."""
    conn = get_connection(db_path)
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

    conn.commit()
    conn.close()
    return current_hash

def queue_sentinel_request(agent: str, action_class: str, action_type: str, target: str, scope: Dict[str, Any], risk_level: str, ttl_seconds: int = 300, db_path: str = DB_PATH) -> str:
    """Enqueues a pending action for human verification (Sentinel Gate)."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    
    req_id = f"sentinel_{int(time.time()*1000)}_{os.urandom(3).hex()}"
    now = time.time()
    expires_at = now + ttl_seconds
    scope_str = json.dumps(scope)
    
    cur.execute("""
        INSERT INTO sentinel_requests (id, agent, action_class, action_type, target, scope_json, risk_level, status, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?);
    """, (req_id, agent, action_class, action_type, target, scope_str, risk_level, now, expires_at))

    conn.commit()
    conn.close()

    log_audit_event(
        actor=agent,
        action="sentinel_request_created",
        target=target,
        result="queued",
        details={"request_id": req_id, "risk_level": risk_level, "action_type": action_type},
        db_path=db_path
    )
    return req_id

def resolve_sentinel_request(req_id: str, approved: bool, resolver: str = "Aadi", db_path: str = DB_PATH) -> bool:
    """Resolves a pending Sentinel request (Approved or Denied)."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute("SELECT * FROM sentinel_requests WHERE id = ?;", (req_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False

    status = "approved" if approved else "denied"
    now = time.time()

    audit_hash = log_audit_event(
        actor=resolver,
        action=f"sentinel_request_{status}",
        target=row["target"],
        result=status,
        details={"request_id": req_id, "risk_level": row["risk_level"]},
        db_path=db_path
    )

    cur.execute("""
        UPDATE sentinel_requests 
        SET status = ?, approved_by = ?, approved_at = ?, audit_hash = ?
        WHERE id = ?;
    """, (status, resolver, now, audit_hash, req_id))

    conn.commit()
    conn.close()
    return True
