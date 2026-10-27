"""Non-destructive dated flight research for Europe 2027.

All amounts are the four-adult totals surfaced on 2026-10-27 by flight search.
None are booked, and prices can change. Empty prices indicate no verified
fare for the selected travel date. No user notes are populated.
"""
from datetime import date

# scenario, route group, date, title, group USD or None, official airline URL,
# origin, destination, departure local, arrival local, stops, operating airline
ROWS = [
 ("14 OTG","STL → Dublin","2027-09-13","British Airways via Heathrow — later Dublin arrival",1290,"https://www.britishairways.com/","STL","DUB","21:00","18:40 (+1 day)","LHR — confirm 3h minimum","British Airways"),
 ("14 OTG","STL → Dublin","2027-09-13","British Airways via Heathrow — evening arrival",1290,"https://www.britishairways.com/","STL","DUB","21:00","19:35 (+1 day)","LHR — confirm 3h minimum","British Airways"),
 ("12 OTG","STL → Dublin","2027-09-15","British Airways via Heathrow — evening arrival",1290,"https://www.britishairways.com/","STL","DUB","21:35","18:00 (+1 day)","LHR — check minimum connection","British Airways"),
 ("12 OTG","STL → Dublin","2027-09-15","British Airways via Heathrow — later arrival",1290,"https://www.britishairways.com/","STL","DUB","21:35","19:30 (+1 day)","LHR — check minimum connection","British Airways"),
 ("12 OTG","STL → Dublin","2027-09-15","American Airlines via Chicago",1336,"https://www.aa.com/","STL","DUB","17:18","11:50 (+1 day)","ORD — duration to verify","American Airlines"),
 ("12 OTG","STL → Dublin","2027-09-15","American Airlines via Philadelphia",1336,"https://www.aa.com/","STL","DUB","11:09","06:30 (+1 day)","PHL — duration to verify","American Airlines"),
 ("12 OTG","Shannon → Edinburgh","2027-09-20","Ryanair FR1676 nonstop",725.40,"https://www.ryanair.com/","SNN","EDI","14:40","16:00","Nonstop","Ryanair"),
 ("14 OTG","Shannon → Edinburgh","2027-09-20","Ryanair FR1676 nonstop",725.40,"https://www.ryanair.com/","SNN","EDI","14:40","16:00","Nonstop","Ryanair"),
 ("12 OTG","Inverness → London","2027-09-25","British Airways — Inverness to Heathrow (schedule pending)",None,"https://www.britishairways.com/","INV","LHR","","","Nonstop route; date not yet on sale","British Airways"),
 ("14 OTG","Inverness → London","2027-09-25","British Airways — Inverness to Heathrow (schedule pending)",None,"https://www.britishairways.com/","INV","LHR","","","Nonstop route; date not yet on sale","British Airways"),
 ("12 OTG","Inverness → London","2027-09-25","easyJet — Inverness to Gatwick (schedule pending)",None,"https://www.easyjet.com/","INV","LGW","","","Nonstop route; date not yet on sale","easyJet"),
 ("14 OTG","Inverness → London","2027-09-25","easyJet — Inverness to Gatwick (schedule pending)",None,"https://www.easyjet.com/","INV","LGW","","","Nonstop route; date not yet on sale","easyJet"),
 ("12 OTG","London → STL","2027-09-28","British Airways BA221 Heathrow nonstop — published schedule",None,"https://www.britishairways.com/","LHR","STL","16:30","19:30","Nonstop; fare not yet on sale","British Airways"),
 ("14 OTG","London → STL","2027-09-28","British Airways BA221 Heathrow nonstop — published schedule",None,"https://www.britishairways.com/","LHR","STL","16:30","19:30","Nonstop; fare not yet on sale","British Airways"),
 ("Backwards 14 OTG","STL → London","2027-09-13","British Airways BA220 Heathrow nonstop",1418,"https://www.britishairways.com/","STL","LHR","21:00","11:10 (+1 day)","Nonstop","British Airways"),
 ("Backwards 12 OTG","STL → London","2027-09-15","British Airways BA220 Heathrow nonstop — published schedule",None,"https://www.britishairways.com/","STL","LHR","21:25","11:35 (+1 day)","Nonstop; confirm fare","British Airways"),
 ("Backwards 12 OTG","STL → London","2027-09-15","American Airlines via Philadelphia",1436,"https://www.aa.com/","STL","LHR","17:43","10:20 (+1 day)","PHL — check layover ≥3h","American Airlines"),
 ("Backwards 12 OTG","STL → London","2027-09-15","American Airlines via Chicago",1436,"https://www.aa.com/","STL","LHR","17:18","10:30 (+1 day)","ORD — check layover ≥3h","American Airlines"),
 ("Backwards 14 OTG","London → Inverness","2027-09-17","British Airways BA1420 Heathrow nonstop",328.80,"https://www.britishairways.com/","LHR","INV","07:55","09:35","Nonstop","British Airways"),
 ("Backwards 14 OTG","London → Inverness","2027-09-17","British Airways BA1424 Heathrow nonstop",612.80,"https://www.britishairways.com/","LHR","INV","13:00","14:35","Nonstop","British Airways"),
 ("Backwards 14 OTG","London → Inverness","2027-09-17","British Airways BA1426 Heathrow nonstop",480.80,"https://www.britishairways.com/","LHR","INV","19:55","21:30","Nonstop","British Airways"),
 ("Backwards 12 OTG","London → Inverness","2027-09-19","British Airways BA1420 Heathrow nonstop",300.80,"https://www.britishairways.com/","LHR","INV","08:50","10:30","Nonstop","British Airways"),
 ("Backwards 12 OTG","London → Inverness","2027-09-19","British Airways BA1424 Heathrow nonstop",416.80,"https://www.britishairways.com/","LHR","INV","12:20","14:00","Nonstop","British Airways"),
 ("Backwards 12 OTG","London → Inverness","2027-09-19","British Airways BA1426 Heathrow nonstop",300.80,"https://www.britishairways.com/","LHR","INV","20:00","21:35","Nonstop","British Airways"),
 ("Backwards 14 OTG","Edinburgh → Shannon","2027-09-22","Ryanair FR1677 nonstop",282.80,"https://www.ryanair.com/","EDI","SNN","14:35","15:50","Nonstop","Ryanair"),
 ("Backwards 12 OTG","Edinburgh → Shannon","2027-09-24","Ryanair — nonstop route; Friday schedule unverified",None,"https://www.ryanair.com/","EDI","SNN","","","Schedule and fare not yet on sale","Ryanair"),
 ("Backwards 12 OTG","Dublin → STL","2027-09-28","American Airlines via Philadelphia — schedule pending",None,"https://www.aa.com/","DUB","STL","","","PHL — check layover ≥3h","American Airlines"),
 ("Backwards 14 OTG","Dublin → STL","2027-09-28","American Airlines via Philadelphia — schedule pending",None,"https://www.aa.com/","DUB","STL","","","PHL — check layover ≥3h","American Airlines"),
 ("Backwards 12 OTG","Dublin → STL","2027-09-28","Air Canada via Toronto — schedule pending",None,"https://www.aircanada.com/","DUB","STL","","","YYZ — check layover ≥3h","Air Canada"),
 ("Backwards 14 OTG","Dublin → STL","2027-09-28","Air Canada via Toronto — schedule pending",None,"https://www.aircanada.com/","DUB","STL","","","YYZ — check layover ≥3h","Air Canada"),
]

