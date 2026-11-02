
import sqlite3
import os
import secrets
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    abort, session, g
)

from city_colors import city_color, route_colors

app = Flask(__name__)
app.jinja_env.globals.update(city_color=city_color, route_colors=route_colors)

# Set FURLONG_DATA_DIR to a persistent, writable volume in production.
# Existing local installations retain their original database location.
DATA_DIR = Path(os.environ.get("FURLONG_DATA_DIR", str(Path(__file__).resolve().parent))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE = DATA_DIR / "furlong.db"
# Local development sessions remain valid when Flask restarts.
_secret_path = Path(__file__).resolve().parent / ".furlong_session_secret"
if os.environ.get("FURLONG_SECRET_KEY"):
    app.secret_key=os.environ["FURLONG_SECRET_KEY"]
else:
    if not _secret_path.exists():
        try:
            fd=os.open(_secret_path,os.O_CREAT | os.O_EXCL | os.O_WRONLY,0o600)
            with os.fdopen(fd,"w") as stream:stream.write(secrets.token_hex(32))
        except FileExistsError:pass
    app.secret_key=_secret_path.read_text().strip()
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("FURLONG_HTTPS", "0") == "1")



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

        connection.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL
        )""")
        trip_columns={row["name"] for row in connection.execute("PRAGMA table_info(trips)")}
        if "user_id" not in trip_columns:
            connection.execute("ALTER TABLE trips ADD COLUMN user_id INTEGER REFERENCES users(id)")
        connection.execute("""CREATE TABLE IF NOT EXISTS excluded_seed_options (
            trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            city TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL,
            scenario_tag TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (trip_id,city,name,category,scenario_tag)
        )""")
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
                food_budget REAL NOT NULL DEFAULT 0,
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
        scenario_columns={row["name"] for row in connection.execute("PRAGMA table_info(trip_scenarios)")}
        if "food_budget" not in scenario_columns:
            connection.execute("ALTER TABLE trip_scenarios ADD COLUMN food_budget REAL NOT NULL DEFAULT 0")
        connection.execute("""CREATE TABLE IF NOT EXISTS flight_option_dates (
            option_id INTEGER NOT NULL REFERENCES saved_options(id) ON DELETE CASCADE,
            scenario_id INTEGER NOT NULL REFERENCES trip_scenarios(id) ON DELETE CASCADE,
            departure_date TEXT NOT NULL,
            PRIMARY KEY(option_id,scenario_id)
        )""")
        # Safe additive migration for existing local trip databases.
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(saved_options)")}
        for field in ("start_date", "end_date", "scenario_tag", "origin", "destination", "departure_time", "arrival_time", "layovers", "carrier", "activity_group"):
            if field not in columns:
                connection.execute(f"ALTER TABLE saved_options ADD COLUMN {field} TEXT")

        connection.execute("""CREATE TABLE IF NOT EXISTS activity_option_dates (
            option_id INTEGER NOT NULL REFERENCES saved_options(id) ON DELETE CASCADE,
            scenario_id INTEGER NOT NULL REFERENCES trip_scenarios(id) ON DELETE CASCADE,
            activity_date TEXT NOT NULL,
            PRIMARY KEY(option_id,scenario_id)
        )""")


def workspace_option_key(option):
    # Each experience has its own alternatives; cities can contain many experiences.
    city=option["city"]
    if option["category"]=="activity":
        city += " · " + (option["activity_group"] or option["name"])
    return city,option["category"]


def workspace_selected(options, choices):
    by_id={o["id"]:o for o in options}
    return {workspace_option_key(by_id[r["option_id"]]):r["option_id"]
            for r in choices if r["option_id"] in by_id}


def get_trip(trip_id):
    with get_db_connection() as connection:
        trip = connection.execute(
            "SELECT * FROM trips WHERE id = ? AND user_id = ?",
            (trip_id,session.get("user_id"))
        ).fetchone()

    if trip is None:
        abort(404)

    return trip


def csrf_token():
    """Return a session-bound token for HTML POST forms."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def validate_csrf_token():
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not app.config.get("TESTING", False):
        submitted = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
        expected = session.get("_csrf_token")
        if not expected or not submitted or not secrets.compare_digest(expected, submitted):
            abort(400, description="Invalid or missing CSRF token")


@app.before_request
def require_login():
    if request.endpoint in ("login","register","static") or request.endpoint is None:
        return
    if not session.get("user_id"):
        return redirect(url_for("login"))
    # Enforce ownership even for legacy handlers that do not call get_trip().
    trip_id=(request.view_args or {}).get("trip_id")
    if trip_id is not None:
        with get_db_connection() as db:
            allowed=db.execute("SELECT 1 FROM trips WHERE id=? AND user_id=?",
                               (trip_id,session["user_id"])).fetchone()
        if not allowed:abort(404)


@app.context_processor
def logged_in_user():
    return {"active_username":session.get("username")}


@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="GET":return render_template("auth.html",mode="register",error=None)
    username=request.form.get("username","").strip()
    password=request.form.get("password","")
    if not 3<=len(username)<=40 or not username.replace("_","").replace("-","").isalnum() or len(password)<10:
        return render_template("auth.html",mode="register",
            error="Use a 3–40 character username (letters, numbers, _ or -) and a password of at least 10 characters."),400
    with get_db_connection() as db:
        if db.execute("SELECT 1 FROM users WHERE username=?",(username,)).fetchone():
            return render_template("auth.html",mode="register",error="That username is already taken."),409
        had_users=db.execute("SELECT COUNT(*) FROM users").fetchone()[0]>0
        db.execute("INSERT INTO users(username,password_hash) VALUES (?,?)",
                   (username,generate_password_hash(password)))
        uid=db.execute("SELECT last_insert_rowid()").fetchone()[0]
        # First local account inherits this installation's existing guest trips.
        # Future accounts never inherit other users' trips.
        if not had_users and os.environ.get("FURLONG_CLAIM_LEGACY_TRIPS") == "1":
            db.execute("UPDATE trips SET user_id=? WHERE user_id IS NULL",(uid,))
    session.clear()
    session.update(user_id=uid,username=username)
    return redirect(url_for("home"))


