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
from typing import Dict, Any, List

from aeonix.core.db import get_connection, log_audit_event

# Whitelisted Sovereign Infrastructure
WHITELISTED_DEVICES = {
    "10.116.23.168": {
        "name": "POCO M4 Pro 5G",
        "role": "Core Mind / Sovereign Vault",
        "authorized": True
    },
    "10.116.23.179": {
        "name": "Fire TV Stick Lite",
        "role": "Living Surface / Glass Terminal",
        "authorized": True
    },
    "10.116.23.1": {
        "name": "Local Gateway / Wi-Fi AP",
        "role": "Local Router",
        "authorized": True
    }
}

COMMON_PROBE_PORTS = [5555, 8080, 80, 443, 22]

async def probe_ip_port(ip: str, port: int, timeout: float = 0.2) -> bool:
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
    
    hostname = "Unknown"
    if is_online:
        try:
            hostname = socket.gethostbyaddr(ip)[0]
        except Exception:
            hostname = ip
            
    auth_info = WHITELISTED_DEVICES.get(ip, {
        "name": "Unidentified Node",
        "role": "Untrusted Subnet Device",
        "authorized": False
    })
    
    return {
        "ip": ip,
        "is_online": is_online,
        "hostname": hostname,
        "name": auth_info["name"],
        "role": auth_info["role"],
        "authorized": auth_info["authorized"],
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
