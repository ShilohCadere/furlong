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
    ("Dublin","Broc House Suites",None,"Previously considered apartment-style lodging; verify a suitable two-bedroom layout and direct price for four adults."),
    ("Dublin","The July – Capel Street",None,"Previously considered serviced apartments; verify two private bedrooms, group total and direct booking."),
    ("Dublin","Modern Two-Bed Apartment, City Centre",None,"Previously considered private apartment; verify listing identity, bedrooms, cancellation rules and 2027 availability."),
    ("Galway","Modern and Spacious 2 – king bed",None,"Previously considered apartment with two king beds; verify listing identity and suitability for two couples."),
    ("Galway","Canal Court",None,"Previously considered apartment; verify listing identity, two private bedrooms and group quote."),
    ("Galway","Exceptional Apartment with River Views",None,"Previously considered apartment; check layout, pricing and direct booking availability."),
    ("Edinburgh","Aparthotel Adagio Edinburgh Royal Mile",None,"Previously considered aparthotel; verify two separate bedrooms or acceptable room configuration."),
    ("Edinburgh","PREMIER SUITES Fountain Court",None,"Previously considered apartment-style lodging; verify location, bedrooms and total cost."),
    ("Edinburgh","Stockbridge Two-Bedroom Apartment",None,"Previously considered private apartment; verify exact listing and availability."),
    ("Inverness","23 Innes Street Apartment",None,"Previously researched entire two-bedroom apartment; verify 2027 terms and price for four adults."),
    ("Inverness","Culloden Apartment",None,"Previously considered apartment; verify exact listing, bedrooms and transportation logistics."),
    ("Inverness","Riverside Two-Bedroom Apartment",None,"Previously considered apartment; verify exact listing, dates and group price."),
    ("London","Citadines Holborn-Covent Garden",None,"Previously considered aparthotel; verify two private bedrooms or two separate units."),
    ("London","Interlude House",None,"Previously considered apartment option; verify listing identity, bedroom count and price."),
    ("London","Marlin Waterloo",None,"Previously considered serviced accommodation; verify exact room configuration for two couples."),

]


