import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for, abort)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "instance", "campus.db"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-in-production")

CATEGORIES = ["General", "Academic", "Exam", "Placement", "Sports", "Cultural", "Hostel"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student',
    department TEXT
);
CREATE TABLE IF NOT EXISTS notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'General',
    created_at TEXT NOT NULL,
    author_id INTEGER REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    venue TEXT NOT NULL,
    event_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    UNIQUE(event_id, user_id)
);
CREATE TABLE IF NOT EXISTS lost_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('lost','found')),
    location TEXT NOT NULL,
    contact TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
"""


# ---------- database helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@campus.com")
    admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")
    if not db.execute("SELECT 1 FROM users WHERE email = ?", (admin_email,)).fetchone():
        db.execute(
            "INSERT INTO users (name, email, password_hash, role, department) VALUES (?,?,?,?,?)",
            ("Administrator", admin_email, generate_password_hash(admin_pass), "admin", "Administration"),
        )
    db.commit()
    db.close()


init_db()


# ---------- auth helpers ----------
@app.before_request
def load_user():
    uid = session.get("user_id")
    g.user = None
    if uid:
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in first.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in first.", "error")
            return redirect(url_for("login", next=request.path))
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {"categories": CATEGORIES}


@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403, message="You are not allowed to do that."), 403


@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404, message="Page not found."), 404


# ---------- home ----------
@app.route("/")
def index():
    db = get_db()
    notices = db.execute("SELECT * FROM notices ORDER BY id DESC LIMIT 5").fetchall()
    today = datetime.now().strftime("%Y-%m-%d")
    events = db.execute(
        "SELECT * FROM events WHERE substr(event_date,1,10) >= ? ORDER BY event_date LIMIT 5", (today,)
    ).fetchall()
    items = db.execute(
        "SELECT * FROM lost_items WHERE status = 'open' ORDER BY id DESC LIMIT 4"
    ).fetchall()
    return render_template("index.html", notices=notices, events=events, items=items)


# ---------- accounts ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        department = request.form.get("department", "").strip()
        password = request.form["password"]
        if not name or not email or len(password) < 6:
            flash("Fill all fields. Password must be at least 6 characters.", "error")
        else:
            try:
                get_db().execute(
                    "INSERT INTO users (name, email, password_hash, role, department) VALUES (?,?,?,?,?)",
                    (name, email, generate_password_hash(password), "student", department),
                )
                get_db().commit()
                flash("Account created. Please log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That email is already registered.", "error")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome, {user['name']}!", "success")
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("index"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# ---------- notices ----------
@app.route("/notices")
def notices():
    category = request.args.get("category", "")
    sql, params = "SELECT * FROM notices", []
    if category in CATEGORIES:
        sql += " WHERE category = ?"
        params.append(category)
    rows = get_db().execute(sql + " ORDER BY id DESC", params).fetchall()
    return render_template("notices.html", notices=rows, selected=category)


@app.route("/notices/new", methods=["GET", "POST"])
@admin_required
def notice_new():
    if request.method == "POST":
        title, body = request.form["title"].strip(), request.form["body"].strip()
        category = request.form.get("category", "General")
        if not title or not body:
            flash("Title and details are required.", "error")
        else:
            get_db().execute(
                "INSERT INTO notices (title, body, category, created_at, author_id) VALUES (?,?,?,?,?)",
                (title, body, category if category in CATEGORIES else "General", now(), g.user["id"]),
            )
            get_db().commit()
            flash("Notice published.", "success")
            return redirect(url_for("notices"))
    return render_template("notice_form.html", notice=None)


@app.route("/notices/<int:nid>/edit", methods=["GET", "POST"])
@admin_required
def notice_edit(nid):
    notice = get_db().execute("SELECT * FROM notices WHERE id = ?", (nid,)).fetchone()
    if notice is None:
        abort(404)
    if request.method == "POST":
        title, body = request.form["title"].strip(), request.form["body"].strip()
        category = request.form.get("category", "General")
        if not title or not body:
            flash("Title and details are required.", "error")
        else:
            get_db().execute(
                "UPDATE notices SET title=?, body=?, category=? WHERE id=?",
                (title, body, category if category in CATEGORIES else "General", nid),
            )
            get_db().commit()
            flash("Notice updated.", "success")
            return redirect(url_for("notices"))
    return render_template("notice_form.html", notice=notice)


@app.route("/notices/<int:nid>/delete", methods=["POST"])
@admin_required
def notice_delete(nid):
    get_db().execute("DELETE FROM notices WHERE id = ?", (nid,))
    get_db().commit()
    flash("Notice deleted.", "success")
    return redirect(url_for("notices"))


# ---------- events ----------
@app.route("/events")
def events():
    db = get_db()
    rows = db.execute(
        """SELECT e.*, (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id) AS total
           FROM events e ORDER BY event_date"""
    ).fetchall()
    registered = set()
    if g.user:
        registered = {r["event_id"] for r in db.execute(
            "SELECT event_id FROM registrations WHERE user_id = ?", (g.user["id"],))}
    return render_template("events.html", events=rows, registered=registered)


@app.route("/events/new", methods=["GET", "POST"])
@admin_required
def event_new():
    if request.method == "POST":
        f = {k: request.form[k].strip() for k in ("title", "description", "venue", "event_date")}
        if not all(f.values()):
            flash("All fields are required.", "error")
        else:
            get_db().execute(
                "INSERT INTO events (title, description, venue, event_date, created_at) VALUES (?,?,?,?,?)",
                (f["title"], f["description"], f["venue"], f["event_date"].replace("T", " "), now()),
            )
            get_db().commit()
            flash("Event created.", "success")
            return redirect(url_for("events"))
    return render_template("event_form.html", event=None)


@app.route("/events/<int:eid>/edit", methods=["GET", "POST"])
@admin_required
def event_edit(eid):
    event = get_db().execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone()
    if event is None:
        abort(404)
    if request.method == "POST":
        f = {k: request.form[k].strip() for k in ("title", "description", "venue", "event_date")}
        if not all(f.values()):
            flash("All fields are required.", "error")
        else:
            get_db().execute(
                "UPDATE events SET title=?, description=?, venue=?, event_date=? WHERE id=?",
                (f["title"], f["description"], f["venue"], f["event_date"].replace("T", " "), eid),
            )
            get_db().commit()
            flash("Event updated.", "success")
            return redirect(url_for("events"))
    return render_template("event_form.html", event=event)


@app.route("/events/<int:eid>/delete", methods=["POST"])
@admin_required
def event_delete(eid):
    get_db().execute("DELETE FROM events WHERE id = ?", (eid,))
    get_db().commit()
    flash("Event deleted.", "success")
    return redirect(url_for("events"))


@app.route("/events/<int:eid>/register", methods=["POST"])
@login_required
def event_register(eid):
    db = get_db()
    if db.execute("SELECT 1 FROM events WHERE id = ?", (eid,)).fetchone() is None:
        abort(404)
    try:
        db.execute("INSERT INTO registrations (event_id, user_id, created_at) VALUES (?,?,?)",
                   (eid, g.user["id"], now()))
        db.commit()
        flash("You are registered for the event.", "success")
    except sqlite3.IntegrityError:
        flash("You are already registered.", "error")
    return redirect(url_for("events"))


@app.route("/events/<int:eid>/unregister", methods=["POST"])
@login_required
def event_unregister(eid):
    get_db().execute("DELETE FROM registrations WHERE event_id = ? AND user_id = ?", (eid, g.user["id"]))
    get_db().commit()
    flash("Registration cancelled.", "success")
    return redirect(url_for("events"))


@app.route("/events/<int:eid>/registrations")
@admin_required
def event_registrations(eid):
    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone()
    if event is None:
        abort(404)
    people = db.execute(
        """SELECT u.name, u.email, u.department, r.created_at FROM registrations r
           JOIN users u ON u.id = r.user_id WHERE r.event_id = ? ORDER BY r.id""", (eid,)
    ).fetchall()
    return render_template("registrations.html", event=event, people=people)


# ---------- lost & found ----------
@app.route("/lostfound")
def lostfound():
    kind = request.args.get("kind", "")
    sql, params = "SELECT l.*, u.name AS poster FROM lost_items l JOIN users u ON u.id = l.user_id", []
    if kind in ("lost", "found"):
        sql += " WHERE l.kind = ?"
        params.append(kind)
    rows = get_db().execute(sql + " ORDER BY l.status, l.id DESC", params).fetchall()
    return render_template("lostfound.html", items=rows, selected=kind)


@app.route("/lostfound/new", methods=["GET", "POST"])
@login_required
def lostfound_new():
    if request.method == "POST":
        f = {k: request.form[k].strip() for k in ("title", "description", "location", "contact")}
        kind = request.form.get("kind", "lost")
        if not all(f.values()) or kind not in ("lost", "found"):
            flash("All fields are required.", "error")
        else:
            get_db().execute(
                """INSERT INTO lost_items (title, description, kind, location, contact, user_id, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (f["title"], f["description"], kind, f["location"], f["contact"], g.user["id"], now()),
            )
            get_db().commit()
            flash("Item posted.", "success")
            return redirect(url_for("lostfound"))
    return render_template("lostfound_form.html")


