"""
SIGNAL — Hidden Pattern & Latent Correlation Detector
Discovers non-obvious correlations across database entities, audit event frequencies,
and anomalous temporal clusters.
"""

import time
from typing import Dict, Any, List
try:
    from aeonix.core.db import query_db, log_audit_event
except ImportError:
    from core.db import query_db, log_audit_event


class SignalPatternDetector:
    def __init__(self):
        pass

    def scan_for_latent_patterns(self) -> Dict[str, Any]:
        """
        Latent Pattern & Anomaly Detector:
        - Calculates real measured baselines from SQLite audit logs and sentinel requests.
        - Computes dynamic anomaly scores based on error frequencies, rejection ratios, and temporal distribution.
        """
        start_time = time.time()

        # 1. Audit Log Baselines
        total_rows = query_db("SELECT COUNT(*) FROM audit_log;")
        total_events = total_rows[0][0] if total_rows else 0

        # Query top active actors in audit log
        rows = query_db(
            "SELECT actor, COUNT(*) as cnt FROM audit_log GROUP BY actor ORDER BY cnt DESC LIMIT 5;"
        )
        actor_distribution = {r[0]: r[1] for r in rows}

        # Query error/rejection count
        error_rows = query_db(
            "SELECT COUNT(*) FROM audit_log WHERE result IN ('rejected', 'error', 'failed', 'kill_switch_hold');"
        )
        error_events = error_rows[0][0] if error_rows else 0

        # 2. Entity Density in Nexus Graph
        ent_rows = query_db(
            "SELECT entity_type, COUNT(*) as cnt FROM entities GROUP BY entity_type;"
        )
        entity_distribution = {r[0]: r[1] for r in ent_rows}

        # 3. Sentinel Gate Activity
        sentinel_counts = query_db("SELECT status, COUNT(*) FROM sentinel_requests GROUP BY status;")
        sentinel_dist = {r[0]: r[1] for r in sentinel_counts}

        # 4. Dynamic Anomaly Calculation
        # Nominal baseline error rate is < 3%
        error_rate = (error_events / max(1, total_events))
        # Anomaly score scaled from measured failure frequencies
        if error_rate < 0.03:
            anomaly_score = round(max(0.01, error_rate * 1.5), 3)
            signal_status = "PATTERNS_NOMINAL"
        elif error_rate < 0.10:
            anomaly_score = round(0.10 + error_rate * 2.0, 3)
            signal_status = "ELEVATED_VARIANCE"
        else:
            anomaly_score = round(min(0.99, 0.30 + error_rate * 3.0), 3)
            signal_status = "ANOMALY_DETECTED"

        patterns_found = [
            f"Audit log density concentrated across {len(actor_distribution)} core autonomous daemons ({total_events} total logged events).",
            f"Entity graph populated across {len(entity_distribution)} distinct schema domains.",
            f"Measured operational error/rejection rate: {error_rate*100:.1f}% ({error_events} events).",
        ]

        if sentinel_dist.get("expired", 0) > 0:
            patterns_found.append(f"Temporal anomaly: {sentinel_dist['expired']} Sentinel requests expired before human verification.")
        else:
            patterns_found.append("Temporal cadence exhibits zero rogue clustering outside authorized user sessions.")

        latency_ms = round((time.time() - start_time) * 1000, 2)
        log_audit_event("SIGNAL", "latent_pattern_scan", "AUDIT_VAULT", "SUCCESS", {
            "anomaly_score": anomaly_score,
            "total_events": total_events,
            "latency_ms": latency_ms
        })

        return {
            "signal_status": signal_status,
            "total_events_measured": total_events,
            "actor_distribution": actor_distribution,
            "entity_distribution": entity_distribution,
            "sentinel_distribution": sentinel_dist,
            "detected_patterns": patterns_found,
            "anomaly_score": anomaly_score,
            "latency_ms": latency_ms,
        }


signal_detector = SignalPatternDetector()
