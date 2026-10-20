"""One-time, idempotent Europe 2027 demonstration import.

All USD amounts are planning estimates, not verified 2027 two-room bookings.
Other costs reconcile the previously audited complete-trip group totals.
"""
HOTELS = [
    # city, name, price USD for group, S1 dates, L1 dates, notes
    ("Dublin","Keavans Port",818,("2027-09-01","2027-09-03"),("2027-08-30","2027-09-02"),"Baseline Dublin; S1 $818, L1 $1112 total group. Verify direct two-room inventory."),
    ("Dublin","Donnybrook Hall",742,None,("2027-08-30","2027-09-02"),"L1 budget alternative; farther from city centre, allow extra transit."),
    ("Galway","Eyre Square Townhouse",856,("2027-09-03","2027-09-05"),("2027-09-02","2027-09-05"),"Planning allowance S1 $856 / L1 $1006 for 2 rooms. Not a confirmed 2027 two-room checkout."),
    ("Galway","Four Seasons B&B",None,("2027-09-03","2027-09-05"),("2027-09-02","2027-09-05"),"Candidate; actual two-room direct quote unverified."),
    ("Galway","The Western Hotel",None,("2027-09-03","2027-09-05"),("2027-09-02","2027-09-05"),"Candidate; exact two-room checkout total unverified."),
    ("Galway","HYDE Hotel",None,("2027-09-03","2027-09-05"),("2027-09-02","2027-09-05"),"Candidate; exact two-room checkout total unverified."),
    ("Galway","Harbour Hotel",None,("2027-09-03","2027-09-05"),("2027-09-02","2027-09-05"),"Candidate; exact two-room checkout total unverified."),
    ("Galway","Eyre Square Hotel",None,("2027-09-03","2027-09-05"),("2027-09-02","2027-09-05"),"Candidate; verify noise, room size and two-room availability."),
    ("Edinburgh","Premier Inn + Melville Castle",1829,("2027-09-05","2027-09-08"),("2027-09-05","2027-09-08"),"Two nights Premier Inn Haymarket, one night TWO Junior Suites at Melville Castle. GBP quote £610 + £762; USD planning conversion. Confirm castle room location and terms."),
    ("Edinburgh","Premier Inn + Dalhousie Castle",None,("2027-09-05","2027-09-08"),("2027-09-05","2027-09-08"),"Backup castle arrangement; require confirmation of two actual castle rooms."),
    ("Inverness","Dionard Guest House",710,("2027-09-08","2027-09-10"),("2027-09-08","2027-09-10"),"Two rooms; group planning allowance, verify availability."),
    ("London","The Belgrave",1248,("2027-09-10","2027-09-13"),("2027-09-10","2027-09-13"),"Baseline group hotel quote; two rooms, verify dates and terms."),
    ("London","City London Hotel",1070,("2027-09-10","2027-09-13"),("2027-09-10","2027-09-13"),"Budget alternative, group estimate $1070; verify room suitability."),
]
BASELINES = {
    "S1":{"budget":20000,"total":18939,"dates":("2027-09-01","2027-09-13"),
          "hotels":{"Dublin":"Keavans Port","Galway":"Eyre Square Townhouse","Edinburgh":"Premier Inn + Melville Castle","Inverness":"Dionard Guest House","London":"The Belgrave"}},
    "L1":{"budget":20000,"total":19817,"dates":("2027-08-30","2027-09-13"),
          "hotels":{"Dublin":"Keavans Port","Galway":"Eyre Square Townhouse","Edinburgh":"Premier Inn + Melville Castle","Inverness":"Dionard Guest House","London":"The Belgrave"}}
}
PRICE_OVERRIDES={("L1","Dublin","Keavans Port"):1112,("L1","Galway","Eyre Square Townhouse"):1006}
DOC_URL="https://docs.google.com/document/d/1eAZXLq-bxdhCem6wpQr63s2CaozNO8oSur_ejBxW8jo/edit"


