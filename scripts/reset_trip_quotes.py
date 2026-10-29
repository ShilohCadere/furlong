"""Clear Europe 2027 notes, reset quotes, and merge duplicate options.
Run: python scripts/reset_trip_quotes.py --username scadere
Creates a database backup first. Applies only to the owned Europe 2027 trip.
"""
import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import os
import re
import sqlite3
import unicodedata

def clean_name(name):
    return re.sub(r"\s*\[sep research\]", "", name, flags=re.I).strip()

def key_name(name):
    name=unicodedata.normalize("NFKD",clean_name(name)).casefold()
    return "".join(c for c in name if c.isalnum())

def reset(db,username):
    db.row_factory=sqlite3.Row
    rows=db.execute("""SELECT t.id FROM trips t JOIN users u ON u.id=t.user_id
        WHERE u.username=? AND t.name='Europe 2027'""",(username,)).fetchall()
    if len(rows)!=1: raise ValueError("Expected one owned Europe 2027 trip.")
    tid=rows[0]["id"]
    options=db.execute("SELECT * FROM saved_options WHERE trip_id=?",(tid,)).fetchall()
    selected={r[0] for r in db.execute("""SELECT c.option_id FROM scenario_choices c
        JOIN trip_scenarios s ON s.id=c.scenario_id WHERE s.trip_id=?""",(tid,))}
    groups=defaultdict(list)
    for row in options:
        # Different scenarios, categories and stay dates remain independent.
        key=(row["scenario_tag"],row["city"].casefold(),row["category"],
             key_name(row["name"]),row["start_date"],row["end_date"])
        groups[key].append(row)
    removed=0
    for group in groups.values():
        # Prefer the selected ID, then the oldest original record.
        group.sort(key=lambda r:(r["id"] not in selected,r["id"]))
        keep=group[0]
        link=keep["link"] or next((r["link"] for r in group if r["link"]),None)
        preferred=max(r["is_preferred"] for r in group)
        for duplicate in group[1:]:
            # Redirect selections before deleting the duplicate.
            db.execute("UPDATE scenario_choices SET option_id=? WHERE option_id=?",
                       (keep["id"],duplicate["id"]))
            # Prevent legacy seed code from bringing back an alternate name.
            if duplicate["name"]!=keep["name"]:
                db.execute("""INSERT OR IGNORE INTO excluded_seed_options
                    (trip_id,city,category,name,scenario_tag) VALUES(?,?,?,?,?)""",
                    (tid,duplicate["city"],duplicate["category"],duplicate["name"],duplicate["scenario_tag"] or ""))
            db.execute("DELETE FROM saved_options WHERE id=?",(duplicate["id"],))
            removed+=1
        db.execute("UPDATE saved_options SET name=?,link=?,is_preferred=? WHERE id=?",
                   (clean_name(keep["name"]),link,preferred,keep["id"]))
    db.execute("UPDATE saved_options SET notes='',price=NULL WHERE trip_id=?",(tid,))
    db.execute("UPDATE scenario_itinerary SET notes='' WHERE trip_id=?",(tid,))
    db.execute("""UPDATE day_activities SET notes='' WHERE itinerary_id IN
        (SELECT id FROM scenario_itinerary WHERE trip_id=?)""",(tid,))
    return tid,removed

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username",required=True)
    parser.add_argument("--database",type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    path=args.database or Path(os.environ.get("FURLONG_DATA_DIR",str(root)))/"furlong.db"
    if not path.is_file(): parser.error("Existing database not found.")
    db=sqlite3.connect(str(path))
    db.execute("PRAGMA foreign_keys=ON")
    backup=path.with_name(path.name+".before-quote-reset-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".bak")
    with sqlite3.connect(str(backup)) as target: db.backup(target)
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            tid,removed=reset(db,args.username)
    finally: db.close()
    print("Notes cleared. All option prices set to Quote needed.")
    print("Duplicate options removed: "+str(removed))
    print("Backup: "+str(backup))
    print("Open /trip/"+str(tid)+"/workspace")

if __name__=="__main__": main()

