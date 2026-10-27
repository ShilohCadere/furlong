"""Restore original S1/L1 day sections on their corrected September dates.
Source: europe_seed.py / EUROPE_DAILY_PLANS (blob dd612dbd).
Later castle decision retained: last Edinburgh night, not Galway.
Run: python scripts/repair_itinerary_sections.py --username scadere
"""
import argparse
from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import unicodedata

PLANS=json.loads(r'''{"S1": [["2027-09-15", "Transit", "St. Louis to Dublin", "St. Louis to Dublin"], ["2027-09-16", "Dublin", "Dublin arrival and easy city walk", "Dublin arrival and easy city walk"], ["2027-09-17", "Dublin", "Trinity College and historic Dublin", "Trinity College and historic Dublin"], ["2027-09-18", "Galway", "Train to Galway and city exploration", "Train to Galway and castle arrival"], ["2027-09-19", "Galway", "Cliffs of Moher and the Burren", "Cliffs of Moher and the Burren"], ["2027-09-20", "Edinburgh", "Galway to Edinburgh", "Galway to Edinburgh"], ["2027-09-21", "Edinburgh", "Edinburgh Castle and Royal Mile", "Edinburgh Castle and Royal Mile"], ["2027-09-22", "Edinburgh", "Flexible Edinburgh and castle stay", "Flexible Edinburgh"], ["2027-09-23", "Inverness", "Train to Inverness", "Train to Inverness"], ["2027-09-24", "Inverness", "Isle of Skye and Eilean Donan", "Isle of Skye and Eilean Donan"], ["2027-09-25", "London", "Fly to London", "Fly to London"], ["2027-09-26", "London", "Windsor Castle and Stonehenge", "Windsor Castle and Stonehenge"], ["2027-09-27", "London", "Tower of London and final evening", "Tower of London and final evening"], ["2027-09-28", "Departure", "Return to St. Louis", "Return to St. Louis"]], "L1": [["2027-09-13", "Transit", "St. Louis to Dublin", "St. Louis to Dublin"], ["2027-09-14", "Dublin", "Dublin arrival", "Dublin arrival"], ["2027-09-15", "Dublin", "Trinity, Book of Kells and Dublin heritage", "Trinity, Book of Kells and Dublin heritage"], ["2027-09-16", "Dublin", "Kilmainham Gaol and Guinness Storehouse", "Kilmainham Gaol and Guinness Storehouse"], ["2027-09-17", "Galway", "Train to Galway and city exploration", "Train west to Galway, castle check-in"], ["2027-09-18", "Galway", "Cliffs of Moher and the Burren", "Cliffs of Moher and the Burren"], ["2027-09-19", "Galway", "Connemara and Kylemore Abbey", "Connemara and Kylemore Abbey"], ["2027-09-20", "Edinburgh", "Galway to Edinburgh", "Galway to Edinburgh"], ["2027-09-21", "Edinburgh", "Edinburgh Castle and Old Town", "Edinburgh Castle and Old Town"], ["2027-09-22", "Edinburgh", "Stirling Castle or Rosslyn Chapel, then castle stay", "Stirling Castle or Rosslyn Chapel"], ["2027-09-23", "Inverness", "Highland rail journey to Inverness", "Highland rail journey to Inverness"], ["2027-09-24", "Inverness", "Isle of Skye and Eilean Donan", "Isle of Skye and Eilean Donan"], ["2027-09-25", "London", "Flight south to London", "Flight south to London"], ["2027-09-26", "London", "Windsor Castle and Stonehenge", "Windsor Castle and Stonehenge"], ["2027-09-27", "London", "Tower of London, Tower Bridge and farewell", "Tower of London, Tower Bridge and farewell"], ["2027-09-28", "Departure", "Flight home", "Flight home"]]}''')

def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKD",value).casefold() if c.isalnum())

def activity_date(title,city,plan,fallback):
    days=[d[0] for d in plan if d[1]==city]
    if not days:return fallback
    text=title.casefold()
    if city=="Dublin":
        if "arrival" in text:return days[0]
        if "trinity" in text or "kells" in text:return days[1]
        if "kilmainham" in text or "guinness" in text:return days[-1]
    if city=="Galway":
        if "connemara" in text or "kylemore" in text:return days[-1] if len(days)==3 else fallback
        if any(x in text for x in ("cliffs","burren","aran")):return days[1]
        if "arrival" in text or "train" in text:return days[0]
    if city=="Edinburgh":
        if any(x in text for x in ("rosslyn","stirling","melville","dalhousie")):return days[-1]
        if "edinburgh castle" in text:return days[1]
        if "arrival" in text or "galway to edinburgh" in text:return days[0]
    if city=="Inverness":
        if "skye" in text or "eilean donan" in text:return days[1]
        if "arrival" in text or "train" in text:return days[0]
    if city=="London":
        if "stonehenge" in text or "windsor" in text:return days[1]
        if "tower of london" in text or "tower bridge" in text:return days[2]
        if "arrival" in text or "flight" in text or "fly to london" in text:return days[0]
    return fallback