@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="GET":return render_template("auth.html",mode="login",error=None)
    username=request.form.get("username","").strip()
    with get_db_connection() as db:
        user=db.execute("SELECT * FROM users WHERE username=?",(username,)).fetchone()
    if not user or not check_password_hash(user["password_hash"],request.form.get("password","")):
        return render_template("auth.html",mode="login",error="Incorrect username or password."),401
    session.clear()
    session.update(user_id=user["id"],username=user["username"])
    return redirect(url_for("home"))


@app.route("/logout",methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        trip_name = request.form.get("trip-name", "").strip()
        destination = request.form.get("destination", "").strip()
        first_route = request.form.get("first-route-name", "Main route").strip()
        if not first_route or len(first_route) > 50: abort(400, "Enter a route name up to 50 characters.")

        if trip_name and len(trip_name) <= 120:
            with get_db_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO trips (name, destination, user_id)
                    VALUES (?, ?, ?)
                    """,
                    (trip_name, destination,session["user_id"])
                )
                trip_id=connection.execute("SELECT last_insert_rowid()").fetchone()[0]
                connection.execute("INSERT INTO trip_scenarios (trip_id,name) VALUES (?,?)",(trip_id,first_route))

        return redirect(url_for("home"))

    with get_db_connection() as connection:
        trips = connection.execute(
            "SELECT * FROM trips WHERE user_id=? ORDER BY id DESC"
            ,(session["user_id"],)
        ).fetchall()

    return render_template("index.html", trips=trips)


@app.route("/trip/<int:trip_id>/legacy")
def trip_overview(trip_id):
    trip = get_trip(trip_id)

    with get_db_connection() as connection:
        scenarios = connection.execute(
            "SELECT * FROM trip_scenarios WHERE trip_id=? ORDER BY id", (trip_id,)
        ).fetchall()
        sid = request.args.get("scenario", type=int)
        scenario = next((s for s in scenarios if s["id"] == sid), None) if sid is not None else (scenarios[0] if scenarios else None)
        if sid is not None and scenario is None:
            abort(404)
        route_days = connection.execute(
            "SELECT * FROM scenario_itinerary WHERE scenario_id=? ORDER BY day_date",
            (scenario["id"],)
        ).fetchall() if scenario else []
        legacy_days = connection.execute(
            "SELECT * FROM itinerary_days WHERE trip_id=? ORDER BY day_number", (trip_id,)
        ).fetchall()
        # Preview the actual saved options available to the active trip version.
        # Shared options are eligible; alternatives from other versions are not.
        if scenario:
            saved_ideas = connection.execute(
                """SELECT id, name, city, category, price, start_date FROM saved_options
                   WHERE trip_id=? AND (scenario_tag IS NULL OR scenario_tag=?)
                   ORDER BY id DESC LIMIT 3""",
                (trip_id, scenario["name"])
            ).fetchall()
            saved_ideas_count = connection.execute(
                """SELECT COUNT(*) FROM saved_options
                   WHERE trip_id=? AND (scenario_tag IS NULL OR scenario_tag=?)""",
                (trip_id, scenario["name"])
            ).fetchone()[0]
        else:
            saved_ideas = connection.execute(
                """SELECT id, name, city, category, price, start_date FROM saved_options
                   WHERE trip_id=? ORDER BY id DESC LIMIT 3""", (trip_id,)
            ).fetchall()
            saved_ideas_count = connection.execute(
                "SELECT COUNT(*) FROM saved_options WHERE trip_id=?", (trip_id,)
            ).fetchone()[0]

    itinerary_scenario = scenario["id"] if scenario else None
    if route_days:
        numbered_days = [dict(day, day_number=i) for i, day in enumerate(route_days, 1)]
        upcoming = [day for day in numbered_days if day["day_date"] >= date.today().isoformat()]
        days = (upcoming or numbered_days)[:3]
        day_count = len(numbered_days)
        day_anchor_prefix = "day-"
    else:
        days = legacy_days[:3]
        day_count = len(legacy_days)
        day_anchor_prefix = "legacy-day-"

    return render_template(
        "trip.html",
        trip=trip,
        days=days,
        day_count=day_count,
        scenarios=scenarios,
        scenario=scenario,
        itinerary_scenario=itinerary_scenario,
        day_anchor_prefix=day_anchor_prefix,
        saved_ideas=saved_ideas,
        saved_ideas_count=saved_ideas_count
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
    for item in sorted(activity_rows, key=activity_sort_key):activities.setdefault(item["itinerary_id"],[]).append(item)
    return render_template("itinerary.html",trip=trip,days=days,scenarios=scenarios,
       scenario=scenario,route_days=route_days,activities=activities)


def activity_sort_key(activity):
    """Sort clock times first, descriptive timing next, and untimed items last."""
    timing = " ".join((activity["start_time"] or "").upper().split())
    stable = (activity["position"], activity["id"])
    if not timing:
        return (2, 0, *stable)
    for fmt in ("%H:%M", "%I:%M %p", "%I %p"):
        try:
            clock = datetime.strptime(timing, fmt)
            return (0, clock.hour * 60 + clock.minute, *stable)
        except ValueError:
            continue
    return (1, 0, *stable)


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
    if not city or not name or len(city) > 100 or len(name) > 160 or category not in ("hotel", "castle", "activity", "transport", "flight") or len(notes) > 1000 or len(link) > 500 or (link and not link.startswith(("https://", "http://"))):
        abort(400, description="Check the option fields and link.")
    try:
        price = float(price_raw) if price_raw else None
    except ValueError:
        abort(400, description="Price must be a number.")
    if price is not None and (not 0 <= price <= 10000000 or not __import__("math").isfinite(price)):
        abort(400, description="Price must be a valid nonnegative amount.")
    sid=request.form.get("scenario_id",type=int) if request.form.get("return_workspace")=="1" else None
    with get_db_connection() as connection:
        scenario_tag=None
        if sid is not None:
            plan=connection.execute("SELECT name FROM trip_scenarios WHERE id=? AND trip_id=?",(sid,trip_id)).fetchone()
            if not plan or category not in ("hotel","castle"):abort(400)
            scenario_tag=plan["name"]
        connection.execute(
            """INSERT INTO saved_options (trip_id, city, name, category, price, link, notes, start_date, end_date, scenario_tag)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trip_id, city, name, category, price, link, notes, start_date or None, end_date or None,scenario_tag)
        )
    if sid is not None:
        slug=city.lower().replace(" ","-")
        return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+"#hotel-"+slug)
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
        item=connection.execute("SELECT * FROM saved_options WHERE id=? AND trip_id=?",(option_id,trip_id)).fetchone()
        if item is None:abort(404)
        connection.execute("""INSERT OR IGNORE INTO excluded_seed_options
            (trip_id,city,name,category,scenario_tag) VALUES (?,?,?,?,?)""",
            (trip_id,item["city"],item["name"],item["category"],item["scenario_tag"] or ""))
        connection.execute("DELETE FROM saved_options WHERE id=? AND trip_id=?",(option_id,trip_id))
    if request.form.get("return_workspace")=="1":
        sid=request.form.get("scenario_id",type=int)
        with get_db_connection() as db:
            valid=db.execute("SELECT 1 FROM trip_scenarios WHERE trip_id=? AND id=?",(trip_id,sid)).fetchone()
        if valid:return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+("#flights" if item["category"]=="flight" else "#excursions" if item["category"]=="activity" else "#stays"))
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
    if not city or not name or len(city)>100 or len(name)>160 or category not in ("hotel","castle","activity","transport","flight") or len(link)>500 or len(notes)>1000 or (link and not link.startswith(("https://","http://"))):
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