def add_missing_europe_candidates(db, trip_id):
    """Add new city alternatives safely even if Europe was imported earlier.

    Do not overwrite edited options, selected plans, or budgets.
    """
    # Explicitly excluded candidate: never re-import Staycity Dublin.
    db.execute("""DELETE FROM scenario_choices WHERE option_id IN (
        SELECT id FROM saved_options WHERE trip_id=? AND city='Dublin'
          AND name='Staycity Aparthotels Dublin City Centre'
          AND scenario_tag IN ('S1','L1'))""",(trip_id,))
    db.execute("""DELETE FROM saved_options WHERE trip_id=? AND city='Dublin'
        AND name='Staycity Aparthotels Dublin City Centre'
        AND scenario_tag IN ('S1','L1')""",(trip_id,))
    scenarios={row["name"] for row in db.execute(
        "SELECT name FROM trip_scenarios WHERE trip_id=?",(trip_id,))}
    for variant in ("S1","L1"):
        if variant not in scenarios: continue
        for city,name,price,note in MORE_HOTELS:
            # Reuse city-specific dates from the existing trip's researched baseline.
            city_dates={
                "S1":{"Dublin":("2027-09-01","2027-09-03"),
                      "Galway":("2027-09-03","2027-09-05"),
                      "Edinburgh":("2027-09-05","2027-09-08"),
                      "Inverness":("2027-09-08","2027-09-10"),
                      "London":("2027-09-10","2027-09-13")},
                "L1":{"Dublin":("2027-08-30","2027-09-02"),
                      "Galway":("2027-09-02","2027-09-05"),
                      "Edinburgh":("2027-09-05","2027-09-08"),
                      "Inverness":("2027-09-08","2027-09-10"),
                      "London":("2027-09-10","2027-09-13")}
            }[variant][city]
            exists=db.execute("""SELECT id FROM saved_options
                WHERE trip_id=? AND city=? AND name=? AND scenario_tag=?""",
                (trip_id,city,name,variant)).fetchone()
            if exists:continue
            excluded=db.execute("""SELECT 1 FROM excluded_seed_options
                WHERE trip_id=? AND city=? AND name=? AND category='hotel' AND scenario_tag=?""",
                (trip_id,city,name,variant)).fetchone()
            if excluded:continue
            db.execute("""INSERT INTO saved_options
                (trip_id,city,name,category,price,notes,start_date,end_date,scenario_tag)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (trip_id,city,name,"hotel",price,
                 "["+variant+" candidate] "+note+" Group USD price unknown.",
                 city_dates[0],city_dates[1],variant))



import json

EUROPE_DAILY_PLANS = json.loads("[{\"variant\":\"S1\",\"date\":\"2027-08-31\",\"title\":\"St. Louis to Dublin\",\"notes\":\"Depart St. Louis on an overnight transatlantic itinerary, connecting in the United States if needed. Keep passports, hotel information, transfer arrangements and toiletries accessible offline. Eat and sleep as much as practical on the overnight portion. Overnight: aircraft.\"},{\"variant\":\"S1\",\"date\":\"2027-09-01\",\"title\":\"Dublin arrival and easy city walk\",\"notes\":\"Morning/midday: clear immigration, transfer from Dublin Airport, store luggage at a centrally located hotel and eat. Afternoon: walk Temple Bar, Ha’penny Bridge, River Liffey and Grafton Street at a relaxed pace. Evening: casual Irish pub meal; traditional music only if everyone has energy. Do not prebook major attractions on jet-lag day. Overnight: Dublin (1/2).\"},{\"variant\":\"S1\",\"date\":\"2027-09-02\",\"title\":\"Trinity College and historic Dublin\",\"notes\":\"Morning: reserve the Book of Kells Experience at Trinity College; allow about two hours, recognizing that Old Library access may change during its restoration. Afternoon: choose one primary paid experience, preferably Kilmainham Gaol for modern Irish history, or Guinness Storehouse for brewing heritage and Gravity Bar views. Stroll the nearby historic streets. Evening: dinner and optional music in central Dublin. Overnight: Dublin (2/2).\"},{\"variant\":\"S1\",\"date\":\"2027-09-03\",\"title\":\"Train to Galway and castle arrival\",\"notes\":\"Morning: transfer to Heuston Station; take the approximately 2½-hour intercity rail journey to Galway. Afternoon: explore Eyre Square, Shop Street, the Latin Quarter and Spanish Arch, with lunch. Later: prearranged taxi to the castle candidate, Cloonacauneen Castle. Verify that both rooms are physically inside the historic castle, not adjacent accommodation. Evening: dinner at the property if served, otherwise arranged taxi into Galway and back. Overnight: Galway/castle (1/2).\"},{\"variant\":\"S1\",\"date\":\"2027-09-04\",\"title\":\"Cliffs of Moher and the Burren\",\"notes\":\"Early morning: taxi to a Galway tour departure and join a guided County Clare excursion. Stop at the Burren’s limestone landscape, Doolin for lunch and Cliffs of Moher viewpoints. If suitable, add a boat cruise beneath the cliffs; this is weather and sea dependent. Aran Islands could substitute or combine only on a carefully verified operator timetable, not as a guaranteed extra. Evening: return via Galway to the castle; rest. Overnight: Galway/castle (2/2).\"},{\"variant\":\"S1\",\"date\":\"2027-09-05\",\"title\":\"Galway to Edinburgh\",\"notes\":\"Morning: taxi into Galway and take the airport coach to Dublin Airport, allowing around 2½–3 hours and generous flight buffer. Fly to Edinburgh on a schedule compatible with the ground transfer; flight unverified. Afternoon/evening: transfer to hotel, short Royal Mile or Old Town walk and Scottish dinner. Treat the day as transit, not a sightseeing marathon. Overnight: Edinburgh (1/3).\"},{\"variant\":\"S1\",\"date\":\"2027-09-06\",\"title\":\"Edinburgh Castle and Royal Mile\",\"notes\":\"Morning: prebook Edinburgh Castle; allow roughly 2½–3 hours for the fortress, Crown Jewels, Great Hall and St Margaret’s Chapel. The One O’Clock Gun may be a bonus if operating. Afternoon: St Giles’ Cathedral, closes, Victoria Street and Grassmarket, including café breaks on Edinburgh’s hills and cobblestones. Evening: traditional dinner, with optional ghost walk. Overnight: Edinburgh (2/3).\"},{\"variant\":\"S1\",\"date\":\"2027-09-07\",\"title\":\"Flexible Edinburgh\",\"notes\":\"Morning: choose the Palace of Holyroodhouse if operating, or the National Museum of Scotland. Afternoon: Calton Hill for views, then shops, Dean Village/Water of Leith, café time or rest. Evening: good Scottish dinner and pack. Deliberately avoid an additional long Highlands coach excursion before Skye. Overnight: Edinburgh (3/3).\"},{\"variant\":\"S1\",\"date\":\"2027-09-08\",\"title\":\"Train to Inverness\",\"notes\":\"Morning: train Edinburgh Waverley to Inverness; allow around 3½–4 hours depending on service. Afternoon: check in, explore River Ness and central Inverness. Optional brief Loch Ness outing only if the train arrival and available transport permit it; avoid packing in a full excursion. Evening: early dinner and rest ahead of Skye. Overnight: Inverness (1/2).\"},{\"variant\":\"S1\",\"date\":\"2027-09-09\",\"title\":\"Isle of Skye and Eilean Donan\",\"notes\":\"Early start (illustratively 7:45): 12-hour small-group Highlands and Skye tour from Inverness. Seek Loch Ness-side scenery, Eilean Donan Castle with enough time to enter if desired, Portree harbor lunch, and scenic stops around Old Man of Storr, Kilt Rock, Quiraing or Sligachan, as allowed by conditions/operator routing. Mostly viewpoint stops, not full hikes. Return approximately evening; simple dinner. Waterproof layers and snacks recommended. Overnight: Inverness (2/2).\"},{\"variant\":\"S1\",\"date\":\"2027-09-10\",\"title\":\"Fly to London\",\"notes\":\"Morning/midday: transfer to Inverness Airport for an unverified London flight; arrival airport matters for hotel logistics. Afternoon: hotel check-in and Westminster orientation: Big Ben, Parliament, Westminster Abbey exterior, Westminster Bridge and South Bank. Optional Thames sightseeing cruise if energy and schedules allow. Dinner near river or Covent Garden. Overnight: London (1/3).\"},{\"variant\":\"S1\",\"date\":\"2027-09-11\",\"title\":\"Windsor Castle and Stonehenge\",\"notes\":\"Morning: join a two-stop guided coach tour from London, favoring an operator that includes admission to Windsor Castle as well as Stonehenge. See Windsor State Apartments and St George’s Chapel subject to closures. Afternoon: continue to Salisbury Plain to see Stonehenge and its visitor exhibits. Avoid adding Bath or the Cotswolds to this already long day. Evening: return to London, easy dinner. Overnight: London (2/3).\"},{\"variant\":\"S1\",\"date\":\"2027-09-12\",\"title\":\"Tower of London and final evening\",\"notes\":\"Morning: prebook Tower of London; allow three hours for Crown Jewels, White Tower, Tudor/medieval stories and a Yeoman Warder tour if running. Afternoon: walk Tower Bridge and riverside, with optional bridge walkways, Borough Market (check Sunday hours), South Bank or Covent Garden. Evening: shared farewell dinner and pack. Overnight: London (3/3).\"},{\"variant\":\"S1\",\"date\":\"2027-09-13\",\"title\":\"Return to St. Louis\",\"notes\":\"Check out and transfer to the actual London departure airport with adequate international flight and baggage time. Travel home to St. Louis via the booked connection. Trip concludes.\"},{\"variant\":\"L1\",\"date\":\"2027-08-29\",\"title\":\"St. Louis to Dublin\",\"notes\":\"Afternoon/evening: depart St. Louis on the transatlantic itinerary, connecting through an appropriate U.S. hub if needed. Carry passports, flight documents, change of clothes, essentials and Dublin hotel address. Try to sleep during the overnight flight. Overnight: aircraft.\"},{\"variant\":\"L1\",\"date\":\"2027-08-30\",\"title\":\"Dublin arrival\",\"notes\":\"Morning: arrive at Dublin Airport, clear immigration and transfer into the centre, ideally Temple Bar or similarly walkable surroundings. Store bags if early. Afternoon: light route by Ha’penny Bridge, River Liffey, Temple Bar streets, Grafton Street and St Stephen’s Green, with coffee and breaks. Evening: traditional Irish meal and music only if everyone is awake enough. No fixed timed attraction on the arrival day. Overnight: Dublin (1/3).\"},{\"variant\":\"L1\",\"date\":\"2027-08-31\",\"title\":\"Trinity, Book of Kells and Dublin heritage\",\"notes\":\"Morning: Trinity College’s Book of Kells Experience, allowing about two hours; confirm 2027 access to the Old Library while renovation continues. Afternoon: Dublin Castle, Christ Church Cathedral and St Patrick’s Cathedral area; choose one substantial interior to avoid excessive tickets and walking. Evening: dinner and optional traditional music; no next-morning intercity pressure. Overnight: Dublin (2/3).\"},{\"variant\":\"L1\",\"date\":\"2027-09-01\",\"title\":\"Kilmainham Gaol and Guinness Storehouse\",\"notes\":\"Morning: advance-reserved guided Kilmainham Gaol tour for Ireland’s independence and social history. Tickets can be scarce. Afternoon: Guinness Storehouse exhibits and Gravity Bar city views; suitable nonalcoholic options should be checked. Evening: free time in the Liberties and dinner. Alternate for those preferring coast over brewery: substitute Howth harbor and seafood, rather than trying to fit it on top. Overnight: Dublin (3/3).\"},{\"variant\":\"L1\",\"date\":\"2027-09-02\",\"title\":\"Train west to Galway, castle check-in\",\"notes\":\"Morning: depart Dublin Heuston by train for Galway (approximately 2½ hours subject to departure). Afternoon: stroll Eyre Square, Shop Street, Latin Quarter, Spanish Arch, the Corrib and waterfront, with lunch. Late afternoon: arranged taxi to Cloonacauneen Castle, or an approved comparable actual castle-room option. Verify the exact room locations for two couples, access and return taxi costs. Evening: castle grounds and possible on-site dinner if restaurant operating. Overnight: Galway/castle (1/3).\"},{\"variant\":\"L1\",\"date\":\"2027-09-03\",\"title\":\"Cliffs of Moher and the Burren\",\"notes\":\"Morning: taxi to Galway tour meeting point; full-day County Clare tour through Burren limestone scenery and coastal viewpoints. Lunch around Doolin if route allows. Afternoon: dedicated time at Cliffs of Moher clifftop viewing areas, plus optional weather-dependent cruise from below. Do not assume Aran Islands and cliffs can both be covered meaningfully without a specifically verified combined itinerary. Evening: return to Galway and castle. Overnight: Galway/castle (2/3).\"},{\"variant\":\"L1\",\"date\":\"2027-09-04\",\"title\":\"Connemara and Kylemore Abbey\",\"notes\":\"Morning: join guided Connemara tour from Galway, with scenic valleys, Twelve Bens or Lough Inagh views and countryside stops. Late morning/afternoon: Kylemore Abbey and lakeside estate, Gothic church, Victorian Walled Garden and café; target roughly two hours if tour timing permits. Afternoon: continue through the Connemara region, possibly Clifden, Letterfrack or Killary Harbour depending on provider. Evening: return and enjoy last castle dinner if available. This full day is the key experience regained by L1. Overnight: Galway/castle (3/3).\"},{\"variant\":\"L1\",\"date\":\"2027-09-05\",\"title\":\"Galway to Edinburgh\",\"notes\":\"Morning: castle checkout, taxi to Galway airport coach stop, and coach transfer to Dublin Airport (~3 hours with traffic allowances). Midday/afternoon: flight to Edinburgh if an actual flight schedule supports sufficient buffer. Afternoon/evening: hotel check-in, introduction to Royal Mile and Old Town, dinner nearby. This is a transit day, not a major sightseeing day. Overnight: Edinburgh (1/3).\"},{\"variant\":\"L1\",\"date\":\"2027-09-06\",\"title\":\"Edinburgh Castle and Old Town\",\"notes\":\"Morning: prebook Edinburgh Castle (2½–3 hours), including Crown Jewels, Great Hall, fortifications and chapel. Check One O’Clock Gun operation. Afternoon: leisurely Royal Mile, St Giles’ Cathedral, historic closes, Victoria Street, Grassmarket, shops and café stop. Evening: traditional dinner or optional ghost tour. Expect hills and cobbles. Overnight: Edinburgh (2/3).\"},{\"variant\":\"L1\",\"date\":\"2027-09-07\",\"title\":\"Stirling Castle or Rosslyn Chapel\",\"notes\":\"Preferred: morning train Edinburgh to Stirling, taxi or uphill walk to Stirling Castle for royal-palace and military history. Lunch and some time in historic Stirling before returning to Edinburgh. Alternative: Rosslyn Chapel for medieval carvings, leaving more afternoon time in Edinburgh; or stay local for Holyroodhouse/National Museum. Treat these as competing choices, not all promised attractions. Evening: last Edinburgh dinner and pack. Overnight: Edinburgh (3/3).\"},{\"variant\":\"L1\",\"date\":\"2027-09-08\",\"title\":\"Highland rail journey to Inverness\",\"notes\":\"Morning: Edinburgh Waverley to Inverness train (~3½–4 hours subject to service), scenic journey and luggage handling. Afternoon: hotel, lunch, River Ness walk and city centre. Optional excursion to Urquhart Castle or Loch Ness if there is adequate time and transportation; not a guaranteed included activity. Evening: early dinner before long Skye tour. Overnight: Inverness (1/2).\"},{\"variant\":\"L1\",\"date\":\"2027-09-09\",\"title\":\"Isle of Skye and Eilean Donan\",\"notes\":\"Early morning: depart Inverness on approximately 12-hour small-group tour. Seek scenic Loch Ness road, Eilean Donan Castle with interior time if offered, scenic Skye crossing, Portree lunch, views of Old Man of Storr, Kilt Rock, Quiraing and Sligachan if conditions allow. The provider determines exact stops; these are viewpoints rather than extended hikes. Evening: return around dinner time, depending on actual operator, then rest. Overnight: Inverness (2/2).\"},{\"variant\":\"L1\",\"date\":\"2027-09-10\",\"title\":\"Flight south to London\",\"notes\":\"Morning: check out, go to Inverness Airport and fly to London on a schedule not yet confirmed. Consider the London arrival airport before finalizing hotel. Afternoon: settle into hotel, then Westminster walk covering Big Ben, Houses of Parliament, Abbey exterior, Westminster Bridge and South Bank. Optional Thames cruise only if time/energy permit. Evening: dinner near the river or Covent Garden. Overnight: London (1/3).\"},{\"variant\":\"L1\",\"date\":\"2027-09-11\",\"title\":\"Windsor Castle and Stonehenge\",\"notes\":\"Morning: coach excursion from London with Windsor Castle entry included. State Apartments, grounds and St George’s Chapel subject to royal closures and opening policy. Afternoon: travel to Stonehenge, see monument and interpretive visitor centre, allow meaningful viewing time. Avoid an overloaded three-or-four-stop excursion; Bath/Cotswolds not included this day. Evening: return to London, relaxed dinner. Overnight: London (2/3).\"},{\"variant\":\"L1\",\"date\":\"2027-09-12\",\"title\":\"Tower of London, Tower Bridge and farewell\",\"notes\":\"Morning: Tower of London prebooked admission, allocate around three hours for Crown Jewels, White Tower and Yeoman Warder tour if available. Afternoon: Tower Bridge photographs/optional high walkways, Borough Market (verify Sunday hours), riverfront, or Covent Garden souvenir time. Evening: final celebratory meal, pack and verify next day’s airport transfer. Overnight: London (3/3).\"},{\"variant\":\"L1\",\"date\":\"2027-09-13\",\"title\":\"Flight home\",\"notes\":\"Check out, travel to confirmed London airport with international departure buffer, and return to St. Louis on booked itinerary. Trip concludes.\"}]")


def fill_europe_day_details(db, trip_id):
    """Ground daily notes in preserved Master Trip Guide; do not overwrite edits."""
    for day in EUROPE_DAILY_PLANS:
        plan=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name=?",
            (trip_id,day["variant"])).fetchone()
        if not plan:continue
        current=db.execute("SELECT id,title,notes FROM scenario_itinerary WHERE scenario_id=? AND day_date=?",
            (plan["id"],day["date"])).fetchone()
        if current:
            if not current["notes"] and (current["title"].endswith(" · explore and discover") or current["title"]=="Departure day"):
                db.execute("UPDATE scenario_itinerary SET title=?,notes=? WHERE id=?",
                    (day["title"],day["notes"],current["id"]))
        else:
            city="Transit"
            db.execute("""INSERT INTO scenario_itinerary(trip_id,scenario_id,day_date,city,title,notes)
                VALUES (?,?,?,?,?,?)""",(trip_id,plan["id"],day["date"],city,day["title"],day["notes"]))


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
        fill_europe_day_details(db, existing["id"])
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
    fill_europe_day_details(db, trip_id)
    return trip_id