# Additional researched candidates. No fabricated two-room quotes.
MORE_HOTELS = [
    ("Dublin","Premier Inn Dublin City Centre (Temple Bar)",None,"Central alternative; verify two rooms for exact dates."),
    ("Dublin","Staycity Aparthotels Dublin City Centre",None,"Apartment-hotel alternative; check two separate bedrooms/units and cancellation terms."),
    ("Dublin","The Alex Hotel",None,"Higher-comfort comparison; exact two-room quote unverified."),
    ("Edinburgh","Premier Inn Haymarket + Melville Castle",None,"Confirm room category, two suites inside the main castle, and group total before comparing."),
    ("Edinburgh","Premier Inn Haymarket + Dalhousie Castle",None,"Castle backup; two castle-interior rooms and ground transfers unverified."),
    ("Edinburgh","Apex Grassmarket + Melville Castle",None,"Alternative city hotel for first two nights; castle night retained; full group price unquoted."),
    ("Inverness","Premier Inn Inverness Centre (River Ness)",None,"Central riverside budget candidate; two rooms unquoted."),
    ("Inverness","Aye Stay",None,"Guesthouse candidate; room availability and group price unverified."),
    ("Inverness","Ballifeary Guest House",None,"Guesthouse candidate; room availability and group price unverified."),
    ("London","The Resident Victoria",None,"Central alternative; two-room group quote unverified."),
    ("London","Premier Inn London County Hall",None,"Family-friendly location; verify exact two-room availability and pricing."),
    ("London","hub by Premier Inn London Goodge Street",None,"Compact rooms; confirm suitability for two couples."),
]