@app.route("/trip/<int:trip_id>/options/<int:option_id>/quote",methods=["POST"])
def update_saved_option_quote(trip_id,option_id):
    get_trip(trip_id)
    raw=request.form.get("price","").strip()
    try:
        amount=float(raw) if raw else None
    except ValueError:
        abort(400,"Enter a valid group quote in USD")
    if amount is not None and (not __import__("math").isfinite(amount) or not 0<=amount<=10000000):
        abort(400,"Enter a nonnegative group quote in USD")
    with get_db_connection() as db:
        item=db.execute("SELECT id,category,city FROM saved_options WHERE id=? AND trip_id=?",(option_id,trip_id)).fetchone()
        if item is None:abort(404)
        if item["category"] not in ("hotel","castle"):abort(400,"This quote form is for lodging only")
        sid=request.form.get("scenario_id",type=int)
        if sid is not None and not db.execute("SELECT 1 FROM trip_scenarios WHERE id=? AND trip_id=?",(sid,trip_id)).fetchone():
            abort(404)
        db.execute("UPDATE saved_options SET price=? WHERE id=? AND trip_id=?",(amount,option_id,trip_id))
    if sid is not None:
        slug="".join(c.lower() if c.isalnum() or c=="-" else "-" for c in item["city"]).strip("-")
        return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+"#hotel-"+slug)
    return redirect(url_for("saved_options",trip_id=trip_id))


@app.route("/trip/<int:trip_id>/options/<int:option_id>/link",methods=["POST"])
def update_saved_option_link(trip_id,option_id):
    get_trip(trip_id)
    link=request.form.get("link","").strip()
    if len(link)>2048:
        abort(400,"Booking link must be 2048 characters or fewer")
    if link and not link.lower().startswith(("https://","http://")):
        abort(400,"Booking link must begin with https:// or http://")
    with get_db_connection() as db:
        item=db.execute("SELECT city,category FROM saved_options WHERE id=? AND trip_id=?",(option_id,trip_id)).fetchone()
        if item is None: abort(404)
        if item["category"] not in ("hotel","castle"):abort(400)
        sid=request.form.get("scenario_id",type=int)
        if sid is not None and not db.execute("SELECT 1 FROM trip_scenarios WHERE trip_id=? AND id=?",(trip_id,sid)).fetchone():
            abort(404)
        db.execute("UPDATE saved_options SET link=? WHERE id=? AND trip_id=?",(link or None,option_id,trip_id))
    if sid is not None:
        slug="".join(c.lower() if c.isalnum() or c=="-" else "-" for c in item["city"]).strip("-")
        return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+"#hotel-"+slug)
    return redirect(url_for("saved_options",trip_id=trip_id))


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



def reconcile_12_otg_forward(db, trip_id, scenario_id):
    """One-time correction from the shifted Sep 15–28 schedule to Sep 14–27.

    Dates already entered correctly are left alone; other routes are untouched.
    """
    db.execute("""CREATE TABLE IF NOT EXISTS route_date_corrections (
        scenario_id INTEGER PRIMARY KEY, correction TEXT NOT NULL
    )""")
    if db.execute("SELECT 1 FROM route_date_corrections WHERE scenario_id=?",(scenario_id,)).fetchone():
        return
    # Only shift the itinerary if it actually follows the erroneous Sep 16–28 pattern.
    days=db.execute("""SELECT id,day_date FROM scenario_itinerary
        WHERE trip_id=? AND scenario_id=? ORDER BY day_date""",(trip_id,scenario_id)).fetchall()
    dates={row["day_date"] for row in days}
    if "2027-09-16" in dates and "2027-09-28" in dates and "2027-09-15" not in dates:
        # Update in-place from earliest to latest to avoid date uniqueness conflicts.
        from datetime import timedelta
        for row in days:
            shifted=(date.fromisoformat(row["day_date"])-timedelta(days=1)).isoformat()
            db.execute("UPDATE scenario_itinerary SET day_date=? WHERE id=?",(shifted,row["id"]))
    # Correct only matching legacy stay dates, scoped to this route.
    lodging={
        "Dublin":("2027-09-16","2027-09-18","2027-09-15","2027-09-17"),
        "Galway":("2027-09-18","2027-09-20","2027-09-17","2027-09-19"),
        "Edinburgh":("2027-09-20","2027-09-22","2027-09-19","2027-09-21"),
        "Inverness":("2027-09-23","2027-09-25","2027-09-22","2027-09-24"),
        "London":("2027-09-25","2027-09-28","2027-09-24","2027-09-27"),
    }
    for city,(old_start,old_end,new_start,new_end) in lodging.items():
        db.execute("""UPDATE saved_options SET start_date=?,end_date=?
            WHERE trip_id=? AND city=? AND category='hotel'
              AND scenario_tag='12 OTG' AND start_date=? AND end_date=?""",
            (new_start,new_end,trip_id,city,old_start,old_end))
    db.execute("""UPDATE saved_options SET start_date='2027-09-21',end_date='2027-09-22'
        WHERE trip_id=? AND city='Edinburgh' AND category='castle'
          AND scenario_tag='12 OTG'
          AND start_date='2027-09-22' AND end_date='2027-09-23'""",(trip_id,))
    for old,new in (("2027-09-15","2027-09-14"),("2027-09-20","2027-09-19"),
                    ("2027-09-25","2027-09-24"),("2027-09-28","2027-09-27")):
        db.execute("""UPDATE flight_option_dates SET departure_date=?
            WHERE scenario_id=? AND departure_date=?""",(new,scenario_id,old))
    db.execute("INSERT INTO route_date_corrections(scenario_id,correction) VALUES(?,?)",
               (scenario_id,"12 OTG Forward Sep 14–27"))


