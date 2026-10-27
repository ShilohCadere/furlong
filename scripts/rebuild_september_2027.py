"""Update existing S1 to September 14–28 and add research to an existing Furlong trip.

Run from repository root:
  python scripts/rebuild_september_2027.py --username scadere
Uses the existing database only. Backs it up before writing. Retimes S1 only, preserves its historical quotes and selections, and leaves L1 unchanged. No network calls.
Source baseline: main 2ad42348 / feature 89e85eec, checked 2026-10-26.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, date, timedelta

DATA = json.loads(r'''{"stays":[["Dublin","2027-09-15","2027-09-17",700,[["Keavan’s Port","https://hotels.jdwetherspoon.com/hotels/keavans-port/","89 en-suite rooms; air conditioning. Taxi drop-off on Grantham Street."],["Premier Inn Dublin","https://www.premierinn.com/gb/en/faq/making-a-booking.html","Search Dublin city hotels; confirm exact property and room category before comparing."]]],["Galway","2027-09-17","2027-09-19",800,[["Eyre Square Townhouse","https://www.eyresquaretownhouse.com/","Original candidate; verify two doubles rather than one family room."]]],["Edinburgh","2027-09-19","2027-09-21",700,[["Edinburgh city hotel comparison","https://www.premierinn.com/gb/en/hotels/scotland/lothian/edinburgh.html","Compare central Premier Inn options; confirm full-size rooms versus compact hub rooms."]]],["Edinburgh","2027-09-21","2027-09-22",850,[["Melville Castle — two castle rooms","https://melvillecastle.com/rooms/","Request two double rooms inside the castle. Two-bedroom suite has double/four-poster plus twin room, so do not assume two double beds."],["Dalhousie Castle — two Castle Classic rooms","https://www.dalhousiecastle.co.uk/stay/castle-classic/","Castle Classic is inside historic castle walls. Exclude Lodge categories for authentic castle-room requirement."]]],["Inverness","2027-09-22","2027-09-24",650,[["Eildon Guest House","https://eildonguesthouse.co.uk/","Direct site describes breakfast, parking and central location. Two-room September inventory unverified."],["Mardon Guest House","https://www.mardonguesthouse.co.uk/","Direct booking and en-suite rooms. Two suitable doubles and dates unverified."]]],["London","2027-09-24","2027-09-28",1700,[["The Belgrave","https://www.the-belgrave.com/rooms/","Original baseline candidate in Pimlico; quote TWO rooms for FOUR nights, not old three-night total."]]]],"activities":[["Dublin","2027-09-16","Historic Dublin / Dublin Castle research",140,"https://www.heritageireland.ie/","Must-have Dublin Castle. Exact ticket, public access and 2027 timetable still need checking; allowance only."],["Galway","2027-09-18","Cliffs of Moher & Burren — land-based option",300,"https://galwaytourcompany.com/tours/cliffs-of-moher-the-burren/","Operator includes cliff admission and minimum 1.5-hour stop. Date inventory and group checkout unverified; preferred weather backup."],["Galway","2027-09-18","Aran Islands & Cliffs cruise — alternative",null,"https://galwaytourcompany.com/calendar/","Published adult reference €70 (€280 for four), not a Sep 18 2027 quote. Confirm all admissions/ferries and weather cancellation. Choose instead of land tour; do not add both."],["Galway","2027-09-18","Galway docks ferry & Cliffs cruise — alternative",null,"https://www.aranislandferries.com/day-tours/galway-city/cliffs-of-moher","Direct Galway City Docks departure. Sea-level Cliffs view is different from cliff-top admission; check season end and 2027 sailing."],["Edinburgh","2027-09-20","Edinburgh Castle",140,"https://www.edinburghcastle.scot/plan-your-visit/tickets/","Official timed tickets. 2027 four-person total unverified; USD allowance only. Allow a substantial morning."],["Edinburgh","2027-09-20","The Real Mary King’s Close",160,"https://www.realmarykingsclose.com/plan-your-visit/opening-times/","Official guided experience; confirm date-specific ticket and mobility requirements. Keep separate from ghost/vault tours."],["Edinburgh","2027-09-21","Rosslyn Chapel before castle check-in",70,"https://www.rosslynchapel.com/visit/admission/","Current full adult reference £12 (£48 for four); NOT 2027 quote. Concessions may apply. Bags, taxis and castle check-in need coordination."],["Edinburgh","2027-09-20","Stirling Castle — optional replacement day",null,"https://www.stirlingcastle.scot/","Existing must-have but no free full day in Edinburgh. Requires moving/replacing activities or a night reallocation; do not silently claim it fits."],["Inverness","2027-09-23","Skye & Eilean Donan — full-day tour",500,"https://www.rabbies.com/en-us/tours/scotland/from-inverness/day-tours","Published from $102/adult is generic, not Sep 23 2027 checkout. $500 group planning allowance; verify castle admission and lunch exclusions."],["Inverness","2027-09-23","Timberbush Skye & Eilean Donan — alternative",null,"https://www.timberbush-tours.co.uk/our-tours/from-inverness/1-day-tours/isle-skye-eilean-donan-castle","Compare final group total and admissions with Rabbie’s. Choose one operator only."],["London","2027-09-25","Tower of London",220,"https://www.hrp.org.uk/tower-of-london/visit/tickets-and-prices/","Official ticket includes Tower entry; choose base admission before donation/extras. Sep 2027 price and opening times unverified."],["London","2027-09-26","Windsor, Stonehenge & Bath — coach option",650,"https://www.goldentours.com/day-trips-from-london/windsor-castle-bath-stonehenge-tour","Select actual admissions package. Headline rates may exclude entries; exact 2027 four-person total unverified. Long day."],["London","2027-09-26","Stonehenge & Bath — less ambitious alternative",null,"https://www.goldentours.com/stonehenge-tours-and-tickets/stonehenge-and-bath","Entry to Stonehenge and Roman Baths only if selected; food and meeting-point transport excluded. Alternative to three-stop tour."],["London","2027-09-26","Premium Windsor / Bath / Stonehenge — alternative",null,"https://www.goldentours.com/luxury-tours/heritage-and-luxury-windsor-bath-and-stonehenge","Published from £203.15/adult (£812.60/four), not dated quote; includes all three admissions, lunch pack, drinks. Compare against standard with identical entries."]],"transport":[["Dublin → Galway","2027-09-17","Irish Rail Heuston → Galway",160,"https://www.irishrail.ie/en-ie/faqs/how-far-in-advance-can-i-make-a-reservation","Reservations open up to 90 days ahead (approximately June 19, 2027 for Sep 17). Fare and departure unknown. Add Dublin hotel-to-Heuston transfer separately."],["Galway → Dublin Airport","2027-09-19","Citylink airport coach",140,"https://www.dublinairport.com/to-from-the-airport/by-bus/by-bus-destinations","Airport lists Galway Citylink 760/763. Reconfirm 2027 stops/timetable and luggage. Plan a late enough Dublin flight for coach plus airport buffer."],["Edinburgh → Inverness","2027-09-22","ScotRail / LNER train research",240,"https://www.nationalrail.co.uk/travel-information/advance-booking-dates/","Exact 2027 timetable not confirmed. National Rail normally confirms timetables 12 weeks ahead (around June 30 for Sep 22). Check direct versus changing services; castle-to-Waverley taxi extra."],["Airport / local transfers","2027-09-15","Whole-trip airport, local transit & castle taxis",650,"https://www.dublinairport.com/to-from-the-airport/by-bus/buy-bus-tickets/bus-tickets-destinations","USD allowance only: Dublin arrival/Heuston, Edinburgh airport, Rosslyn/castle taxis, castle-Waverley, Inverness airport, London airport-city and transit. No duplicate regional train/coach charges."]],"flights":[["International flights","2027-09-14","2027-09-28","Open-jaw STL → DUB / London → STL",4500,"https://www.aircanada.com/en-us/flights-from-st-louis-mo-to-toronto","STL","DUB / London → STL","Air Canada candidate via Toronto","Research protected multi-city ticket; prefer Toronto over Chicago, connections at least 3 hours. Outbound Sep 14 arrives Sep 15; return Sep 28. No specific flights, seat inventory, baggage or dated fares verified."],["Dublin → Edinburgh","2027-09-19","2027-09-19","Aer Lingus DUB → EDI candidate",480,"https://www.aerlingus.com/en-ie/flights-from-dublin-to-edinburgh","DUB","EDI","Aer Lingus","Official route has multiple daily flights; exact Sep 19 2027 operation/price unverified. Four adults; add bags/seat selection. Avoid early departure after Galway."],["Inverness → London","2027-09-24","2027-09-24","easyJet INV → LGW candidate",480,"https://www.easyjet.com/en/cheap-flights/Inverness/London-Gatwick","INV","LGW","easyJet","Route confirmed on airline site; exact Sep 24 inventory unverified. Four adults; compare bag-inclusive total plus Gatwick transfer."],["Inverness → London","2027-09-24","2027-09-24","British Airways INV → LHR alternative",null,"https://www.heathrow.com/arrivals/terminal-5/flight-details/BA1421","INV","LHR","British Airways","Current airport flight page supports route, NOT Sep 24 2027 schedule. Compare baggage and Heathrow transfer with easyJet; choose one only."]],"days":[["2027-09-14","Transit","Depart STL","Overnight outbound; connection at least 3 hours. No hotel tonight."],["2027-09-15","Dublin","Arrival and easy Dublin walk","Immigration, hotel bags, relaxed city walk. No nonrefundable timed attraction on arrival."],["2027-09-16","Dublin","Historic Dublin","Dublin Castle priority. Choose remaining paid visits only after opening hours and route fit are verified."],["2027-09-17","Galway","Rail to Galway","Heuston-Galway train; settle in and explore central Galway."],["2027-09-18","Galway","Cliffs of Moher","Choose land tour OR island/cruise combination. Weather backup needed."],["2027-09-19","Edinburgh","Galway → Dublin Airport → Edinburgh","Transit day. Coach-to-flight connection self-managed; allow generous buffer and do not use early flight."],["2027-09-20","Edinburgh","Castle & Mary King’s Close","Castle morning; Close later with buffer. Stirling does not also fit as a full day."],["2027-09-21","Edinburgh","Rosslyn Chapel & castle overnight","Check out city hotel; coordinate luggage, chapel and taxi to Melville/Dalhousie. Castle night separate."],["2027-09-22","Inverness","Castle → Waverley → Inverness","Taxi from castle, then train north. No Skye tour on transfer day."],["2027-09-23","Inverness","Skye / Eilean Donan","One full-day tour; choose operator and admission package."],["2027-09-24","London","Fly Inverness → London","Compare Heathrow/Gatwick all-in journey. London hotel starts tonight."],["2027-09-25","London","Tower of London","Morning Tower; flexible afternoon walk."],["2027-09-26","London","Stonehenge day trip","Choose Stonehenge/Bath OR Windsor/Stonehenge/Bath; exact Sunday opening hours/admissions need checking."],["2027-09-27","London","Flexible London","Extra London day is the difference from the old 12-night route. Can reallocate to Scotland to fit Stirling before obtaining quotes."],["2027-09-28","Departure","Return London → STL","Hotel checkout; airport buffer and protected connection at least 3 hours."]]}''')
ROUTE = "S1"
CHECKED = "2026-10-26"

def install(db, username):
    db.row_factory = sqlite3.Row
    owner = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if not owner:
        raise ValueError("Existing username not found; no data changed.")
    trips = db.execute("SELECT id FROM trips WHERE user_id=? AND name='Europe 2027'", (owner["id"],)).fetchall()
    if len(trips) != 1:
        raise ValueError("Expected exactly one owned Europe 2027 trip; no data changed.")
    tid = trips[0]["id"]
    scenario = db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name='S1'", (tid,)).fetchone()
    if not scenario:
        raise ValueError("Existing S1 not found; no data changed.")
    sid = scenario["id"]
    db.execute("CREATE TABLE IF NOT EXISTS research_updates (trip_id INTEGER, scenario_id INTEGER, version TEXT, PRIMARY KEY(trip_id,scenario_id,version))")
    version = "S1-september-14-28-2027-v1"
    if db.execute("SELECT 1 FROM research_updates WHERE trip_id=? AND scenario_id=? AND version=?", (tid,sid,version)).fetchone():
        return tid,sid,False
    old_days = db.execute("SELECT * FROM scenario_itinerary WHERE scenario_id=? ORDER BY day_date", (sid,)).fetchall()
    if not old_days:
        raise ValueError("S1 has no itinerary dates; cannot safely infer date shift.")
    old_start=date.fromisoformat(old_days[0]["day_date"])
    old_end=date.fromisoformat(old_days[-1]["day_date"])
    target=date(2027,9,14)
    delta=target-old_start
    def move(value, final=False):
        if not value: return value
        d=date.fromisoformat(value)
        if final and d==old_end: return "2027-09-28"
        return (d+delta).isoformat()
    # A 14-day old S1 gains one London day. If already retimed to the
    # target dates, retain it. Other trip lengths require explicit review.
    if (old_end-old_start).days not in (13,14):
        raise ValueError("S1 duration differs from the known route; no data changed.")
    opts=db.execute("SELECT * FROM saved_options WHERE trip_id=? AND scenario_tag='S1'", (tid,)).fetchall()
    for row in opts:
        start=move(row["start_date"], row["category"] in ("flight","transport"))
        end=move(row["end_date"], True)
        note=("[S1 retimed 2026-10-26: previous price is historical, NOT verified for new dates; "
              "original dates "+str(row["start_date"])+" to "+str(row["end_date"])+".]\n"+(row["notes"] or ""))
        db.execute("UPDATE saved_options SET start_date=?,end_date=?,notes=? WHERE id=?", (start,end,note,row["id"]))
    # Temporary unique dates prevent collisions while preserving activity IDs.
    for row in old_days:
        db.execute("UPDATE scenario_itinerary SET day_date=? WHERE id=?", ("moving-"+str(row["id"]),row["id"]))
    for row in old_days:
        newday=move(row["day_date"],True)
        db.execute("UPDATE scenario_itinerary SET day_date=? WHERE id=?", (newday,row["id"]))
    db.execute("UPDATE trip_scenarios SET food_days=15 WHERE id=?", (sid,))

    def option(city, name, category, price, start, end, link, notes, select=False, **extra):
        note = ("Research checked " + CHECKED + ". " +
                ("USD group BUDGET ALLOWANCE, not a provider quote. " if price is not None else
                 "Exact-date price UNKNOWN; not free. ") + notes)
        db.execute("""INSERT INTO saved_options
            (trip_id,city,name,category,price,start_date,end_date,link,notes,scenario_tag,
             origin,destination,carrier,layovers)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tid,city,name+" [Sep research]",category,None,start,end,link,note,ROUTE,
             extra.get("origin"),extra.get("destination"),extra.get("carrier"),
             extra.get("layovers")))
        oid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        if False:  # Research alternatives never replace saved selections.
            db.execute("INSERT INTO scenario_choices(scenario_id,city,category,option_id) VALUES(?,?,?,?)",
                       (sid,city,category,oid))
        return oid

    for city, start, end, allowance, candidates in DATA["stays"]:
        category = "castle" if start == "2027-09-21" else "hotel"
        for index, (name, link, notes) in enumerate(candidates):
            option(city,name,category,allowance if index == 0 else None,start,end,link,
                   "TWO rooms / FOUR adults (two couples). Verify two double beds or two private double bedrooms; "
                   "taxes, breakfast, cancellation, prepayment and room location unknown. " + notes, index == 0)
    for city, start, end, name, price, link, origin, destination, carrier, notes in DATA["flights"]:
        option(city,name,"flight",price,start,end,link,notes,price is not None,
               origin=origin,destination=destination,carrier=carrier,
               layovers="At least 3 hours for international connecting itineraries; exact schedules unverified")
    for city, day, name, price, link, notes in DATA["transport"]:
        option(city,name,"transport",price,day,day,link,notes,True)
    for city, day, name, price, link, notes in DATA["activities"]:
        option(city,name,"activity",price,day,day,link,notes)
    for day, city, title, notes in DATA["days"]:
        found=db.execute("SELECT id FROM scenario_itinerary WHERE scenario_id=? AND day_date=?", (sid,day)).fetchone()
        if not found:
            db.execute("INSERT INTO scenario_itinerary(trip_id,scenario_id,day_date,city,title,notes) VALUES (?,?,?,?,?,?)", (tid,sid,day,city,title,notes))
        else:
            db.execute("UPDATE scenario_itinerary SET notes=notes || ? WHERE id=?", ("\n[New-date research] "+notes,found["id"]))
    db.execute("INSERT INTO research_updates VALUES (?,?,?)", (tid,sid,version))
    return tid,sid,True

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username",required=True)
    parser.add_argument("--database",type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    path=args.database or Path(os.environ.get("FURLONG_DATA_DIR",str(root)))/"furlong.db"
    if not path.is_file():
        parser.error("Existing database not found. Refusing to create an empty database.")
    db=sqlite3.connect(str(path))
    db.execute("PRAGMA foreign_keys=ON")
    # Backup is a complete, consistent SQLite snapshot before any writes.
    stamp=datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup=path.with_name(path.name+".pre-september-"+stamp+".bak")
    with sqlite3.connect(str(backup)) as target:
        db.backup(target)
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            tid,sid,created=install(db,args.username)
    finally:
        db.close()
    print("Existing S1 retimed and research saved." if created else "Update already applied; user edits preserved.")
    print("Backup: "+str(backup))
    print("Open /trip/"+str(tid)+"/workspace?scenario="+str(sid))
    print("Open /trip/"+str(tid)+"/itinerary?scenario="+str(sid))
    print("All priced items are budget allowances; no dated 2027 provider quotes verified.")

if __name__ == "__main__":
    main()

