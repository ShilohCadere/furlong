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


def import_europe_2027(db):
    """Create a separate trip and scenarios, not overwriting any existing trip."""
    existing=db.execute("SELECT id FROM trips WHERE name=? ORDER BY id LIMIT 1",("Europe 2027",)).fetchone()
    if existing:
        # Repeat clicks never duplicate or overwrite user changes.
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
                (trip_id,city,name,category,price,link,notes,start_date,end_date)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (trip_id,city,name,"hotel",actual_price,None,f"[{variant} estimate] {notes}",dates[0],dates[1]))
            oid=db.execute("SELECT last_insert_rowid()").fetchone()[0]
            lookup[(variant,city,name)]=oid
    for variant,info in BASELINES.items():
        subtotal=sum(db.execute("SELECT price FROM saved_options WHERE id=?",
                 (lookup[(variant,city,name)],)).fetchone()[0] or 0
                 for city,name in info["hotels"].items())
        db.execute("INSERT INTO trip_scenarios (trip_id,name,budget_limit,other_costs) VALUES (?,?,?,?)",
                   (trip_id,variant,info["budget"],info["total"]-subtotal))
        scenario=db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for city,name in info["hotels"].items():
            db.execute("INSERT INTO scenario_choices(scenario_id,city,category,option_id) VALUES (?,?,?,?)",
                       (scenario,city,"hotel",lookup[(variant,city,name)]))
    return trip_id
