"""Issue one-time private beta invitations from a trusted administrator shell.

Usage:
  FURLONG_PUBLIC_URL=https://your-domain.example python scripts/issue_beta_invitation.py tester@example.com

This command runs on the server with access to the persistent Furlong database.
It has no HTTP endpoint and prints the invitation URL once. Treat it as a secret.
"""
import hashlib
import os
import secrets
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import quote


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/issue_beta_invitation.py email@example.com")
    email = sys.argv[1].strip().lower()
    if not email or len(email) > 254 or "@" not in email or any(c.isspace() for c in email):
        raise SystemExit("Provide a valid email address.")
    origin = os.environ.get("FURLONG_PUBLIC_URL", "").rstrip("/")
    if not origin.startswith("https://") or "/" in origin[8:]:
        raise SystemExit("Set FURLONG_PUBLIC_URL to an HTTPS origin without a path.")
    data_dir = Path(os.environ.get("FURLONG_DATA_DIR", str(Path(__file__).resolve().parents[1]))).expanduser().resolve()
    database = data_dir / "furlong.db"
    if not database.is_file():
        raise SystemExit("Furlong database does not exist. Start the application to initialize it.")
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = int(time.time())
    with sqlite3.connect(database) as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone():
            raise SystemExit("That email is already registered.")
        # Supersede any outstanding invitations for this email.
        db.execute("DELETE FROM beta_invitations WHERE email=? COLLATE NOCASE AND used_at IS NULL", (email,))
        db.execute("INSERT INTO beta_invitations(token_hash,email,expires_at) VALUES (?,?,?)",
                   (digest, email, now + 7 * 86400))
    print("Send this invitation URL privately to " + email + ":")
    print(origin + "/register?invitation=" + quote(token))


if __name__ == "__main__":
    main()