def reconcile_12_otg_backwards(db,trip_id,scenario_id):
    """One-time date correction for the 12-night reverse itinerary."""
    db.execute("""CREATE TABLE IF NOT EXISTS route_date_corrections (
        scenario_id INTEGER PRIMARY KEY, correction TEXT NOT NULL
    )""")
    if db.execute("SELECT 1 FROM route_date_corrections WHERE scenario_id=?",(scenario_id,)).fetchone():
        return
    days=db.execute("""SELECT id,day_date FROM scenario_itinerary
        WHERE trip_id=? AND scenario_id=? ORDER BY day_date""",(trip_id,scenario_id)).fetchall()
    dates={row["day_date"] for row in days}
    if "2027-09-16" in dates and "2027-09-28" in dates and "2027-09-15" not in dates:
        from datetime import timedelta
        for row in days:
            shifted=(date.fromisoformat(row["day_date"])-timedelta(days=1)).isoformat()
            db.execute("UPDATE scenario_itinerary SET day_date=? WHERE id=?",(shifted,row["id"]))
    lodging={
        "London":("2027-09-16","2027-09-19","2027-09-15","2027-09-18"),
        "Inverness":("2027-09-19","2027-09-21","2027-09-18","2027-09-20"),
        "Edinburgh":("2027-09-21","2027-09-23","2027-09-20","2027-09-22"),
        "Galway":("2027-09-24","2027-09-26","2027-09-23","2027-09-25"),
        "Dublin":("2027-09-26","2027-09-28","2027-09-25","2027-09-27"),
    }
    for city,(a,b,c,d) in lodging.items():
        db.execute("""UPDATE saved_options SET start_date=?,end_date=?
           WHERE trip_id=? AND city=? AND category='hotel'
           AND scenario_tag='12 OTG Backwards' AND start_date=? AND end_date=?""",
           (c,d,trip_id,city,a,b))
    db.execute("""UPDATE saved_options SET start_date='2027-09-22',end_date='2027-09-23'
        WHERE trip_id=? AND city='Edinburgh' AND category='castle'
        AND scenario_tag='12 OTG Backwards'
        AND start_date='2027-09-23' AND end_date='2027-09-24'""",(trip_id,))
    for old,new in (("2027-09-15","2027-09-14"),("2027-09-19","2027-09-18"),
                    ("2027-09-24","2027-09-23"),("2027-09-28","2027-09-27")):
        db.execute("UPDATE flight_option_dates SET departure_date=? WHERE scenario_id=? AND departure_date=?",
                   (new,scenario_id,old))
    db.execute("INSERT INTO route_date_corrections(scenario_id,correction) VALUES(?,?)",
               (scenario_id,"12 OTG Backwards Sep 14–27"))


def confirmed_four_route_date(flight, route_name):
    """September 2027 flight legs for the four approved Europe itineraries."""
    schedules={
        "12 OTG":{("stl","dub"):"2027-09-14",("snn","edi"):"2027-09-19",
                  ("inv","lon"):"2027-09-24",("lon","stl"):"2027-09-27"},
        "14 OTG":{("stl","dub"):"2027-09-13",("snn","edi"):"2027-09-20",
                  ("inv","lon"):"2027-09-25",("lon","stl"):"2027-09-28"},
        "12 OTG Backwards":{("stl","lon"):"2027-09-14",("lon","inv"):"2027-09-18",
                             ("edi","snn"):"2027-09-23",("dub","stl"):"2027-09-27"},
        "14 OTG Backwards":{("stl","lon"):"2027-09-13",("lon","inv"):"2027-09-17",
                             ("edi","snn"):"2027-09-22",("dub","stl"):"2027-09-28"},
    }
    if route_name not in schedules:return ""
    names={"STL":"stl","St Louis":"stl","St. Louis":"stl",
           "DUB":"dub","Dublin":"dub","SNN":"snn","Shannon":"snn",
           "EDI":"edi","Edinburgh":"edi","INV":"inv","Inverness":"inv",
           "LON":"lon","London":"lon","LHR":"lon","LGW":"lon",
           "LCY":"lon","LTN":"lon","STN":"lon"}
    def canonical(value):
        v=(value or "").lower().strip()
        for label,code in sorted(names.items(),key=lambda entry:-len(entry[0])):
            if v==label.lower():return code
        return ""
    origin=canonical(flight["origin"])
    dest=canonical(flight["destination"])
    if not origin or not dest:
        label=(flight["city"] or "").replace("→"," to ").replace("–"," to ")
        segments=label.lower().split(" to ")
        if len(segments)==2:
            origin=origin or canonical(segments[0])
            dest=dest or canonical(segments[1])
    return schedules[route_name].get((origin,dest),"")


