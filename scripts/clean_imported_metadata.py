"""Clean imported itinerary metadata conservatively.

Only archive empty pre-September stops and update scenario start dates.
Do not touch researched options, quotes, legacy records or bookings.
Default dry-run. --apply makes SQLite backup first.
"""
import argparse,json,os,sqlite3
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
START={"12 OTG":"2027-09-15","14 OTG":"2027-09-14","Backwards 12 OTG":"2027-09-15","Backwards 14 OTG":"2027-09-14"}
p=argparse.ArgumentParser();p.add_argument("--apply",action="store_true");a=p.parse_args()
path=Path(os.environ.get("FURLONG_DATA_DIR","."))/"furlong.db"
db=sqlite3.connect(path);db.row_factory=sqlite3.Row
trip=db.execute("SELECT id FROM trips WHERE name='Europe 2027'").fetchone()
if not trip:raise SystemExit("Europe 2027 trip missing")
row=db.execute("SELECT * FROM planner_trip_documents WHERE trip_id=?",(trip["id"],)).fetchone()
if not row:raise SystemExit("Planner trip document missing")
state=json.loads(row["body"]);changes=[];blocked=[]
for sc in state["scenarios"].values():
 if sc["name"] not in START:continue
 sid=sc["id"];start=START[sc["name"]]
 if sc.get("startDate")!=start:changes.append((sc,"startDate",start))
 for st in state["stops"].values():
  if st.get("scenarioId")!=sid or st.get("archived") or not st.get("startDate") or st["startDate"]>=start:continue
  day_refs=[d for d in state["days"].values() if d.get("stopId")==st["id"] and not d.get("archived")]
  group_refs=[g for g in state["groups"].values() if g.get("stopId")==st["id"] and not g.get("archived")]
  if day_refs or group_refs:
   blocked.append(f"{sc['name']} / {st['name']} / {st['startDate']}: {len(day_refs)} live days, {len(group_refs)} decision groups; retained")
  else:changes.append((st,"archived",True))
print("Proposed metadata updates:",len(changes),dict(Counter(field for _,field,_ in changes)))
for msg in blocked:print("PRESERVED FOR RECONCILIATION:",msg)
if not a.apply:print("DRY RUN ONLY")
elif not changes:print("No safe metadata updates needed")
else:
 backup=path.with_name("furlong-before-metadata-cleanup-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".db")
 target=sqlite3.connect(backup);db.backup(target);target.close();print("Backup:",backup)
 for obj,key,value in changes:obj[key]=value
 db.execute("BEGIN IMMEDIATE")
 cur=db.execute("UPDATE planner_trip_documents SET body=?,revision=revision+1,updated_at=? WHERE trip_id=? AND revision=?",(json.dumps(state),datetime.now(timezone.utc).isoformat(),trip["id"],row["revision"]))
 if cur.rowcount!=1:db.rollback();raise SystemExit("Concurrent edit detected; aborted")
 db.commit();print("Metadata updated; linked records and quotes untouched")
db.close()
