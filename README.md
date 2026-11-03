<p align="center">
  <img src="static/furlong-bear.svg" alt="Furlong polar bear" width="150">
</p>

# Furlong

**A travel planning workspace for comparing possibilities before committing to a journey.**

Furlong brings itinerary alternatives, saved research, accommodation and transport options, and trip costs into one place. It began with a real planning problem: organizing a multi-city trip for four adults while weighing different routes, trip lengths, budgets, and priorities.

The interesting part is what happens when plans change. A hotel can remain worth considering even when its quote needs refreshing. Two routes can share the same research without sharing dates or selections. A booking and its recorded payments should survive a switch to another itinerary.

Created by **Shiloh Cadere**, under **Cadere Productions**.

> **Status:** Actively developed portfolio project. The redesigned planner is on [`feature/saved-options-panel`](https://github.com/ShilohCadere/furlong/tree/feature/saved-options-panel); `main` contains an earlier implementation. The redesign features below refer to that development branch. Public release readiness and deployment configuration are separate from feature implementation.

## The planning problem

Travel research often ends up split between spreadsheets, browser tabs, notes, and booking confirmations. Comparing a shorter trip with a longer one then means duplicating information and trying to remember which dates, prices, and choices belong to which version.

Furlong models those distinctions explicitly:

- **Ideas** hold reusable research about a place, stay, or experience.
- **Options** add the dates, quotes, and details for a particular itinerary.
- **Decision groups** hold competing options for one choice, such as accommodation at a stop.
- **Scenarios** keep complete itinerary alternatives independent.
- **Bookings and payments** preserve commitments and actual spending separately from tentative selections.

For example, the same hotel idea can appear in two routes with different stay dates and quotes. Selecting it in one route does not select it in the other.

## What you can do

| Area | Implemented in the redesigned planner |
| --- | --- |
| Plan a journey | Create and edit stops, itinerary days, activities, and connections; copy and reorder stops. |
| Compare alternatives | Create and duplicate scenarios with independent dates, options, and selections. |
| Keep useful research | Save ideas, links, notes, and favorites; reuse an idea across alternatives. |
| Track changing costs | Record quotes and quote history, unit-based prices, currencies, allowances, and expenses; surface unknown or provisional costs. |
| Record commitments | Track bookings, payments, refunds, and optional traveler or household cost shares. |
| Find the next decision | Review planning notices and tasks that link back to the relevant details. |
| View the route | Explore journey and day views on a map; use a travel-focused view of the active plan. |
| Customize the workspace | Adjust item fields, time blocks, display preferences, and task settings. |
| Preserve work | Use browser-local storage and queued edits, resolve overlapping changes, and export trip data. |

The interface uses a navy foundation, jewel tones, and metallic accents. Consistent city colors help connect navigation, stops, and options across the workspace.

## Engineering choices

### Separate research from decisions

Shared ideas live in a user document; itinerary-specific options live in a trip document. This allows research to be reused while dates, quotes, and choices remain specific to each alternative.

### Preserve uncertainty in the budget

An unknown price remains unknown rather than becoming a misleading zero-cost item. Quotes retain their original context, while the budget distinguishes estimates, recorded payments, refunds, and allowance coverage. Currency conversion applies differently to unpaid estimates and recorded payment amounts.

### Handle edits without silently overwriting work

The browser queues operations and stores a local working copy in IndexedDB. The server checks field-level changes against their previous values: unrelated edits can merge, while overlapping changes return a conflict for review. Operation IDs prevent a retried request from applying the same operation twice.

This is synchronization within an account, not a claim of shared multi-user trip collaboration.

### Evolve persistence without discarding existing trips

The application combines its original relational SQLite tables with versioned JSON planning documents stored in SQLite. The redesigned workspace imports legacy planning data additively. Database backup and restore-check scripts support the persistence workflow.

### Keep calculations separate from interface code

Pure JavaScript planning functions live in `static/planner-core.js`, separate from rendering and interaction code. This makes quote calculations, date changes, and operation generation testable without a browser.

## Stack and structure

| Layer | Technology |
| --- | --- |
| Server | Python, Flask, Jinja |
| Persistence | SQLite through Python's `sqlite3`; relational tables and versioned JSON documents |
| Client | JavaScript, HTML, CSS, IndexedDB |
| Maps | Leaflet, loaded by the map view |
| Supporting libraries | Werkzeug for password hashing; Beautiful Soup for link previews |
| Deployment entry point | Gunicorn / WSGI |
| Verification | Python `unittest`, Node's built-in test runner, GitHub Actions workflow |

Key files on the development branch:

| Path | Responsibility |
| --- | --- |
| `app.py` | Authentication, trip ownership, schema initialization, and original planning routes |
| `planner.py` | Planning documents, legacy import, synchronization API, validation, exports, and attachments |
| `static/planner-core.js` | Cost calculations, date utilities, planning notices, and change operations |
| `static/planner.js` | Workspace views, editors, local persistence, and synchronization |
| `templates/` and `static/*.css` | Page shells and visual design |
| `tests/` | Server regression tests and JavaScript calculation tests |
| `scripts/` | Database backup, restore verification, and targeted data maintenance |

## Run locally

Use **Python 3.12** to match the development branch's Python workflow. Git and a Python virtual environment are sufficient for the application; Node.js is needed only for the JavaScript tests.

```bash
git clone --branch feature/saved-options-panel https://github.com/ShilohCadere/furlong.git
cd furlong
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Then install dependencies and start the local development server:

```bash
python -m pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**. The development branch provides local account registration. Database tables are initialized at startup; your local database is not included in the repository.

`python app.py` enables Flask debug mode and is intended for local development. For hosted configuration, persistent storage, and backup guidance, read [DEPLOYMENT.md](DEPLOYMENT.md). Keep the Europe trip import disabled for ordinary use; it is a development fixture.

## Verification

Run the Python regression suite from the repository root:

```bash
python -m unittest discover -s tests -v
```

On the development branch, run the JavaScript planning tests with a Node.js version that supports `node:test`:

```bash
node --test tests/planner-core.test.js
```

The repository includes tests for:

- Account ownership, cross-account access rejection, and CSRF handling.
- Independent scenarios, selections, and itinerary ordering.
- Additive imports and preservation of quotes and existing data.
- Field-level synchronization, atomic conflicts, and idempotent retries.
- Unknown prices, unit quotes, exchange rates, refunds, and duplicate booking totals.
- Date shifts, booked-date preservation, and elapsed flight time across time zones.

The development branch also has a manually triggered GitHub Actions workflow for Python regression tests and database backup/restore verification. These are descriptions of the checks in the repository, not a claim that every check passes on every revision.

## Current scope and next steps

Furlong is a working application under active iteration. Its current focus is making real planning data dependable through repeated changes.

- Harden itinerary date changes and legacy-data reconciliation.
- Continue refining budget editing, imported idea organization, and navigation.
- Validate offline behavior, synchronization, and recovery through complete browser journeys.
- Reconcile development and release branches before a broader public release.

Furlong stores planning information and manually recorded booking details. Reservations and purchases take place with the travel provider. Map connections illustrate the journey; they are not turn-by-turn directions. New link previews, attachment uploads, exchange-rate refreshes, and online map resources require connectivity.

## Portfolio perspective

This project demonstrates practical work across **data modeling, SQL, API validation, state synchronization, regression testing, and iterative product design**. Its central challenge is preserving the meaning and history of data as a user's decisions change.

The same discipline applies beyond travel: separate source information from derived choices, represent missing data honestly, keep changes scoped, and make important calculations reproducible.

## License

[MIT](LICENSE)
