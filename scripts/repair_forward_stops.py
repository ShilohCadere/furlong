"""Repair forward itinerary stop dates without deleting research.

Dry run by default. --apply creates a SQLite backup. Only the two
forward Europe 2027 scenarios are modified.
"""
import argparse
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCHEDULES = {
    "12 OTG": [("Dublin", "2027-09-15", 2), ("Galway", "2027-09-17", 2),
               ("Edinburgh", "2027-09-19", 3), ("Inverness", "2027-09-22", 2),
               ("London", "2027-09-24", 3)],
    "14 OTG": [("Dublin", "2027-09-14", 3), ("Galway", "2027-09-17", 3),
               ("Edinburgh", "2027-09-20", 3), ("Inverness", "2027-09-23", 2),
               ("London", "2027-09-25", 3)],
}
parser = argparse.ArgumentParser()
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()
path = Path(os.environ.get("FURLONG_DATA_DIR", ".")) / "furlong.db"
db = sqlite3.connect(path)
db.row_factory = sqlite3.Row
trip = db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()
if not trip:
    raise SystemExit("Europe 2027 not found")
row = db.execute("SELECT * FROM planner_trip_documents WHERE trip_id=?", (trip["id"],)).fetchone()
if not row:
    raise SystemExit("Planner document not found")
state = json.loads(row["body"])
changes = []
blockers = []
redirect = {}

def change(obj, field, value):
    if obj.get(field) != value:
        changes.append((obj, field, obj.get(field), value))

def city_of(stop):
    return (stop.get("location") or stop.get("name") or "").strip().casefold()

for scenario in state["scenarios"].values():
    name = scenario.get("name")
    if name not in SCHEDULES or scenario.get("archived"):
        continue
    sid = scenario["id"]
    change(scenario, "startDate", SCHEDULES[name][0][1])
    print("\n" + name)
    for city, start, nights in SCHEDULES[name]:
        matches = [st for st in state["stops"].values()
                   if st.get("scenarioId") == sid and not st.get("archived")
                   and city_of(st) == city.casefold()]
        if not matches:
            blockers.append(name + ": missing " + city)
            continue
        def score(st):
            key = st["id"]
            days = sum(d.get("stopId") == key and not d.get("archived")
                       for d in state["days"].values())
            groups = sum(g.get("stopId") == key and not g.get("archived")
                         for g in state["groups"].values())
            return (days + groups, st.get("startDate") == start)
        primary = max(matches, key=score)
        change(primary, "startDate", start)
        change(primary, "nights", nights)
        print(" ", city, len(matches), "active stops")
        for duplicate in matches:
            if duplicate["id"] == primary["id"]:
                continue
            redirect[duplicate["id"]] = primary["id"]
            change(duplicate, "archived", True)

# Redirect references in the affected scenarios. Preserve every referenced
# day, decision group, option, activity, and quote.
target_ids = {s["id"] for s in state["scenarios"].values()
              if s.get("name") in SCHEDULES and not s.get("archived")}
def rewrite(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("stopId", "fromStopId", "toStopId") and isinstance(child, str):
                if child in redirect:
                    change(value, key, redirect[child])
            elif isinstance(child, (dict, list)):
                rewrite(child)
    elif isinstance(value, list):
        for child in value:
            rewrite(child)

for collection, records in state.items():
    if not isinstance(records, dict) or collection in ("scenarios", "stops"):
        continue
    for entity in records.values():
        if isinstance(entity, dict) and entity.get("scenarioId") in target_ids:
            rewrite(entity)

# Block if any active day or group would retain a reference to an archived stop.
for collection in ("days", "groups"):
    for entity in state[collection].values():
        if entity.get("scenarioId") in target_ids and not entity.get("archived"):
            if entity.get("stopId") in redirect:
                if not any(obj is entity and field == "stopId" for obj, field, _, _ in changes):
                    blockers.append("Unredirected " + collection + " reference")

print("\nProposed changes:", len(changes), dict(Counter(field for _, field, _, _ in changes)))
for item in blockers:
    print("BLOCKER:", item)
if not args.apply:
    print("DRY RUN: database unchanged")
elif blockers:
    raise SystemExit("NOT APPLIED: unresolved references")
else:
    backup = path.with_name("furlong-before-forward-stop-repair-" +
                            datetime.now().strftime("%Y%m%d-%H%M%S") + ".db")
    destination = sqlite3.connect(backup)
    db.backup(destination)
    destination.close()
    print("Backup:", backup)
    for obj, field, old, new in changes:
        obj[field] = new
    db.execute("BEGIN IMMEDIATE")
    result = db.execute(
        "UPDATE planner_trip_documents SET body=?, revision=revision+1, updated_at=? "
        "WHERE trip_id=? AND revision=?",
        (json.dumps(state), datetime.now(timezone.utc).isoformat(),
         trip["id"], row["revision"]))
    if result.rowcount != 1:
        db.rollback()
        raise SystemExit("Concurrent update detected; rolled back")
    db.commit()
    print("Applied forward itinerary stop repair; backwards scenarios untouched")
db.close()
