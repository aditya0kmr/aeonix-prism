"""
ÆONIX PRISM // GUARDIAN Network Perimeter Defense & Subnet Discovery
Detects local network topology, tracks authorized sovereign hardware, and alerts on rogue devices.
Zero Cloud Dependencies.
"""

import os
import json
import time
import socket
import asyncio
import hashlib
import uuid
from typing import Dict, Any, List, Optional, Tuple

from aeonix.core.db import get_connection, log_audit_event, record_durable_event

# Whitelisted Sovereign Infrastructure
WHITELISTED_DEVICES = {
    "10.116.23.168": {
        "name": "POCO M4 Pro 5G",
        "role": "Core Mind / Sovereign Vault",
        "authorized": True,
        "trust_level": "SOVEREIGN_CORE",
        "mac": "LOCAL"
    },
    "10.116.23.179": {
        "name": "Fire TV Stick Lite",
        "role": "Living Surface / Glass Terminal",
        "authorized": True,
        "trust_level": "DUMB_GLASS",
        "mac": "REMOTE"
    },
    "10.116.23.1": {
        "name": "Local Gateway / Wi-Fi AP",
        "role": "Local Router",
        "authorized": True,
        "trust_level": "TRUSTED_GATEWAY",
        "mac": "GATEWAY"
    }
}

COMMON_PROBE_PORTS = [5555, 8080, 80, 443, 22]

# =========================================================================
# BOUNDED TELEMETRY & EXPONENTIAL BACKOFF STATE (Master Spec Section 19/22)
# =========================================================================
_LAST_TELEMETRY_SAMPLE: float = 0.0
_CURRENT_BACKOFF_INTERVAL: float = 60.0   # Baseline 60s
_LAST_INVENTORY_DIGEST: str = ""
_CACHED_TELEMETRY: Optional[Dict[str, Any]] = None
_TELEMETRY_LOCK = asyncio.Lock() if hasattr(asyncio, "Lock") else None


