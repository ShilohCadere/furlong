"""Add two reverse-direction Europe 2027 scenarios without altering S1 or L1.

These are research plans, not booked trips. Hotel, flight and rail prices are
left NULL until a date-specific four-adult/two-room quote is checked. Public
activity prices, where present, are converted group planning estimates using
rates retrieved 2026-10-27 (GBP/USD 1.33062, EUR/USD 1.11374).
User notes are intentionally empty. Re-running never changes existing variants.
"""
from datetime import date

GBP_TO_USD = 1.33062
EUR_TO_USD = 1.11374

# One transit departure day, 12/14 on-the-ground days and one return day.
# The unchanged September 28 return and September 15/13 outbound departures
# preserve the lengths of the currently approved S1 and L1 options.
PLANS = {
    "Backwards 12 OTG": {
        "source": "S1",
        "departure": "2027-09-15",
        "stays": [
            ("London", "2027-09-16", "2027-09-19"),
            ("Inverness", "2027-09-19", "2027-09-21"),
            ("Edinburgh", "2027-09-21", "2027-09-23"),
            ("Edinburgh Castle Night", "2027-09-23", "2027-09-24"),
            ("Galway", "2027-09-24", "2027-09-26"),
            ("Dublin", "2027-09-26", "2027-09-28"),
        ],
        "days": [
            ("2027-09-15", "Transit", "Depart St. Louis for London", []),
            ("2027-09-16", "London", "Arrive London; easy sightseeing", ["Arrival and hotel check-in", "Westminster and South Bank stroll"]),
            ("2027-09-17", "London", "Stonehenge-only excursion", ["Stonehenge-only return coach tour"]),
            ("2027-09-18", "London", "Tower of London and riverside", ["Tower of London", "Tower Bridge and riverside walk"]),
            ("2027-09-19", "Inverness", "London to Inverness", ["Flight London to Inverness", "River Ness walk"]),
            ("2027-09-20", "Inverness", "Isle of Skye and Eilean Donan", ["Rabbie's Skye and Eilean Donan day tour"]),
            ("2027-09-21", "Edinburgh", "Train to Edinburgh; Old Town", ["ScotRail Inverness to Edinburgh", "Old Town orientation"]),
            ("2027-09-22", "Edinburgh", "Edinburgh Castle and Royal Mile", ["Edinburgh Castle", "Royal Mile"]),
            ("2027-09-23", "Edinburgh", "Melville Castle stay", ["Transfer to Melville Castle", "Castle overnight in two rooms"]),
            ("2027-09-24", "Galway", "Edinburgh to Shannon and Galway", ["Flight Edinburgh to Shannon (schedule unconfirmed)", "Transfer Shannon to Galway"]),
            ("2027-09-25", "Galway", "Aran Islands and Cliffs of Moher", ["Aran Islands and Cliffs of Moher cruise (weather dependent)"]),
            ("2027-09-26", "Dublin", "Galway to Dublin", ["Irish Rail Galway to Dublin", "Easy Dublin city walk"]),
            ("2027-09-27", "Dublin", "Trinity and historic Dublin", ["Book of Kells Experience", "Historic Dublin walk"]),
            ("2027-09-28", "Transit", "Return Dublin to St. Louis", ["International return flight (connection to be confirmed)"]),
        ],
    },
    "Backwards 14 OTG": {
        "source": "L1",
        "departure": "2027-09-13",
        "stays": [
            ("London", "2027-09-14", "2027-09-17"),
            ("Inverness", "2027-09-17", "2027-09-19"),
            ("Edinburgh", "2027-09-19", "2027-09-21"),
            ("Edinburgh Castle Night", "2027-09-21", "2027-09-22"),
            ("Galway", "2027-09-22", "2027-09-25"),
            ("Dublin", "2027-09-25", "2027-09-28"),
        ],
        "days": [
            ("2027-09-13", "Transit", "Depart St. Louis for London", []),
            ("2027-09-14", "London", "Arrive London; easy sightseeing", ["Arrival and hotel check-in", "Westminster and South Bank stroll"]),
            ("2027-09-15", "London", "Stonehenge-only excursion", ["Stonehenge-only return coach tour"]),
            ("2027-09-16", "London", "Tower of London and riverside", ["Tower of London", "Tower Bridge and riverside walk"]),
            ("2027-09-17", "Inverness", "London to Inverness", ["Flight London to Inverness", "River Ness walk"]),
            ("2027-09-18", "Inverness", "Isle of Skye and Eilean Donan", ["Rabbie's Skye and Eilean Donan day tour"]),
            ("2027-09-19", "Edinburgh", "Train to Edinburgh; Old Town", ["ScotRail Inverness to Edinburgh", "Old Town orientation"]),
            ("2027-09-20", "Edinburgh", "Edinburgh Castle and Royal Mile", ["Edinburgh Castle", "Royal Mile"]),
            ("2027-09-21", "Edinburgh", "Melville Castle stay", ["Transfer to Melville Castle", "Castle overnight in two rooms"]),
            ("2027-09-22", "Galway", "Edinburgh to Shannon and Galway", ["Flight Edinburgh to Shannon (schedule unconfirmed)", "Transfer Shannon to Galway"]),
            ("2027-09-23", "Galway", "Connemara and Kylemore Abbey", ["Connemara and Kylemore Abbey day tour"]),
            ("2027-09-24", "Galway", "Aran Islands and Cliffs of Moher", ["Aran Islands and Cliffs of Moher cruise (weather dependent)"]),
            ("2027-09-25", "Dublin", "Galway to Dublin", ["Irish Rail Galway to Dublin", "Easy Dublin city walk"]),
            ("2027-09-26", "Dublin", "Trinity and historic Dublin", ["Book of Kells Experience", "Historic Dublin walk"]),
            ("2027-09-27", "Dublin", "Kilmainham Gaol and Guinness Storehouse", ["Kilmainham Gaol", "Guinness Storehouse"]),
            ("2027-09-28", "Transit", "Return Dublin to St. Louis", ["International return flight (connection to be confirmed)"]),
        ],
    },
}

