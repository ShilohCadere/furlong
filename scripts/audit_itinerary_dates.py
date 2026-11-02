"""Inspect Europe 2027 planner days against approved September schedules.

Read-only. Reports which imported days belong to each city stay, duplicate dates,
and out-of-window records. Does not modify legacy or planner data.
"""
import json,os,sqlite3
from collections import Counter
from datetime import date,timedelta
from pathlib import Path

SCHEDULES={
"12 OTG":[("Dublin","2027-09-15","2027-09-17"),("Galway","2027-09-17","2027-09-19"),("Edinburgh","2027-09-19","2027-09-22"),("Inverness","2027-09-22","2027-09-24"),("London","2027-09-24","2027-09-27")],
"14 OTG":[("Dublin","2027-09-14","2027-09-17"),("Galway","2027-09-17","2027-09-20"),("Edinburgh","2027-09-20","2027-09-23"),("Inverness","2027-09-23","2027-09-25"),("London","2027-09-25","2027-09-28")],
"Backwards 12 OTG":[("London","2027-09-15","2027-09-18"),("Inverness","2027-09-18","2027-09-20"),("Edinburgh","2027-09-20","2027-09-23"),("Galway","2027-09-23","2027-09-25"),("Dublin","2027-09-25","2027-09-27")],
"Backwards 14 OTG":[("London","2027-09-14","2027-09-17"),("Inverness","2027-09-17","2027-09-19"),("Edinburgh","2027-09-19","2027-09-22"),("Galway","2027-09-22","2027-09-25"),("Dublin","2027-09-25","2027-09-28")],
}
path=Path(os.environ.get("FURLONG_DATA_DIR","."))/"furlong.db"
con=sqlite3.connect(f"file:{path.resolve()}?mode=ro",uri=True)
con.row_factory=sqlite3.Row
trip=con.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()
if not trip:raise SystemExit("Europe 2027 not found")
row=con.execute("SELECT body FROM planner_trip_documents WHERE trip_id=?",(trip["id"],)).fetchone()
if not row:raise SystemExit("Planner data not yet imported")
state=json.loads(row["body"])
for scenario in state["scenarios"].values():
 name=scenario["name"]
 if name not in SCHEDULES:continue
 sid=scenario["id"]
 stops={s["id"]:s for s in state["stops"].values() if s.get("scenarioId")==sid}
 days=[d for d in state["days"].values() if d.get("scenarioId")==sid and not d.get("archived")]
 print("\\n"+name+" ("+str(len(days))+" imported days)")
 for city,start,end in SCHEDULES[name]:
  a=date.fromisoformat(start);b=date.fromisoformat(end)
  expected=[(a+timedelta(days=i)).isoformat() for i in range((b-a).days)]
  found=[d for d in days if (stops.get(d.get("stopId"),{}).get("location") or stops.get(d.get("stopId"),{}).get("name") or "").casefold()==city.casefold()]
  counts=Counter(d.get("date") for d in found)
  missing=[d for d in expected if not counts[d]]
  repeated=[d for d in expected if counts[d]>1]
  extra=[d.get("date") for d in found if d.get("date") not in expected]
  print(f"  {city} {start} to {end}: expected {len(expected)} nights; matching {sum(counts[d] for d in expected)}; missing {missing}; repeated {repeated}; other dates {len(extra)}")
 assigned=set()
 for city,start,end in SCHEDULES[name]:
  a=date.fromisoformat(start);b=date.fromisoformat(end)
  for d in days:
   loc=(stops.get(d.get("stopId"),{}).get("location") or stops.get(d.get("stopId"),{}).get("name") or "").casefold()
   if loc==city.casefold() and d.get("date") and a<=date.fromisoformat(d["date"])<b:assigned.add(d["id"])
 print("  Imported days not matching approved stays:",len(days)-len(assigned))
print("\\nREAD ONLY. No changes made.")
