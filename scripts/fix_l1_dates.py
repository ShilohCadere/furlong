"""Correct existing L1 to September 13–28, 2027 without changing S1.
Run: python scripts/fix_l1_dates.py --username scadere
Backs up the existing database. Does not create prices or write planning notes.
"""
import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import os
import sqlite3

SLOTS={
 "Transit":["2027-09-13"],
 "Dublin":["2027-09-14","2027-09-15","2027-09-16"],
 "Galway":["2027-09-17","2027-09-18","2027-09-19"],
 "Edinburgh":["2027-09-20","2027-09-21","2027-09-22"],
 "Inverness":["2027-09-23","2027-09-24"],
 "London":["2027-09-25","2027-09-26","2027-09-27"],
 "Departure":["2027-09-28"]}
STAYS={"Dublin":("2027-09-14","2027-09-17"),"Galway":("2027-09-17","2027-09-20"),
 "Edinburgh":("2027-09-20","2027-09-22"),"Inverness":("2027-09-23","2027-09-25"),
 "London":("2027-09-25","2027-09-28")}

def fix(db,username):
    db.row_factory=sqlite3.Row
    matches=db.execute("""SELECT t.id AS trip_id,s.id AS scenario_id FROM trips t
        JOIN users u ON u.id=t.user_id JOIN trip_scenarios s ON s.trip_id=t.id
        WHERE u.username=? AND t.name='Europe 2027' AND s.name='L1'""",(username,)).fetchall()
    if len(matches)!=1:raise ValueError("Expected one owned Europe 2027 / L1 itinerary.")
    tid,sid=matches[0]["trip_id"],matches[0]["scenario_id"]
    rows=db.execute("SELECT * FROM scenario_itinerary WHERE scenario_id=? ORDER BY day_date,id",(sid,)).fetchall()
    if not rows:raise ValueError("L1 has no itinerary days.")
    assigned=defaultdict(list)
    for index,row in enumerate(rows):
        city=row["city"]
        if city not in SLOTS:
            if index==0:city="Transit"
            elif index==len(rows)-1:city="Departure"
            else:raise ValueError("Unrecognized L1 city: "+repr(city)+". No changes committed.")
        assigned[city].append(row)
    date_map={}
    for city,items in assigned.items():
        for i,row in enumerate(items):
            date_map[row["day_date"]]=SLOTS[city][min(i,len(SLOTS[city])-1)]
    # Temporary dates prevent uniqueness conflicts; linked activity IDs survive.
    for row in rows:db.execute("UPDATE scenario_itinerary SET day_date=? WHERE id=?",("fixing-"+str(row["id"]),row["id"]))
    for city,slots in SLOTS.items():
        items=assigned[city]
        for i,day in enumerate(slots):
            if i<len(items):
                keep=items[i]["id"]
                db.execute("UPDATE scenario_itinerary SET day_date=?,city=? WHERE id=?",(day,city,keep))
            else:
                title={"Transit":"Depart STL","Departure":"Return London → STL"}.get(city,city+" · flexible day")
                db.execute("""INSERT INTO scenario_itinerary(trip_id,scenario_id,day_date,city,title,notes)
                    VALUES(?,?,?,?,?,'')""",(tid,sid,day,city,title))
                keep=db.execute("SELECT last_insert_rowid()").fetchone()[0]
            if i==len(slots)-1:
                for extra in items[len(slots):]:
                    db.execute("UPDATE day_activities SET itinerary_id=? WHERE itinerary_id=?",(keep,extra["id"]))
                    db.execute("DELETE FROM scenario_itinerary WHERE id=?",(extra["id"],))
    for option in db.execute("SELECT * FROM saved_options WHERE trip_id=? AND scenario_tag='L1'",(tid,)).fetchall():
        city,cat=option["city"],option["category"]
        start=date_map.get(option["start_date"],option["start_date"])
        end=date_map.get(option["end_date"],option["end_date"])
        if cat=="hotel" and city in STAYS:
            start,end=STAYS[city]
            if city=="Edinburgh" and " + " in option["name"] and "Castle" in option["name"]:end="2027-09-23"
        elif cat=="castle" and city=="Edinburgh":start,end="2027-09-22","2027-09-23"
        elif cat=="flight":
            route=(city+" "+(option["origin"] or "")+" "+(option["destination"] or "")).casefold()
            if ("dublin" in route or "dub" in route) and ("edinburgh" in route or "edi" in route):start=end="2027-09-20"
            elif "inverness" in route or "inv" in route:start=end="2027-09-25"
            elif "international" in route or "stl" in route:start,end="2027-09-13","2027-09-28"
        db.execute("UPDATE saved_options SET start_date=?,end_date=? WHERE id=?",(start,end,option["id"]))
    db.execute("UPDATE trip_scenarios SET food_days=16 WHERE id=?",(sid,))
    actual=[r[0] for r in db.execute("SELECT day_date FROM scenario_itinerary WHERE scenario_id=? ORDER BY day_date",(sid,))]
    expected=sorted(d for slots in SLOTS.values() for d in slots)
    if actual!=expected:raise ValueError("L1 date verification failed; no changes committed.")
    return tid,sid

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--username",required=True)
    p.add_argument("--database",type=Path)
    args=p.parse_args()
    path=args.database or Path(os.environ.get("FURLONG_DATA_DIR",str(Path(__file__).resolve().parents[1])))/"furlong.db"
    if not path.is_file():p.error("Existing database not found.")
    db=sqlite3.connect(str(path));db.execute("PRAGMA foreign_keys=ON")
    backup=path.with_name(path.name+".before-l1-fix-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".bak")
    with sqlite3.connect(str(backup)) as target:db.backup(target)
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            tid,sid=fix(db,args.username)
    finally:db.close()
    print("Verified L1: September 13–28, 2027; 16 days / 14 hotel nights. S1 unchanged.")
    print("Backup: "+str(backup))
    print("Open /trip/"+str(tid)+"/itinerary?scenario="+str(sid))
if __name__=="__main__":main()
