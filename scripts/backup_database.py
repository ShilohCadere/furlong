"""Create a consistent SQLite backup without stopping Furlong.

Usage: python scripts/backup_database.py /secure/backups
Set FURLONG_DATA_DIR to the same persistent volume used by the app.
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/backup_database.py BACKUP_DIRECTORY")
    source = Path(os.environ.get("FURLONG_DATA_DIR", str(Path(__file__).resolve().parents[1]))).expanduser().resolve() / "furlong.db"
    if not source.is_file():
        raise SystemExit(f"Database not found: {source}")
    destination_dir = Path(sys.argv[1]).expanduser().resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    if destination_dir == source.parent:
        raise SystemExit("Backups must be stored outside the live database directory")
    destination = destination_dir / f"furlong-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.db"
    if destination.exists():
        raise SystemExit(f"Backup already exists: {destination}")
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as live:
        with sqlite3.connect(destination) as backup:
            live.backup(backup)
            integrity = backup.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                destination.unlink(missing_ok=True)
                raise SystemExit(f"Backup failed integrity check: {integrity}")
    destination.chmod(0o600)
    print(f"Verified backup: {destination}")

if __name__ == "__main__":
    main()
