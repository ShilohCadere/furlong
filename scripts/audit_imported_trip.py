"""Read-only audit of Furlong's imported planner data. No records are changed."""
import json
import os
import sqlite3
from collections import defaultdict
from pathlib import Path

db = Path(os.environ.get("FURLONG_DATA_DIR", ".")) / "furlong.db"
if not db.is_file():
    raise SystemExit(f"Database not found: {db}")
con = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

def norm(value):
    return " ".join(str(value or "").casefold().split())

print("DATABASE AUDIT (READ ONLY)")
print("Database:", db)
for trip in con.execute("SELECT id,name FROM trips ORDER BY id"):
    tid = trip["id"]
    print(f"\nTRIP {tid}: {trip['name']}")
    legacy = list(con.execute("SELECT id,name FROM trip_scenarios WHERE trip_id=? ORDER BY id", (tid,)))
    for scenario in legacy:
        dates = con.execute("SELECT MIN(day_date),MAX(day_date),COUNT(*) FROM scenario_itinerary WHERE trip_id=? AND scenario_id=?", (tid,scenario["id"])).fetchone()
        print(f"  Legacy scenario {scenario['id']}: {scenario['name']} | {dates[0]} to {dates[1]} | {dates[2]} days")
    row = con.execute("SELECT body FROM planner_trip_documents WHERE trip_id=?", (tid,)).fetchone()
    if row:
        body = json.loads(row["body"])
        for sc in body.get("scenarios", {}).values():
            days = sorted(d["date"] for d in body.get("days", {}).values() if d.get("scenarioId")==sc["id"] and d.get("date") and not d.get("archived"))
            print(f"  Planner scenario: {sc['name']} | {days[0] if days else '-'} to {days[-1] if days else '-'} | {len(days)} dated days | archived={sc.get('archived',False)}")
    rows = list(con.execute("SELECT id,name,category,city,link,notes,scenario_tag FROM saved_options WHERE trip_id=? ORDER BY id",(tid,)))
    groups=defaultdict(list)
    for r in rows:groups[(norm(r["city"]),norm(r["category"]),norm(r["name"]))].append(r)
    duplicates=[v for v in groups.values() if len(v)>1]
    print(f"  Legacy research: {len(rows)} rows, {len(groups)} distinct city/type/name groups, {sum(len(v)-1 for v in duplicates)} excess rows")
    for group in sorted(duplicates,key=lambda v:(-len(v),norm(v[0]["name"])))[:30]:
        links=len(set(norm(r["link"]) for r in group))
        notes=len(set(norm(r["notes"]) for r in group))
        tags=sorted(set(str(r["scenario_tag"] or "shared") for r in group))
        print(f"    {group[0]['city']} / {group[0]['category']} / {group[0]['name']}: {len(group)} rows; link variants={links}; note variants={notes}; scenario tags={tags}")
    if len(duplicates)>30:print(f"    ... {len(duplicates)-30} additional duplicate groups")
users=list(con.execute("SELECT user_id,body FROM planner_user_documents"))
for user in users:
    ideas=json.loads(user["body"]).get("ideas",{})
    groups=defaultdict(list)
    for idea in ideas.values():
        if not idea.get("archived"):groups[(norm(idea.get("location")),norm(idea.get("type")),norm(idea.get("name")))].append(idea)
    print(f"\nPLANNER LIBRARY user_id={user['user_id']}: {len(ideas)} ideas, {sum(len(v)-1 for v in groups.values() if len(v)>1)} repeated city/type/name entries")
print("\nAudit complete. Database unchanged.")
