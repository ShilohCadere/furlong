
import sqlite3
from datetime import date
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    abort
)

app = Flask(__name__)

DATABASE = Path(__file__).resolve().parent / "furlong.db"


def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with get_db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                destination TEXT
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS itinerary_days (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL,
                day_number INTEGER NOT NULL,
                title TEXT,
                trip_date TEXT,
                FOREIGN KEY (trip_id) REFERENCES trips(id)
                    ON DELETE CASCADE,
                UNIQUE (trip_id, day_number)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS saved_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL,
                city TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'hotel',
                price REAL,
                link TEXT,
                notes TEXT,
                is_preferred INTEGER NOT NULL DEFAULT 0,
                start_date TEXT,
                end_date TEXT,
                scenario_tag TEXT,
                origin TEXT,
                destination TEXT,
                departure_time TEXT,
                arrival_time TEXT,
                layovers TEXT,
                carrier TEXT,
                FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS trip_scenarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                budget_limit REAL NOT NULL DEFAULT 20000,
                other_costs REAL NOT NULL DEFAULT 0,
                UNIQUE(trip_id, name)
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS scenario_choices (
                scenario_id INTEGER NOT NULL REFERENCES trip_scenarios(id) ON DELETE CASCADE,
                city TEXT NOT NULL,
                category TEXT NOT NULL,
                option_id INTEGER NOT NULL REFERENCES saved_options(id) ON DELETE CASCADE,
                PRIMARY KEY(scenario_id, city, category)
            )
        """)
        connection.execute("""CREATE TABLE IF NOT EXISTS scenario_itinerary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            scenario_id INTEGER NOT NULL REFERENCES trip_scenarios(id) ON DELETE CASCADE,
            day_date TEXT NOT NULL,
            city TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            UNIQUE(scenario_id,day_date)
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS day_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            itinerary_id INTEGER NOT NULL REFERENCES scenario_itinerary(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            start_time TEXT,
            notes TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS scenario_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id INTEGER NOT NULL REFERENCES trip_scenarios(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            included_in_allowance INTEGER NOT NULL DEFAULT 1
        )""")
        # Safe additive migration for existing local trip databases.
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(saved_options)")}
        for field in ("start_date", "end_date", "scenario_tag", "origin", "destination", "departure_time", "arrival_time", "layovers", "carrier"):
            if field not in columns:
                connection.execute(f"ALTER TABLE saved_options ADD COLUMN {field} TEXT")


def get_trip(trip_id):
    with get_db_connection() as connection:
        trip = connection.execute(
            "SELECT * FROM trips WHERE id = ?",
            (trip_id,)
        ).fetchone()

    if trip is None:
        abort(404)

    return trip


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        trip_name = request.form.get("trip-name", "").strip()
        destination = request.form.get("destination", "").strip()

        if trip_name and len(trip_name) <= 120:
            with get_db_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO trips (name, destination)
                    VALUES (?, ?)
                    """,
                    (trip_name, destination)
                )

        return redirect(url_for("home"))

    with get_db_connection() as connection:
        trips = connection.execute(
            "SELECT * FROM trips ORDER BY id DESC"
        ).fetchall()

    return render_template("index.html", trips=trips)


@app.route("/trip/<int:trip_id>")
def trip_overview(trip_id):
    trip = get_trip(trip_id)

    with get_db_connection() as connection:
        days = connection.execute(
            """
            SELECT *
            FROM itinerary_days
            WHERE trip_id = ?
            ORDER BY day_number
            LIMIT 3
            """,
            (trip_id,)
        ).fetchall()

        day_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM itinerary_days
            WHERE trip_id = ?
            """,
            (trip_id,)
        ).fetchone()[0]

    return render_template(
        "trip.html",
        trip=trip,
        days=days,
        day_count=day_count
    )


@app.route("/trip/<int:trip_id>/edit", methods=["POST"])
def edit_trip(trip_id):
    trip_name = request.form.get("trip-name", "").strip()
    destination = request.form.get("destination", "").strip()

    if not trip_name or len(trip_name) > 120:
        abort(400, description="Enter a trip name of up to 120 characters.")

    get_trip(trip_id)

    with get_db_connection() as connection:
        connection.execute(
            """
            UPDATE trips
            SET name = ?, destination = ?
            WHERE id = ?
            """,
            (trip_name, destination, trip_id)
        )

    return redirect(url_for("trip_overview", trip_id=trip_id))


@app.route("/trip/<int:trip_id>/itinerary")
def itinerary(trip_id):
    trip=get_trip(trip_id)
    with get_db_connection() as db:
        scenarios=db.execute("SELECT * FROM trip_scenarios WHERE trip_id=? ORDER BY id",(trip_id,)).fetchall()
        sid=request.args.get("scenario",type=int)
        scenario=next((p for p in scenarios if p["id"]==sid),None) if sid else (scenarios[0] if scenarios else None)
        days=db.execute("SELECT * FROM itinerary_days WHERE trip_id=? ORDER BY day_number",(trip_id,)).fetchall()
        route_days=db.execute("SELECT * FROM scenario_itinerary WHERE scenario_id=? ORDER BY day_date",(scenario["id"],)).fetchall() if scenario else []
        activity_rows=db.execute("""SELECT a.* FROM day_activities a JOIN scenario_itinerary d ON d.id=a.itinerary_id
            WHERE d.scenario_id=? ORDER BY a.position,a.id""",(scenario["id"],)).fetchall() if scenario else []
    activities={}
    for item in activity_rows:activities.setdefault(item["itinerary_id"],[]).append(item)
    return render_template("itinerary.html",trip=trip,days=days,scenarios=scenarios,
       scenario=scenario,route_days=route_days,activities=activities)


@app.route("/trip/<int:trip_id>/itinerary/day",methods=["POST"])
def save_scenario_day(trip_id):
    get_trip(trip_id)
    sid=request.form.get("scenario_id",type=int)
    when=request.form.get("day_date","").strip()
    city=request.form.get("city","").strip()
    title=request.form.get("title","").strip()
    notes=request.form.get("notes","").strip()
    try:date.fromisoformat(when)
    except ValueError:abort(400,"Use a valid itinerary date")
    if len(city)>100 or len(title)>160 or len(notes)>1500:abort(400)
    with get_db_connection() as db:
        if not db.execute("SELECT 1 FROM trip_scenarios WHERE id=? AND trip_id=?",(sid,trip_id)).fetchone():abort(404)
        db.execute("""INSERT INTO scenario_itinerary(trip_id,scenario_id,day_date,city,title,notes)
            VALUES(?,?,?,?,?,?) ON CONFLICT(scenario_id,day_date) DO UPDATE SET
            city=excluded.city,title=excluded.title,notes=excluded.notes""",
            (trip_id,sid,when,city,title,notes))
    return redirect(url_for("itinerary",trip_id=trip_id,scenario=sid))


@app.route("/trip/<int:trip_id>/itinerary/activity",methods=["POST"])
def add_day_activity(trip_id):
    get_trip(trip_id)
    sid=request.form.get("scenario_id",type=int)
    day_id=request.form.get("itinerary_id",type=int)
    title=request.form.get("title","").strip()
    timing=request.form.get("start_time","").strip()
    notes=request.form.get("notes","").strip()
    if not title or len(title)>160 or len(timing)>30 or len(notes)>1000:abort(400)
    with get_db_connection() as db:
        if not db.execute("""SELECT 1 FROM scenario_itinerary
            WHERE id=? AND trip_id=? AND scenario_id=?""",(day_id,trip_id,sid)).fetchone():abort(404)
        position=db.execute("SELECT COALESCE(MAX(position),0)+1 FROM day_activities WHERE itinerary_id=?",(day_id,)).fetchone()[0]
        db.execute("INSERT INTO day_activities(itinerary_id,title,start_time,notes,position) VALUES(?,?,?,?,?)",
            (day_id,title,timing,notes,position))
    return redirect(url_for("itinerary",trip_id=trip_id,scenario=sid))



@app.route("/trip/<int:trip_id>/itinerary/activity/<int:activity_id>/edit",methods=["POST"])
def edit_day_activity(trip_id,activity_id):
    get_trip(trip_id)
    sid=request.form.get("scenario_id",type=int)
    dest=request.form.get("itinerary_id",type=int)
    title=request.form.get("title","").strip()
    timing=request.form.get("start_time","").strip()
    notes=request.form.get("notes","").strip()
    if not title or len(title)>160 or len(timing)>30 or len(notes)>1000:abort(400)
    with get_db_connection() as db:
        activity=db.execute("""SELECT a.id FROM day_activities a JOIN scenario_itinerary d ON d.id=a.itinerary_id
            WHERE a.id=? AND d.trip_id=? AND d.scenario_id=?""",(activity_id,trip_id,sid)).fetchone()
        destination=db.execute("SELECT id FROM scenario_itinerary WHERE id=? AND trip_id=? AND scenario_id=?",
            (dest,trip_id,sid)).fetchone()
        if not activity or not destination:abort(404)
        pos=db.execute("SELECT COALESCE(MAX(position),0)+1 FROM day_activities WHERE itinerary_id=?",
            (dest,)).fetchone()[0]
        db.execute("""UPDATE day_activities SET itinerary_id=?,title=?,start_time=?,notes=?,position=?
            WHERE id=?""",(dest,title,timing,notes,pos,activity_id))
    return redirect(url_for("itinerary",trip_id=trip_id,scenario=sid))


@app.route("/trip/<int:trip_id>/itinerary/activity/<int:activity_id>/delete",methods=["POST"])
def delete_day_activity(trip_id,activity_id):
    get_trip(trip_id)
    sid=request.form.get("scenario_id",type=int)
    with get_db_connection() as db:
        item=db.execute("""SELECT a.id FROM day_activities a JOIN scenario_itinerary d ON d.id=a.itinerary_id
            WHERE a.id=? AND d.trip_id=? AND d.scenario_id=?""",(activity_id,trip_id,sid)).fetchone()
        if not item:abort(404)
        db.execute("DELETE FROM day_activities WHERE id=?",(activity_id,))
    return redirect(url_for("itinerary",trip_id=trip_id,scenario=sid))


@app.route("/trip/<int:trip_id>/itinerary/add-day", methods=["POST"])
def add_itinerary_day(trip_id):
    with get_db_connection() as connection:
        # Lock writes while determining the next day number.
        connection.execute("BEGIN IMMEDIATE")

        trip = connection.execute(
            "SELECT id FROM trips WHERE id = ?",
            (trip_id,)
        ).fetchone()

        if trip is None:
            abort(404)

        next_number = connection.execute(
            """
            SELECT COALESCE(MAX(day_number), 0) + 1
            FROM itinerary_days
            WHERE trip_id = ?
            """,
            (trip_id,)
        ).fetchone()[0]

        connection.execute(
            """
            INSERT INTO itinerary_days (trip_id, day_number)
            VALUES (?, ?)
            """,
            (trip_id, next_number)
        )

    return redirect(url_for("itinerary", trip_id=trip_id))



@app.route("/trip/<int:trip_id>/options")
def saved_options(trip_id):
    trip = get_trip(trip_id)
    with get_db_connection() as connection:
        options = connection.execute(
            "SELECT * FROM saved_options WHERE trip_id = ? ORDER BY city COLLATE NOCASE, category, is_preferred DESC, price IS NULL, price, name",
            (trip_id,)
        ).fetchall()
    groups = {}
    for option in options:
        groups.setdefault(option["city"], []).append(option)
    preferred_total = sum(float(item["price"]) for item in options if item["is_preferred"] and item["price"] is not None)
    return render_template("options.html", trip=trip, groups=groups, preferred_total=preferred_total)


@app.route("/trip/<int:trip_id>/options/add", methods=["POST"])
def add_saved_option(trip_id):
    get_trip(trip_id)
    city = request.form.get("city", "").strip()
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "hotel").strip()
    link = request.form.get("link", "").strip()
    notes = request.form.get("notes", "").strip()
    price_raw = request.form.get("price", "").strip()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    if (start_date and not end_date) or (end_date and not start_date):
        abort(400, description="Provide both start and end dates, or neither.")
    if start_date:
        try:
            arrival = date.fromisoformat(start_date)
            departure = date.fromisoformat(end_date)
        except ValueError:
            abort(400, description="Dates must be valid.")
        if departure <= arrival:
            abort(400, description="End date must be later than start date.")
    if not city or not name or len(city) > 100 or len(name) > 160 or category not in ("hotel", "activity", "transport", "flight") or len(notes) > 1000 or len(link) > 500 or (link and not link.startswith(("https://", "http://"))):
        abort(400, description="Check the option fields and link.")
    try:
        price = float(price_raw) if price_raw else None
    except ValueError:
        abort(400, description="Price must be a number.")
    if price is not None and (not 0 <= price <= 10000000 or not __import__("math").isfinite(price)):
        abort(400, description="Price must be a valid nonnegative amount.")
    with get_db_connection() as connection:
        connection.execute(
            "INSERT INTO saved_options (trip_id, city, name, category, price, link, notes, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trip_id, city, name, category, price, link, notes, start_date or None, end_date or None)
        )
    return redirect(url_for("saved_options", trip_id=trip_id))


@app.route("/trip/<int:trip_id>/options/<int:option_id>/prefer", methods=["POST"])
def prefer_saved_option(trip_id, option_id):
    get_trip(trip_id)
    with get_db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        option = connection.execute(
            "SELECT * FROM saved_options WHERE id = ? AND trip_id = ?",
            (option_id, trip_id)
        ).fetchone()
        if option is None:
            abort(404)
        connection.execute(
            "UPDATE saved_options SET is_preferred = 0 WHERE trip_id = ? AND city = ? AND category = ?",
            (trip_id, option["city"], option["category"])
        )
        connection.execute("UPDATE saved_options SET is_preferred = 1 WHERE id = ?", (option_id,))
    return redirect(url_for("saved_options", trip_id=trip_id))


@app.route("/trip/<int:trip_id>/options/<int:option_id>/remove", methods=["POST"])
def remove_saved_option(trip_id, option_id):
    get_trip(trip_id)
    with get_db_connection() as connection:
        connection.execute("DELETE FROM saved_options WHERE id = ? AND trip_id = ?", (option_id, trip_id))
    return redirect(url_for("saved_options", trip_id=trip_id))



def option_fields():
    city = request.form.get("city", "").strip()
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "hotel").strip()
    link = request.form.get("link", "").strip()
    notes = request.form.get("notes", "").strip()
    start = request.form.get("start_date", "").strip()
    end = request.form.get("end_date", "").strip()
    raw = request.form.get("price", "").strip()
    if not city or not name or len(city)>100 or len(name)>160 or category not in ("hotel","activity","transport","flight") or len(link)>500 or len(notes)>1000 or (link and not link.startswith(("https://","http://"))):
        abort(400, "Invalid option details")
    if bool(start) != bool(end):
        abort(400,"Enter both dates or leave both blank")
    if start:
        try:
            if date.fromisoformat(end) <= date.fromisoformat(start):
                abort(400,"Checkout must follow check-in")
        except ValueError:
            abort(400,"Invalid dates")
    try:
        price = float(raw) if raw else None
    except ValueError:
        abort(400,"Invalid price")
    if price is not None and (not __import__("math").isfinite(price) or price<0 or price>10000000):
        abort(400,"Invalid price")
    return city,name,category,price,link,notes,start or None,end or None


@app.route("/trip/<int:trip_id>/options/<int:option_id>/edit",methods=["POST"])
def edit_saved_option(trip_id,option_id):
    get_trip(trip_id)
    fields=option_fields()
    with get_db_connection() as db:
        item=db.execute("SELECT * FROM saved_options WHERE id=? AND trip_id=?",(option_id,trip_id)).fetchone()
        if item is None: abort(404)
        db.execute("""UPDATE saved_options SET city=?,name=?,category=?,price=?,link=?,notes=?,start_date=?,end_date=?
            WHERE id=? AND trip_id=?""",(*fields,option_id,trip_id))
        # Remove scenario associations when a selected option changes its group.
        if item["city"]!=fields[0] or item["category"]!=fields[2]:
            db.execute("DELETE FROM scenario_choices WHERE option_id=?",(option_id,))
    if request.form.get("return_workspace") == "1":
        sid=request.form.get("scenario_id",type=int)
        with get_db_connection() as db:
            valid=db.execute("SELECT 1 FROM trip_scenarios WHERE id=? AND trip_id=?",(sid,trip_id)).fetchone()
        if valid:
            slug="".join(c.lower() if c.isalnum() or c=="-" else "-" for c in fields[0]).strip("-")
            return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+"#hotel-"+slug)
    return redirect(url_for("saved_options",trip_id=trip_id))


@app.route("/trip/<int:trip_id>/workspace")
def trip_workspace(trip_id):
    trip=get_trip(trip_id)
    with get_db_connection() as db:
        if trip["name"] == "Europe 2027":
            from europe_seed import add_missing_europe_candidates
            add_missing_europe_candidates(db,trip_id)
            from europe_seed import add_europe_route_days
            add_europe_route_days(db,trip_id)
            from europe_seed import fill_europe_day_details
            fill_europe_day_details(db,trip_id)
        scenarios=db.execute("SELECT * FROM trip_scenarios WHERE trip_id=? ORDER BY id",(trip_id,)).fetchall()
        if not scenarios:
            db.execute("INSERT INTO trip_scenarios (trip_id,name) VALUES (?,?)",(trip_id,"Plan A"))
            scenarios=db.execute("SELECT * FROM trip_scenarios WHERE trip_id=?",(trip_id,)).fetchall()
        selected_id=request.args.get("scenario",type=int) or scenarios[0]["id"]
        scenario=next((s for s in scenarios if s["id"]==selected_id),None)
        if scenario is None: abort(404)
        # Upgrade legacy flight allowances without changing the selected amounts.
        db.execute("""UPDATE saved_options SET category='flight'
            WHERE trip_id=? AND category='transport'
              AND city='International flights'""",(trip_id,))
        db.execute("""UPDATE scenario_choices SET category='flight'
            WHERE scenario_id IN (SELECT id FROM trip_scenarios WHERE trip_id=?)
              AND city='International flights' AND category='transport'""",(trip_id,))
        options=db.execute("SELECT * FROM saved_options WHERE trip_id=? ORDER BY city,category,price,name",(trip_id,)).fetchall()
        # Historical Europe imports predate scenario_tag; identify them without
        # disturbing user-created shared options or their saved selections.
        if trip["name"] == "Europe 2027":
            db.execute("""UPDATE saved_options SET scenario_tag=substr(notes,2,2)
                WHERE trip_id=? AND scenario_tag IS NULL
                AND notes GLOB '[[]S1 estimate]*' OR
                trip_id=? AND scenario_tag IS NULL AND notes GLOB '[[]L1 estimate]*'""",(trip_id,trip_id))
            db.execute("""UPDATE saved_options SET scenario_tag=substr(name,1,2)
                WHERE trip_id=? AND scenario_tag IS NULL
                AND (name LIKE 'S1: %' OR name LIKE 'L1: %')""",(trip_id,))
        expenses=db.execute("SELECT * FROM scenario_expenses WHERE scenario_id=? ORDER BY category,name",(scenario["id"],)).fetchall()
        choices=db.execute("""SELECT sc.city, sc.category, sc.option_id FROM scenario_choices sc
            JOIN saved_options o ON o.id=sc.option_id AND o.trip_id=?
            WHERE sc.scenario_id=?""",(trip_id,scenario["id"])).fetchall()
    selected={(r["city"],r["category"]):r["option_id"] for r in choices}
    groups={}
    for opt in options:
        if opt["scenario_tag"] is None or opt["scenario_tag"] == scenario["name"]:
            groups.setdefault((opt["city"],opt["category"]),[]).append(opt)
    picked=[next((o for o in choiceset if o["id"]==selected.get(key)),None) for key,choiceset in groups.items()]
    picked=[p for p in picked if p is not None]
    subtotal=sum(o["price"] or 0 for o in picked)
    missing=[o["name"] for o in picked if o["price"] is None]
    stays=sorted([o for o in picked if o["category"]=="hotel" and o["start_date"] and o["end_date"]],key=lambda o:o["start_date"])
    warnings=[]
    for a,b in zip(stays,stays[1:]):
        if a["end_date"]>b["start_date"]:
            warnings.append("Overlapping stays: "+a["name"]+" and "+b["name"])
        elif a["end_date"]<b["start_date"]:
            warnings.append("Gap between "+a["name"]+" and "+b["name"])
    undated=[o["name"] for o in picked if o["category"]=="hotel" and not o["start_date"]]
    hotels={k:v for k,v in groups.items() if k[1]=="hotel"}
    flights={k:v for k,v in groups.items() if k[1]=="flight"}
    excursions={k:v for k,v in groups.items() if k[1]=="activity"}
    transport={k:v for k,v in groups.items() if k[1]=="transport"}
    selected_flights=[p for p in picked if p["category"]=="flight"]
    extra_expenses=sum(row["amount"] for row in expenses if not row["included_in_allowance"])
    total=subtotal+scenario["other_costs"]+extra_expenses
    return render_template("workspace.html",trip=trip,scenarios=scenarios,scenario=scenario,groups=groups,hotels=hotels,flights=flights,excursions=excursions,transport=transport,selected_flights=selected_flights,selected=selected,stays=stays,warnings=warnings,undated=undated,missing=missing,subtotal=subtotal,total=total,remaining=scenario["budget_limit"]-total,expenses=expenses,extra_expenses=extra_expenses)


@app.route("/trip/<int:trip_id>/flights/add", methods=["POST"])
def add_flight_option(trip_id):
    get_trip(trip_id)
    name=request.form.get("name","").strip()
    route=request.form.get("route","").strip()
    origin=request.form.get("origin","").strip()
    destination=request.form.get("destination","").strip()
    carrier=request.form.get("carrier","").strip()
    departure=request.form.get("departure_time","").strip()
    arrival=request.form.get("arrival_time","").strip()
    layovers=request.form.get("layovers","").strip()
    scenario_tag=request.form.get("scenario_tag","").strip() or None
    price_str=request.form.get("price","").strip()
    if not name or not route or len(name)>160 or len(route)>100 or any(len(x)>300 for x in (origin,destination,carrier,departure,arrival,layovers)):
        abort(400,"Invalid flight information")
    if scenario_tag:
        with get_db_connection() as db:
            if not db.execute("SELECT 1 FROM trip_scenarios WHERE trip_id=? AND name=?",(trip_id,scenario_tag)).fetchone():abort(400)
    try: price=float(price_str) if price_str else None
    except ValueError: abort(400)
    if price is not None and (not __import__("math").isfinite(price) or price<0 or price>10000000): abort(400)
    with get_db_connection() as db:
        db.execute("""INSERT INTO saved_options
        (trip_id,city,name,category,price,scenario_tag,origin,destination,departure_time,arrival_time,layovers,carrier)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (trip_id,route,name,"flight",price,scenario_tag,origin,destination,departure,arrival,layovers,carrier))
    return redirect(url_for("trip_workspace",trip_id=trip_id))


