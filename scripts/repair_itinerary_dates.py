"""Conservative itinerary repair: preserve activities and all research.
Dry-run by default; --apply backs up DB. Refuses unsafe scenarios.
"""
import argparse,json,os,sqlite3
from collections import defaultdict
from datetime import date,timedelta,datetime,timezone
from pathlib import Path

SCHEDULES={
"12 OTG":[("Dublin","2027-09-15",2),("Galway","2027-09-17",2),("Edinburgh","2027-09-19",3),("Inverness","2027-09-22",2),("London","2027-09-24",3)],
"14 OTG":[("Dublin","2027-09-14",3),("Galway","2027-09-17",3),("Edinburgh","2027-09-20",3),("Inverness","2027-09-23",2),("London","2027-09-25",3)],
"Backwards 12 OTG":[("London","2027-09-15",3),("Inverness","2027-09-18",2),("Edinburgh","2027-09-20",3),("Galway","2027-09-23",2),("Dublin","2027-09-25",2)],
"Backwards 14 OTG":[("London","2027-09-14",3),("Inverness","2027-09-17",2),("Edinburgh","2027-09-19",3),("Galway","2027-09-22",3),("Dublin","2027-09-25",3)],
}
p=argparse.ArgumentParser();p.add_argument("--apply",action="store_true");args=p.parse_args()
path=Path(os.environ.get("FURLONG_DATA_DIR","."))/"furlong.db"
con=sqlite3.connect(path);con.row_factory=sqlite3.Row
trip=con.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()
if not trip:raise SystemExit("Europe 2027 missing")
row=con.execute("SELECT * FROM planner_trip_documents WHERE trip_id=?",(trip["id"],)).fetchone()
if not row:raise SystemExit("Planner document missing")
state=json.loads(row["body"]);changes=[];warnings=[];blockers=[]
for sc in state["scenarios"].values():
 if sc["name"] not in SCHEDULES:continue
 sid=sc["id"];stops=[s for s in state["stops"].values() if s.get("scenarioId")==sid and not s.get("archived")]
 days=[d for d in state["days"].values() if d.get("scenarioId")==sid and not d.get("archived")]
 acts=defaultdict(list)
 for a in state["activities"].values():
  if a.get("scenarioId")==sid and not a.get("archived"):acts[a.get("dayId")].append(a)
 print("\n"+sc["name"])
 for city,start,nights in SCHEDULES[sc["name"]]:
  city_stops=[s for s in stops if (s.get("location") or s.get("name") or "").casefold()==city.casefold()]
  city_days=sorted([d for d in days if d.get("stopId") in {s["id"] for s in city_stops}],key=lambda d:(d.get("date") or "",d.get("position",0)))
  if not city_stops:
   blockers.append(f"{sc['name']}: missing stop {city}");continue
  expected=[(date.fromisoformat(start)+timedelta(days=j)).isoformat() for j in range(nights)]
  # Prefer existing correctly dated days, then the oldest dated days without activity, then dated days with activity.
  remaining=list(city_days);keep=[]
  for target in expected:
   match=next((d for d in remaining if d.get("date")==target),None)
   if match:
    keep.append((match,target));remaining.remove(match)
   else:keep.append((None,target))
  for index,(d,target) in enumerate(keep):
   if d is not None:continue
   if not remaining:
    blockers.append(f"{sc['name']} {city}: no day to assign to {target}");continue
   candidate=min(remaining,key=lambda d:(len(acts[d["id"]])>0,abs((date.fromisoformat(d["date"])-date.fromisoformat(target)).days) if d.get("date") else 9999))
   remaining.remove(candidate);keep[index]=(candidate,target)
  for index,(d,target) in enumerate(keep):
   if not d:continue
   if d.get("date")!=target:changes.append(("date",d,d.get("date"),target))
   if d.get("position")!=index:changes.append(("position",d,d.get("position"),index))
  for extra in remaining:
   if acts[extra["id"]]:
    blockers.append(f"{sc['name']} {city}: extra {extra.get('date')} has {len(acts[extra['id']])} activities; manual reconciliation needed")
   else:changes.append(("archive",extra,False,True))
  # Stop ranges can be normalized only when there is a single stop for the city.
  if len(city_stops)==1:
   st=city_stops[0]
   if st.get("startDate")!=start:changes.append(("startDate",st,st.get("startDate"),start))
   if st.get("nights")!=nights:changes.append(("nights",st,st.get("nights"),nights))
  else:warnings.append(f"{sc['name']} {city}: multiple stops; stop dates left unchanged")
 # Flag unmatched stops/days rather than silently removing them.
 known={c.casefold() for c,_,_ in SCHEDULES[sc["name"]]}
 for st in stops:
  if (st.get("location") or st.get("name") or "").casefold() not in known:
   warnings.append(f"{sc['name']}: extra stop {st.get('name')} preserved")
print(f"\nProposed changes: {len(changes)}")
from collections import Counter
print("By operation:",dict(Counter(c[0] for c in changes)))
for w in warnings:print("PRESERVED:",w)
for w in blockers:print("BLOCKER:",w)
if not args.apply:print("DRY RUN: no database changed.")
elif blockers:raise SystemExit("NOT APPLIED: unsafe records need review; no database changed.")
else:
 backup=path.with_name("furlong-before-dates-repair-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".db")
 dest=sqlite3.connect(backup);con.backup(dest);dest.close();print("Backup:",backup)
 for field,item,old,new in changes:item[field]=new
 con.execute("BEGIN IMMEDIATE")
 cur=con.execute("UPDATE planner_trip_documents SET body=?,revision=revision+1,updated_at=? WHERE trip_id=? AND revision=?",(json.dumps(state),datetime.now(timezone.utc).isoformat(),trip["id"],row["revision"]))
 if cur.rowcount!=1:con.rollback();raise SystemExit("Revision changed; repair aborted")
 con.commit();print("Applied safely. Legacy data and scenario-specific quotes untouched.")
con.close()
