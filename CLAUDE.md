# Furlong (travel planner)

Personal multi-city trip planner for 4 travelers (2027). Built for one person's planning style: weighing competing priorities and comparing options. Portfolio piece for a biotech data-role pivot, so the owner must be able to explain every design choice in an interview.

## Stack
- Python / Flask, single file `app.py` (~200 lines)
- SQLite (`furlong.db`, git-ignored), raw `sqlite3`, no ORM
- Jinja templates in `templates/` (`index.html`, `trip.html`, `itinerary.html`), plain CSS/JS in `static/`
- Run: `python app.py` (debug mode, http://127.0.0.1:5000)
- `hello.py` is a leftover scratch file

## Current schema
- `trips(id, name, destination)`
- `itinerary_days(id, trip_id, day_number, title, trip_date)`, UNIQUE(trip_id, day_number), cascades on trip delete

## Routes
- `/` GET list trips, POST create trip
- `/trip/<id>` overview (first 3 days + count)
- `/trip/<id>/edit` POST rename / change destination
- `/trip/<id>/itinerary` full day list
- `/trip/<id>/itinerary/add-day` POST append next day number

## Conventions already in the code (keep them)
- Open connections via `get_db_connection()`; it enables foreign keys and Row access
- Always parameterized SQL (`?`), never string-formatted
- Form field names are kebab-case (`trip-name`)
- Trip names are required and max 120 chars
- Next day number is computed under `BEGIN IMMEDIATE` to avoid races
- Look up a trip with `get_trip()`, which 404s if missing

## Not built yet (the owner's real goals)
- Multiple cities per trip
- Competing priorities (budget, travel time, per-traveler preferences) as explicit weights
- Side-by-side option comparison with ranked results
- Per-day activities, travelers

## How to work in this repo (saves tokens)
- Make small, targeted edits. Do not rewrite whole files or regenerate templates.
- Do not read `static/style.css` (17 KB) unless the task is about styling.
- Do not ask for verification of things this file already states; proceed and note assumptions afterward.
- Explain the reasoning behind each design choice in one or two lines, so the owner can restate it in an interview.
- Add tests for scoring and constraint logic when it is written (pytest).
- Commit messages: short, imperative.