def add_missing_europe_candidates(db, trip_id):
    """Add new city alternatives safely even if Europe was imported earlier.

    Do not overwrite edited options, selected plans, or budgets.
    """
    scenarios={row["name"] for row in db.execute(
        "SELECT name FROM trip_scenarios WHERE trip_id=?",(trip_id,))}
    for variant in ("S1","L1"):
        if variant not in scenarios: continue
        for city,name,price,note in MORE_HOTELS:
            dates=BASELINES[variant]["dates"]
            # Reuse city-specific dates from the existing trip's researched baseline.
            city_dates={
                "S1":{"Dublin":("2027-09-01","2027-09-03"),
                      "Edinburgh":("2027-09-05","2027-09-08"),
                      "Inverness":("2027-09-08","2027-09-10"),
                      "London":("2027-09-10","2027-09-13")},
                "L1":{"Dublin":("2027-08-30","2027-09-02"),
                      "Edinburgh":("2027-09-05","2027-09-08"),
                      "Inverness":("2027-09-08","2027-09-10"),
                      "London":("2027-09-10","2027-09-13")}
            }[variant][city]
            exists=db.execute("""SELECT id FROM saved_options
                WHERE trip_id=? AND city=? AND name=? AND scenario_tag=?""",
                (trip_id,city,name,variant)).fetchone()
            if exists:continue
            db.execute("""INSERT INTO saved_options
                (trip_id,city,name,category,price,notes,start_date,end_date,scenario_tag)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (trip_id,city,name,"hotel",price,
                 "["+variant+" candidate] "+note+" Group USD price unknown.",
                 city_dates[0],city_dates[1],variant))



def add_europe_route_days(db, trip_id):
    """Seed date/city skeletons without claiming unverified daily activities."""
    from datetime import date,timedelta
    city_spans={
      "S1":[("2027-09-01","Dublin"),("2027-09-02","Dublin"),
            ("2027-09-03","Galway"),("2027-09-04","Galway"),
            ("2027-09-05","Edinburgh"),("2027-09-06","Edinburgh"),
            ("2027-09-07","Edinburgh"),("2027-09-08","Inverness"),
            ("2027-09-09","Inverness"),("2027-09-10","London"),
            ("2027-09-11","London"),("2027-09-12","London"),
            ("2027-09-13","Departure")],
      "L1":[("2027-08-30","Dublin"),("2027-08-31","Dublin"),
            ("2027-09-01","Dublin"),("2027-09-02","Galway"),
            ("2027-09-03","Galway"),("2027-09-04","Galway"),
            ("2027-09-05","Edinburgh"),("2027-09-06","Edinburgh"),
            ("2027-09-07","Edinburgh"),("2027-09-08","Inverness"),
            ("2027-09-09","Inverness"),("2027-09-10","London"),
            ("2027-09-11","London"),("2027-09-12","London"),
            ("2027-09-13","Departure")]
    }
    for variant,route in city_spans.items():
        row=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name=?",(trip_id,variant)).fetchone()
        if not row:continue
        for when,city in route:
            db.execute("""INSERT OR IGNORE INTO scenario_itinerary(trip_id,scenario_id,day_date,city,title)
                VALUES (?,?,?,?,?)""",(trip_id,row["id"],when,city,"Departure day" if city=="Departure" else city+" · explore and discover"))

def import_europe_2027(db):
    """Create a separate trip and scenarios, not overwriting any existing trip."""
    existing=db.execute("SELECT id FROM trips WHERE name=? ORDER BY id LIMIT 1",("Europe 2027",)).fetchone()
    if existing:
        # Repeat clicks never duplicate or overwrite user changes.
        add_missing_europe_candidates(db, existing["id"])
        add_europe_route_days(db, existing["id"])
        return existing["id"]
    db.execute("INSERT INTO trips(name,destination) VALUES (?,?)",
               ("Europe 2027","Ireland · Scotland · England"))
    trip_id=db.execute("SELECT last_insert_rowid()").fetchone()[0]
    # Distinct dated candidate records for each route, so dates aren't lost.
    lookup={}
    for city,name,price,s1,l1,notes in HOTELS:
        for variant,dates in [("S1",s1),("L1",l1)]:
            if dates is None:continue
            actual_price=PRICE_OVERRIDES.get((variant,city,name),price)
            db.execute("""INSERT INTO saved_options
                (trip_id,city,name,category,price,link,notes,start_date,end_date,scenario_tag)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (trip_id,city,name,"hotel",actual_price,None,f"[{variant} estimate] {notes}",dates[0],dates[1],variant))
            oid=db.execute("SELECT last_insert_rowid()").fetchone()[0]
            lookup[(variant,city,name)]=oid
    for variant,info in BASELINES.items():
        # Separately adjustable group allowances. No claim these are booked.
        components = [
            ("International flights","transport","Main-economy roundtrip/open-jaw group flight allowance",4225 if variant=="S1" else 4680),
            ("Regional transportation","transport","Intercity flights, rail, transfers, taxis and baggage allowances",2323),
            ("Excursions","activity","Tours and attractions with unpriced-entry reserve",2105 if variant=="S1" else 2409),
        ]
        for city,category,label,amount in components:
            db.execute("""INSERT INTO saved_options
                (trip_id,city,name,category,price,notes,scenario_tag)
                VALUES (?,?,?,?,?,?,?)""",
                (trip_id,city,f"{variant}: {label}",category,amount,
                 f"{variant} whole-trip USD group planning allowance; not a booked price.",variant))
            option_id=db.execute("SELECT last_insert_rowid()").fetchone()[0]
            lookup[(variant,city,f"{variant}: {label}")]=option_id
        subtotal=sum(db.execute("SELECT price FROM saved_options WHERE id=?",
                 (lookup[(variant,city,name)],)).fetchone()[0] or 0
                 for city,name in info["hotels"].items())
        subtotal += sum(component[3] for component in components)
        db.execute("INSERT INTO trip_scenarios (trip_id,name,budget_limit,other_costs) VALUES (?,?,?,?)",
                   (trip_id,variant,info["budget"],info["total"]-subtotal))
        scenario=db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for city,name in info["hotels"].items():
            db.execute("INSERT INTO scenario_choices(scenario_id,city,category,option_id) VALUES (?,?,?,?)",
                       (scenario,city,"hotel",lookup[(variant,city,name)]))
        for city,category,label,amount in components:
            name=f"{variant}: {label}"
            db.execute("INSERT INTO scenario_choices(scenario_id,city,category,option_id) VALUES (?,?,?,?)",
                       (scenario,city,category,lookup[(variant,city,name)]))
    add_missing_europe_candidates(db, trip_id)
    add_europe_route_days(db, trip_id)
    return trip_id