def _route_for_existing(row):
    """Infer an actual segment from stored endpoints or recognizable labels."""
    name = (row["name"] or "").lower()
    origin = (row["origin"] or "").strip().upper()
    destination = (row["destination"] or "").strip().upper()
    if origin in ("STL", "LHR", "LGW", "LON", "DUB", "SNN", "EDI", "INV") and destination in ("STL", "LHR", "LGW", "LON", "DUB", "SNN", "EDI", "INV"):
        cities = {"STL":"STL", "LHR":"London", "LGW":"London", "LON":"London",
                  "DUB":"Dublin", "SNN":"Shannon", "EDI":"Edinburgh", "INV":"Inverness"}
        return cities[origin] + " → " + cities[destination]
    # Recognize both natural-language and airport-code names; do not guess
    # direction for generic allowances or ambiguous user-created options.
    labels = [
        (("st. louis to london", "stl to london", "stl → london"),"STL → London"),
        (("st. louis to dublin", "stl to dublin", "stl → dublin"),"STL → Dublin"),
        (("london to st. louis", "london to stl", "london → stl"),"London → STL"),
        (("dublin to st. louis", "dublin to stl", "dublin → stl"),"Dublin → STL"),
        (("london to inverness", "london → inverness"),"London → Inverness"),
        (("inverness to london", "inverness → london"),"Inverness → London"),
        (("edinburgh to shannon", "edinburgh → shannon"),"Edinburgh → Shannon"),
        (("shannon to edinburgh", "shannon → edinburgh"),"Shannon → Edinburgh"),
    ]
    for phrases, route in labels:
        if any(phrase in name for phrase in phrases):
            return route
    return None