@app.route("/trip/<int:trip_id>/excursions/add", methods=["POST"])
def add_excursion_option(trip_id):
    get_trip(trip_id)
    city=request.form.get("city","").strip()
    name=request.form.get("name","").strip()
    day=request.form.get("start_date","").strip()
    raw=request.form.get("price","").strip()
    if not city or not name or len(city)>100 or len(name)>160:abort(400)
    if day:
        try: date.fromisoformat(day)
        except ValueError:abort(400)
    try:price=float(raw) if raw else None
    except ValueError:abort(400)
    if price is not None and (not __import__("math").isfinite(price) or price<0 or price>10000000):abort(400)
    with get_db_connection() as db:
        db.execute("""INSERT INTO saved_options(trip_id,city,name,category,price,start_date,notes)
            VALUES (?,?,?,'activity',?,?,?)""",
            (trip_id,city,name,price,day or None,request.form.get("notes","")[:1000]))
    return redirect(url_for("trip_workspace",trip_id=trip_id))


@app.route("/trip/<int:trip_id>/workspace/expense",methods=["POST"])
def add_scenario_expense(trip_id):
    get_trip(trip_id)
    sid=request.form.get("scenario_id",type=int)
    category=request.form.get("category","").strip()
    name=request.form.get("name","").strip()
    included=int(request.form.get("included_in_allowance","1"))
    if category not in ("food","excursion","flight","transport","other") or not name or len(name)>160 or included not in (0,1):abort(400)
    try:amount=float(request.form.get("amount",""))
    except ValueError:abort(400)
    if not __import__("math").isfinite(amount) or not 0<=amount<=10000000:abort(400)
    with get_db_connection() as db:
        if not db.execute("SELECT 1 FROM trip_scenarios WHERE id=? AND trip_id=?",(sid,trip_id)).fetchone():abort(404)
        db.execute("INSERT INTO scenario_expenses(scenario_id,category,name,amount,included_in_allowance) VALUES(?,?,?,?,?)",
            (sid,category,name,amount,included))
    return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+"#budget")


