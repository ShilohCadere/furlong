"""Consolidate duplicate shared Ideas without changing scenario-specific options.

Default: dry run. --apply creates a timestamped SQLite backup and updates only
planner JSON documents. Legacy saved_options and itinerary dates are untouched.
"""
import argparse
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument("--apply",action="store_true")
args=p.parse_args()
path=Path(os.environ.get("FURLONG_DATA_DIR","."))/"furlong.db"
if not path.exists():raise SystemExit(f"Database missing: {path}")
conn=sqlite3.connect(path)
conn.row_factory=sqlite3.Row
def norm(x):return " ".join(str(x or "").casefold().split())
def score(i):return (bool(i.get("website"))*2+bool(i.get("notes"))+bool(i.get("image"))+bool(i.get("favorite")))
def utc():return datetime.now(timezone.utc).isoformat()
users=list(conn.execute("SELECT user_id,revision,body FROM planner_user_documents"))
trips=list(conn.execute("SELECT trip_id,revision,body FROM planner_trip_documents"))
updated_users={}
updated_trips={r["trip_id"]:json.loads(r["body"]) for r in trips}
rewrites={}
for row in users:
    user=json.loads(row["body"])
    groups=defaultdict(list)
    for idea in user.get("ideas",{}).values():
        if not idea.get("archived"):
            groups[(norm(idea.get("location")),norm(idea.get("type")),norm(idea.get("name")))].append(idea)
    merged=0
    for group in groups.values():
        if len(group)<2:continue
        canonical=max(group,key=lambda i:(score(i),i["id"]))
        for idea in group:
            if idea["id"]==canonical["id"]:continue
            rewrites[idea["id"]]=canonical["id"]
            # Preserve the original record and all metadata as an archived historical copy.
            idea["archived"]=True
            idea["mergedInto"]=canonical["id"]
            merged+=1
    updated_users[row["user_id"]]=user
    print(f"User {row['user_id']}: {merged} redundant Ideas archived; {len(groups)} unique active identities")
changed_trips=0
for row in trips:
    state=updated_trips[row["trip_id"]]
    changed=0
    for collection in ("options","activities"):
        for item in state.get(collection,{}).values():
            old=item.get("ideaId")
            if old in rewrites:
                item["ideaId"]=rewrites[old]
                changed+=1
    if changed:changed_trips+=1
    print(f"Trip {row['trip_id']}: {changed} scenario-specific references redirected; dates/quotes untouched")
print(f"Total duplicates: {len(rewrites)}. Planner documents affected: {changed_trips}.")
if not args.apply:
    print("DRY RUN ONLY. To perform backed-up repair, run with --apply.")
else:
    backup=path.with_name("furlong-before-ideas-repair-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".db")
    dest=sqlite3.connect(backup)
    conn.backup(dest)
    dest.close()
    print("SQLite backup:",backup)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for row in users:
            conn.execute("UPDATE planner_user_documents SET body=?,revision=revision+1,updated_at=? WHERE user_id=? AND revision=?",
                (json.dumps(updated_users[row["user_id"]]),utc(),row["user_id"],row["revision"]))
            if conn.total_changes<1:raise RuntimeError("User revision conflict")
        for row in trips:
            conn.execute("UPDATE planner_trip_documents SET body=?,revision=revision+1,updated_at=? WHERE trip_id=? AND revision=?",
                (json.dumps(updated_trips[row["trip_id"]]),utc(),row["trip_id"],row["revision"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    print("Repair committed. Original records archived, not deleted. Restart/refresh planner.")
conn.close()