# Verified official supplier booking pages; no intermediary or speculative links.
# Price fields for stays always remain NULL until dates and room count are quoted.
STAY_CHOICES = {
    "London": [
        ("Premier Inn London County Hall", "hotel", "https://www.premierinn.com/gb/en/hotels/england/greater-london/london/london-county-hall.html"),
    ],
    "Inverness": [
        ("Dionard Guest House", "hotel", "https://www.dionardguesthouse.co.uk/"),
    ],
    "Edinburgh": [
        ("Premier Inn Edinburgh City Centre (Princes Street)", "hotel", "https://www.premierinn.com/gb/en/hotels/scotland/lothian/edinburgh/edinburgh-city-centre-princes-street.html"),
        ("hub by Premier Inn Edinburgh Haymarket", "hotel", "https://www.premierinn.com/gb/en/hotels/scotland/lothian/edinburgh/hub-edinburgh-haymarket.html"),
    ],
    "Edinburgh Castle Night": [
        ("Melville Castle — two castle rooms", "castle", "https://melvillecastle.com/roombooking/"),
    ],
    "Galway": [
        ("Eyre Square Townhouse", "hotel", "https://www.eyresquaretownhouse.com/"),
        ("The Western Hotel", "hotel", "https://www.westernhotelgalway.ie/"),
        ("Eyre Square Hotel", "hotel", "https://www.eyresquarehotel.com/"),
    ],
    "Dublin": [
        ("Premier Inn Dublin City Centre (Temple Bar)", "hotel", "https://www.premierinn.com/gb/en/hotels/republic-of-ireland/dublin/dublin/dublin-city-centre-temple-bar.html"),
        ("Keavan's Port", "hotel", "https://www.jdwetherspoon.com/pubs/keavans-port-dublin/"),
    ],
}

# Converted from published per-adult rates for four travelers, as research
# estimates only (not date-specific tickets). "from" figures can increase.
ACTIVITIES = [
    ("London", "Simply Stonehenge coach tour — 4 adults, public from-price", "https://www.goldentours.com/day-trips-from-london/simply-stonehenge-tour-morning", "GBP", 60.83, None),
    ("London", "Tower of London — 4 adult tickets, published admission", "https://www.hrp.org.uk/tower-of-london/visit/tickets-and-prices/", "GBP", 38, None),
    ("Edinburgh", "Edinburgh Castle — ticket booking", "https://www.edinburghcastle.scot/plan-your-visit/tickets/", None, None, None),
    ("Inverness", "Rabbie's Skye and Eilean Donan — guided day tour", "https://www.rabbies.com/en-gb/tour/skye-eilean-donan-castle-day-tour-from-inverness", None, None, None),
    ("Galway", "Aran Islands and Cliffs of Moher ferry — 4 adults, published rate", "https://www.aranislandferries.com/day-tours/galway-city/cliffs-of-moher", "EUR", 55, None),
    ("Galway", "Connemara and Kylemore Abbey — 4 adults, public from-price", "https://lallytours.com/tour/connemara-and-kylemore-abbey-full-day-tour/", "EUR", 65, "Backwards 14 OTG"),
    ("Dublin", "Book of Kells Experience — 4 adults, public from-price", "https://www.visittrinity.ie/book-now-tickets/", "EUR", 25, None),
    ("Dublin", "Kilmainham Gaol — 4 adult tickets, published admission", "https://www.kilmainhamgaolmuseum.ie/", "EUR", 8, "Backwards 14 OTG"),
    ("Dublin", "Guinness Storehouse — 4 adults, public from-price", "https://www.guinness-storehouse.com/en/booking?experience=SGI", "EUR", 24, "Backwards 14 OTG"),
]