def flight_date_from_itinerary(flight, days):
    """Only infer a flight date from an identifiable travel day, never a generic stay."""
    aliases={"STL":("st. louis","st louis"),"DUB":("dublin",),
             "EDI":("edinburgh",),"INV":("inverness",),
             "LHR":("london",),"LGW":("london",),"STN":("london",),
             "LCY":("london",),"LTN":("london",),"SNN":("shannon",),
             "BFS":("belfast",),"BHD":("belfast",),"GLA":("glasgow",)}
    dest=(flight["destination"] or "").strip().upper()
    targets=aliases.get(dest,(dest.lower(),)) if dest else ()
    if not targets:
        route=(flight["city"] or "").lower()
        targets=tuple(x for x in ("dublin","edinburgh","inverness","london","st. louis","shannon","glasgow","belfast")
                      if x in route.split(" to ")[-1] or x in route.split(" → ")[-1])
    matches=[]
    for day in days:
        title=(day["title"] or "").lower()
        city=(day["city"] or "").lower()
        if not any(word in title for word in ("flight","fly","return"," to ","depart")):
            continue
        if any(target and (target in title or (target in city and "flight" in title))
               for target in targets):
            matches.append(day["day_date"])
        elif dest=="STL" and any(x in title for x in ("flight home","return home")):
            matches.append(day["day_date"])
    return matches[0] if len(set(matches))==1 else ""


@app.route("/trip/<int:trip_id>/workspace/legacy")
def trip_workspace(trip_id):
    trip=get_trip(trip_id)
    with get_db_connection() as db:
        if trip["name"] == "Europe 2027" and db.execute("SELECT 1 FROM trip_scenarios WHERE trip_id=? AND name='S1'", (trip_id,)).fetchone():
            from europe_seed import add_missing_europe_candidates
            add_missing_europe_candidates(db,trip_id)
            from europe_seed import split_edinburgh_stays
            split_edinburgh_stays(db,trip_id)
            from europe_seed import add_europe_route_days
            add_europe_route_days(db,trip_id)
            from europe_seed import fill_europe_day_details
            fill_europe_day_details(db,trip_id)
        scenarios=db.execute("SELECT * FROM trip_scenarios WHERE trip_id=? ORDER BY id",(trip_id,)).fetchall()
        if not scenarios:
            db.execute("INSERT INTO trip_scenarios (trip_id,name) VALUES (?,?)",(trip_id,"Plan A"))
            scenarios=db.execute("SELECT * FROM trip_scenarios WHERE trip_id=?",(trip_id,)).fetchall()
        for route in scenarios:
            if route["name"]=="12 OTG":
                reconcile_12_otg_forward(db,trip_id,route["id"])
            elif route["name"]=="12 OTG Backwards":
                reconcile_12_otg_backwards(db,trip_id,route["id"])
        if trip["name"] == "Europe 2027":
            from backward_lodging import add_backward_lodging
            add_backward_lodging(db, trip_id)
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
        if trip["name"] == "Europe 2027" and db.execute("SELECT 1 FROM trip_scenarios WHERE trip_id=? AND name='S1'", (trip_id,)).fetchone():
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
    # Dates belong to a route version, not a shared flight record.
    with get_db_connection() as db:
        days=db.execute("SELECT day_date,city,title FROM scenario_itinerary WHERE trip_id=? AND scenario_id=? ORDER BY day_date",(trip_id,scenario["id"])).fetchall()
        for opt in options:
            if opt["category"]!="flight" or (opt["scenario_tag"] not in (None,scenario["name"])):
                continue
            existing=db.execute("SELECT departure_date FROM flight_option_dates WHERE option_id=? AND scenario_id=?",(opt["id"],scenario["id"])).fetchone()
            if existing is None:
                inferred=confirmed_four_route_date(opt,scenario["name"]) or (flight_date_from_itinerary(opt,days) if scenario["name"] not in ("12 OTG","14 OTG","12 OTG Backwards","14 OTG Backwards") else "")
                if inferred:
                    db.execute("INSERT OR IGNORE INTO flight_option_dates(option_id,scenario_id,departure_date) VALUES(?,?,?)",(opt["id"],scenario["id"],inferred))
        flight_dates={row["option_id"]:row["departure_date"] for row in db.execute(
            """SELECT fd.option_id,fd.departure_date FROM flight_option_dates fd
               JOIN saved_options o ON o.id=fd.option_id
               WHERE o.trip_id=? AND fd.scenario_id=?""",(trip_id,scenario["id"])).fetchall()}
    selected=workspace_selected(options,choices)
    groups={}
    for opt in options:
        if opt["scenario_tag"] is None or opt["scenario_tag"] == scenario["name"]:
            groups.setdefault(workspace_option_key(opt),[]).append(opt)
    picked=[next((o for o in choiceset if o["id"]==selected.get(key)),None) for key,choiceset in groups.items()]
    picked=[p for p in picked if p is not None]
    subtotal=sum(o["price"] or 0 for o in picked)
    missing=[o["name"] for o in picked if o["price"] is None]
    stays=sorted([o for o in picked if o["category"] in ("hotel","castle") and o["start_date"] and o["end_date"]],key=lambda o:o["start_date"])
    warnings=[]
    for a,b in zip(stays,stays[1:]):
        if a["end_date"]>b["start_date"]:
            warnings.append("Overlapping stays: "+a["name"]+" and "+b["name"])
        elif a["end_date"]<b["start_date"]:
            warnings.append("Gap between "+a["name"]+" and "+b["name"])
    undated=[o["name"] for o in picked if o["category"] in ("hotel","castle") and not o["start_date"]]
    # Follow the route's chronological stays, rather than alphabetical city names.
    route_order={}
    for key,items in groups.items():
        if key[1]=="hotel":
            dates=[item["start_date"] for item in items if item["start_date"]]
            if dates: route_order[key[0]]=min(dates)
    def city_sort(key):
        return (route_order.get(key[0],"9999-12-31"),key[0].casefold(),key[1])
    groups=dict(sorted(groups.items(),key=lambda entry:city_sort(entry[0])))
    # A destination does not disappear just because its last hotel was removed.
    # Include itinerary cities for this route, even with zero hotel candidates.
    
    with get_db_connection() as db:
        db_cities=[row["city"] for row in db.execute(
            """SELECT city FROM scenario_itinerary
               WHERE trip_id=? AND scenario_id=? AND TRIM(city) <> ''
               GROUP BY city ORDER BY MIN(day_date),city COLLATE NOCASE""",
            (trip_id,scenario["id"])).fetchall()]
    hotels={k:v for k,v in groups.items() if k[1]=="hotel"}
    for city in db_cities:
        if city not in ("Transit","Departure"):
            hotels.setdefault((city,"hotel"),[])
    castles={k:v for k,v in groups.items() if k[1]=="castle"}
    flights={k:v for k,v in groups.items() if k[1]=="flight"}
    flight_group_dates={
        key:min((flight_dates[o["id"]] for o in items if flight_dates.get(o["id"])),default="")
        for key,items in flights.items()}
    flights=dict(sorted(flights.items(),key=lambda entry:(
        min((flight_dates.get(o["id"],"9999-12-31") for o in entry[1]),default="9999-12-31"),
        entry[0][0].casefold())))
    excursions={k:v for k,v in groups.items() if k[1]=="activity"}
    transport={k:v for k,v in groups.items() if k[1]=="transport"}
    with get_db_connection() as db:
        overrides={r["option_id"]:r["activity_date"] for r in db.execute(
            "SELECT option_id,activity_date FROM activity_option_dates WHERE scenario_id=?",(scenario["id"],))}
    activity_dates={o["id"]:overrides.get(o["id"],o["start_date"] or "")
                    for o in options if o["category"]=="activity"}
    selected_flights=[p for p in picked if p["category"]=="flight"]
    extra_expenses=sum(row["amount"] for row in expenses if not row["included_in_allowance"])
    total=subtotal+scenario["food_budget"]+extra_expenses
    # Presentation-only attention notices: never change selections or trip data.
    attention=[]
    def option_target(option):
        if option["category"] in ("hotel","castle"):
            return "hotel-"+option["city"].lower().replace(" ","-")
        return "option-"+str(option["id"])
    for a,b in zip(stays,stays[1:]):
        if a["end_date"] != b["start_date"]:
            overlap=a["end_date"] > b["start_date"]
            attention.append({"title":b["city"]+" · "+("Overlapping stays" if overlap else "Gap between stays"),
                "detail":a["name"]+" ends "+a["end_date"]+"; "+b["name"]+" starts "+b["start_date"]+".",
                "target":option_target(b)})
    for option in picked:
        if option["price"] is None:
            attention.append({"title":option["city"]+" · Quote needed",
                "detail":option["name"]+" has no price. The working total is incomplete.","target":option_target(option)})
        if option["category"] in ("hotel","castle") and (not option["start_date"] or not option["end_date"]):
            attention.append({"title":option["city"]+" · Stay dates needed",
                "detail":"Add check-in and check-out dates for "+option["name"]+".","target":option_target(option)})
    stop_summaries={}
    for key,items in hotels.items():
        city_days=[day for day in days if day["city"]==key[0]]
        stop_summaries[key[0]]={"days":city_days,
            "start":city_days[0]["day_date"] if city_days else "",
            "end":city_days[-1]["day_date"] if city_days else ""}
    return render_template("workspace.html",trip=trip,scenarios=scenarios,scenario=scenario,attention=attention,stop_summaries=stop_summaries,groups=groups,hotels=hotels,castles=castles,flights=flights,excursions=excursions,transport=transport,activity_dates=activity_dates,selected_flights=selected_flights,flight_dates=flight_dates,flight_group_dates=flight_group_dates,selected=selected,stays=stays,warnings=warnings,undated=undated,missing=missing,subtotal=subtotal,total=total,remaining=scenario["budget_limit"]-total,expenses=expenses,extra_expenses=extra_expenses)