@app.route("/trip/<int:trip_id>/workspace/expense/<int:expense_id>/delete",methods=["POST"])
def delete_scenario_expense(trip_id,expense_id):
    get_trip(trip_id)
    sid=request.form.get("scenario_id",type=int)
    with get_db_connection() as db:
        row=db.execute("""SELECT e.id FROM scenario_expenses e JOIN trip_scenarios s ON s.id=e.scenario_id
            WHERE e.id=? AND e.scenario_id=? AND s.trip_id=?""",(expense_id,sid,trip_id)).fetchone()
        if row is None:abort(404)
        db.execute("DELETE FROM scenario_expenses WHERE id=?",(expense_id,))
    return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+"#budget")


@app.route("/trip/<int:trip_id>/flights/<int:option_id>/edit",methods=["POST"])
def edit_flight_option(trip_id,option_id):
    get_trip(trip_id)
    allowed=("name","origin","destination","carrier","departure_time","arrival_time","layovers")
    fields={key:request.form.get(key,"").strip() for key in allowed}
    if not fields["name"] or len(fields["name"])>160 or any(len(fields[key])>300 for key in allowed if key!="name"):abort(400)
    raw=request.form.get("price","").strip()
    try:price=float(raw) if raw else None
    except ValueError:abort(400)
    if price is not None and (not __import__("math").isfinite(price) or price<0 or price>10000000):abort(400)
    with get_db_connection() as db:
        row=db.execute("SELECT id FROM saved_options WHERE id=? AND trip_id=? AND category='flight'",(option_id,trip_id)).fetchone()
        if not row:abort(404)
        db.execute("""UPDATE saved_options SET name=?,origin=?,destination=?,carrier=?,
            departure_time=?,arrival_time=?,layovers=?,price=? WHERE id=? AND trip_id=?""",
            (fields["name"],fields["origin"],fields["destination"],fields["carrier"],
             fields["departure_time"],fields["arrival_time"],fields["layovers"],price,option_id,trip_id))
    sid=request.form.get("scenario_id",type=int)
    return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+"#flights")



