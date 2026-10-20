
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
                FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
            )
        """)

        # Safe additive migration for existing local trip databases.
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(saved_options)")}
        for field in ("start_date", "end_date"):
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
    trip = get_trip(trip_id)

    with get_db_connection() as connection:
        days = connection.execute(
            """
            SELECT *
            FROM itinerary_days
            WHERE trip_id = ?
            ORDER BY day_number
            """,
            (trip_id,)
        ).fetchall()

    return render_template(
        "itinerary.html",
        trip=trip,
        days=days
    )


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
    if not city or not name or len(city) > 100 or len(name) > 160 or category not in ("hotel", "activity", "transport") or len(notes) > 1000 or len(link) > 500 or (link and not link.startswith(("https://", "http://"))):
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


init_db()

if __name__ == "__main__":
    app.run(debug=True)
