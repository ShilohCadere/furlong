# Furlong (travel planner)

Personal multi-city trip planner, built for one planning style: compare competing options (hotels, flights, excursions) under a budget, per route. First real use: "Europe 2027" for 4 travelers (Ireland, Scotland, more). Portfolio piece for a move from wet-lab biology into biotech data roles, so the owner must be able to explain every design choice in an interview.

## Stack and run
- Python / Flask, one file `app.py` (~1000 lines), raw `sqlite3`, no ORM, DB file `furlong.db` (git-ignored)
- Jinja templates in `templates/`; plain CSS/JS in `static/` (`style.css` is ~74 KB, plus `workspace-refinement.css` and `city-refinement.css`)
- Install: `pip install -r requirements-dev.txt` (Flask 3.1, beautifulsoup4)
- Run: `python app.py` (debug mode)
- Tests: `python -m unittest discover -s tests -v`
- Session secret: env `FURLONG_SECRET_KEY`, else auto-created `.furlong_session_secret` (git-ignored)

## Core model
- **Scenario** (`trip_scenarios`) = one route/plan for a trip, with `budget_limit` (default 20000) and `other_costs`. Default scenario is "Plan A". Europe 2027 uses "S1" and "L1".
- **Saved option** (`saved_options`) = a candidate hotel, castle, flight, activity, or transport item for a city, with price, dates, link, notes, flight fields. `scenario_tag` NULL means shared across scenarios; otherwise it belongs to one scenario only.
- **Choice** (`scenario_choices`) = the one option picked per (scenario, city, category).
- **Budget math** (`trip_workspace` in `app.py`): total = sum of chosen option prices + scenario `other_costs` + expenses not marked `included_in_allowance`. Remaining = `budget_limit` - total.
- **Warnings**: overlapping or gapped hotel/castle stays, undated stays, and chosen options with no price.
- Per scenario: `scenario_itinerary` (days by date and city) with `day_activities`, and `scenario_expenses`.
- Older tables still exist: `itinerary_days` (legacy numbered days), `excluded_seed_options` (remembers deleted seed candidates so they stay deleted).
- Accounts: `users` (hashed passwords). `trips.user_id` scopes every trip to its owner.

## Routes (all under `/trip/<id>/` unless noted)
- Auth: `/register`, `/login`, `/logout`
- `/` list and create trips, `edit`, `itinerary` (+ day, activity add/edit/delete, add-day)
- `options` (+ add, prefer, remove, quote, link, edit)
- `workspace` (+ scenarios, scenarios/rename, settings, choose, expense add/delete), `city/<city>`, `budget-playground` (read-only), `flights/add`, `flights/<id>/edit`, `excursions/add`
- `/trips/import-europe-2027` POST: dev fixture, 404 unless `app.config["ENABLE_EUROPE_IMPORT"]`
- `europe_seed.py` holds the Europe 2027 seed data and its reconcile helpers

## Conventions and gotchas (keep these)
- Open DBs via `get_db_connection()` (foreign keys on, Row access). SQL is parameterized.
- Ownership: `get_trip()` filters by `user_id`, and `require_login` (before_request) also enforces ownership for any route with `trip_id`. New trip routes get this for free; do not bypass it.
- Schema changes are additive: add `CREATE TABLE IF NOT EXISTS` or an `ALTER TABLE ... ADD COLUMN` guarded by a `PRAGMA table_info` check inside `init_db()`.
- `trip_workspace` GET performs writes (legacy fix-ups, Europe seed top-ups). Tests assert the playground GET preserves every row, so keep read-only pages read-only.
- Seed logic keys on the trip name "Europe 2027" and scenario names "S1"/"L1". Don't rename them casually.
- Form fields: older routes use kebab-case (`trip-name`), newer ones snake_case (`scenario_id`, `option_id`).
- `app.py` is written in a dense style (few spaces, one-line handlers). Match it locally rather than reformatting.
- `templates/auth.html` and `templates/city.html` are single-line files; edit them with unique-string replacements.
- Options may not cross scenarios: `choose_scenario_option` aborts 400 if an option's `scenario_tag` belongs to another scenario.

## Tests
- 34 tests, all passing as of this writing (about 5 s). `tests/test_saved_options.py` has 24 (accounts, options, scenarios, Europe seed idempotency, flights, itineraries, budget, isolation) and `tests/test_release_journeys.py` has 10 (overview, activity ordering, cross-account access, persistence)
- Output is noisy with `ResourceWarning: unclosed database`: `with sqlite3.connect()` commits but does not close. Harmless, but `get_db_connection()` callers could close connections explicitly.
- Each test uses a temp SQLite DB by swapping `furlong.DATABASE`, registers `testuser`, and drives the Flask test client
- Add a test with every behavior change

## Not built yet
- Per-traveler preferences and weighted multi-criteria scoring. Today the only quantitative lens is price against a scenario budget, plus manual choice.
- Travelers as entities; shared/collaborative editing across accounts

## How to work in this repo (saves tokens)
- Make small, targeted edits. Do not rewrite whole files.
- Don't read the CSS files unless the task is styling. Use Grep for routes (`^@app.route`) instead of reading `app.py` top to bottom.
- Don't ask the owner to verify things this file already states. Proceed and note assumptions afterward.
- Explain the reasoning behind each design choice in one or two lines so the owner can restate it in an interview.
- Commit messages: short, imperative.