@app.route("/trip/<int:trip_id>/workspace/scenarios",methods=["POST"])
def add_trip_scenario(trip_id):
    get_trip(trip_id)
    name=request.form.get("name","").strip()
    if not name or len(name)>50: abort(400)
    with get_db_connection() as db:
        try:
            db.execute("INSERT INTO trip_scenarios (trip_id,name) VALUES (?,?)",(trip_id,name))
        except sqlite3.IntegrityError:
            abort(400,"Scenario name already used")
        sid=db.execute("SELECT last_insert_rowid()").fetchone()[0]
    return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid))


@app.route("/trip/<int:trip_id>/workspace/settings",methods=["POST"])
def workspace_settings(trip_id):
    get_trip(trip_id)
    sid=request.form.get("scenario_id",type=int)
    try:
        budget=float(request.form.get("budget_limit",""))
        other=float(request.form.get("other_costs",""))
    except ValueError: abort(400,"Costs must be numbers")
    if not all(__import__("math").isfinite(x) and 0<=x<=100000000 for x in [budget,other]): abort(400)
    with get_db_connection() as db:
        row=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND id=?",(trip_id,sid)).fetchone()
        if not row: abort(404)
        db.execute("UPDATE trip_scenarios SET budget_limit=?,other_costs=? WHERE id=?",(budget,other,sid))
    return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid))


