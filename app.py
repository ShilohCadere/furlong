
import sqlite3
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


init_db()

if __name__ == "__main__":
    app.run(debug=True)
