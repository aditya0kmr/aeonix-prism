"""
ÆONIX PRISM // Sovereign TLS Certificate & Transport Encryption Engine
Generates and manages sovereign self-signed X.509 certificates for encrypted WSS/HTTPS transport.
Provides deterministic SHA-256 certificate pinning for glass terminals.
"""

import os
import json
import time
import datetime
import ipaddress
from typing import Tuple, Dict, Any, Optional

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from aeonix.core.auth import SECRETS_DIR

CERT_FILE = os.path.join(SECRETS_DIR, "aeonix_cert.pem")
KEY_FILE = os.path.join(SECRETS_DIR, "aeonix_key.pem")
PIN_FILE = os.path.join(SECRETS_DIR, "cert_fingerprint.json")


def ensure_sovereign_tls_credentials(
    secrets_dir: str = SECRETS_DIR,
    primary_ip: str = "10.116.23.168"
) -> Tuple[str, str, str]:
    """
    Ensures sovereign TLS certificate and key exist in secrets directory.
    Returns (cert_path: str, key_path: str, sha256_fingerprint: str).
    """
    os.makedirs(secrets_dir, mode=0o700, exist_ok=True)
    cert_path = os.path.join(secrets_dir, "aeonix_cert.pem")
    key_path = os.path.join(secrets_dir, "aeonix_key.pem")
    pin_path = os.path.join(secrets_dir, "cert_fingerprint.json")

    if os.path.exists(cert_path) and os.path.exists(key_path) and os.path.exists(pin_path):
        try:
            with open(pin_path, "r") as f:
                data = json.load(f)
                return cert_path, key_path, data["sha256_fingerprint"]
        except Exception:
            pass

    # Generate 2048-bit RSA private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )

    # Subject and Issuer (Self-Signed Sovereign Root)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AEONIX PRISM Sovereign Mind"),
        x509.NameAttribute(NameOID.COMMON_NAME, "aeonix-core.local"),
    ])

    # Subject Alternative Names (SAN)
    san_list = [
        x509.DNSName("localhost"),
        x509.DNSName("aeonix-core.local"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ]
    try:
        san_list.append(x509.IPAddress(ipaddress.IPv4Address(primary_ip)))
    except Exception:
        pass

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650)) # 10-year sovereign certificate
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )

    # Compute SHA-256 fingerprint
    fingerprint = cert.fingerprint(hashes.SHA256()).hex().upper()

    # Write private key with 0600 mode
    key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    with open(key_path, "wb") as f:
        f.write(key_bytes)
    os.chmod(key_path, 0o600)

    # Write certificate with 0644 mode
    cert_bytes = cert.public_bytes(serialization.Encoding.PEM)
    with open(cert_path, "wb") as f:
        f.write(cert_bytes)
    os.chmod(cert_path, 0o644)

    # Write fingerprint pin file with 0600 mode
    with open(pin_path, "w") as f:
        json.dump({
            "sha256_fingerprint": fingerprint,
            "created_at": time.time(),
            "common_name": "aeonix-core.local",
            "primary_ip": primary_ip
        }, f, indent=2)
    os.chmod(pin_path, 0o600)

    return cert_path, key_path, fingerprint


def get_cert_fingerprint(secrets_dir: str = SECRETS_DIR) -> str:
    _, _, fp = ensure_sovereign_tls_credentials(secrets_dir=secrets_dir)
    return fp