TRANSPORT = [
    ("International flights", "British Airways — St. Louis to London Heathrow", "flight", "https://www.britishairways.com/content/en/us/flights/england/london"),
    ("International flights", "Dublin to St. Louis — airline booking search", "flight", "https://www.britishairways.com/travel/booking/public/en_gb"),
    ("UK regional flights", "London to Inverness — airline booking search", "flight", "https://www.britishairways.com/travel/booking/public/en_gb"),
    ("Ireland regional flights", "Ryanair Edinburgh to Shannon — flight search", "flight", "https://www.ryanair.com/gb/en/flights/flights-from-edinburgh-to-shannon"),
    ("Scotland rail", "ScotRail Inverness to Edinburgh — official tickets", "transport", "https://www.buytickets.scotrail.co.uk/buytickets/login.aspx?TabName=deliveryoption.aspx"),
    ("Ireland rail", "Irish Rail Galway to Dublin — official fares and booking", "transport", "https://www.irishrail.ie/rail-fares-and-tickets/dublin-galway"),
    ("Ireland transfers", "Irish Citylink — Galway / Shannon transfers (verify stops)", "transport", "https://www.citylink.ie/"),
]


def _cost_usd(currency, amount):
    if currency is None or amount is None:
        return None
    return round(4 * amount * (GBP_TO_USD if currency == "GBP" else EUR_TO_USD), 2)


def ensure_reverse_europe_routes(db, trip_id):
    """Create only missing named scenarios. Never overwrite any saved user edit."""
    existing = {r["name"] for r in db.execute(
        "SELECT name FROM trip_scenarios WHERE trip_id=?", (trip_id,)).fetchall()}
    for name, plan in PLANS.items():
        if name in existing:
            continue
        original = db.execute(
            "SELECT * FROM trip_scenarios WHERE trip_id=? AND name=?",
            (trip_id, plan["source"])).fetchone()
        if original is None:
            continue

        days_on_ground = 12 if name == "Backwards 12 OTG" else 14
        assert len(plan["days"]) == days_on_ground + 2
        assert (date.fromisoformat(plan["days"][-1][0]) -
                date.fromisoformat(plan["departure"])).days == days_on_ground + 1

        # No hidden auto-flight allowance. Keep four-adult food budget at $80/day
        # plus the source plan's explicit non-flight reserves.
        db.execute("""INSERT INTO trip_scenarios
          (trip_id,name,budget_limit,other_costs,food_travelers,food_days,
           food_daily_rate,ground_transport_allowance,contingency_allowance,
           insurance_allowance,fees_allowance)
          VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
          (trip_id, name, original["budget_limit"], 0, 4,
           days_on_ground, 80, original["ground_transport_allowance"],
           original["contingency_allowance"], original["insurance_allowance"],
           original["fees_allowance"]))
        sid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        for when, city, title, activities in plan["days"]:
            db.execute("""INSERT INTO scenario_itinerary
                (trip_id,scenario_id,day_date,city,title,notes)
                VALUES (?,?,?,?,?,'')""", (trip_id,sid,when,city,title))
            day_id=db.execute("SELECT last_insert_rowid()").fetchone()[0]
            for position, activity in enumerate(activities, 1):
                db.execute("""INSERT INTO day_activities
                    (itinerary_id,title,start_time,notes,position)
                    VALUES (?,?,NULL,'',?)""", (day_id,activity,position))

        for span_name, begin, end in plan["stays"]:
            city = "Edinburgh" if span_name == "Edinburgh Castle Night" else span_name
            for idx, (hotel, category, link) in enumerate(STAY_CHOICES[span_name]):
                db.execute("""INSERT INTO saved_options
                   (trip_id,city,name,category,price,link,notes,start_date,
                    end_date,scenario_tag) VALUES (?,?,?,?,NULL,?,'',?,?,?)""",
                   (trip_id,city,hotel,category,link,begin,end,name))
                oid=db.execute("SELECT last_insert_rowid()").fetchone()[0]
                if idx == 0:
                    db.execute("""INSERT INTO scenario_choices
                        (scenario_id,city,category,option_id) VALUES (?,?,?,?)""",
                        (sid,city,category,oid))

        # Research choices are not auto-selected: optional spending should only
        # hit the budget after the traveler chooses it. Flight prices unquoted.
        for city,label,link,currency,amount,only in ACTIVITIES:
            if only and only != name:
                continue
            db.execute("""INSERT INTO saved_options
              (trip_id,city,name,category,price,link,notes,scenario_tag)
              VALUES (?,?,?,'activity',?,?,'',?)""",
              (trip_id,city,label,_cost_usd(currency,amount),link,name))
        for city,label,category,link in TRANSPORT:
            db.execute("""INSERT INTO saved_options
              (trip_id,city,name,category,price,link,notes,scenario_tag)
              VALUES (?,?,?, ?,NULL,?,'',?)""",
              (trip_id,city,label,category,link,name))
    return None
