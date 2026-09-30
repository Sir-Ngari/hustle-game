#!/usr/bin/env python3
"""Hustle to a Billion - game server.

Serves the game and the admin dashboard, stores player accounts, saved games
and activity in a single SQLite file. Uses only the Python standard library
(Python 3.8 or newer), so nothing needs to be installed with pip.

Settings come from environment variables (see deploy/hustle.env.example):
  HUSTLE_ADMIN_PASSWORD   password for /admin (at least 10 characters; admin is off without it)
  HUSTLE_HOST / HUSTLE_PORT  where to listen (default 127.0.0.1:8090, behind nginx)
  HUSTLE_DB               path of the SQLite database (default ./data/hustle.db)
  HUSTLE_SECURE_COOKIES   "1" (default) when served over HTTPS, "0" for local testing
  HUSTLE_TRUST_PROXY      "1" (default) to read the visitor IP from nginx's X-Real-IP header
"""
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(BASE, "public")
HOST = os.environ.get("HUSTLE_HOST", "127.0.0.1")
PORT = int(os.environ.get("HUSTLE_PORT", "8090"))
DB_PATH = os.environ.get("HUSTLE_DB", os.path.join(BASE, "data", "hustle.db"))
ADMIN_PASSWORD = os.environ.get("HUSTLE_ADMIN_PASSWORD", "")
SECURE_COOKIES = os.environ.get("HUSTLE_SECURE_COOKIES", "1") == "1"
TRUST_PROXY = os.environ.get("HUSTLE_TRUST_PROXY", "1") == "1"

MAX_BODY = 3 * 1024 * 1024          # largest request body accepted
MAX_STATE = int(2.5 * 1024 * 1024)  # largest saved game
PLAYER_SESSION_SECONDS = 30 * 86400
ADMIN_SESSION_SECONDS = 12 * 3600
PBKDF2_ROUNDS = 200_000

USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,20}$")
BACKGROUNDS = {"hustler", "grad", "heir"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  pw_salt TEXT NOT NULL,
  pw_hash TEXT NOT NULL,
  name TEXT NOT NULL,
  company TEXT NOT NULL,
  town TEXT NOT NULL,
  bg TEXT NOT NULL,
  color INTEGER NOT NULL DEFAULT 0,
  created INTEGER NOT NULL,
  last_seen INTEGER NOT NULL,
  logins INTEGER NOT NULL DEFAULT 0,
  disabled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY,
  user_id INTEGER,
  is_admin INTEGER NOT NULL DEFAULT 0,
  created INTEGER NOT NULL,
  expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS saves(
  user_id INTEGER PRIMARY KEY,
  state TEXT NOT NULL,
  updated INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS stats(
  user_id INTEGER PRIMARY KEY,
  nw REAL NOT NULL DEFAULT 0,
  best REAL NOT NULL DEFAULT 0,
  cash REAL NOT NULL DEFAULT 0,
  month INTEGER NOT NULL DEFAULT 0,
  rank TEXT NOT NULL DEFAULT '',
  billion_month INTEGER,
  bankrupt INTEGER NOT NULL DEFAULT 0,
  games INTEGER NOT NULL DEFAULT 1,
  months_played INTEGER NOT NULL DEFAULT 0,
  detail TEXT NOT NULL DEFAULT '{}',
  updated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  ts INTEGER NOT NULL,
  game INTEGER NOT NULL DEFAULT 1,
  seq INTEGER,
  game_month INTEGER,
  kind TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS events_seq ON events(user_id, game, seq);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS snapshots(
  user_id INTEGER NOT NULL,
  game INTEGER NOT NULL DEFAULT 1,
  month INTEGER NOT NULL,
  nw REAL NOT NULL,
  ts INTEGER NOT NULL,
  PRIMARY KEY(user_id, game, month)
);
CREATE TABLE IF NOT EXISTS activity_days(
  user_id INTEGER NOT NULL,
  day TEXT NOT NULL,
  PRIMARY KEY(user_id, day)
);
"""

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
_db = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
_db.row_factory = sqlite3.Row
_db.execute("PRAGMA journal_mode=WAL")
_db.execute("PRAGMA foreign_keys=ON")
_db.executescript(SCHEMA)
_lock = threading.Lock()


def q(sql, args=(), one=False):
    """Run one query under the lock and return rows (or one row)."""
    with _lock:
        cur = _db.execute(sql, args)
        rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def tx(fn):
    """Run several statements as one transaction."""
    with _lock:
        _db.execute("BEGIN")
        try:
            result = fn(_db)
            _db.execute("COMMIT")
            return result
        except Exception:
            _db.execute("ROLLBACK")
            raise


def now():
    return int(time.time())


def today():
    return time.strftime("%Y-%m-%d", time.gmtime())


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()
    return salt, digest


# ---- simple in-memory rate limit for log-in style endpoints -----------------
_attempts = {}
_attempts_lock = threading.Lock()


def rate_limited(key, limit=10, window=600):
    t = time.time()
    with _attempts_lock:
        hits = [x for x in _attempts.get(key, []) if t - x < window]
        hits.append(t)
        _attempts[key] = hits
        return len(hits) > limit


def clean_text(value, max_len):
    """Trim a player-supplied string and drop control characters."""
    if not isinstance(value, str):
        return ""
    value = "".join(ch for ch in value if ch.isprintable())
    return value.strip()[:max_len]


def num(value, default=0.0):
    try:
        v = float(value)
        return v if v == v and abs(v) < 1e18 else default
    except (TypeError, ValueError):
        return default


def user_public(u):
    return {"id": u["id"], "username": u["username"], "name": u["name"], "company": u["company"],
            "town": u["town"], "bg": u["bg"], "color": u["color"]}


class Handler(BaseHTTPRequestHandler):
    server_version = "Hustle/1.0"
    sys_version = ""

    # ---------- plumbing ----------
    def log_message(self, fmt, *args):
        print("%s %s" % (self.client_ip(), fmt % args), flush=True)

    def client_ip(self):
        if TRUST_PROXY:
            real = self.headers.get("X-Real-IP")
            if real:
                return real.strip()
        return self.client_address[0]

    def security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                         "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                         "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
                         "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

    def send_json(self, status, payload, cookies=()):
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for c in cookies:
            self.send_header("Set-Cookie", c)
        self.security_headers()
        self.end_headers()
        self.wfile.write(body)

    def error(self, status, message):
        self.send_json(status, {"error": message})

    def cookie(self, name):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        c = SimpleCookie()
        try:
            c.load(raw)
        except Exception:
            return None
        return c[name].value if name in c else None

    def make_cookie(self, name, value, max_age):
        parts = ["%s=%s" % (name, value), "Path=/", "HttpOnly", "SameSite=Lax", "Max-Age=%d" % max_age]
        if SECURE_COOKIES:
            parts.append("Secure")
        return "; ".join(parts)

    def read_json(self):
        """Read a JSON body. Requires the JSON content type (blocks cross-site form posts)."""
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self.error(415, "Send JSON.")
            return None
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self.error(413, "Request is empty or too large.")
            return None
        try:
            data = json.loads(self.rfile.read(length))
        except Exception:
            self.error(400, "That was not valid JSON.")
            return None
        if not isinstance(data, dict):
            self.error(400, "Send a JSON object.")
            return None
        return data

    def session_user(self):
        token = self.cookie("hs")
        if not token:
            return None
        row = q("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token=? AND s.is_admin=0 AND s.expires>?", (token, now()), one=True)
        if not row or row["disabled"]:
            return None
        return row

    def is_admin(self):
        token = self.cookie("ha")
        if not token or not ADMIN_PASSWORD:
            return False
        return q("SELECT 1 FROM sessions WHERE token=? AND is_admin=1 AND expires>?", (token, now()), one=True) is not None

    def touch(self, user_id):
        q("UPDATE users SET last_seen=? WHERE id=?", (now(), user_id))
        q("INSERT OR IGNORE INTO activity_days(user_id, day) VALUES(?,?)", (user_id, today()))

    def serve_file(self, name):
        path = os.path.realpath(os.path.join(PUBLIC, name))
        if not path.startswith(os.path.realpath(PUBLIC) + os.sep) or not os.path.isfile(path):
            self.send_error(404)
            return
        with open(path, "rb") as f:
            data = f.read()
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.security_headers()
        self.end_headers()
        self.wfile.write(data)

    # ---------- routing ----------
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self.serve_file("index.html")
        if path in ("/admin", "/admin/", "/admin.html"):
            return self.serve_file("admin.html")
        if path == "/healthz":
            return self.send_json(200, {"ok": True})
        if path == "/api/me":
            return self.api_me()
        if path == "/api/leaderboard":
            return self.api_leaderboard()
        if path.startswith("/api/admin/"):
            return self.api_admin_get(path)
        if path.startswith("/api/"):
            return self.error(404, "Not found.")
        return self.serve_file(path.lstrip("/"))

    def do_POST(self):
        path = urlparse(self.path).path
        routes = {"/api/signup": self.api_signup, "/api/login": self.api_login, "/api/logout": self.api_logout,
                  "/api/admin/login": self.api_admin_login, "/api/admin/logout": self.api_admin_logout}
        if path in routes:
            return routes[path]()
        m = re.match(r"^/api/admin/player/(\d+)/(disable|enable|reset|delete)$", path)
        if m:
            return self.api_admin_action(int(m.group(1)), m.group(2))
        self.error(404, "Not found.")

    def do_PUT(self):
        if urlparse(self.path).path == "/api/save":
            return self.api_save()
        self.error(404, "Not found.")

    # ---------- player API ----------
    def api_signup(self):
        if rate_limited("signup:" + self.client_ip(), limit=8, window=3600):
            return self.error(429, "Too many new accounts from your network. Try again later.")
        d = self.read_json()
        if d is None:
            return
        username = clean_text(d.get("username"), 40).lower()
        password = d.get("password") if isinstance(d.get("password"), str) else ""
        name = clean_text(d.get("name"), 24)
        company = clean_text(d.get("company"), 16) or "Savanna"
        town = clean_text(d.get("town"), 20) or "Nairobi"
        bg = d.get("bg") if d.get("bg") in BACKGROUNDS else "hustler"
        try:
            color = max(0, min(5, int(d.get("color", 0))))
        except (TypeError, ValueError):
            color = 0
        if not USERNAME_RE.match(username):
            return self.error(400, "Usernames are 3 to 20 characters: letters, numbers, dots and underscores.")
        if len(password) < 8 or len(password) > 128:
            return self.error(400, "Passwords need at least 8 characters.")
        if not name:
            return self.error(400, "Enter your name.")
        if q("SELECT 1 FROM users WHERE username=?", (username,), one=True):
            return self.error(409, "That username is taken. Try another.")
        salt, digest = hash_password(password)
        t = now()
        token = secrets.token_urlsafe(32)

        def create(db):
            cur = db.execute("INSERT INTO users(username,pw_salt,pw_hash,name,company,town,bg,color,created,last_seen,logins) "
                             "VALUES(?,?,?,?,?,?,?,?,?,?,1)", (username, salt, digest, name, company, town, bg, color, t, t))
            uid = cur.lastrowid
            db.execute("INSERT INTO stats(user_id, updated) VALUES(?,?)", (uid, t))
            db.execute("INSERT INTO sessions(token,user_id,is_admin,created,expires) VALUES(?,?,0,?,?)",
                       (token, uid, t, t + PLAYER_SESSION_SECONDS))
            db.execute("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,1,'account',?)",
                       (uid, t, "Created an account (%s)" % {"hustler": "street hustler", "grad": "university graduate", "heir": "family business heir"}[bg]))
            db.execute("INSERT OR IGNORE INTO activity_days(user_id, day) VALUES(?,?)", (uid, today()))
            return uid

        try:
            uid = tx(create)
        except sqlite3.IntegrityError:
            return self.error(409, "That username is taken. Try another.")
        user = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
        self.send_json(201, {"user": user_public(user), "save": None},
                       [self.make_cookie("hs", token, PLAYER_SESSION_SECONDS)])

    def api_login(self):
        if rate_limited("login:" + self.client_ip(), limit=10, window=600):
            return self.error(429, "Too many attempts. Wait ten minutes and try again.")
        d = self.read_json()
        if d is None:
            return
        username = clean_text(d.get("username"), 40).lower()
        password = d.get("password") if isinstance(d.get("password"), str) else ""
        user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        ok = False
        if user:
            _, digest = hash_password(password, user["pw_salt"])
            ok = hmac.compare_digest(digest, user["pw_hash"])
        else:
            hash_password(password)  # same work either way, so timing reveals nothing
        if not ok:
            return self.error(401, "That username and password don't match.")
        if user["disabled"]:
            return self.error(403, "This account has been disabled. Contact the game's host.")
        token = secrets.token_urlsafe(32)
        t = now()
        q("INSERT INTO sessions(token,user_id,is_admin,created,expires) VALUES(?,?,0,?,?)",
          (token, user["id"], t, t + PLAYER_SESSION_SECONDS))
        q("UPDATE users SET logins=logins+1 WHERE id=?", (user["id"],))
        q("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'login','Logged in')",
          (user["id"], t, self.current_game(user["id"])))
        self.touch(user["id"])
        save = q("SELECT state FROM saves WHERE user_id=?", (user["id"],), one=True)
        self.send_json(200, {"user": user_public(user), "save": json.loads(save["state"]) if save else None},
                       [self.make_cookie("hs", token, PLAYER_SESSION_SECONDS)])

    def api_logout(self):
        token = self.cookie("hs")
        if token:
            q("DELETE FROM sessions WHERE token=?", (token,))
        self.send_json(200, {"ok": True}, [self.make_cookie("hs", "", 0)])

    def api_me(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Not logged in.")
        self.touch(user["id"])
        save = q("SELECT state FROM saves WHERE user_id=?", (user["id"],), one=True)
        self.send_json(200, {"user": user_public(user), "save": json.loads(save["state"]) if save else None})

    def current_game(self, uid):
        row = q("SELECT games FROM stats WHERE user_id=?", (uid,), one=True)
        return row["games"] if row else 1

    def api_save(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Your session ended. Log in again to keep saving.")
        d = self.read_json()
        if d is None:
            return
        state = d.get("state")
        summary = d.get("summary") if isinstance(d.get("summary"), dict) else {}
        events = d.get("events") if isinstance(d.get("events"), list) else []
        if not isinstance(state, dict):
            return self.error(400, "Missing game state.")
        state_text = json.dumps(state, separators=(",", ":"))
        if len(state_text) > MAX_STATE:
            return self.error(413, "This saved game is too large.")
        uid = user["id"]
        t = now()
        month = int(num(summary.get("month")))
        nw = num(summary.get("nw"))
        new_game = bool(summary.get("newGame"))
        detail_keys = ("industries", "units", "properties", "teams", "happiness", "reputation", "influence",
                       "debt", "married", "kids", "age", "tab", "race", "foundation", "cities", "gender", "spouse")
        detail = {k: summary.get(k) for k in detail_keys if isinstance(summary.get(k), (int, float, str, bool))}
        detail = {k: (clean_text(v, 40) if isinstance(v, str) else v) for k, v in detail.items()}

        def write(db):
            st = db.execute("SELECT * FROM stats WHERE user_id=?", (uid,)).fetchone()
            game = st["games"] if st else 1
            prev_month = st["month"] if st else 0
            if new_game:
                game += 1
                db.execute("DELETE FROM snapshots WHERE user_id=? AND game<?", (uid, game - 3))
                db.execute("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'game','Started a new game')", (uid, t, game))
                prev_month = 0
            played = max(0, month - prev_month) if not new_game else month
            best = max(st["best"] if st and not new_game else 0, nw)
            billion = st["billion_month"] if st and not new_game else None
            if billion is None and summary.get("won"):
                billion = month
            db.execute("INSERT INTO saves(user_id,state,updated) VALUES(?,?,?) "
                       "ON CONFLICT(user_id) DO UPDATE SET state=excluded.state, updated=excluded.updated",
                       (uid, state_text, t))
            db.execute("INSERT INTO stats(user_id,nw,best,cash,month,rank,billion_month,bankrupt,games,months_played,detail,updated) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET nw=excluded.nw, best=excluded.best, "
                       "cash=excluded.cash, month=excluded.month, rank=excluded.rank, billion_month=excluded.billion_month, "
                       "bankrupt=excluded.bankrupt, games=excluded.games, months_played=stats.months_played+?, "
                       "detail=excluded.detail, updated=excluded.updated",
                       (uid, nw, best, num(summary.get("cash")), month, clean_text(summary.get("rank"), 30), billion,
                        1 if summary.get("over") else 0, game, played, json.dumps(detail), t, played))
            if month % 3 == 0 or month != prev_month:
                db.execute("INSERT OR REPLACE INTO snapshots(user_id,game,month,nw,ts) VALUES(?,?,?,?,?)",
                           (uid, game, month, nw, t))
            for e in events[:60]:
                if not isinstance(e, dict):
                    continue
                text = clean_text(e.get("t"), 300)
                if not text:
                    continue
                try:
                    seq = int(e.get("n"))
                    gm = int(e.get("m"))
                except (TypeError, ValueError):
                    continue
                db.execute("INSERT OR IGNORE INTO events(user_id,ts,game,seq,game_month,kind,text) VALUES(?,?,?,?,?,?,?)",
                           (uid, t, game, seq, gm, clean_text(e.get("k"), 12), text))
            return game

        game = tx(write)
        self.touch(uid)
        self.send_json(200, {"ok": True, "game": game})

    def api_leaderboard(self):
        rows = q("SELECT u.name,u.company,u.color,s.best,s.nw,s.month,s.billion_month,s.bankrupt FROM users u "
                 "JOIN stats s ON s.user_id=u.id WHERE u.disabled=0 AND s.best>0 "
                 "ORDER BY (s.billion_month IS NULL), s.billion_month, s.best DESC LIMIT 25")
        self.send_json(200, {"players": [dict(r) for r in rows]})

    # ---------- admin API ----------
    def api_admin_login(self):
        if not ADMIN_PASSWORD or len(ADMIN_PASSWORD) < 10:
            return self.error(503, "Admin is switched off. Set HUSTLE_ADMIN_PASSWORD (10+ characters) on the server.")
        if rate_limited("admin:" + self.client_ip(), limit=5, window=900):
            return self.error(429, "Too many attempts. Wait fifteen minutes and try again.")
        d = self.read_json()
        if d is None:
            return
        password = d.get("password") if isinstance(d.get("password"), str) else ""
        if not hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
            return self.error(401, "Wrong admin password.")
        token = secrets.token_urlsafe(32)
        t = now()
        q("INSERT INTO sessions(token,user_id,is_admin,created,expires) VALUES(?,NULL,1,?,?)", (token, t, t + ADMIN_SESSION_SECONDS))
        q("DELETE FROM sessions WHERE expires<?", (t,))
        self.send_json(200, {"ok": True}, [self.make_cookie("ha", token, ADMIN_SESSION_SECONDS)])

    def api_admin_logout(self):
        token = self.cookie("ha")
        if token:
            q("DELETE FROM sessions WHERE token=?", (token,))
        self.send_json(200, {"ok": True}, [self.make_cookie("ha", "", 0)])

    def api_admin_get(self, path):
        if not self.is_admin():
            return self.error(401, "Log in as admin.")
        if path == "/api/admin/overview":
            return self.admin_overview()
        if path == "/api/admin/players":
            rows = q("SELECT u.id,u.username,u.name,u.company,u.town,u.bg,u.color,u.created,u.last_seen,u.logins,u.disabled,"
                     "s.nw,s.best,s.cash,s.month,s.rank,s.billion_month,s.bankrupt,s.games,s.months_played,s.detail,"
                     "(SELECT COUNT(*) FROM activity_days a WHERE a.user_id=u.id) AS days_active "
                     "FROM users u LEFT JOIN stats s ON s.user_id=u.id ORDER BY u.last_seen DESC")
            players = []
            for r in rows:
                p = dict(r)
                p["detail"] = json.loads(p["detail"] or "{}")
                players.append(p)
            return self.send_json(200, {"players": players, "now": now()})
        m = re.match(r"^/api/admin/player/(\d+)$", path)
        if m:
            uid = int(m.group(1))
            u = q("SELECT id,username,name,company,town,bg,color,created,last_seen,logins,disabled FROM users WHERE id=?", (uid,), one=True)
            if not u:
                return self.error(404, "No such player.")
            st = q("SELECT * FROM stats WHERE user_id=?", (uid,), one=True)
            game = st["games"] if st else 1
            snaps = q("SELECT month,nw FROM snapshots WHERE user_id=? AND game=? ORDER BY month", (uid, game))
            evs = q("SELECT ts,game_month,kind,text FROM events WHERE user_id=? ORDER BY id DESC LIMIT 200", (uid,))
            stats = dict(st) if st else {}
            if stats:
                stats["detail"] = json.loads(stats.get("detail") or "{}")
            return self.send_json(200, {"user": dict(u), "stats": stats, "snapshots": [dict(s) for s in snaps],
                                        "events": [dict(e) for e in evs], "now": now()})
        self.error(404, "Not found.")

    def admin_overview(self):
        t = now()
        k = {
            "players": q("SELECT COUNT(*) c FROM users", one=True)["c"],
            "active24h": q("SELECT COUNT(*) c FROM users WHERE last_seen>?", (t - 86400,), one=True)["c"],
            "active7d": q("SELECT COUNT(*) c FROM users WHERE last_seen>?", (t - 7 * 86400,), one=True)["c"],
            "signups7d": q("SELECT COUNT(*) c FROM users WHERE created>?", (t - 7 * 86400,), one=True)["c"],
            "monthsPlayed": q("SELECT COALESCE(SUM(months_played),0) c FROM stats", one=True)["c"],
            "billionaires": q("SELECT COUNT(*) c FROM stats WHERE billion_month IS NOT NULL", one=True)["c"],
            "bankrupt": q("SELECT COUNT(*) c FROM stats WHERE bankrupt=1", one=True)["c"],
        }
        days = []
        for i in range(13, -1, -1):
            day = time.strftime("%Y-%m-%d", time.gmtime(t - i * 86400))
            start = int(time.mktime(time.strptime(day, "%Y-%m-%d"))) - time.timezone
            days.append({
                "day": day,
                "active": q("SELECT COUNT(*) c FROM activity_days WHERE day=?", (day,), one=True)["c"],
                "signups": q("SELECT COUNT(*) c FROM users WHERE created>=? AND created<?", (start, start + 86400), one=True)["c"],
            })
        feed = q("SELECT e.ts,e.game_month,e.kind,e.text,u.id AS user_id,u.name,u.company,u.color FROM events e "
                 "JOIN users u ON u.id=e.user_id ORDER BY e.id DESC LIMIT 60")
        self.send_json(200, {"kpis": k, "days": days, "feed": [dict(f) for f in feed], "now": t})

    def api_admin_action(self, uid, action):
        if not self.is_admin():
            return self.error(401, "Log in as admin.")
        if not q("SELECT 1 FROM users WHERE id=?", (uid,), one=True):
            return self.error(404, "No such player.")
        # the admin page sends a JSON body so a cross-site form cannot trigger these
        if self.read_json() is None:
            return
        t = now()
        if action == "disable":
            q("UPDATE users SET disabled=1 WHERE id=?", (uid,))
            q("DELETE FROM sessions WHERE user_id=?", (uid,))
            q("INSERT INTO events(user_id,ts,kind,text) VALUES(?,?,'admin','Account disabled by the host')", (uid, t))
        elif action == "enable":
            q("UPDATE users SET disabled=0 WHERE id=?", (uid,))
            q("INSERT INTO events(user_id,ts,kind,text) VALUES(?,?,'admin','Account re-enabled by the host')", (uid, t))
        elif action == "reset":
            def reset(db):
                db.execute("DELETE FROM saves WHERE user_id=?", (uid,))
                db.execute("UPDATE stats SET nw=0,best=0,cash=0,month=0,rank='',billion_month=NULL,bankrupt=0,games=games+1,detail='{}',updated=? WHERE user_id=?", (t, uid))
                db.execute("INSERT INTO events(user_id,ts,kind,text) VALUES(?,?,'admin','Game reset by the host')", (uid, t))
            tx(reset)
        elif action == "delete":
            def delete(db):
                for table in ("sessions", "saves", "stats", "events", "snapshots", "activity_days"):
                    db.execute("DELETE FROM %s WHERE user_id=?" % table, (uid,))
                db.execute("DELETE FROM users WHERE id=?", (uid,))
            tx(delete)
        self.send_json(200, {"ok": True})


def main():
    if not ADMIN_PASSWORD or len(ADMIN_PASSWORD) < 10:
        print("Note: admin dashboard is off. Set HUSTLE_ADMIN_PASSWORD (10+ characters) to turn it on.", flush=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print("Hustle to a Billion is running on http://%s:%d" % (HOST, PORT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