@app.route("/trip/<int:trip_id>/city/<city>")
def city_view(trip_id,city):
    trip=get_trip(trip_id)
    with get_db_connection() as db:
        plans=db.execute("SELECT * FROM trip_scenarios WHERE trip_id=? ORDER BY id",(trip_id,)).fetchall()
        sid=request.args.get("scenario",type=int) or (plans[0]["id"] if plans else None)
        plan=next((p for p in plans if p["id"]==sid),None)
        if plan is None:abort(404)
        # Destinations are places to stay, not placeholder labels such as Transit or Departure.
        names=[row["city"] for row in db.execute("""SELECT city FROM saved_options
            WHERE trip_id=? AND category='hotel' AND city NOT IN ('Transit','Departure')
              AND TRIM(city) <> '' AND (scenario_tag IS NULL OR scenario_tag=?)
            GROUP BY city ORDER BY MIN(COALESCE(start_date,'9999-12-31')),city COLLATE NOCASE""",
            (trip_id,plan["name"])).fetchall()]
        itinerary_names=[row["city"] for row in db.execute(
            """SELECT DISTINCT city FROM scenario_itinerary
               WHERE trip_id=? AND scenario_id=? AND TRIM(city) <> ''""",
            (trip_id,sid)).fetchall() if row["city"] not in ("Transit","Departure")]
        names=list(dict.fromkeys(names+itinerary_names))
        if city not in names:abort(404)
        days=db.execute("""SELECT * FROM scenario_itinerary WHERE trip_id=? AND scenario_id=? AND city=?
            ORDER BY day_date""",(trip_id,sid,city)).fetchall()
        day_ids=[d["id"] for d in days]
        activities={}
        for d in days:
            activities[d["id"]]=sorted(db.execute("SELECT * FROM day_activities WHERE itinerary_id=? ORDER BY position,id",(d["id"],)).fetchall(), key=activity_sort_key)
        hotels=db.execute("""SELECT * FROM saved_options WHERE trip_id=? AND city=? AND category='hotel'
            AND (scenario_tag IS NULL OR scenario_tag=?) ORDER BY price IS NULL,price,name""",
            (trip_id,city,plan["name"])).fetchall()
        selected=db.execute("""SELECT o.* FROM scenario_choices sc JOIN saved_options o ON o.id=sc.option_id
            WHERE sc.scenario_id=? AND sc.city=? AND sc.category='hotel' AND o.trip_id=?""",
            (sid,city,trip_id)).fetchone()
        selected_castle=db.execute("""SELECT o.* FROM scenario_choices sc JOIN saved_options o ON o.id=sc.option_id
            WHERE sc.scenario_id=? AND sc.city=? AND sc.category='castle' AND o.trip_id=?""",
            (sid,city,trip_id)).fetchone()
        ideas=db.execute("""SELECT * FROM saved_options WHERE trip_id=? AND city=? AND category='activity'
            AND (scenario_tag IS NULL OR scenario_tag=?) ORDER BY start_date,name""",
            (trip_id,city,plan["name"])).fetchall()
    return render_template("city.html",trip=trip,city=city,plans=plans,plan=plan,
        days=days,activities=activities,hotels=hotels,selected=selected,selected_castle=selected_castle,ideas=ideas,names=names)