def repair(db,username):
    db.row_factory=sqlite3.Row
    trips=db.execute("""SELECT t.id FROM trips t JOIN users u ON u.id=t.user_id
        WHERE u.username=? AND t.name='Europe 2027'""",(username,)).fetchall()
    if len(trips)!=1:raise ValueError("Expected one owned Europe 2027 trip.")
    tid=trips[0]["id"]
    result=[]
    for variant,plan in PLANS.items():
        scenario=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name=?",(tid,variant)).fetchone()
        if not scenario:raise ValueError("Missing "+variant+"; no changes committed.")
        sid=scenario["id"]
        old=db.execute("SELECT * FROM scenario_itinerary WHERE scenario_id=? ORDER BY day_date,id",(sid,)).fetchall()
        ids={}
        source_titles={normalized(d[3]):d[0] for d in plan}
        # Keep existing IDs at the right dates, rebuilding headings from source.
        for day,city,title,_ in plan:
            row=next((r for r in old if r["day_date"]==day),None)
            if row:
                oid=row["id"]
                db.execute("UPDATE scenario_itinerary SET city=?,title=?,notes='' WHERE id=?",(city,title,oid))
            else:
                db.execute("INSERT INTO scenario_itinerary(trip_id,scenario_id,day_date,city,title,notes) VALUES(?,?,?,?,?,'')",(tid,sid,day,city,title))
                oid=db.execute("SELECT last_insert_rowid()").fetchone()[0]
            ids[day]=oid
        valid=set(ids)
        removed=0
        for row in old:
            fallback=row["day_date"] if row["day_date"] in valid else next((d[0] for d in plan if d[1]==row["city"]),plan[0][0])
            destination=source_titles.get(normalized(row["title"]),fallback)
            for activity in db.execute("SELECT * FROM day_activities WHERE itinerary_id=?",(row["id"],)).fetchall():
                day=activity_date(activity["title"],row["city"],plan,destination)
                db.execute("UPDATE day_activities SET itinerary_id=?,notes='' WHERE id=?",(ids[day],activity["id"]))
            if row["day_date"] not in valid:
                db.execute("DELETE FROM scenario_itinerary WHERE id=?",(row["id"],))
                removed+=1
        # Remove exact repeated activities only, retaining distinct choices/times.
        seen=set();duplicates=0
        for row in db.execute("""SELECT a.* FROM day_activities a JOIN scenario_itinerary d
            ON d.id=a.itinerary_id WHERE d.scenario_id=? ORDER BY a.id""",(sid,)).fetchall():
            key=(row["itinerary_id"],normalized(row["title"]),row["start_time"] or "")
            if key in seen:
                db.execute("DELETE FROM day_activities WHERE id=?",(row["id"],));duplicates+=1
            else:seen.add(key)
        db.execute("UPDATE trip_scenarios SET food_days=? WHERE id=?",(len(plan),sid))
        actual=[tuple(r) for r in db.execute("SELECT day_date,city,title,notes FROM scenario_itinerary WHERE scenario_id=? ORDER BY day_date",(sid,))]
        expected=[(d,c,t,"") for d,c,t,_ in plan]
        if actual!=expected:raise ValueError("Final "+variant+" verification failed.")
        result.append((variant,len(plan),removed,duplicates))
    return tid,result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username",required=True)
    parser.add_argument("--database",type=Path)
    args=parser.parse_args()
    path=args.database or Path(os.environ.get("FURLONG_DATA_DIR",str(Path(__file__).resolve().parents[1])))/"furlong.db"
    if not path.is_file():parser.error("Existing database not found.")
    db=sqlite3.connect(str(path));db.execute("PRAGMA foreign_keys=ON")
    backup=path.with_name(path.name+".before-itinerary-repair-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".bak")
    with sqlite3.connect(str(backup)) as target:db.backup(target)
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            tid,results=repair(db,args.username)
    finally:db.close()
    for variant,days,extra,duplicates in results:
        print(variant+": verified "+str(days)+" days; "+str(extra)+" extra day sections and "+str(duplicates)+" repeated activities removed.")
    print("Notes empty. Prices, selections and booking links unchanged.")
    print("Backup: "+str(backup))
    print("Open /trip/"+str(tid)+"/itinerary")
if __name__=="__main__":main()
