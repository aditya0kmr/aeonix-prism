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

echo "🚀 [3/3] Launching ÆONIX PRISM Core Server..."
# Sovereign Default-Deny: Bind strictly to localhost (127.0.0.1) unless operator explicitly configures AEONIX_BIND_HOST
BIND_HOST="${AEONIX_BIND_HOST:-127.0.0.1}"
RAW_PORT="${AEONIX_PORT:-8080}"

# Validate port is numeric and within 1-65535
if ! [[ "${RAW_PORT}" =~ ^[0-9]+$ ]] || [ "${RAW_PORT}" -lt 1 ] || [ "${RAW_PORT}" -gt 65535 ]; then
    echo "🚨 FATAL: Invalid AEONIX_PORT '${RAW_PORT}'. Must be an integer between 1 and 65535." >&2
    exit 1
fi
BIND_PORT="${RAW_PORT}"

KEY_FILE="${HOME}/.aeonix/secrets/aeonix_key.pem"
CERT_FILE="${HOME}/.aeonix/secrets/aeonix_cert.pem"

SSL_OPTS=()
if [ "${BIND_HOST}" != "127.0.0.1" ]; then
    if [ ! -r "${CERT_FILE}" ] || [ ! -r "${KEY_FILE}" ]; then
        echo "🚨 FATAL: Non-loopback bind (${BIND_HOST}) strictly requires readable TLS certificate and private key." >&2
        echo "Missing or unreadable TLS credentials in ${HOME}/.aeonix/secrets" >&2
        exit 1
    fi
    # Validate certificate and key compatibility via Python without exposing secret contents
    if ! python3 -c "
import ssl
ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
ctx.load_cert_chain(certfile='${CERT_FILE}', keyfile='${KEY_FILE}')
" 2>/dev/null; then
        echo "🚨 FATAL: TLS certificate and private key pair is invalid, malformed, or mismatched." >&2
        exit 1
    fi
    echo "🔐 Sovereign TLS Active: Validated certificate and private key."
    SSL_OPTS=(--ssl-keyfile "${KEY_FILE}" --ssl-certfile "${CERT_FILE}")
elif [ -r "${CERT_FILE}" ] && [ -r "${KEY_FILE}" ]; then
    SSL_OPTS=(--ssl-keyfile "${KEY_FILE}" --ssl-certfile "${CERT_FILE}")
fi

echo "🔒 Binding to: ${BIND_HOST}:${BIND_PORT} (LAN binding requires explicit AEONIX_BIND_HOST=0.0.0.0)"
exec uvicorn aeonix.core.server:app --host "${BIND_HOST}" --port "${BIND_PORT}" "${SSL_OPTS[@]}" --workers 1 --no-access-log