@app.route("/trip/<int:trip_id>/workspace/choose",methods=["POST"])
def choose_scenario_option(trip_id):
    get_trip(trip_id)
    sid=request.form.get("scenario_id",type=int)
    oid=request.form.get("option_id",type=int)
    city=request.form.get("city","")
    category=request.form.get("category","")
    with get_db_connection() as db:
        plan=db.execute("SELECT * FROM trip_scenarios WHERE id=? AND trip_id=?",(sid,trip_id)).fetchone()
        if not plan:abort(404)
        if oid:
            opt=db.execute("SELECT * FROM saved_options WHERE id=? AND trip_id=?",(oid,trip_id)).fetchone()
            if not opt or opt["city"]!=city or opt["category"]!=category or (opt["scenario_tag"] is not None and opt["scenario_tag"] != plan["name"]):abort(400,"Option belongs to another scenario")
            db.execute("""INSERT INTO scenario_choices (scenario_id,city,category,option_id) VALUES (?,?,?,?)
                ON CONFLICT(scenario_id,city,category) DO UPDATE SET option_id=excluded.option_id""",(sid,city,category,oid))
        else:
            db.execute("DELETE FROM scenario_choices WHERE scenario_id=? AND city=? AND category=?",(sid,city,category))
    return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid))



@app.route("/trips/import-europe-2027",methods=["POST"])
def import_europe_trip():
    from europe_seed import import_europe_2027
    with get_db_connection() as db:
        trip_id=import_europe_2027(db)
    return redirect(url_for("trip_workspace",trip_id=trip_id))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
