"""City lodging comparisons for the four Europe 2027 scenarios.
Hotel totals are 2x one-room/2-adult search results, not confirmed 2-room stock.
Rental totals are for 4 adults with the search's 2-bedroom filter, but each
property's exact sleeping layout must be checked. No automatic selection.
Date matches against real itinerary days prevent incorrect scenario insertions.
"""
# scenario, city, checkin, checkout, mode, [(name, group total USD, Expedia hotel id)]
DATA = [
("Backwards 12 OTG","London","2027-09-16","2027-09-19","hotel",[
 ("Garden View Hotel",792,"582415"),("Premier Inn London Hammersmith Talgarth Road",866,"106118573"),
 ("Premier Inn London Fulham",892,"1209124"),("The Princess Hotel – St Pancras",910,"8398593")]),
("Backwards 14 OTG","London","2027-09-14","2027-09-17","hotel",[
 ("Mornington Victor Hotel Belgravia",1078,"1383708"),("Grand Plaza Serviced Apartments",1172,"914263"),
 ("Vancouver Studios",1280,"520898")]),
("Backwards 12 OTG","London","2027-09-16","2027-09-19","rental",[
 ("South Kensington Apartments",574,"69712519"),("Heinze Building by City Living London",729,"74798995"),
 ("Avari Apartments Hatton Collection",732,"92330920"),("Grand Plaza Serviced Apartments",765,"914263"),
 ("Charming spacious 2 bed apartment",937,"111618931")]),
("Backwards 14 OTG","London","2027-09-14","2027-09-17","rental",[
 ("South Kensington Apartments",None,"69712519"),
 ("Central London 2BR apartment near London Bridge",699,"123343386")]),
("Backwards 12 OTG","Inverness","2027-09-19","2027-09-21","hotel",[
 ("Glen Mhor Hotel",1976,"1627747")]),
("Backwards 14 OTG","Inverness","2027-09-17","2027-09-19","hotel",[
 ("Glen Mhor Hotel",1680,"1627747")]),
("Backwards 12 OTG","Inverness","2027-09-19","2027-09-21","rental",[
 ("The Loft Inverness",305,"58034953"),("Waverley Inn Apartments",395,"60534060"),
 ("2-bedroom house by Caledonian Canal",437,"68733424"),
 ("Comfortable 2 Bedroom Cottage",451,"33389848"),
 ("Pleasant 2-bedroom house Inverness",499,"121269610")]),
("Backwards 14 OTG","Inverness","2027-09-17","2027-09-19","rental",[
 ("The Loft Inverness",305,"58034953"),("2-bedroom house by Caledonian Canal",437,"68733424"),
 ("Comfortable 2 Bedroom Cottage",451,"33389848")]),
("Backwards 12 OTG","Edinburgh","2027-09-21","2027-09-23","hotel",[
 ("Premier Inn Edinburgh Lauriston Place",1054,"11785423"),
 ("Point A Edinburgh St Andrew Square",1090,"130563968"),
 ("Premier Inn Edinburgh City Centre Hotel",1146,"126400436"),
 ("Apex City of Edinburgh Hotel",1192,"800968")]),
("Backwards 14 OTG","Edinburgh","2027-09-19","2027-09-21","hotel",[
 ("Premier Inn Edinburgh Lauriston Place",636,"11785423"),
 ("Premier Inn Edinburgh Princes Street",716,"11785431"),
 ("Premier Inn Edinburgh Royal Mile",736,"40084945"),
 ("Premier Inn Edinburgh Waverley",750,"54245895")]),
("Backwards 12 OTG","Edinburgh","2027-09-21","2027-09-23","rental",[
 ("Niddry Street Apartments",739,"11828892"),("Castle apartment central",880,"39677248"),
 ("The Knight Residence Apartments",1021,"529490"),
 ("Braid Apartments by Mansley",1047,"12292861"),
 ("Destiny Scotland George IV Apartments",1056,"113865912")]),
("Backwards 14 OTG","Edinburgh","2027-09-19","2027-09-21","rental",[
 ("Niddry Street Apartments",739,"11828892"),
 ("Old Town Apartment Central Edinburgh",867,"107589684"),
 ("Castle apartment central",874,"39677248"),
 ("Destiny Scotland Broughton St Lofts",903,"17268506"),
 ("Destiny Scotland Princes St Residence",931,"12674920")]),
("Backwards 12 OTG","Galway","2027-09-24","2027-09-26","hotel",[
 ("Eyre Square Townhouse",684,"2750038"),
 ("The Snug Townhouse",1168,"76691106")]),
("Backwards 14 OTG","Galway","2027-09-22","2027-09-25","hotel",[
 ("The Snug Townhouse",1638,"76691106"),
 ("The Dean Galway",2344,"75709839")]),
("Backwards 12 OTG","Galway","2027-09-24","2027-09-26","rental",[
 ("Modern and Spacious 2 king bed",624,"132026383")]),
("Backwards 14 OTG","Galway","2027-09-22","2027-09-25","rental",[
 ("Robins Roost 2 (outside city; verify access)",540,"114094769"),
 ("Ben Gower (outside city; verify access)",540,"114090288")]),
]

def seed_remaining_city_lodging(db,trip_id):
    known={r["name"] for r in db.execute("SELECT name FROM trip_scenarios WHERE trip_id=?",(trip_id,))}
    for scenario,city,checkin,checkout,kind,items in DATA:
        if scenario not in known: continue
        days=[r["day_date"] for r in db.execute("""SELECT d.day_date FROM scenario_itinerary d
            JOIN trip_scenarios s ON s.id=d.scenario_id
            WHERE d.trip_id=? AND s.name=? AND d.city=? ORDER BY d.day_date""",
            (trip_id,scenario,city))]
        if not days or days[0]!=checkin: continue
        for name,price,hid in items:
            title=name+(" — rental, verify 2 bedrooms" if kind=="rental" else " — 2-room estimate")
            if db.execute("""SELECT 1 FROM saved_options WHERE trip_id=? AND city=?
                 AND category='hotel' AND scenario_tag=? AND name=?""",
                 (trip_id,city,scenario,title)).fetchone():continue
            if db.execute("""SELECT 1 FROM excluded_seed_options WHERE trip_id=?
                 AND city=? AND category='hotel' AND scenario_tag=? AND name=?""",
                 (trip_id,city,scenario,title)).fetchone():continue
            url=f"https://www.expedia.com/.h{hid}.Hotel-Information?chkin={checkin}&chkout={checkout}&rm1=a{4 if kind=='rental' else 2}"
            db.execute("""INSERT INTO saved_options
                 (trip_id,city,name,category,price,link,notes,start_date,end_date,scenario_tag)
                 VALUES (?,?,?,'hotel',?,?,'',?,?,?)""",
                 (trip_id,city,title,price,url,checkin,checkout,scenario))