@app.route("/trip/<int:trip_id>/budget-playground")
def budget_playground(trip_id):
    """Temporary what-if comparisons: never modify booked/selected choices."""
    trip=get_trip(trip_id)
    with get_db_connection() as db:
        plans=db.execute("SELECT * FROM trip_scenarios WHERE trip_id=? ORDER BY id",(trip_id,)).fetchall()
        sid=request.args.get("scenario",type=int) or (plans[0]["id"] if plans else None)
        plan=next((p for p in plans if p["id"]==sid),None)
        if not plan:abort(404)
        options=db.execute("""SELECT * FROM saved_options WHERE trip_id=?
            AND (scenario_tag IS NULL OR scenario_tag=?)
            ORDER BY city COLLATE NOCASE,category,price IS NULL,price,name""",
            (trip_id,plan["name"])).fetchall()
        rows=db.execute("""SELECT city,category,option_id FROM scenario_choices WHERE scenario_id=?""",(sid,)).fetchall()
        expenses=db.execute("SELECT * FROM scenario_expenses WHERE scenario_id=?",(sid,)).fetchall()
    selected=workspace_selected(options,rows)
    groups={}
    for item in options:
        # Superseded Edinburgh hotel+castle bundles remain archived in the DB,
        # but never present them as a competing single city stay.
        if (item["city"]=="Edinburgh" and item["category"]=="hotel"
                and " + " in item["name"] and "Castle" in item["name"]):
            continue
        groups.setdefault(workspace_option_key(item),[]).append(item)
    # Expenses outside allowances are already included in the active plan's estimate.
    extras=sum(e["amount"] for e in expenses if not e["included_in_allowance"])
    total=plan["food_budget"]+extras+sum(
        next((o["price"] or 0 for o in opts if o["id"]==selected.get(key)),0)
        for key,opts in groups.items())
    return render_template("playground.html",trip=trip,plans=plans,plan=plan,
        groups=groups,selected=selected,baseline=total,extras=extras)


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
    sid=request.form.get("scenario_id",type=int)
    flight_date=request.form.get("flight_date","").strip()
    if flight_date:
        try:date.fromisoformat(flight_date)
        except ValueError:abort(400,"Invalid departure date")
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
        oid=db.execute("SELECT last_insert_rowid()").fetchone()[0]
        if flight_date:
            if scenario_tag:
                plan=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND name=?",(trip_id,scenario_tag)).fetchone()
            else:
                plan=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND id=?",(trip_id,sid)).fetchone()
            if not plan:abort(400)
            db.execute("INSERT INTO flight_option_dates(option_id,scenario_id,departure_date) VALUES(?,?,?)",
                       (oid,plan["id"],flight_date))
    return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+"#flights")


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
    group=request.form.get("activity_group","").strip()
    link=request.form.get("link","").strip()
    notes=request.form.get("notes","").strip()
    if len(group)>160 or len(notes)>1000 or len(link)>500 or (link and not link.startswith(("https://","http://"))):abort(400)
    sid=request.form.get("scenario_id",type=int)
    with get_db_connection() as db:
        plan=db.execute("SELECT * FROM trip_scenarios WHERE trip_id=? AND id=?",(trip_id,sid)).fetchone()
        if sid is not None and not plan:abort(404)
        db.execute("""INSERT INTO saved_options(trip_id,city,name,category,price,start_date,notes,activity_group,link,scenario_tag)
            VALUES (?,?,?,'activity',?,?,?,?,?,?)""",
            (trip_id,city,name,price,day or None,notes,group or name,link,plan["name"] if plan else None))
    return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+"#excursions")


@app.route("/trip/<int:trip_id>/excursions/<int:option_id>/edit",methods=["POST"])
def edit_excursion_option(trip_id,option_id):
    get_trip(trip_id)
    sid=request.form.get("scenario_id",type=int)
    name=request.form.get("name","").strip()
    link=request.form.get("link","").strip()
    notes=request.form.get("notes","").strip()
    day=request.form.get("start_date","").strip()
    if not name or len(name)>160 or len(notes)>1000 or len(link)>500 or (link and not link.startswith(("https://","http://"))):abort(400)
    if day:
        try:date.fromisoformat(day)
        except ValueError:abort(400)
    raw=request.form.get("price","").strip()
    try:price=float(raw) if raw else None
    except ValueError:abort(400)
    if price is not None and (not __import__("math").isfinite(price) or price<0 or price>10000000):abort(400)
    with get_db_connection() as db:
        plan=db.execute("SELECT * FROM trip_scenarios WHERE id=? AND trip_id=?",(sid,trip_id)).fetchone()
        opt=db.execute("SELECT * FROM saved_options WHERE id=? AND trip_id=? AND category='activity'",(option_id,trip_id)).fetchone()
        if not plan or not opt:abort(404)
        if opt["scenario_tag"] not in (None,plan["name"]):abort(400)
        db.execute("""UPDATE saved_options SET name=?,price=?,link=?,notes=?,activity_group=? WHERE id=?""",
                   (name,price,link,notes,opt["activity_group"] or opt["name"],option_id))
        db.execute("""INSERT INTO activity_option_dates(option_id,scenario_id,activity_date) VALUES (?,?,?)
            ON CONFLICT(option_id,scenario_id) DO UPDATE SET activity_date=excluded.activity_date""",(option_id,sid,day))
    return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+"#excursions")


