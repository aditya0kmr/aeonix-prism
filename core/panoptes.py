"""
ÆONIX PRISM // PANOPTES Autonomous OSINT & Entity Graph Engine
Lawful passive intelligence gathering, entity graph traversal, and Sentinel-gated probing.
Zero Paid APIs, 100% Local-First Provenance.
"""

import os
import json
import time
import socket
import urllib.parse
from typing import Dict, Any, List, Optional
import httpx

from aeonix.core.db import get_connection, log_audit_event, queue_sentinel_request

def upsert_entity(name: str, entity_type: str, attributes: Dict[str, Any]) -> str:
    """Inserts or updates an entity in the PANOPTES graph."""
    conn = get_connection()
    cur = conn.cursor()
    now = time.time()
    
    # Generate deterministic ID based on type and name to prevent duplicate nodes
    clean_name = name.strip().lower()
    clean_type = entity_type.strip().lower()
    entity_id = f"ent_{clean_type}_{hash(clean_name) & 0xffffffffffff:012x}"
    
    cur.execute("SELECT attributes_json FROM entities WHERE id = ?;", (entity_id,))
    row = cur.fetchone()
    if row:
        existing_attrs = json.loads(row["attributes_json"])
        existing_attrs.update(attributes)
        cur.execute("""
            UPDATE entities 
            SET attributes_json = ?, updated_at = ?
            WHERE id = ?;
        """, (json.dumps(existing_attrs), now, entity_id))
    else:
        cur.execute("""
            INSERT INTO entities (id, name, entity_type, attributes_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (entity_id, name, clean_type, json.dumps(attributes), now, now))
    
    conn.commit()
    conn.close()
    return entity_id

def add_relation(
    source_id: str, 
    target_id: str, 
    relation_type: str, 
    confidence: float = 1.0, 
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Creates a directed edge between two entities in the graph."""
    if metadata is None:
        metadata = {}
    conn = get_connection()
    cur = conn.cursor()
    now = time.time()
    
    rel_id = f"rel_{source_id[:8]}_{target_id[:8]}_{relation_type[:6]}"
    cur.execute("""
        INSERT OR REPLACE INTO entity_relations (id, source_id, target_id, relation_type, confidence, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?);
    """, (rel_id, source_id, target_id, relation_type.lower(), confidence, json.dumps(metadata), now))
    
    conn.commit()
    conn.close()
    return rel_id

def get_entity_graph(start_id: str, max_depth: int = 2) -> Dict[str, Any]:
    """Traverses the entity graph using BFS up to max_depth."""
    conn = get_connection()
    cur = conn.cursor()
    
    visited_nodes = {}
    visited_edges = []
    queue = [(start_id, 0)]
    
    while queue:
        current_id, depth = queue.pop(0)
        if current_id in visited_nodes:
            continue
        
        cur.execute("SELECT id, name, entity_type, attributes_json FROM entities WHERE id = ?;", (current_id,))
        node = cur.fetchone()
        if not node:
            continue
        
        visited_nodes[current_id] = {
            "id": node["id"],
            "name": node["name"],
            "type": node["entity_type"],
            "attributes": json.loads(node["attributes_json"])
        }
        
        if depth < max_depth:
            cur.execute("""
                SELECT id, source_id, target_id, relation_type, confidence, metadata_json
                FROM entity_relations
                WHERE source_id = ? OR target_id = ?;
            """, (current_id, current_id))
            edges = cur.fetchall()
            for edge in edges:
                edge_dict = {
                    "id": edge["id"],
                    "source": edge["source_id"],
                    "target": edge["target_id"],
                    "relation": edge["relation_type"],
                    "confidence": edge["confidence"]
                }
                if edge_dict not in visited_edges:
                    visited_edges.append(edge_dict)
                
                next_id = edge["target_id"] if edge["source_id"] == current_id else edge["source_id"]
                if next_id not in visited_nodes:
                    queue.append((next_id, depth + 1))
                    
    conn.close()
    return {
        "nodes": list(visited_nodes.values()),
        "edges": visited_edges,
        "total_nodes": len(visited_nodes),
        "total_edges": len(visited_edges)
    }

# =========================================================================
# PASSIVE LAWFUL OSINT MODULES (Zero External API Keys)
# =========================================================================

def passive_dns_recon(domain: str) -> Dict[str, Any]:
    """Performs lawful, passive DNS reconnaissance using standard socket resolver."""
    clean_domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    records = {"domain": clean_domain, "ipv4": [], "aliases": []}
    
    try:
        host, aliases, ips = socket.gethostbyname_ex(clean_domain)
        records["ipv4"] = ips
        records["aliases"] = aliases
    except Exception as e:
        records["dns_error"] = str(e)
    
    return records

def cert_transparency_recon(domain: str, timeout: float = 8.0) -> List[str]:
    """Queries crt.sh public Certificate Transparency log to uncover subdomains passively."""
    clean_domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    url = f"https://crt.sh/?q=%.{clean_domain}&output=json"
    subdomains = set()
    
    try:
        with httpx.Client(timeout=timeout) as client:
            res = client.get(url, headers={"User-Agent": "Aeonix-Panoptes/2.0"})
            if res.status_code == 200:
                entries = res.json()
                for entry in entries:
                    name_value = entry.get("name_value", "")
                    for name in name_value.splitlines():
                        name = name.strip().lower()
                        if name.endswith(clean_domain) and "*" not in name:
                            subdomains.add(name)
    except Exception:
        pass
    
    return sorted(list(subdomains))

def http_fingerprint(target: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Inspects HTTP headers, status code, and security posture."""
    if not target.startswith("http://") and not target.startswith("https://"):
        target = f"https://{target}"
    
    fingerprint = {
        "target": target,
        "status_code": None,
        "server": None,
        "hsts": False,
        "csp": False,
        "headers": {}
    }
    
    try:
        with httpx.Client(timeout=timeout, verify=False, follow_redirects=True) as client:
            res = client.get(target, headers={"User-Agent": "Mozilla/5.0 (Aeonix PRISM Sovereign Scanner)"})
            fingerprint["status_code"] = res.status_code
            fingerprint["server"] = res.headers.get("server")
            fingerprint["hsts"] = "strict-transport-security" in res.headers
            fingerprint["csp"] = "content-security-policy" in res.headers
            fingerprint["headers"] = dict(res.headers)
    except Exception as e:
        fingerprint["error"] = str(e)
        
    return fingerprint

def run_passive_osint(domain: str, active_probe: bool = False, **kwargs) -> Dict[str, Any]:
    """Executes full passive OSINT pipeline and populates the entity-relation graph."""
    clean_domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    
    # 1. Ingest Primary Domain Entity
    domain_id = upsert_entity(clean_domain, "domain", {"verified_domain": True})
    
    # 2. DNS Recon
    dns_data = passive_dns_recon(clean_domain)
    for ip in dns_data.get("ipv4", []):
        ip_id = upsert_entity(ip, "ipv4_address", {"version": 4})
        add_relation(domain_id, ip_id, "resolves_to", confidence=1.0)
    
    # 3. Certificate Transparency Subdomains (Skip for raw IP addresses)
    is_ip = all(part.isdigit() for part in clean_domain.split(".")) if "." in clean_domain else False
    subdomains = []
    if not is_ip and "." in clean_domain:
        subdomains = cert_transparency_recon(clean_domain)
        for sub in subdomains[:15]: # Cap to top 15 to stay fast
            sub_id = upsert_entity(sub, "subdomain", {"parent": clean_domain})
            add_relation(domain_id, sub_id, "has_subdomain", confidence=0.95)

    
    # 4. HTTP Fingerprint
    http_data = http_fingerprint(clean_domain)
    server_banner = http_data.get("server")
    if server_banner:
        srv_id = upsert_entity(server_banner, "software_banner", {"role": "web_server"})
        add_relation(domain_id, srv_id, "runs_software", confidence=0.85)
    
    # 5. Log audit event
    log_audit_event(
        actor="PANOPTES",
        action="passive_osint_scan",
        target=clean_domain,
        result="success",
        details={
            "subdomains_found": len(subdomains),
            "ips_found": len(dns_data.get("ipv4", [])),
            "server": server_banner
        }
    )
    
    # Return graph centered on domain
    return get_entity_graph(domain_id, max_depth=2)

def generate_osint_report(domain: str, generated_by: str = "Aadi") -> Dict[str, Any]:
    """
    Generates a comprehensive OSINT intelligence dossier for a domain.
    Aggregates passive DNS, CT logs, HTTP headers, entity graph, and posture assessment.
    """
    clean_domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    t0 = time.time()
    graph = run_passive_osint(clean_domain)
    http_data = http_fingerprint(clean_domain)
    
    # Analyze security posture
    findings = []
    if not http_data.get("hsts"):
        findings.append({"severity": "MEDIUM", "issue": "Missing Strict-Transport-Security (HSTS) header"})
    if not http_data.get("csp"):
        findings.append({"severity": "LOW", "issue": "Missing Content-Security-Policy (CSP) header"})
        
    subdomains = [n["name"] for n in graph.get("nodes", []) if n.get("type") == "subdomain"]
    ips = [n["name"] for n in graph.get("nodes", []) if n.get("type") == "ipv4_address"]
    
    dossier_markdown = f"""# PANOPTES Intelligence Dossier: {clean_domain}
- **Generated At:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
- **Generated By:** {generated_by}
- **Target Domain:** `{clean_domain}`
- **Web Server:** `{http_data.get('server') or 'Unknown/Hidden'}`

## Infrastructure Footprint
- **Total Correlated Entities:** {graph.get('total_nodes', 0)}
- **Discovered IP Addresses ({len(ips)}):** {', '.join(ips) if ips else 'None resolved'}
- **Discovered Subdomains ({len(subdomains)}):** {', '.join(subdomains[:10]) if subdomains else 'None'}

## Security Posture
- **HSTS Active:** {http_data.get('hsts', False)}
- **CSP Active:** {http_data.get('csp', False)}
- **Identified Findings:** {len(findings)}
"""

    report = {
        "domain": clean_domain,
        "generated_at": time.time(),
        "generated_by": generated_by,
        "latency_seconds": round(time.time() - t0, 3),
        "total_entities": graph.get("total_nodes", 0),
        "total_relations": graph.get("total_edges", 0),
        "subdomains": subdomains,
        "ips": ips,
        "web_fingerprint": http_data,
        "findings": findings,
        "dossier_markdown": dossier_markdown
    }

    log_audit_event(
        actor=generated_by,
        action="osint_report_generated",
        target=clean_domain,
        result="success",
        details={"entities": report["total_entities"], "findings": len(findings)}
    )
    return report

def request_active_probe(target: str, port_range: List[int]) -> Dict[str, Any]:
    """
    Submits an active port scan / probe request to the Sentinel Gate.
    Active probes CANNOT execute without explicit human authorization from POCO Core!
    """
    req_id = queue_sentinel_request(
        agent="PANOPTES",
        action_class="NETWORK_PROBE",
        action_type="ACTIVE_PORT_SCAN",
        target=target,
        scope={"ports": port_range, "notice": "Non-passive active TCP syn probe"},
        risk_level="R3_HIGH",
        ttl_seconds=300
    )
    return {
        "status": "sentinel_gate_hold",
        "request_id": req_id,
        "message": "Active probe paused at Sentinel Gate. Authorization required on POCO Core Mind."
    }

panoptes_scan = run_passive_osint
link_entities = add_relation


if __name__ == "__main__":
    print("Testing PANOPTES Passive OSINT on example.com...")
    t0 = time.time()
    graph = run_passive_osint("example.com")
    dt = time.time() - t0
    print(f"Graph generated in {dt:.2f}s:")
    print(f"Nodes ({graph['total_nodes']}): {[n['name'] for n in graph['nodes']]}")
    print(f"Edges ({graph['total_edges']}): {[e['relation'] for e in graph['edges']]}")