def _consolidate_flight_routes(db, trip_id):
    """Rekey old grouping labels and their selections without losing option IDs."""
    rows = db.execute("""SELECT * FROM saved_options
        WHERE trip_id=? AND category='flight'""", (trip_id,)).fetchall()
    for row in rows:
        route = _route_for_existing(row)
        if not route or row["city"] == route:
            continue
        # A scenario can only select one flight in a given route group.
        # Retain the old choice unchanged if there would be a conflict.
        choices = db.execute("""SELECT scenario_id FROM scenario_choices
            WHERE option_id=? AND category='flight'""", (row["id"],)).fetchall()
        collision = any(db.execute("""SELECT 1 FROM scenario_choices
            WHERE scenario_id=? AND city=? AND category='flight'""",
            (choice["scenario_id"], route)).fetchone() for choice in choices)
        if collision:
            continue
        db.execute("""UPDATE saved_options SET city=? WHERE id=?""",
                   (route, row["id"]))
        db.execute("""UPDATE scenario_choices SET city=?
            WHERE option_id=? AND category='flight'""",(route,row["id"]))


def add_europe_flight_research(db, trip_id):
    """Insert missing date-specific candidate rows only; never overwrite selections."""
    _consolidate_flight_routes(db, trip_id)
    known = {r["name"] for r in db.execute(
        "SELECT name FROM trip_scenarios WHERE trip_id=?", (trip_id,)).fetchall()}
    aliases = {"12 OTG": "S1", "14 OTG": "L1"}
    for tag, group, when, name, price, url, origin, destination, dep, arr, layovers, carrier in ROWS:
        effective_tag = tag if tag in known else aliases.get(tag, tag)
        if effective_tag not in known:
            continue
        # The flight is offered only within its intended scenario and route group.
        # Do not recreate a candidate that a user has explicitly excluded.
        excluded = db.execute("""SELECT 1 FROM excluded_seed_options
            WHERE trip_id=? AND city=? AND name=? AND category='flight'
                AND scenario_tag=?""",(trip_id,group,name,effective_tag)).fetchone()
        if excluded:
            continue
        exists = db.execute("""SELECT 1 FROM saved_options
            WHERE trip_id=? AND city=? AND name=? AND category='flight'
              AND scenario_tag=?""",(trip_id,group,name,effective_tag)).fetchone()
        if exists:
            continue
        db.execute("""INSERT INTO saved_options
            (trip_id,city,name,category,price,link,notes,start_date,
             scenario_tag,origin,destination,departure_time,arrival_time,layovers,carrier)
            VALUES (?,?,?,'flight',?,?,'',?,?,?,?,?,?,?,?)""",
            (trip_id,group,name,price,url,when,effective_tag,
             origin,destination,dep,arr,layovers,carrier))
