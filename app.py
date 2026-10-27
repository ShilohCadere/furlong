
import sqlite3
import os
import secrets
import hashlib
import smtplib
from email.message import EmailMessage
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    abort, session, g
)

app = Flask(__name__)

# Set FURLONG_DATA_DIR to a persistent, writable volume in production.
# Existing local installations retain their original database location.
DATA_DIR = Path(os.environ.get("FURLONG_DATA_DIR", str(Path(__file__).resolve().parent))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE = DATA_DIR / "furlong.db"
# Local development sessions remain valid when Flask restarts.
_secret_path = Path(__file__).resolve().parent / ".furlong_session_secret"
if os.environ.get("FURLONG_ENV") == "production" and (not os.environ.get("FURLONG_SECRET_KEY") or os.environ.get("FURLONG_HTTPS") != "1"):
    raise RuntimeError("Production requires FURLONG_SECRET_KEY and FURLONG_HTTPS=1")
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

# Conservative limits for a text-based travel planner.
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
app.config["MAX_FORM_MEMORY_SIZE"] = 256 * 1024
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)

@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Content-Security-Policy",
        "frame-ancestors 'none'; object-src 'none'; base-uri 'self'")
    if app.config["SESSION_COOKIE_SECURE"]:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response




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

        connection.execute("""CREATE TABLE IF NOT EXISTS auth_attempts (
            attempt_key TEXT PRIMARY KEY,
            attempts INTEGER NOT NULL,
            window_started INTEGER NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL
        )""")
        # Additive beta-account migration; preserve existing local users and trips.
        user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
        if "email" not in user_columns:
            connection.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if "email_verified" not in user_columns:
            connection.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users(email COLLATE NOCASE) WHERE email IS NOT NULL")
        connection.execute("""CREATE TABLE IF NOT EXISTS beta_invitations (
            token_hash TEXT PRIMARY KEY,
            email TEXT NOT NULL COLLATE NOCASE,
            expires_at INTEGER NOT NULL,
            used_at INTEGER
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS email_activations (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL,
            used_at INTEGER
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
        scenario_columns = {row["name"] for row in connection.execute("PRAGMA table_info(trip_scenarios)")}
        for field, definition in (("food_travelers", "INTEGER NOT NULL DEFAULT 4"), ("food_days", "INTEGER NOT NULL DEFAULT 14"), ("food_daily_rate", "REAL NOT NULL DEFAULT 0"), ("ground_transport_allowance", "REAL NOT NULL DEFAULT 0"), ("contingency_allowance", "REAL NOT NULL DEFAULT 0"), ("insurance_allowance", "REAL NOT NULL DEFAULT 0"), ("fees_allowance", "REAL NOT NULL DEFAULT 0")):
            if field not in scenario_columns:
                connection.execute(f"ALTER TABLE trip_scenarios ADD COLUMN {field} {definition}")
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(saved_options)")}
        for field in ("start_date", "end_date", "scenario_tag", "origin", "destination", "departure_time", "arrival_time", "layovers", "carrier"):
            if field not in columns:
                connection.execute(f"ALTER TABLE saved_options ADD COLUMN {field} TEXT")


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
    if request.endpoint in ("login","register","activate_email","resend_activation","static") or request.endpoint is None:
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


def send_beta_email(recipient, subject, body):
    """Send transactional email over authenticated STARTTLS; never log credentials or tokens."""
    required = ("FURLONG_SMTP_HOST", "FURLONG_SMTP_FROM", "FURLONG_SMTP_USERNAME", "FURLONG_SMTP_PASSWORD")
    if not all(os.environ.get(name) for name in required):
        raise RuntimeError("Beta email delivery is not configured")
    message = EmailMessage()
    message["From"] = os.environ["FURLONG_SMTP_FROM"]
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(os.environ["FURLONG_SMTP_HOST"],
                      int(os.environ.get("FURLONG_SMTP_PORT", "587")), timeout=10) as smtp:
        smtp.starttls()
        smtp.login(os.environ["FURLONG_SMTP_USERNAME"], os.environ["FURLONG_SMTP_PASSWORD"])
        smtp.send_message(message)


def valid_beta_invitation(token):
    """Return the invited email only for an unused, unexpired invitation."""
    if not token or len(token) > 256:
        return None
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = int(datetime.now(timezone.utc).timestamp())
    with get_db_connection() as db:
        invitation = db.execute(
            "SELECT email FROM beta_invitations WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
            (digest, now)
        ).fetchone()
    return invitation["email"] if invitation else None


@app.route("/resend-activation", methods=["POST"])
def resend_activation():
    """Resend only for an existing unverified account, with per-IP throttling."""
    email = request.form.get("email", "").strip().lower()
    generic = "If an unverified account exists, an activation email will be sent."
    if not email or len(email) > 254:
        return generic, 200
    ip_digest = hashlib.sha256((request.remote_addr or "unknown").encode()).hexdigest()
    ip_key = "resend-ip:" + ip_digest
    key = "resend:" + hashlib.sha256(((request.remote_addr or "unknown") + ":" + email).encode()).hexdigest()
    now = int(datetime.now(timezone.utc).timestamp())
    with get_db_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        ip_recent = db.execute("SELECT attempts,window_started FROM auth_attempts WHERE attempt_key=?", (ip_key,)).fetchone()
        if ip_recent and now - ip_recent["window_started"] < 3600 and ip_recent["attempts"] >= 15:
            return generic, 200
        db.execute("""INSERT INTO auth_attempts(attempt_key,attempts,window_started) VALUES (?,1,?)
            ON CONFLICT(attempt_key) DO UPDATE SET
            attempts=CASE WHEN ?-window_started>=3600 THEN 1 ELSE attempts+1 END,
            window_started=CASE WHEN ?-window_started>=3600 THEN ? ELSE window_started END""",
            (ip_key,now,now,now,now))
        recent = db.execute("SELECT attempts,window_started FROM auth_attempts WHERE attempt_key=?", (key,)).fetchone()
        if recent and now - recent["window_started"] < 3600 and recent["attempts"] >= 3:
            return generic, 200
        db.execute("""INSERT INTO auth_attempts(attempt_key,attempts,window_started) VALUES (?,1,?)
            ON CONFLICT(attempt_key) DO UPDATE SET
            attempts=CASE WHEN ?-window_started>=3600 THEN 1 ELSE attempts+1 END,
            window_started=CASE WHEN ?-window_started>=3600 THEN ? ELSE window_started END""",
            (key,now,now,now,now))
        user = db.execute("SELECT id FROM users WHERE email=? COLLATE NOCASE AND email_verified=0", (email,)).fetchone()
        if user is None:
            return generic, 200
        token = secrets.token_urlsafe(32)
        db.execute("DELETE FROM email_activations WHERE user_id=?", (user["id"],))
        db.execute("INSERT INTO email_activations(token_hash,user_id,expires_at) VALUES (?,?,?)",
                   (hashlib.sha256(token.encode()).hexdigest(),user["id"],now+86400))
    origin = os.environ.get("FURLONG_PUBLIC_URL", "").rstrip("/")
    if not origin.startswith("https://"):
        return generic, 200
    try:
        send_beta_email(email, "Activate your Furlong account",
                        "Activate within 24 hours: " + origin + url_for("activate_email",token=token))
    except (RuntimeError, OSError, smtplib.SMTPException):
        pass
    return generic, 200


@app.route("/activate/<token>", methods=["GET"])
def activate_email(token):
    """Consume a single-use, 24-hour email activation token atomically."""
    if len(token) > 256:
        abort(400)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = int(datetime.now(timezone.utc).timestamp())
    with get_db_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        activation = db.execute(
            "SELECT user_id FROM email_activations WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
            (digest, now)
        ).fetchone()
        if activation is None:
            abort(400, description="Invalid or expired activation link.")
        db.execute("UPDATE users SET email_verified=1 WHERE id=?", (activation["user_id"],))
        db.execute("UPDATE email_activations SET used_at=? WHERE token_hash=?", (now, digest))
    return redirect(url_for("login"))


@app.route("/register",methods=["GET","POST"])
def register():
    beta = os.environ.get("FURLONG_ENV") == "production"
    invitation_token = request.values.get("invitation", "").strip()
    invited_email = valid_beta_invitation(invitation_token) if beta else None
    if beta and not invited_email:
        abort(403, description="A valid private beta invitation is required.")
    if request.method == "GET":
        return render_template("auth.html", mode="register", error=None,
                               invitation=invitation_token if beta else None,
                               invite_email=invited_email)
    if beta:
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not 3 <= len(username) <= 40 or not username.replace("_", "").replace("-", "").isalnum() or len(password) < 10:
            return "Invalid username or password requirements.", 400
        public_url = os.environ.get("FURLONG_PUBLIC_URL", "").rstrip("/")
        if not public_url.startswith("https://"):
            abort(503, description="A secure public URL is required for activation.")
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(invitation_token.encode("utf-8")).hexdigest()
        now = int(datetime.now(timezone.utc).timestamp())
        with get_db_connection() as db:
            db.execute("BEGIN IMMEDIATE")
            invitation = db.execute(
                "SELECT email FROM beta_invitations WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
                (digest, now)
            ).fetchone()
            if invitation is None:
                abort(403)
            if db.execute("SELECT 1 FROM users WHERE username=? OR email=? COLLATE NOCASE",
                          (username, invitation["email"])).fetchone():
                return "Username or invited email already registered.", 409
            db.execute("INSERT INTO users(username,password_hash,email,email_verified) VALUES (?,?,?,0)",
                       (username, generate_password_hash(password), invitation["email"]))
            uid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute("INSERT INTO email_activations(token_hash,user_id,expires_at) VALUES (?,?,?)",
                       (hashlib.sha256(token.encode("utf-8")).hexdigest(), uid, now + 86400))
            db.execute("UPDATE beta_invitations SET used_at=? WHERE token_hash=?", (now, digest))
        activation_link = public_url + url_for("activate_email", token=token)
        try:
            send_beta_email(invitation["email"], "Activate your Furlong account",
                            "Activate your account within 24 hours: " + activation_link)
        except (RuntimeError, OSError, smtplib.SMTPException):
            # Keep the unverified account and token for a future controlled resend.
            return "Your account was created, but activation email delivery failed. Contact the beta administrator.", 503
        return "Check your email for your Furlong activation link.", 202
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
    session.permanent = True
    return redirect(url_for("home"))


# SQLite-backed throttling persists across workers and application restarts.
# Use separate limits for source IP and username to resist username rotation.
AUTH_WINDOW_SECONDS = 15 * 60
AUTH_MAX_USER_ATTEMPTS = 5
AUTH_MAX_IP_ATTEMPTS = 30

def _auth_keys(username):
    import hashlib
    ip = request.remote_addr or "unknown"
    digest = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
    return (("ip:" + digest(ip), AUTH_MAX_IP_ATTEMPTS),
            ("user:" + digest(username.casefold()), AUTH_MAX_USER_ATTEMPTS))

def _auth_blocked(username):
    now = int(datetime.now(timezone.utc).timestamp())
    with get_db_connection() as db:
        for key, limit in _auth_keys(username):
            row = db.execute("SELECT attempts,window_started FROM auth_attempts WHERE attempt_key=?", (key,)).fetchone()
            if row and now - row["window_started"] < AUTH_WINDOW_SECONDS and row["attempts"] >= limit:
                return True
    return False

def _auth_failed(username):
    now = int(datetime.now(timezone.utc).timestamp())
    with get_db_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        for key, _ in _auth_keys(username):
            db.execute("""INSERT INTO auth_attempts(attempt_key,attempts,window_started)
                VALUES(?,1,?) ON CONFLICT(attempt_key) DO UPDATE SET
                attempts=CASE WHEN ? - window_started >= ? THEN 1 ELSE attempts+1 END,
                window_started=CASE WHEN ? - window_started >= ? THEN ? ELSE window_started END""",
                (key, now, now, AUTH_WINDOW_SECONDS, now, AUTH_WINDOW_SECONDS, now))

def _auth_succeeded(username):
    # Keep IP failure count to deter distributed username guessing from one address.
    with get_db_connection() as db:
        db.execute("DELETE FROM auth_attempts WHERE attempt_key=?", (_auth_keys(username)[1][0],))


@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="GET":return render_template("auth.html",mode="login",error=None)
    username=request.form.get("username","").strip()
    if _auth_blocked(username):
        return render_template("auth.html",mode="login",error="Too many attempts. Try again in 15 minutes."),429
    with get_db_connection() as db:
        user=db.execute("SELECT * FROM users WHERE username=?",(username,)).fetchone()
    if not user or not check_password_hash(user["password_hash"],request.form.get("password","")):
        _auth_failed(username)
        return render_template("auth.html",mode="login",error="Incorrect username or password."),401
    if os.environ.get("FURLONG_ENV") == "production" and not user["email_verified"]:
        return render_template("auth.html",mode="login",
            error="Verify your email address before signing in."),403
    _auth_succeeded(username)
    session.clear()
    session.update(user_id=user["id"],username=user["username"])
    session.permanent = True
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


@app.route("/trip/<int:trip_id>")
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
        scenario=next((p for p in scenarios if p["id"]==sid),None) if sid is not None else (scenarios[0] if scenarios else None)
        if sid is not None and scenario is None: abort(404)
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
        if valid:return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid)+"#stays")
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


@app.route("/trip/<int:trip_id>/workspace")
def trip_workspace(trip_id):
    trip=get_trip(trip_id)
    with get_db_connection() as db:
        if trip["name"] == "Europe 2027" and db.execute("SELECT 1 FROM trip_scenarios WHERE trip_id=? AND name='S1'", (trip_id,)).fetchone():
            from europe_seed import add_missing_europe_candidates
            add_missing_europe_candidates(db,trip_id)
            from europe_seed import split_edinburgh_stays
            split_edinburgh_stays(db,trip_id)
            # Do not re-seed pre-revision route days after the user has
            # shifted S1/L1 to September 2027; their dates and notes are authoritative.
            revised_days = db.execute("""SELECT 1 FROM scenario_itinerary d
                JOIN trip_scenarios s ON s.id=d.scenario_id
                WHERE d.trip_id=? AND s.name IN ('S1','L1')
                  AND d.day_date >= '2027-09-14' LIMIT 1""",
                (trip_id,)).fetchone()
            if not revised_days:
                from europe_seed import add_europe_route_days
                add_europe_route_days(db,trip_id)
                from europe_seed import fill_europe_day_details
                fill_europe_day_details(db,trip_id)
        if trip["name"] == "Europe 2027":
            from reverse_routes import ensure_reverse_europe_routes
            ensure_reverse_europe_routes(db,trip_id)
            from europe_flight_research import add_europe_flight_research
            add_europe_flight_research(db,trip_id)
            from dublin_hotel_research import seed_dublin_hotel_research
            seed_dublin_hotel_research(db,trip_id)
            from dublin_rental_research import seed_dublin_rentals
            seed_dublin_rentals(db,trip_id)
            from other_city_lodging_research import seed_remaining_city_lodging
            seed_remaining_city_lodging(db,trip_id)
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
    selected={(r["city"],r["category"]):r["option_id"] for r in choices}
    groups={}
    for opt in options:
        if opt["scenario_tag"] is None or opt["scenario_tag"] == scenario["name"]:
            groups.setdefault((opt["city"],opt["category"]),[]).append(opt)
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
    hotels={k:v for k,v in groups.items() if k[1]=="hotel"}
    castles={k:v for k,v in groups.items() if k[1]=="castle"}
    # Display flight comparison groups in chronological itinerary order.
    # Keep grouping keys and saved selections unchanged; route dates are attached
    # to the researched options and the itinerary itself.
    reverse_route = scenario["name"].startswith("Backwards")
    route_sequence = (["STL → London", "London → Inverness", "Edinburgh → Shannon", "Dublin → STL"]
                      if reverse_route else
                      ["STL → Dublin", "Shannon → Edinburgh", "Inverness → London", "London → STL"])
    def flight_sort(entry):
        (route, _category), options_for_route = entry
        if route in route_sequence:
            return (0, route_sequence.index(route), route.casefold())
        dated = [o["start_date"] for o in options_for_route if o["start_date"]]
        return (1, min(dated) if dated else "9999-12-31", route.casefold())
    flights=dict(sorted(((k,v) for k,v in groups.items() if k[1]=="flight"), key=flight_sort))
    excursions={k:v for k,v in groups.items() if k[1]=="activity"}
    transport={k:v for k,v in groups.items() if k[1]=="transport"}
    selected_flights=[p for p in picked if p["category"]=="flight"]
    extra_expenses=sum(row["amount"] for row in expenses if not row["included_in_allowance"])
    food_allowance=scenario["food_travelers"]*scenario["food_days"]*scenario["food_daily_rate"]
    total=subtotal+food_allowance+scenario["ground_transport_allowance"]+scenario["contingency_allowance"]+scenario["insurance_allowance"]+scenario["fees_allowance"]+extra_expenses
    return render_template("workspace.html",trip=trip,scenarios=scenarios,scenario=scenario,groups=groups,hotels=hotels,castles=castles,flights=flights,excursions=excursions,transport=transport,selected_flights=selected_flights,selected=selected,stays=stays,warnings=warnings,undated=undated,missing=missing,subtotal=subtotal,food_allowance=food_allowance,total=total,remaining=scenario["budget_limit"]-total,expenses=expenses,extra_expenses=extra_expenses)


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
    selected={(row["city"],row["category"]):row["option_id"] for row in rows}
    groups={}
    for item in options:
        # Superseded Edinburgh hotel+castle bundles remain archived in the DB,
        # but never present them as a competing single city stay.
        if (item["city"]=="Edinburgh" and item["category"]=="hotel"
                and " + " in item["name"] and "Castle" in item["name"]):
            continue
        groups.setdefault((item["city"],item["category"]),[]).append(item)
    # Expenses outside allowances are already included in the active plan's estimate.
    extras=sum(e["amount"] for e in expenses if not e["included_in_allowance"])
    total=plan["food_travelers"]*plan["food_days"]*plan["food_daily_rate"]+plan["ground_transport_allowance"]+plan["contingency_allowance"]+plan["insurance_allowance"]+plan["fees_allowance"]+extras+sum(
        next((o["price"] or 0 for o in opts if o["id"]==selected.get(key)),0)
        for key,opts in groups.items())
    return render_template("playground.html",trip=trip,plans=plans,plan=plan,
        groups=groups,selected=selected,baseline=total,extras=extras,
        fixed_allowances=plan["food_travelers"]*plan["food_days"]*plan["food_daily_rate"]+plan["ground_transport_allowance"]+plan["contingency_allowance"]+plan["insurance_allowance"]+plan["fees_allowance"])


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
    link=request.form.get("link","").strip()
    notes=request.form.get("notes","").strip()
    if len(link)>500 or (link and not link.startswith(("https://","http://"))) or len(notes)>1000: abort(400,"Invalid flight link or notes")
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
        db.execute("UPDATE saved_options SET link=?,notes=? WHERE id=last_insert_rowid()",(link,notes))
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
    allowed=("name","origin","destination","carrier","departure_time","arrival_time","layovers","link","notes","route")
    fields={key:request.form.get(key,"").strip() for key in allowed}
    if not fields["name"] or not fields["route"] or len(fields["name"])>160 or len(fields["route"])>100 or len(fields["notes"])>1000 or len(fields["link"])>500 or (fields["link"] and not fields["link"].startswith(("https://","http://"))) or any(len(fields[key])>300 for key in ("origin","destination","carrier","departure_time","arrival_time","layovers")):abort(400)
    raw=request.form.get("price","").strip()
    try:price=float(raw) if raw else None
    except ValueError:abort(400)
    if price is not None and (not __import__("math").isfinite(price) or price<0 or price>10000000):abort(400)
    with get_db_connection() as db:
        row=db.execute("SELECT id,city FROM saved_options WHERE id=? AND trip_id=? AND category='flight'",(option_id,trip_id)).fetchone()
        if not row:abort(404)
        db.execute("""UPDATE saved_options SET name=?,origin=?,destination=?,carrier=?,
            departure_time=?,arrival_time=?,layovers=?,price=?,link=?,notes=?,city=? WHERE id=? AND trip_id=?""",
            (fields["name"],fields["origin"],fields["destination"],fields["carrier"],
             fields["departure_time"],fields["arrival_time"],fields["layovers"],price,fields["link"],fields["notes"],fields["route"],option_id,trip_id))
        if row["city"]!=fields["route"]:
            db.execute("DELETE FROM scenario_choices WHERE option_id=?",(option_id,))
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
        food_travelers=int(request.form.get("food_travelers",""))
        food_days=int(request.form.get("food_days",""))
        food_daily_rate=float(request.form.get("food_daily_rate",""))
        ground=float(request.form.get("ground_transport_allowance",""))
        contingency=float(request.form.get("contingency_allowance",""))
        insurance=float(request.form.get("insurance_allowance",""))
        fees=float(request.form.get("fees_allowance",""))
    except (ValueError, TypeError): abort(400,"Costs must be numbers")
    if not all(__import__("math").isfinite(x) and 0<=x<=100000000 for x in [budget,food_daily_rate,ground,contingency,insurance,fees]): abort(400)
    if not (1 <= food_travelers <= 100 and 1 <= food_days <= 365): abort(400)
    with get_db_connection() as db:
        row=db.execute("SELECT id FROM trip_scenarios WHERE trip_id=? AND id=?",(trip_id,sid)).fetchone()
        if not row: abort(404)
        db.execute("UPDATE trip_scenarios SET budget_limit=?,food_travelers=?,food_days=?,food_daily_rate=?,ground_transport_allowance=?,contingency_allowance=?,insurance_allowance=?,fees_allowance=? WHERE id=?",(budget,food_travelers,food_days,food_daily_rate,ground,contingency,insurance,fees,sid))
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
    if request.form.get("return_city")=="1" and category=="hotel":
        return redirect(url_for("city_view",trip_id=trip_id,city=city,scenario=sid))
    return redirect(url_for("trip_workspace",trip_id=trip_id,scenario=sid))



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

if __name__ == "__main__":
    app.run(debug=True)


