#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# ÆONIX PRISM Core Mind Daemon (POCO M4 Pro 5G)
# Hardware Guarded: 1 Worker, Pre-allocated Memory, Anti-OOM wake-lock
# ==============================================================================
set -e

echo "🌌 [1/3] Acquiring Android Wake Lock to prevent CPU sleep..."
termux-wake-lock 2>/dev/null || true

export PYTHONPATH="/data/data/com.termux/files/home/aeonix-prism"
cd /data/data/com.termux/files/home/aeonix-prism

echo "🛡️  [2/3] Verifying SQLite Vault & Sentinel Queue..."
python3 -c "from aeonix.core.db import init_database; init_database(); print('Vault integrity OK')"

echo "🚀 [3/3] Launching ÆONIX PRISM Core Server (Port 8080)..."
# Sovereign Default-Deny: Bind strictly to localhost (127.0.0.1) unless operator explicitly configures AEONIX_BIND_HOST
BIND_HOST="${AEONIX_BIND_HOST:-127.0.0.1}"
echo "🔒 Binding to: ${BIND_HOST}:8080 (LAN binding requires explicit AEONIX_BIND_HOST=0.0.0.0)"
exec uvicorn aeonix.core.server:app --host "${BIND_HOST}" --port 8080 --workers 1 --no-access-log