@app.route("/trip/<int:trip_id>/workspace/expense",methods=["POST"])
def add_scenario_expense(trip_id):
    get_trip(trip_id)
    sid=request.form.get("scenario_id",type=int)
    category=request.form.get("category","").strip()
    name=request.form.get("name","").strip()
    included_raw=request.form.get("included_in_allowance","1")
    if included_raw not in ("0","1"):abort(400,"Choose whether this expense is included in the allowance")
    included=int(included_raw)
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
    date_value=request.form.get("flight_date","").strip()
    if date_value:
        try:date.fromisoformat(date_value)
        except ValueError:abort(400,"Invalid departure date")
    raw=request.form.get("price","").strip()
    try:price=float(raw) if raw else None
    except ValueError:abort(400)
    if price is not None and (not __import__("math").isfinite(price) or price<0 or price>10000000):abort(400)
    with get_db_connection() as db:
        row=db.execute("SELECT * FROM saved_options WHERE id=? AND trip_id=? AND category='flight'",(option_id,trip_id)).fetchone()
        if not row:abort(404)
        sid=request.form.get("scenario_id",type=int)
        valid=db.execute("SELECT name FROM trip_scenarios WHERE id=? AND trip_id=?",(sid,trip_id)).fetchone()
        if not valid:abort(404)
        if row["scenario_tag"] not in (None,valid["name"]):abort(400)
        db.execute("""INSERT INTO flight_option_dates(option_id,scenario_id,departure_date)
            VALUES (?,?,?) ON CONFLICT(option_id,scenario_id) DO UPDATE SET departure_date=excluded.departure_date""",
            (option_id,sid,date_value))
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


@app.route("/trip/<int:trip_id>/workspace/scenarios/rename",methods=["POST"])
def rename_trip_scenario(trip_id):
    get_trip(trip_id)
    sid=request.form.get("scenario_id",type=int)
    name=request.form.get("name","").strip()
    if not name or len(name)>50:abort(400,"Enter a route name up to 50 characters.")
    with get_db_connection() as db:
        row=db.execute("SELECT name FROM trip_scenarios WHERE id=? AND trip_id=?",(sid,trip_id)).fetchone()
        if row is None:abort(404)
        if row["name"]!=name:
            taken=db.execute("SELECT 1 FROM trip_scenarios WHERE trip_id=? AND name=?",(trip_id,name)).fetchone()
            if taken:abort(400,"Route name already used.")
            db.execute("UPDATE trip_scenarios SET name=? WHERE id=? AND trip_id=?",(name,sid,trip_id))
            db.execute("UPDATE saved_options SET scenario_tag=? WHERE trip_id=? AND scenario_tag=?",(name,trip_id,row["name"]))
    return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid))


@app.route("/trip/<int:trip_id>/workspace/settings",methods=["POST"])
def workspace_settings(trip_id):
    get_trip(trip_id)
    sid=request.form.get("scenario_id",type=int)
    try:
        budget=float(request.form.get("budget_limit",""))
        other=float(request.form.get("other_costs","0"))
        food_raw=request.form.get("food_budget")
        food=float(food_raw) if food_raw is not None else None
    except ValueError: abort(400,"Costs must be numbers")
    if not all(__import__("math").isfinite(x) and 0<=x<=100000000 for x in [budget,other] + ([food] if food is not None else [])): abort(400)
    with get_db_connection() as db:
        row=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND id=?",(trip_id,sid)).fetchone()
        if not row: abort(404)
        if food is None:
            db.execute("UPDATE trip_scenarios SET budget_limit=?,other_costs=? WHERE id=?",(budget,other,sid))
        else:
            db.execute("UPDATE trip_scenarios SET budget_limit=?,other_costs=?,food_budget=? WHERE id=?",(budget,other,food,sid))
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
            if not opt or opt["category"]!=category or city not in (opt["city"],workspace_option_key(opt)[0]) or (opt["scenario_tag"] is not None and opt["scenario_tag"] != plan["name"]):abort(400,"Option belongs to another scenario")
            city=workspace_option_key(opt)[0]
            # Replace this experience's alternative, including legacy city-only choices.
            if category=="activity":
                prior=db.execute("""SELECT o.* FROM scenario_choices sc JOIN saved_options o ON o.id=sc.option_id
                    WHERE sc.scenario_id=? AND sc.category='activity'""",(sid,)).fetchall()
                for item in prior:
                    if workspace_option_key(item)[0]==city:
                        db.execute("DELETE FROM scenario_choices WHERE scenario_id=? AND option_id=?",(sid,item["id"]))
            db.execute("""INSERT INTO scenario_choices (scenario_id,city,category,option_id) VALUES (?,?,?,?)
                ON CONFLICT(scenario_id,city,category) DO UPDATE SET option_id=excluded.option_id""",(sid,city,category,oid))
        else:
            if category=="activity":
                prior=db.execute("""SELECT o.* FROM scenario_choices sc JOIN saved_options o ON o.id=sc.option_id
                    WHERE sc.scenario_id=? AND sc.category='activity'""",(sid,)).fetchall()
                for item in prior:
                    if workspace_option_key(item)[0]==city:
                        db.execute("DELETE FROM scenario_choices WHERE scenario_id=? AND option_id=?",(sid,item["id"]))
            else:
                db.execute("DELETE FROM scenario_choices WHERE scenario_id=? AND city=? AND category=?",(sid,city,category))
    if request.form.get("return_city")=="1" and category=="hotel":
        return redirect(url_for("city_view",trip_id=trip_id,city=city,scenario=sid))
    anchor="#flights" if category=="flight" else "#excursions" if category=="activity" else "#hotel-"+city.lower().replace(" ","-") if category in ("hotel","castle") else "#ground"
    return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+anchor)



@app.route("/trips/import-europe-2027",methods=["POST"])
def import_europe_trip():
    # Development fixture only; disabled for regular accounts and beta deployments.
    if not app.config.get("ENABLE_EUROPE_IMPORT", False):
        abort(404)
    from europe_seed import import_europe_2027
    with get_db_connection() as db:
        trip_id=import_europe_2027(db,session["user_id"])
    return redirect(url_for("trip_workspace",trip_id=trip_id))


init_db()

from planner import install as install_planner
install_planner(app,get_db_connection,get_trip,DATA_DIR)

if __name__ == "__main__":
    app.run(debug=True)

