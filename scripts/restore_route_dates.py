"""Restore S1/L1 lengths, retaining the shared September 28 return.
Run: python scripts/restore_route_dates.py --username scadere
Existing Europe 2027 database only; backup before changes.
"""
import argparse
import os
import sqlite3
from datetime import date, timedelta, datetime
from pathlib import Path

STAYS={
 "S1":{"Dublin":("2027-09-16","2027-09-18"),"Galway":("2027-09-18","2027-09-20")},
 "L1":{"Dublin":("2027-09-14","2027-09-17"),"Galway":("2027-09-17","2027-09-20")}
}
COMMON={"Edinburgh":("2027-09-20","2027-09-22"),"Inverness":("2027-09-23","2027-09-25"),"London":("2027-09-25","2027-09-28")}

def restore(db, username):
    db.row_factory=sqlite3.Row
    trips=db.execute("""SELECT t.id FROM trips t JOIN users u ON u.id=t.user_id
        WHERE u.username=? AND t.name='Europe 2027'""",(username,)).fetchall()
    if len(trips)!=1: raise ValueError("Expected one owned Europe 2027 trip.")
    tid=trips[0]["id"]
    db.execute("""CREATE TABLE IF NOT EXISTS research_updates
        (trip_id INTEGER,scenario_id INTEGER,version TEXT,PRIMARY KEY(trip_id,scenario_id,version))""")
    plans=db.execute("SELECT id,name FROM trip_scenarios WHERE trip_id=? AND name IN ('S1','L1')",(tid,)).fetchall()
    if len(plans)!=2: raise ValueError("Both existing S1 and L1 are required.")
    for plan in plans:
        sid,variant=plan["id"],plan["name"]
        marker="restore-true-lengths-september-2027-v1"
        if db.execute("SELECT 1 FROM research_updates WHERE trip_id=? AND scenario_id=? AND version=?",(tid,sid,marker)).fetchone():
            continue
        days=db.execute("SELECT * FROM scenario_itinerary WHERE scenario_id=? ORDER BY day_date",(sid,)).fetchall()
        if not days or days[0]["day_date"]!="2027-09-14" or days[-1]["day_date"]!="2027-09-28" or len(days)!=15:
            raise ValueError(variant+": expected the previous September 14–28 update. No changes committed.")
        def move(value):
            if not value: return value
            d=date.fromisoformat(value)
            if not date(2027,9,14)<=d<=date(2027,9,28):
                raise ValueError("Option date outside the expected September itinerary: "+value)
            if variant=="S1":
                return min(d+timedelta(days=1),date(2027,9,27)).isoformat() if d<date(2027,9,28) else value
            return (d-timedelta(days=1)).isoformat() if d<=date(2027,9,16) else value
        for row in db.execute("SELECT * FROM saved_options WHERE trip_id=? AND scenario_tag=?",(tid,variant)).fetchall():
            start,end=move(row["start_date"]),move(row["end_date"])
            if row["category"]=="hotel":
                pair={**COMMON,**STAYS[variant]}.get(row["city"])
                if pair: start,end=pair
                # Historical bundled Edinburgh alternatives remain archived,
                # with the full city+castle span rather than two city nights.
                if row["city"]=="Edinburgh" and " + " in row["name"] and "Castle" in row["name"]:
                    start,end="2027-09-20","2027-09-23"
            elif row["category"]=="castle" and row["city"]=="Edinburgh":
                start,end="2027-09-22","2027-09-23"
            db.execute("UPDATE saved_options SET start_date=?,end_date=? WHERE id=?",(start,end,row["id"]))
        for row in days:
            db.execute("UPDATE scenario_itinerary SET day_date=? WHERE id=?",("moving-"+str(row["id"]),row["id"]))
        used={}
        for row in days:
            day=move(row["day_date"])
            if day in used:
                keep=used[day]
                # Preserve any activities on the removed flexible day.
                db.execute("UPDATE day_activities SET itinerary_id=? WHERE itinerary_id=?",(keep,row["id"]))
                db.execute("DELETE FROM scenario_itinerary WHERE id=?",(row["id"],))
            else:
                db.execute("UPDATE scenario_itinerary SET day_date=? WHERE id=?",(day,row["id"]))
                used[day]=row["id"]
        if variant=="L1":
            db.execute("""INSERT INTO scenario_itinerary(trip_id,scenario_id,day_date,city,title,notes)
                VALUES(?,?,'2027-09-16','Dublin','Flexible Dublin','')""",(tid,sid))
        db.execute("UPDATE trip_scenarios SET food_days=? WHERE id=?",(14 if variant=="S1" else 16,sid))
        db.execute("INSERT INTO research_updates VALUES(?,?,?)",(tid,sid,marker))
    return tid

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--username",required=True)
    p.add_argument("--database",type=Path)
    args=p.parse_args()
    path=args.database or Path(os.environ.get("FURLONG_DATA_DIR",str(Path(__file__).resolve().parents[1])))/"furlong.db"
    if not path.is_file():p.error("Existing database not found.")
    db=sqlite3.connect(str(path));db.execute("PRAGMA foreign_keys=ON")
    backup=path.with_name(path.name+".before-route-dates-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".bak")
    with sqlite3.connect(str(backup)) as target:db.backup(target)
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            tid=restore(db,args.username)
    finally:db.close()
    print("S1: September 15–28, 2027; 12 hotel nights.")
    print("L1: September 13–28, 2027; 14 hotel nights.")
    print("Backup: "+str(backup))
    print("Open /trip/"+str(tid)+"/workspace")
if __name__=="__main__": main()