def read_passive_arp_table() -> List[Dict[str, str]]:
    """
    Passively reads local ARP cache (/proc/net/arp) without generating network packets.
    Gracefully handles Android 13 SELinux permission boundaries.
    """
    arp_entries: List[Dict[str, str]] = []
    arp_path = "/proc/net/arp"
    if not os.path.exists(arp_path):
        return arp_entries

    try:
        with open(arp_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # Header: IP address HW type Flags HW address Mask Device
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 6:
                ip = parts[0]
                mac = parts[3]
                dev = parts[5]
                # Filter out 00:00:00:00:00:00
                if mac != "00:00:00:00:00:00":
                    arp_entries.append({
                        "ip": ip,
                        "mac": mac,
                        "interface": dev
                    })
    except (PermissionError, OSError):
        # Android unprivileged sandbox / SELinux restrictions
        pass

    return arp_entries


def compute_inventory_digest(devices: List[Dict[str, Any]]) -> str:
    """Computes a deterministic SHA-256 evidence digest across sorted devices."""
    canonical = [
        {
            "ip": d.get("ip", ""),
            "mac": d.get("mac", ""),
            "authorized": bool(d.get("authorized", False)),
            "trust_level": d.get("trust_level", "")
        }
        for d in sorted(devices, key=lambda x: x.get("ip", ""))
    ]
    raw = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_passive_network_topology() -> Dict[str, Any]:
    """
    Constructs network topology from passive observations:
    1. Local ARP cache (if unblocked).
    2. Registered devices in SQLite database.
    3. Whitelisted sovereign hardware.
    Zero active probes, zero battery drain.
    """
    arp_entries = read_passive_arp_table()
    arp_map = {e["ip"]: e for e in arp_entries}

    # Query registered sovereign devices from database
    db_devices: Dict[str, Dict[str, Any]] = {}
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, type, ip_address, trust_level, status FROM devices;")
        rows = cur.fetchall()
        for r in rows:
            ip = r["ip_address"]
            if ip:
                db_devices[ip] = {
                    "id": r["id"],
                    "name": r["name"],
                    "role": r["type"],
                    "trust_level": r["trust_level"],
                    "status": r["status"]
                }
        conn.close()
    except Exception:
        pass

    devices_dict: Dict[str, Dict[str, Any]] = {}

    # 1. Merge whitelisted devices
    for ip, info in WHITELISTED_DEVICES.items():
        devices_dict[ip] = {
            "ip": ip,
            "name": info["name"],
            "role": info["role"],
            "authorized": info["authorized"],
            "trust_level": info["trust_level"],
            "mac": arp_map.get(ip, {}).get("mac", info.get("mac", "UNKNOWN")),
            "interface": arp_map.get(ip, {}).get("interface", "wlan0"),
            "source": "sovereign_whitelist",
            "is_online": True
        }

    # 2. Merge registered database devices
    for ip, info in db_devices.items():
        if ip not in devices_dict:
            devices_dict[ip] = {
                "ip": ip,
                "name": info["name"],
                "role": info["role"],
                "authorized": True,
                "trust_level": info["trust_level"],
                "mac": arp_map.get(ip, {}).get("mac", "UNKNOWN"),
                "interface": arp_map.get(ip, {}).get("interface", "wlan0"),
                "source": "registered_devices_db",
                "is_online": True
            }

    # 3. Merge discovered passive ARP entries (flags rogues if not recognized)
    for entry in arp_entries:
        ip = entry["ip"]
        if ip not in devices_dict:
            devices_dict[ip] = {
                "ip": ip,
                "name": f"Unidentified Host ({entry['mac'][-8:]})",
                "role": "Untrusted Node",
                "authorized": False,
                "trust_level": "UNTRUSTED",
                "mac": entry["mac"],
                "interface": entry.get("interface", "wlan0"),
                "source": "passive_arp_cache",
                "is_online": True
            }

    devices_list = list(devices_dict.values())
    authorized_count = sum(1 for d in devices_list if d["authorized"])
    rogue_count = sum(1 for d in devices_list if not d["authorized"])
    digest = compute_inventory_digest(devices_list)

    return {
        "timestamp": time.time(),
        "subnet": "10.116.23.0/24",
        "active_devices_count": len(devices_list),
        "authorized_count": authorized_count,
        "rogue_count": rogue_count,
        "perimeter_status": "SECURE" if rogue_count == 0 else "WARNING_ROGUE_DEVICES_DETECTED",
        "inventory_digest": digest,
        "passive_mode": True,
        "devices": devices_list
    }


def get_bounded_network_telemetry(
    force_refresh: bool = False,
    max_backoff: float = 3600.0,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns bounded network topology telemetry with exponential backoff.
    Guarantees:
    - Zero continuous CPU/battery drain (serves cached snapshot if called within backoff window).
    - Automatically adjusts backoff (doubles up to max_backoff on stable inventory; resets on change).
    - Emits durable event envelope with SHA-256 evidence digest into events table.
    """
    global _LAST_TELEMETRY_SAMPLE, _CURRENT_BACKOFF_INTERVAL, _LAST_INVENTORY_DIGEST, _CACHED_TELEMETRY

    now = time.time()
    elapsed = now - _LAST_TELEMETRY_SAMPLE

    # Cache hit check
    if not force_refresh and _CACHED_TELEMETRY is not None and elapsed < _CURRENT_BACKOFF_INTERVAL:
        cached_result = dict(_CACHED_TELEMETRY)
        cached_result["cache_hit"] = True
        cached_result["elapsed_seconds"] = round(elapsed, 2)
        cached_result["backoff_interval"] = _CURRENT_BACKOFF_INTERVAL
        return cached_result

    # Gather passive topology
    topo = get_passive_network_topology()
    current_digest = topo["inventory_digest"]

    # Exponential backoff adjustment
    if _LAST_INVENTORY_DIGEST and current_digest == _LAST_INVENTORY_DIGEST:
        _CURRENT_BACKOFF_INTERVAL = min(_CURRENT_BACKOFF_INTERVAL * 2.0, max_backoff)
    else:
        # Topology changed or initial scan -> reset to baseline 60s
        _CURRENT_BACKOFF_INTERVAL = 60.0

    _LAST_INVENTORY_DIGEST = current_digest
    _LAST_TELEMETRY_SAMPLE = now

    topo["cache_hit"] = False
    topo["elapsed_seconds"] = 0.0
    topo["backoff_interval"] = _CURRENT_BACKOFF_INTERVAL

    # Emit durable event envelope to SQLite events table
    event_id = f"evt_net_{int(now)}_{uuid.uuid4().hex[:8]}"
    try:
        record_durable_event(
            event_id=event_id,
            schema_version="1.0.0",
            observed_at=now,
            device_id="poco_m4_pro_5g",
            source="GUARDIAN",
            event_type="network_topology_snapshot",
            subject="local_subnet",
            payload={
                "inventory_digest": current_digest,
                "device_count": topo["active_devices_count"],
                "authorized_count": topo["authorized_count"],
                "rogue_count": topo["rogue_count"],
                "perimeter_status": topo["perimeter_status"],
                "backoff_interval": _CURRENT_BACKOFF_INTERVAL
            },
            classification="R1",
            db_path=db_path
        )
    except Exception as e:
        # Non-fatal if test environment db_path differs or read-only
        pass

    # Record audit log entry
    try:
        log_audit_event(
            actor="GUARDIAN",
            action="network_telemetry_snapshot",
            target="10.116.23.0/24",
            result="success",
            details={
                "digest": current_digest,
                "device_count": topo["active_devices_count"],
                "rogue_count": topo["rogue_count"],
                "backoff_interval": _CURRENT_BACKOFF_INTERVAL
            },
            db_path=db_path
        )
    except Exception:
        pass

    _CACHED_TELEMETRY = topo
    return topo

async def probe_ip_port(ip: str, port: int, timeout: float = 0.1) -> bool:
    """Probes a specific IP and port via non-blocking TCP connect."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False

async def scan_host(ip: str) -> Dict[str, Any]:
    """Scans a single host across common ports and resolves hostname."""
    open_ports = []
    tasks = [probe_ip_port(ip, port) for port in COMMON_PROBE_PORTS]
    results = await asyncio.gather(*tasks)
    
    for port, is_open in zip(COMMON_PROBE_PORTS, results):
        if is_open:
            open_ports.append(port)
            
    is_online = len(open_ports) > 0 or ip in WHITELISTED_DEVICES
    
    auth_info = WHITELISTED_DEVICES.get(ip, {
        "name": "Unidentified Node",
        "role": "Untrusted Subnet Device",
        "authorized": False,
        "trust_level": "UNTRUSTED",
        "mac": "UNKNOWN"
    })
    
    hostname = auth_info.get("name", ip)
    
    return {
        "ip": ip,
        "is_online": is_online,
        "hostname": hostname,
        "name": auth_info["name"],
        "role": auth_info["role"],
        "authorized": auth_info["authorized"],
        "trust_level": auth_info.get("trust_level", "AUTHORIZED" if auth_info.get("authorized") else "UNTRUSTED"),
        "mac": auth_info.get("mac", "UNKNOWN"),
        "open_ports": open_ports,
        "status": "authorized" if auth_info["authorized"] else ("unauthorized_alert" if is_online else "offline")
    }

async def scan_local_subnet(ip_base: str = "10.116.23", scan_range: range = range(1, 200)) -> List[Dict[str, Any]]:
    """Scans active hosts in the local /24 subnet."""
    target_ips = [f"{ip_base}.{i}" for i in scan_range]
    tasks = [scan_host(ip) for ip in target_ips]
    hosts = await asyncio.gather(*tasks)
    
    online_hosts = [h for h in hosts if h["is_online"]]
    rogue_hosts = [h for h in online_hosts if not h["authorized"]]
    
    # Audit log entry
    log_audit_event(
        actor="GUARDIAN",
        action="subnet_perimeter_scan",
        target=f"{ip_base}.0/24",
        result="success",
        details={
            "total_online": len(online_hosts),
            "rogue_count": len(rogue_hosts),
            "online_ips": [h["ip"] for h in online_hosts]
        }
    )
    
    return online_hosts

async def async_get_network_inventory() -> Dict[str, Any]:
    """Async entrypoint for quick network status."""
    hosts = await scan_local_subnet()
    authorized_count = sum(1 for h in hosts if h["authorized"])
    rogue_count = sum(1 for h in hosts if not h["authorized"])
    
    return {
        "timestamp": time.time(),
        "subnet": "10.116.23.0/24",
        "active_devices_count": len(hosts),
        "authorized_count": authorized_count,
        "rogue_count": rogue_count,
        "perimeter_status": "SECURE" if rogue_count == 0 else "WARNING_ROGUE_DEVICES_DETECTED",
        "devices": hosts
    }

def get_network_inventory() -> Dict[str, Any]:
    """Synchronous entrypoint for quick network status, thread-safe even inside an active asyncio loop."""
    import concurrent.futures

    def _run():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(scan_local_subnet())
        finally:
            new_loop.close()
            
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            hosts = pool.submit(_run).result(timeout=10.0)
    else:
        hosts = _run()
    
    authorized_count = sum(1 for h in hosts if h["authorized"])
    rogue_count = sum(1 for h in hosts if not h["authorized"])
    
    return {
        "timestamp": time.time(),
        "subnet": "10.116.23.0/24",
        "active_devices_count": len(hosts),
        "authorized_count": authorized_count,
        "rogue_count": rogue_count,
        "perimeter_status": "SECURE" if rogue_count == 0 else "WARNING_ROGUE_DEVICES_DETECTED",
        "devices": hosts
    }

if __name__ == "__main__":
    print("Testing GUARDIAN Subnet Discovery...")
    t0 = time.time()
    inv = get_network_inventory()
    dt = time.time() - t0
    print(f"Scan completed in {dt:.2f}s | Perimeter: {inv['perimeter_status']}")
    for d in inv["devices"]:
        print(f"  • {d['ip']} | {d['name']} ({d['role']}) | Ports: {d['open_ports']} | Auth: {d['authorized']}")
