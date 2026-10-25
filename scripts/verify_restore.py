"""Check whether a backup can be restored to a fresh SQLite database.

Usage: python scripts/verify_restore.py /secure/backups/furlong-....db
Never overwrites the running database.
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/verify_restore.py BACKUP_FILE")
    source = Path(sys.argv[1]).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Backup not found: {source}")
    with tempfile.TemporaryDirectory() as temp:
        restored = Path(temp) / "restored.db"
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as backup:
            with sqlite3.connect(restored) as target:
                backup.backup(target)
                integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
                required = {"users", "trips", "trip_scenarios", "saved_options"}
                tables = {r[0] for r in target.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if integrity != "ok" or not required.issubset(tables):
                    raise SystemExit(f"Restore verification failed: integrity={integrity}, missing={required - tables}")
                print("Restore verification passed (temporary database only).")

if __name__ == "__main__":
    main()
