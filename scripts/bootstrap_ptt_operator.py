#!/usr/bin/env python3
"""
ÆONIX PRISM // Sovereign PTT Operator Local Bootstrap CLI
Generates a short-lived (5 min), single-use 128-bit bootstrap secret for operator authentication.
Enforces interactive terminal execution to reduce accidental tool/subagent output capture.
Stores only SHA-256 hash in sovereign vault; secret is revealed only to the operator on screen.

Security Scope:
- Interactive TTY enforcement reduces automated transcript logging and piped captures.
- Does NOT guarantee secrecy against PTY capture, terminal recorders (script, asciinema),
  screenshots, shoulder surfing, or system clipboard exposure.
"""

import sys
import os

# Ensure aeonix package is resolvable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aeonix.core.auth import generate_bootstrap_secret
from aeonix.core.db import get_db_path

def main():
    # Enforce interactive terminal strictly with zero bypass flags
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.stderr.write("[!] REFUSED: Bootstrap generation requires an interactive terminal.\n")
        sys.stderr.write("[!] Run interactively in the local POCO Termux shell to prevent log capture.\n")
        sys.exit(1)

    db_path = get_db_path()
    secret, _ = generate_bootstrap_secret(ttl_seconds=300, db_path=db_path)

    print("\n" + "=" * 65)
    print(">>> ÆONIX PRISM // SOVEREIGN PTT OPERATOR BOOTSTRAP <<<")
    print("=" * 65)
    print(f"Single-Use Bootstrap Secret: {secret}")
    print("Validity: 300 seconds (5 minutes, single exchange only)")
    print("Vault: " + db_path)
    print("Scope: Exchanges for a 15-minute ROLE_PTT_OPERATOR session token")
    print("Security Invariant: Generating a new secret invalidates any previous one.")
    print("Instructions:")
    print("  1. Open https://<lan-ip>:8443/ui/ptt in POCO Chrome")
    print("  2. Enter the secret into the console authentication modal")
    print("  3. Token is held strictly in volatile browser JavaScript memory")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