def _own_item(iid):
    item = get_db().execute("SELECT * FROM lost_items WHERE id = ?", (iid,)).fetchone()
    if item is None:
        abort(404)
    if g.user["role"] != "admin" and item["user_id"] != g.user["id"]:
        abort(403)
    return item


@app.route("/lostfound/<int:iid>/resolve", methods=["POST"])
@login_required
def lostfound_resolve(iid):
    _own_item(iid)
    get_db().execute("UPDATE lost_items SET status = 'resolved' WHERE id = ?", (iid,))
    get_db().commit()
    flash("Marked as resolved.", "success")
    return redirect(url_for("lostfound"))


@app.route("/lostfound/<int:iid>/delete", methods=["POST"])
@login_required
def lostfound_delete(iid):
    _own_item(iid)
    get_db().execute("DELETE FROM lost_items WHERE id = ?", (iid,))
    get_db().commit()
    flash("Post deleted.", "success")
    return redirect(url_for("lostfound"))


# ---------- search ----------
@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    results = {"notices": [], "events": [], "lost": []}
    if q:
        like = f"%{q}%"
        db = get_db()
        results["notices"] = db.execute(
            "SELECT * FROM notices WHERE title LIKE ? OR body LIKE ? OR category LIKE ? ORDER BY id DESC",
            (like, like, like)).fetchall()
        results["events"] = db.execute(
            "SELECT * FROM events WHERE title LIKE ? OR description LIKE ? OR venue LIKE ? ORDER BY event_date",
            (like, like, like)).fetchall()
        results["lost"] = db.execute(
            "SELECT * FROM lost_items WHERE title LIKE ? OR description LIKE ? OR location LIKE ? ORDER BY id DESC",
            (like, like, like)).fetchall()
    total = sum(len(v) for v in results.values())
    return render_template("search.html", q=q, results=results, total=total)


if __name__ == "__main__":
    app.run(debug=True)
