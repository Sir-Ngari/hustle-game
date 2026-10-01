#!/usr/bin/env python3
"""Hustle to an Empire - game server.

Serves the game and the admin dashboard, stores player accounts, saved games
and activity in a single SQLite file. Uses only the Python standard library
(Python 3.8 or newer), so nothing needs to be installed with pip.

Settings come from environment variables (see deploy/hustle.env.example):
  HUSTLE_ADMIN_PASSWORD   password for /admin (at least 10 characters; admin is off without it)
  HUSTLE_HOST / HUSTLE_PORT  where to listen (default 127.0.0.1:8090, behind nginx)
  HUSTLE_DB               path of the SQLite database (default ./data/hustle.db)
  HUSTLE_SECURE_COOKIES   "1" (default) when served over HTTPS, "0" for local testing
  HUSTLE_TRUST_PROXY      "1" (default) to read the visitor IP from nginx's X-Real-IP header
  HUSTLE_SITE_DOMAIN      the game's domain, used in password-reset links (e.g. shwariapps.com)
  HUSTLE_MAIL_PROVIDER    how reset emails are sent: resend, brevo, smtp, or log (prints them); off when empty
  HUSTLE_MAIL_KEY         API key for resend or brevo (or the SMTP password)
  HUSTLE_MAIL_FROM        sender address (default no-reply@<HUSTLE_SITE_DOMAIN>)
  HUSTLE_SMTP_HOST / HUSTLE_SMTP_PORT / HUSTLE_SMTP_USER   only for HUSTLE_MAIL_PROVIDER=smtp
  HUSTLE_OLD_DOMAINS      old web addresses (comma separated) whose pages forward to HUSTLE_SITE_DOMAIN
  HUSTLE_BILLING          "1" turns the Hustle Pass (free trial, then pay) on; off when empty or "0"
  HUSTLE_PESAPAL_KEY / HUSTLE_PESAPAL_SECRET   the consumer key and secret from your Pesapal account
  HUSTLE_PESAPAL_ENV      "live" (default) or "sandbox" for Pesapal's test system
  HUSTLE_TRIAL_HOURS / HUSTLE_GIFT_DAYS / HUSTLE_GIFTS / HUSTLE_BLOCK_DAYS   trial length and the "more free days" offers
  HUSTLE_PRICE_WEEK / HUSTLE_PRICE_MONTH / HUSTLE_PRICE_YEAR   pass prices in Kenya shillings (70 / 250 / 2000)
"""
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

mimetypes.add_type("application/manifest+json", ".webmanifest")
BASE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(BASE, "public")
HOST = os.environ.get("HUSTLE_HOST", "127.0.0.1")
PORT = int(os.environ.get("HUSTLE_PORT", "8090"))
DB_PATH = os.environ.get("HUSTLE_DB", os.path.join(BASE, "data", "hustle.db"))
ADMIN_PASSWORD = os.environ.get("HUSTLE_ADMIN_PASSWORD", "")
SECURE_COOKIES = os.environ.get("HUSTLE_SECURE_COOKIES", "1") == "1"
TRUST_PROXY = os.environ.get("HUSTLE_TRUST_PROXY", "1") == "1"
SITE_DOMAIN = os.environ.get("HUSTLE_SITE_DOMAIN", "").strip().strip("/")
OLD_DOMAINS = {d.strip().lower() for d in os.environ.get("HUSTLE_OLD_DOMAINS", "").split(",") if d.strip()} - {SITE_DOMAIN.lower()}
MAIL_PROVIDER = os.environ.get("HUSTLE_MAIL_PROVIDER", "").strip().lower()
MAIL_KEY = os.environ.get("HUSTLE_MAIL_KEY", "").strip()
MAIL_FROM = os.environ.get("HUSTLE_MAIL_FROM", "").strip() or ("no-reply@" + SITE_DOMAIN if SITE_DOMAIN else "")
SMTP_HOST = os.environ.get("HUSTLE_SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("HUSTLE_SMTP_PORT", "587") or 587)
SMTP_USER = os.environ.get("HUSTLE_SMTP_USER", "").strip()
RESET_SECONDS = 3600


def env_int(name, default):
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


# ---- Hustle Pass (subscription) settings ----
BILLING_ON = os.environ.get("HUSTLE_BILLING", "").strip() == "1"
PESAPAL_KEY = os.environ.get("HUSTLE_PESAPAL_KEY", "").strip()
PESAPAL_SECRET = os.environ.get("HUSTLE_PESAPAL_SECRET", "").strip()
PESAPAL_ENV = "sandbox" if os.environ.get("HUSTLE_PESAPAL_ENV", "").strip().lower() == "sandbox" else "live"
PESAPAL_URL = (os.environ.get("HUSTLE_PESAPAL_URL", "").strip().rstrip("/") or
               ("https://cybqa.pesapal.com/pesapalv3" if PESAPAL_ENV == "sandbox" else "https://pay.pesapal.com/v3"))
TRIAL_HOURS = env_int("HUSTLE_TRIAL_HOURS", 24)   # free trial from sign-up (or from the day billing was switched on)
GIFT_DAYS = env_int("HUSTLE_GIFT_DAYS", 2)        # extra free days offered to a player who leaves the payment screen
GIFTS = env_int("HUSTLE_GIFTS", 2)                # how many times that offer is made
BLOCK_DAYS = env_int("HUSTLE_BLOCK_DAYS", 7)      # after this many days, no more free time: pay to play
PLANS = {
    "week": {"name": "Weekly pass", "days": 7, "kes": env_int("HUSTLE_PRICE_WEEK", 70)},
    "month": {"name": "Monthly pass", "days": 30, "kes": env_int("HUSTLE_PRICE_MONTH", 250)},
    "year": {"name": "Yearly pass", "days": 365, "kes": env_int("HUSTLE_PRICE_YEAR", 2000)},
}

MAX_BODY = 3 * 1024 * 1024          # largest request body accepted
MAX_STATE = int(2.5 * 1024 * 1024)  # largest saved game
PLAYER_SESSION_SECONDS = 30 * 86400
ADMIN_SESSION_SECONDS = 12 * 3600
PBKDF2_ROUNDS = 200_000

USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,20}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[a-z0-9.-]+\.[a-z]{2,}$")
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
CREATE TABLE IF NOT EXISTS resets(
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  created INTEGER NOT NULL,
  expires INTEGER NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS lives(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  game INTEGER NOT NULL,
  ended INTEGER NOT NULL,
  data TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS lives_game ON lives(user_id, game);
CREATE TABLE IF NOT EXISTS season_scores(
  user_id INTEGER NOT NULL,
  season TEXT NOT NULL,
  pts INTEGER NOT NULL DEFAULT 0,
  region TEXT NOT NULL DEFAULT '',
  updated INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(user_id, season)
);
CREATE INDEX IF NOT EXISTS season_rank ON season_scores(season, pts);
CREATE TABLE IF NOT EXISTS activity_days(
  user_id INTEGER NOT NULL,
  day TEXT NOT NULL,
  PRIMARY KEY(user_id, day)
);
CREATE TABLE IF NOT EXISTS meta(
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subs(
  user_id INTEGER PRIMARY KEY,
  paid_until INTEGER NOT NULL DEFAULT 0,
  plan TEXT NOT NULL DEFAULT '',
  gifts INTEGER NOT NULL DEFAULT 0,
  gift_until INTEGER NOT NULL DEFAULT 0,
  paywall_at INTEGER NOT NULL DEFAULT 0,
  later INTEGER NOT NULL DEFAULT 0,
  checkouts INTEGER NOT NULL DEFAULT 0,
  updated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ref TEXT UNIQUE NOT NULL,
  user_id INTEGER NOT NULL,
  plan TEXT NOT NULL,
  days INTEGER NOT NULL,
  amount REAL NOT NULL,
  currency TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  tracking TEXT NOT NULL DEFAULT '',
  method TEXT NOT NULL DEFAULT '',
  code TEXT NOT NULL DEFAULT '',
  created INTEGER NOT NULL,
  updated INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS payments_user ON payments(user_id);
CREATE INDEX IF NOT EXISTS payments_status ON payments(status, created);
"""

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
_db = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
_db.row_factory = sqlite3.Row
_db.execute("PRAGMA journal_mode=WAL")
_db.execute("PRAGMA foreign_keys=ON")
_db.executescript(SCHEMA)
# upgrade older databases: add the email column to accounts made before it existed
if "email" not in [r[1] for r in _db.execute("PRAGMA table_info(users)").fetchall()]:
    _db.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
_db.execute("CREATE INDEX IF NOT EXISTS users_email ON users(email)")
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


def season_now(offset_days=0):
    """The current monthly season, e.g. 2026-10 (UTC)."""
    return time.strftime("%Y-%m", time.gmtime(time.time() + offset_days * 86400))


def season_ok(sid):
    """Accept this month's season, and the neighbouring one around midnight on the 1st (time zones)."""
    return isinstance(sid, str) and sid in (season_now(), season_now(-2), season_now(2))


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


# ---- past lives: one row per finished game ---------------------------------
LIFE_TEXT = {"region": 3, "end": 10, "cause": 160, "rank": 30, "spouse": 40, "who": 40}
LIFE_NUM = ("months", "age", "nw", "best", "start", "kids", "inds", "props", "teams", "ts", "gen")


def clean_life(d):
    """Keep only the known fields of a finished-game summary sent by the browser."""
    if not isinstance(d, dict):
        return None
    out = {k: clean_text(d.get(k), n) for k, n in LIFE_TEXT.items() if isinstance(d.get(k), str)}
    for k in LIFE_NUM:
        if isinstance(d.get(k), (int, float)) and not isinstance(d.get(k), bool):
            out[k] = num(d.get(k))
    for k in ("fdn", "dirty", "bribed", "jailed"):
        out[k] = bool(d.get(k))
    ba = d.get("billionAge")
    out["billionAge"] = int(ba) if isinstance(ba, (int, float)) and not isinstance(ba, bool) and 0 < ba < 200 else None
    if out.get("end") not in ("died", "bankrupt", "restarted", "vanished"):
        out["end"] = "restarted"
    return out


def life_from_records(db, uid, game, st=None):
    """Rebuild what we can of a finished game from the news feed and the stats row."""
    det = {}
    if st is not None:
        try:
            det = json.loads(st["detail"] or "{}")
        except ValueError:
            det = {}
    row = db.execute("SELECT MAX(game_month) m, MAX(ts) t FROM events WHERE user_id=? AND game=?", (uid, game)).fetchone()
    months = int(st["month"]) if st is not None else int(row["m"] or 0)
    death = db.execute("SELECT text FROM events WHERE user_id=? AND game=? AND text LIKE 'You passed away at %' "
                       "ORDER BY id DESC LIMIT 1", (uid, game)).fetchone()
    snap = db.execute("SELECT nw FROM snapshots WHERE user_id=? AND game=? ORDER BY month DESC LIMIT 1", (uid, game)).fetchone()
    best = db.execute("SELECT MAX(nw) b FROM snapshots WHERE user_id=? AND game=?", (uid, game)).fetchone()
    life = {"months": months, "age": 24 + months // 12, "region": det.get("region") or "KE", "partial": st is None,
            "nw": st["nw"] if st is not None else (snap["nw"] if snap else 0),
            "best": st["best"] if st is not None else (best["b"] if best and best["b"] else 0),
            "rank": st["rank"] if st is not None else "", "spouse": "", "kids": det.get("kids") or 0,
            "inds": det.get("industries") or 0, "props": det.get("properties") or 0, "teams": det.get("teams") or 0,
            "fdn": bool(det.get("foundation")), "ts": (row["t"] or 0) * 1000,
            "billionAge": (24 + st["billion_month"] // 12) if st is not None and st["billion_month"] is not None else None}
    if death:
        text = death["text"]
        life["end"] = "died"
        parts = text.split(". ", 1)
        life["cause"] = clean_text(parts[1] if len(parts) > 1 else "", 160)
        try:
            life["age"] = int(parts[0].rsplit(" ", 1)[1])
        except (IndexError, ValueError):
            pass
    else:
        broke = db.execute("SELECT 1 FROM events WHERE user_id=? AND game=? AND text LIKE 'Bankrupt at %' LIMIT 1",
                           (uid, game)).fetchone()
        life["end"] = "bankrupt" if broke or (st is not None and st["bankrupt"]) else "restarted"
    return life


def retention(t):
    """Of players who signed up in the last 90 days, the share who came back N or more days later."""
    users = q("SELECT id, created FROM users WHERE created>?", (t - 90 * 86400,))
    days = {}
    for r in q("SELECT a.user_id, a.day FROM activity_days a JOIN users u ON u.id=a.user_id WHERE u.created>?",
               (t - 90 * 86400,)):
        days.setdefault(r["user_id"], []).append(r["day"])
    out = {}
    for n in (1, 7, 30):
        eligible = [u for u in users if u["created"] <= t - n * 86400]
        back = 0
        for u in eligible:
            cut = time.strftime("%Y-%m-%d", time.gmtime(u["created"] + n * 86400))
            if any(d >= cut for d in days.get(u["id"], [])):
                back += 1
        out["d%d" % n] = {"players": len(eligible), "back": back,
                          "pct": round(100 * back / len(eligible)) if eligible else None}
    return out


def backfill_lives():
    """Give players who finished games before past lives existed a history of them."""
    def run(db):
        for st in db.execute("SELECT user_id, games FROM stats WHERE games>1").fetchall():
            uid = st["user_id"]
            for g in range(1, st["games"]):
                if db.execute("SELECT 1 FROM lives WHERE user_id=? AND game=?", (uid, g)).fetchone():
                    continue
                if not db.execute("SELECT 1 FROM events WHERE user_id=? AND game=? LIMIT 1", (uid, g)).fetchone():
                    continue
                life = life_from_records(db, uid, g)
                db.execute("INSERT OR IGNORE INTO lives(user_id,game,ended,data) VALUES(?,?,?,?)",
                           (uid, g, int(life["ts"] // 1000) or now(), json.dumps(life)))
    tx(run)


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
            "town": u["town"], "bg": u["bg"], "color": u["color"], "email": u["email"]}


def clean_email(value):
    """Return a lower-cased email address, or '' when it doesn't look like one."""
    e = clean_text(value, 120).lower()
    return e if EMAIL_RE.match(e) else ""


def mail_ready():
    if MAIL_PROVIDER == "log":
        return True
    if not SITE_DOMAIN or not MAIL_FROM:
        return False
    if MAIL_PROVIDER in ("resend", "brevo"):
        return bool(MAIL_KEY)
    if MAIL_PROVIDER == "smtp":
        return bool(SMTP_HOST and MAIL_KEY)
    return False


def send_mail(to, subject, text, html):
    """Send one email with the configured provider. Returns True when it was accepted."""
    sender_name = "Hustle to an Empire"
    try:
        if MAIL_PROVIDER == "log":
            print("MAIL to %s | %s\n%s" % (to, subject, text), flush=True)
            return True
        if MAIL_PROVIDER in ("resend", "brevo"):
            if MAIL_PROVIDER == "resend":
                url = "https://api.resend.com/emails"
                body = {"from": "%s <%s>" % (sender_name, MAIL_FROM), "to": [to], "subject": subject, "text": text, "html": html}
                headers = {"Authorization": "Bearer " + MAIL_KEY}
            else:
                url = "https://api.brevo.com/v3/smtp/email"
                body = {"sender": {"name": sender_name, "email": MAIL_FROM}, "to": [{"email": to}], "subject": subject,
                        "textContent": text, "htmlContent": html}
                headers = {"api-key": MAIL_KEY}
            headers.update({"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "hustle-game"})
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=20) as r:
                ok = 200 <= r.status < 300
            if not ok:
                print("Mail provider refused the email to %s" % to, flush=True)
            return ok
        if MAIL_PROVIDER == "smtp":
            msg = EmailMessage()
            msg["From"] = "%s <%s>" % (sender_name, MAIL_FROM)
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(text)
            msg.add_alternative(html, subtype="html")
            ctx = ssl.create_default_context()
            if SMTP_PORT == 465:
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=20) as sm:
                    sm.login(SMTP_USER or MAIL_FROM, MAIL_KEY)
                    sm.send_message(msg)
            else:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as sm:
                    sm.starttls(context=ctx)
                    sm.login(SMTP_USER or MAIL_FROM, MAIL_KEY)
                    sm.send_message(msg)
            return True
    except Exception as e:  # never let a mail problem crash a request
        detail = ""
        if hasattr(e, "read"):
            try:
                detail = e.read().decode()[:300]
            except Exception:
                pass
        print("Could not send email to %s: %s %s" % (to, e, detail), flush=True)
    return False


def html_escape(x):
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def send_reset_emails(email, accounts):
    """accounts: list of (username, name, link). One email lists every account on that address."""
    lines = "\n".join("  %s (@%s): %s" % (n, u, link) for u, n, link in accounts)
    text = ("Someone asked to reset the password for your Hustle to an Empire account%s.\n\n"
            "Open this link to choose a new password:\n%s\n\n"
            "The link works once and expires in 1 hour. If you didn't ask for this, ignore this email; "
            "your password stays the same.\n" % ("s" if len(accounts) > 1 else "", lines))
    buttons = "".join(
        '<p style="margin:18px 0"><a href="%s" style="background:#14261f;color:#ffffff;padding:12px 20px;border-radius:4px;'
        'text-decoration:none;font-weight:bold;display:inline-block">Reset password for @%s</a></p>' % (html_escape(link), html_escape(u))
        for u, n, link in accounts)
    html = ('<div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.5;color:#14261f;max-width:520px">'
            '<h2 style="margin:0 0 12px">Reset your password</h2>'
            '<p>Someone asked to reset the password for your <b>Hustle to an Empire</b> account%s.</p>%s'
            '<p style="color:#5b6660;font-size:13px">The link works once and expires in 1 hour. If you didn\'t ask for this, '
            'ignore this email; your password stays the same.</p></div>') % ("s" if len(accounts) > 1 else "", buttons)
    send_mail(email, "Reset your Hustle to an Empire password", text, html)


# ---- Hustle Pass: who may play, and Pesapal payments -------------------------
def meta_get(k):
    r = q("SELECT v FROM meta WHERE k=?", (k,), one=True)
    return r["v"] if r else None


def meta_set(k, v):
    q("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


def billing_start():
    """When billing was first switched on. Players who joined earlier get their trial from this moment."""
    v = meta_get("billing_start")
    if v is None:
        v = str(now())
        meta_set("billing_start", v)
    return int(v)


def pesapal_ready():
    return bool(PESAPAL_KEY and PESAPAL_SECRET and SITE_DOMAIN)


def plans_public():
    return [{"id": k, "name": p["name"], "days": p["days"], "kes": p["kes"]} for k, p in PLANS.items()]


def sub_row(uid):
    return q("SELECT * FROM subs WHERE user_id=?", (uid,), one=True)


def bill_status(user, mark_paywall=False):
    """The player's pass: off, trial, bonus (gift days), paid, or locked (must pay; maybe offered gift days)."""
    if not BILLING_ON:
        return {"on": False, "state": "off"}
    t = now()
    s = sub_row(user["id"])
    paid_until = s["paid_until"] if s else 0
    gifts = s["gifts"] if s else 0
    gift_until = s["gift_until"] if s else 0
    base = max(user["created"], billing_start())
    trial_end = base + TRIAL_HOURS * 3600
    hard = base + BLOCK_DAYS * 86400
    out = {"on": True, "plans": plans_public(), "payReady": pesapal_ready(), "giftDays": GIFT_DAYS,
           "now": t, "plan": s["plan"] if s else "", "everPaid": paid_until > 0}
    if paid_until > t:
        out.update(state="paid", until=paid_until)
    elif t < trial_end:
        out.update(state="trial", until=trial_end)
    elif gift_until > t:
        out.update(state="bonus", until=gift_until, giftsUsed=gifts)
    else:
        out.update(state="locked", until=0, ended=max(paid_until, gift_until, trial_end),
                   gift=paid_until == 0 and gifts < GIFTS and t < hard - 3600, giftsUsed=gifts)
        if mark_paywall and not (s and s["paywall_at"]):
            q("INSERT INTO subs(user_id,paywall_at,updated) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
              "paywall_at=CASE WHEN subs.paywall_at=0 THEN excluded.paywall_at ELSE subs.paywall_at END, updated=excluded.updated",
              (user["id"], t, t))
    return out


def can_play(user):
    return bill_status(user)["state"] != "locked"


_pp = {"token": None, "exp": 0}
_pp_lock = threading.Lock()


class PesapalError(Exception):
    pass


def pp_request(method, path, body=None, token=None):
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "hustle-game"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(PESAPAL_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode()[:300]
        except Exception:
            pass
        raise PesapalError("Pesapal answered %s %s" % (e.code, detail))
    except Exception as e:
        raise PesapalError("Could not reach Pesapal: %s" % e)
    err = d.get("error") if isinstance(d, dict) else None
    if isinstance(err, dict) and (err.get("code") or err.get("message")):
        raise PesapalError("Pesapal error: %s %s" % (err.get("code") or "", err.get("message") or ""))
    return d


def pp_token():
    with _pp_lock:
        if _pp["token"] and _pp["exp"] > time.time() + 20:
            return _pp["token"]
    d = pp_request("POST", "/api/Auth/RequestToken", {"consumer_key": PESAPAL_KEY, "consumer_secret": PESAPAL_SECRET})
    tok = d.get("token")
    if not tok:
        raise PesapalError("Pesapal did not give a token. Check the consumer key and secret. %s" % (d.get("message") or ""))
    with _pp_lock:
        _pp["token"], _pp["exp"] = tok, time.time() + 240  # tokens last 5 minutes
    return tok


def ipn_url():
    return "https://%s/api/pesapal/ipn" % SITE_DOMAIN


def pp_ipn_id():
    """Register our notification address with Pesapal once, and remember its id."""
    key = "pesapal_ipn:%s:%s" % (PESAPAL_ENV, ipn_url())
    v = meta_get(key)
    if v:
        return v
    d = pp_request("POST", "/api/URLSetup/RegisterIPN", {"url": ipn_url(), "ipn_notification_type": "GET"}, pp_token())
    v = d.get("ipn_id")
    if not v:
        raise PesapalError("Pesapal did not register the notification address. %s" % (d.get("message") or ""))
    meta_set(key, v)
    return v


def credit_payment(ref, method, code):
    """Mark a payment paid (once) and add its days to the player's pass. Returns True the first time."""
    t = now()

    def run(db):
        p = db.execute("SELECT * FROM payments WHERE ref=?", (ref,)).fetchone()
        if not p or p["status"] == "paid":
            return False
        db.execute("UPDATE payments SET status='paid', method=?, code=?, updated=? WHERE ref=?", (method[:40], code[:60], t, ref))
        s = db.execute("SELECT paid_until FROM subs WHERE user_id=?", (p["user_id"],)).fetchone()
        start = max(t, s["paid_until"] if s else 0)
        db.execute("INSERT INTO subs(user_id,paid_until,plan,updated) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                   "paid_until=excluded.paid_until, plan=excluded.plan, updated=excluded.updated",
                   (p["user_id"], start + p["days"] * 86400, p["plan"], t))
        st = db.execute("SELECT games FROM stats WHERE user_id=?", (p["user_id"],)).fetchone()
        db.execute("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'account',?)",
                   (p["user_id"], t, st["games"] if st else 1, "Bought the %s (KSh %s%s)" % (
                       PLANS.get(p["plan"], {}).get("name", p["plan"]).lower(), "{:,.0f}".format(p["amount"]),
                       " via " + method if method else "")))
        return True
    return tx(run)


def reverse_payment(ref):
    t = now()

    def run(db):
        p = db.execute("SELECT * FROM payments WHERE ref=?", (ref,)).fetchone()
        if not p or p["status"] != "paid":
            return
        db.execute("UPDATE payments SET status='reversed', updated=? WHERE ref=?", (t, ref))
        db.execute("UPDATE subs SET paid_until=MAX(0, paid_until-?), updated=? WHERE user_id=?", (p["days"] * 86400, t, p["user_id"]))
        db.execute("INSERT INTO events(user_id,ts,kind,text) VALUES(?,?,'account',?)", (p["user_id"], t, "A pass payment was reversed"))
    tx(run)


def check_payment(ref):
    """Ask Pesapal how a payment went and record the answer. Returns the payment's status."""
    p = q("SELECT * FROM payments WHERE ref=?", (ref,), one=True)
    if not p:
        return None
    if p["status"] == "paid" or not p["tracking"] or not pesapal_ready():
        return p["status"]
    d = pp_request("GET", "/api/Transactions/GetTransactionStatus?orderTrackingId=" + urllib.parse.quote(p["tracking"]), None, pp_token())
    code = d.get("status_code")
    try:
        code = int(code)
    except (TypeError, ValueError):
        code = 0
    if code == 1:
        if (str(d.get("merchant_reference") or "") != ref or str(d.get("currency") or "").upper() != p["currency"]
                or abs(num(d.get("amount")) - p["amount"]) > 0.5):
            print("Payment %s does not match what was ordered: %s" % (ref, json.dumps(d)[:300]), flush=True)
            q("UPDATE payments SET status='mismatch', updated=? WHERE ref=?", (now(), ref))
            return "mismatch"
        credit_payment(ref, clean_text(d.get("payment_method"), 40), clean_text(d.get("confirmation_code"), 60))
        return "paid"
    if code == 3:
        reverse_payment(ref)
        return "reversed"
    if code == 2:
        q("UPDATE payments SET status='failed', updated=? WHERE ref=? AND status='pending'", (now(), ref))
        return "failed"
    return p["status"]


def payment_sweeper():
    """Every few minutes, re-check recent unpaid orders, in case a notification from Pesapal went missing."""
    while True:
        time.sleep(300)
        if not (BILLING_ON and pesapal_ready()):
            continue
        t = now()
        for r in q("SELECT ref FROM payments WHERE status IN ('pending','failed') AND tracking<>'' AND created>? AND created<? "
                   "ORDER BY id DESC LIMIT 30", (t - 2 * 86400, t - 60)):
            try:
                check_payment(r["ref"])
            except Exception as e:
                print("Payment check for %s failed: %s" % (r["ref"], e), flush=True)


def billing_overview(t):
    if not BILLING_ON:
        return {"on": False, "ready": pesapal_ready(), "env": PESAPAL_ENV}
    bs = billing_start()
    users = q("SELECT u.id,u.created,s.paid_until,s.gifts,s.gift_until,s.paywall_at,s.later,s.checkouts FROM users u "
              "LEFT JOIN subs s ON s.user_id=u.id WHERE u.disabled=0")
    k = {"trial": 0, "bonus": 0, "paid": 0, "locked": 0, "lapsed": 0, "reachedPaywall": 0, "tappedLater": 0,
         "startedCheckout": 0, "gift1": 0, "gift2": 0, "everPaid": 0, "hardBlocked": 0}
    for u in users:
        base = max(u["created"], bs)
        pu = u["paid_until"] or 0
        if pu > t:
            k["paid"] += 1
        elif t < base + TRIAL_HOURS * 3600:
            k["trial"] += 1
        elif (u["gift_until"] or 0) > t:
            k["bonus"] += 1
        else:
            k["locked"] += 1
            if pu:
                k["lapsed"] += 1
            elif t >= base + BLOCK_DAYS * 86400 or (u["gifts"] or 0) >= GIFTS:
                k["hardBlocked"] += 1
        if u["paywall_at"]:
            k["reachedPaywall"] += 1
        if u["later"]:
            k["tappedLater"] += 1
        if u["checkouts"]:
            k["startedCheckout"] += 1
        if (u["gifts"] or 0) >= 1:
            k["gift1"] += 1
        if (u["gifts"] or 0) >= 2:
            k["gift2"] += 1
        if pu:
            k["everPaid"] += 1
    rev = lambda since: q("SELECT COALESCE(SUM(amount),0) a, COUNT(*) c FROM payments WHERE status='paid' AND updated>?", (since,), one=True)
    r30, rall = rev(t - 30 * 86400), rev(0)
    k.update(on=True, ready=pesapal_ready(), env=PESAPAL_ENV, since=bs, rev30=r30["a"], pay30=r30["c"], revAll=rall["a"], payAll=rall["c"],
             byPlan={r["plan"]: r["c"] for r in q("SELECT plan, COUNT(*) c FROM payments WHERE status='paid' AND updated>? GROUP BY plan", (t - 30 * 86400,))},
             trialHours=TRIAL_HOURS, giftDays=GIFT_DAYS, gifts=GIFTS, blockDays=BLOCK_DAYS, plans=plans_public())
    return k


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
    def moved(self, path):
        """Pages on an old web address forward to the new one. The API keeps answering there, so open games,
        payment notifications and returns from Pesapal never break."""
        host = (self.headers.get("Host") or "").split(":")[0].strip().lower()
        if not (SITE_DOMAIN and host in OLD_DOMAINS) or path.startswith("/api/"):
            return False
        self.send_response(301)
        self.send_header("Location", "https://%s%s" % (SITE_DOMAIN, self.path if self.path.startswith("/") else "/"))
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return True

    def do_GET(self):
        path = urlparse(self.path).path
        if self.moved(path):
            return
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
        if path == "/api/lives":
            return self.api_lives()
        if path == "/api/season":
            return self.api_season()
        if path == "/api/config":
            return self.send_json(200, {"mail": mail_ready()})
        if path == "/api/billing":
            return self.api_billing()
        if path == "/api/pesapal/ipn":
            return self.api_pesapal_ipn()
        if path.startswith("/api/admin/"):
            return self.api_admin_get(path)
        if path.startswith("/api/"):
            return self.error(404, "Not found.")
        return self.serve_file(path.lstrip("/"))

    def do_POST(self):
        path = urlparse(self.path).path
        routes = {"/api/signup": self.api_signup, "/api/login": self.api_login, "/api/logout": self.api_logout,
                  "/api/forgot": self.api_forgot, "/api/reset": self.api_reset, "/api/email": self.api_email,
                  "/api/admin/login": self.api_admin_login, "/api/admin/logout": self.api_admin_logout,
                  "/api/billing/checkout": self.api_checkout, "/api/billing/confirm": self.api_confirm,
                  "/api/billing/later": self.api_later, "/api/billing/gift": self.api_gift}
        if path in routes:
            return routes[path]()
        m = re.match(r"^/api/admin/player/(\d+)/(disable|enable|reset|delete|password|gift)$", path)
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
        email = clean_email(d.get("email"))
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
        if not email:
            return self.error(400, "Enter a valid email address. It's how you reset your password.")
        if q("SELECT 1 FROM users WHERE username=?", (username,), one=True):
            return self.error(409, "That username is taken. Try another.")
        salt, digest = hash_password(password)
        t = now()
        token = secrets.token_urlsafe(32)

        def create(db):
            cur = db.execute("INSERT INTO users(username,pw_salt,pw_hash,name,company,town,bg,color,created,last_seen,logins,email) "
                             "VALUES(?,?,?,?,?,?,?,?,?,?,1,?)", (username, salt, digest, name, company, town, bg, color, t, t, email))
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
        self.send_json(201, {"user": user_public(user), "save": None, "bill": bill_status(user)},
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
        self.send_json(200, {"user": user_public(user), "save": json.loads(save["state"]) if save else None,
                             "bill": bill_status(user, True)},
                       [self.make_cookie("hs", token, PLAYER_SESSION_SECONDS)])

    def api_logout(self):
        token = self.cookie("hs")
        if token:
            q("DELETE FROM sessions WHERE token=?", (token,))
        self.send_json(200, {"ok": True}, [self.make_cookie("hs", "", 0)])

    def api_email(self):
        """A logged-in player adds or changes their email. Needs their current password."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        if rate_limited("email:%d" % user["id"], limit=10, window=3600):
            return self.error(429, "Too many changes. Try again later.")
        d = self.read_json()
        if d is None:
            return
        email = clean_email(d.get("email"))
        password = d.get("password") if isinstance(d.get("password"), str) else ""
        if not email:
            return self.error(400, "Enter a valid email address.")
        _, digest = hash_password(password, user["pw_salt"])
        if not hmac.compare_digest(digest, user["pw_hash"]):
            return self.error(401, "That password isn't right.")
        q("UPDATE users SET email=? WHERE id=?", (email, user["id"]))
        q("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'account',?)",
          (user["id"], now(), self.current_game(user["id"]), "Updated their email" if user["email"] else "Added an email"))
        user = q("SELECT * FROM users WHERE id=?", (user["id"],), one=True)
        self.send_json(200, {"user": user_public(user)})

    def api_forgot(self):
        """Email a one-time reset link. Always answers the same way, so it never reveals who has an account."""
        if not mail_ready():
            return self.error(503, "Password reset by email isn't switched on yet. Ask the game's host to reset your password.")
        if rate_limited("forgot:" + self.client_ip(), limit=5, window=3600):
            return self.error(429, "Too many requests. Wait an hour and try again.")
        d = self.read_json()
        if d is None:
            return
        who = clean_text(d.get("who"), 120).lower()
        done = {"ok": True, "message": "If an account matches, we've emailed a reset link to its address. It expires in 1 hour. "
                                       "Check your spam folder too."}
        if not who:
            return self.error(400, "Enter your username or email.")
        if "@" in who:
            rows = q("SELECT * FROM users WHERE email=? AND disabled=0", (who,))
        else:
            rows = q("SELECT * FROM users WHERE username=? AND disabled=0 AND email<>''", (who,))
        rows = [r for r in rows if not rate_limited("forgot-user:%d" % r["id"], limit=3, window=3600)]
        if not rows:
            return self.send_json(200, done)
        t = now()
        by_email = {}
        for r in rows:
            token = secrets.token_urlsafe(32)
            q("INSERT INTO resets(token_hash,user_id,created,expires) VALUES(?,?,?,?)",
              (hashlib.sha256(token.encode()).hexdigest(), r["id"], t, t + RESET_SECONDS))
            q("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'account','Asked for a password reset email')",
              (r["id"], t, self.current_game(r["id"])))
            link = "https://%s/?reset=%s" % (SITE_DOMAIN or "localhost", token)
            by_email.setdefault(r["email"], []).append((r["username"], r["name"], link))
        q("DELETE FROM resets WHERE expires<?", (t - 86400,))
        for email, accounts in by_email.items():
            threading.Thread(target=send_reset_emails, args=(email, accounts), daemon=True).start()
        self.send_json(200, done)

    def api_reset(self):
        """Set a new password with a token from a reset email, then log the player in."""
        if rate_limited("reset:" + self.client_ip(), limit=10, window=3600):
            return self.error(429, "Too many attempts. Wait an hour and try again.")
        d = self.read_json()
        if d is None:
            return
        token = d.get("token") if isinstance(d.get("token"), str) else ""
        password = d.get("password") if isinstance(d.get("password"), str) else ""
        if len(password) < 8 or len(password) > 128:
            return self.error(400, "Passwords need at least 8 characters.")
        t = now()
        row = q("SELECT * FROM resets WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),), one=True)
        if not row or row["used"] or row["expires"] < t:
            return self.error(400, "This reset link has expired or was already used. Ask for a new one.")
        user = q("SELECT * FROM users WHERE id=?", (row["user_id"],), one=True)
        if not user or user["disabled"]:
            return self.error(403, "This account can't be reset. Contact the game's host.")
        salt, digest = hash_password(password)
        session = secrets.token_urlsafe(32)
        game = self.current_game(user["id"])  # read before the transaction takes the lock

        def apply(db):
            db.execute("UPDATE users SET pw_salt=?, pw_hash=?, logins=logins+1 WHERE id=?", (salt, digest, user["id"]))
            db.execute("UPDATE resets SET used=1 WHERE user_id=?", (user["id"],))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            db.execute("INSERT INTO sessions(token,user_id,is_admin,created,expires) VALUES(?,?,0,?,?)",
                       (session, user["id"], t, t + PLAYER_SESSION_SECONDS))
            db.execute("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'account','Reset their password by email')",
                       (user["id"], t, game))
        tx(apply)
        self.touch(user["id"])
        save = q("SELECT state FROM saves WHERE user_id=?", (user["id"],), one=True)
        self.send_json(200, {"user": user_public(user), "save": json.loads(save["state"]) if save else None,
                             "bill": bill_status(user, True)},
                       [self.make_cookie("hs", session, PLAYER_SESSION_SECONDS)])

    def api_me(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Not logged in.")
        self.touch(user["id"])
        save = q("SELECT state FROM saves WHERE user_id=?", (user["id"],), one=True)
        self.send_json(200, {"user": user_public(user), "save": json.loads(save["state"]) if save else None,
                             "bill": bill_status(user, True)})

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
        if BILLING_ON and not can_play(user):
            return self.send_json(402, {"error": "Your free time is up. Get the Hustle Pass to keep building your empire.",
                                        "bill": bill_status(user, True)})
        state_text = json.dumps(state, separators=(",", ":"))
        if len(state_text) > MAX_STATE:
            return self.error(413, "This saved game is too large.")
        uid = user["id"]
        t = now()
        month = int(num(summary.get("month")))
        nw = num(summary.get("nw"))
        new_game = bool(summary.get("newGame"))
        detail_keys = ("industries", "units", "properties", "teams", "happiness", "reputation", "influence",
                       "debt", "married", "kids", "age", "tab", "race", "foundation", "cities", "gender", "spouse", "health", "died", "streak", "region", "currency", "gen")
        detail = {k: summary.get(k) for k in detail_keys if isinstance(summary.get(k), (int, float, str, bool))}
        detail = {k: (clean_text(v, 40) if isinstance(v, str) else v) for k, v in detail.items()}

        def write(db):
            st = db.execute("SELECT * FROM stats WHERE user_id=?", (uid,)).fetchone()
            game = st["games"] if st else 1
            prev_month = st["month"] if st else 0
            if new_game:
                if st is not None and st["month"] > 0 or isinstance(summary.get("prev"), dict):
                    life = clean_life(summary.get("prev")) or life_from_records(db, uid, game, st)
                    life.setdefault("ts", t * 1000)
                    db.execute("INSERT OR IGNORE INTO lives(user_id,game,ended,data) VALUES(?,?,?,?)",
                               (uid, game, t, json.dumps(life)))
                game += 1
                db.execute("DELETE FROM snapshots WHERE user_id=? AND game<?", (uid, game - 3))
                db.execute("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'game','Started a new game')", (uid, t, game))
                prev_month = 0
            played = max(0, month - prev_month) if not new_game else month
            best = max(st["best"] if st and not new_game else 0, nw)
            billion = st["billion_month"] if st and not new_game else None
            if billion is None and summary.get("won") and num(summary.get("gen"), 1) <= 1:
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
            sea = summary.get("season")
            if isinstance(sea, dict) and season_ok(sea.get("id")):
                pts = int(max(0, min(1e7, num(sea.get("pts")))))
                region = clean_text(summary.get("region"), 3).upper()
                db.execute("INSERT INTO season_scores(user_id,season,pts,region,updated) VALUES(?,?,?,?,?) "
                           "ON CONFLICT(user_id,season) DO UPDATE SET pts=MAX(season_scores.pts,excluded.pts), "
                           "region=excluded.region, updated=excluded.updated", (uid, sea["id"], pts, region, t))
            return game

        game = tx(write)
        self.touch(uid)
        self.send_json(200, {"ok": True, "game": game})

    # ---------- Hustle Pass ----------
    def api_billing(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        self.send_json(200, {"bill": bill_status(user, True)})

    def api_later(self):
        """The player closed the payment screen without paying. Counted, so the admin can see who drops off."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        if self.read_json() is None:
            return
        t = now()
        q("INSERT INTO subs(user_id,later,updated) VALUES(?,1,?) ON CONFLICT(user_id) DO UPDATE SET later=subs.later+1, updated=excluded.updated",
          (user["id"], t))
        self.send_json(200, {"bill": bill_status(user, True)})

    def api_gift(self):
        """A player who left the payment screen takes the offer of a few more free days."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        if self.read_json() is None:
            return
        b = bill_status(user)
        if b["state"] != "locked" or not b.get("gift"):
            return self.send_json(409, {"error": "That offer isn't available any more.", "bill": b})
        t = now()
        base = max(user["created"], billing_start())
        until = min(t + GIFT_DAYS * 86400, base + BLOCK_DAYS * 86400)
        q("INSERT INTO subs(user_id,gifts,gift_until,updated) VALUES(?,1,?,?) ON CONFLICT(user_id) DO UPDATE SET "
          "gifts=subs.gifts+1, gift_until=excluded.gift_until, updated=excluded.updated", (user["id"], until, t))
        q("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'account',?)",
          (user["id"], t, self.current_game(user["id"]), "Took %d more free days (offer %d of %d)" % (GIFT_DAYS, b.get("giftsUsed", 0) + 1, GIFTS)))
        self.send_json(200, {"bill": bill_status(user)})

    def api_checkout(self):
        """Start a Pesapal payment for a pass. Returns the Pesapal page to send the player to."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        if not BILLING_ON or not pesapal_ready():
            return self.error(503, "Payments aren't switched on yet. Please try again later.")
        if rate_limited("checkout:%d" % user["id"], limit=12, window=3600):
            return self.error(429, "Too many payment attempts. Wait a few minutes and try again.")
        d = self.read_json()
        if d is None:
            return
        plan = d.get("plan") if d.get("plan") in PLANS else None
        if not plan:
            return self.error(400, "Choose a pass.")
        if not user["email"]:
            return self.error(400, "Add your email first (in your account menu). Pesapal sends your receipt there.")
        p = PLANS[plan]
        t = now()
        ref = "HS%d-%s" % (user["id"], secrets.token_hex(4).upper())
        q("INSERT INTO payments(ref,user_id,plan,days,amount,currency,created,updated) VALUES(?,?,?,?,?,?,?,?)",
          (ref, user["id"], plan, p["days"], float(p["kes"]), "KES", t, t))
        q("INSERT INTO subs(user_id,checkouts,updated) VALUES(?,1,?) ON CONFLICT(user_id) DO UPDATE SET checkouts=subs.checkouts+1, updated=excluded.updated",
          (user["id"], t))
        names = (user["name"] or "Player").split()
        body = {"id": ref, "currency": "KES", "amount": float(p["kes"]),
                "description": "Hustle to an Empire - %s" % p["name"],
                "callback_url": "https://%s/?paid=%s" % (SITE_DOMAIN, ref),
                "cancellation_url": "https://%s/?paid=%s&cancelled=1" % (SITE_DOMAIN, ref),
                "notification_id": "", "redirect_mode": "TOP_WINDOW",
                "billing_address": {"email_address": user["email"], "first_name": names[0][:50],
                                    "last_name": " ".join(names[1:])[:50]}}
        try:
            body["notification_id"] = pp_ipn_id()
            r = pp_request("POST", "/api/Transactions/SubmitOrderRequest", body, pp_token())
        except PesapalError as e:
            print("Checkout for %s failed: %s" % (ref, e), flush=True)
            q("UPDATE payments SET status='error', updated=? WHERE ref=?", (now(), ref))
            return self.error(502, "We couldn't open the payment page just now. Please try again in a minute.")
        url, tracking = r.get("redirect_url"), r.get("order_tracking_id")
        if not url or not tracking:
            q("UPDATE payments SET status='error', updated=? WHERE ref=?", (now(), ref))
            return self.error(502, "We couldn't open the payment page just now. Please try again in a minute.")
        q("UPDATE payments SET tracking=?, updated=? WHERE ref=?", (tracking, now(), ref))
        q("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'account',?)",
          (user["id"], t, self.current_game(user["id"]), "Opened the payment page for the %s" % p["name"].lower()))
        self.send_json(200, {"url": url, "ref": ref})

    def api_confirm(self):
        """The player came back from Pesapal. Check how the payment went."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        d = self.read_json()
        if d is None:
            return
        ref = clean_text(d.get("ref"), 60)
        p = q("SELECT * FROM payments WHERE ref=? AND user_id=?", (ref, user["id"]), one=True)
        if not p:
            return self.error(404, "We can't find that payment.")
        status = p["status"]
        try:
            status = check_payment(ref)
        except PesapalError as e:
            print("Confirm %s: %s" % (ref, e), flush=True)
        p = q("SELECT plan,days,amount,status,method FROM payments WHERE ref=?", (ref,), one=True)
        self.send_json(200, {"payment": dict(p), "bill": bill_status(user)})

    def api_pesapal_ipn(self):
        """Pesapal tells us a payment changed. We never trust the message itself: we ask Pesapal for the status."""
        qs = parse_qs(urlparse(self.path).query)
        tracking = (qs.get("OrderTrackingId") or [""])[0][:80]
        ref = (qs.get("OrderMerchantReference") or [""])[0][:60]
        kind = (qs.get("OrderNotificationType") or [""])[0][:30]
        status = 200
        p = q("SELECT * FROM payments WHERE ref=?", (ref,), one=True)
        if p and (not p["tracking"] or p["tracking"] == tracking):
            if not p["tracking"] and tracking:
                q("UPDATE payments SET tracking=? WHERE ref=?", (tracking, ref))
            try:
                check_payment(ref)
            except PesapalError as e:
                print("IPN %s: %s" % (ref, e), flush=True)
                status = 500
        self.send_json(200, {"orderNotificationType": kind, "orderTrackingId": tracking,
                             "orderMerchantReference": ref, "status": status})

    def api_lives(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Log in to see your past lives.")
        rows = q("SELECT game, ended, data FROM lives WHERE user_id=? ORDER BY game DESC LIMIT 50", (user["id"],))
        out = []
        for r in rows:
            try:
                d = json.loads(r["data"])
            except ValueError:
                continue
            d["n"] = r["game"]
            d.setdefault("ts", r["ended"] * 1000)
            out.append(d)
        self.send_json(200, {"lives": out})

    def api_season(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Log in to see the season.")
        uid = user["id"]
        qs = parse_qs(urlparse(self.path).query)
        sid = season_now()
        mine = q("SELECT pts, region FROM season_scores WHERE user_id=? AND season=?", (uid, sid), one=True)
        region = (qs.get("region", [""])[0] or (mine["region"] if mine else "")).upper()[:3]
        scope = qs.get("scope", ["world"])[0]
        where, args = ("s.season=? AND s.region=?", (sid, region)) if scope == "country" and region else ("s.season=?", (sid,))
        top = q("SELECT u.name,u.company,u.color,s.pts,s.region FROM season_scores s JOIN users u ON u.id=s.user_id "
                "WHERE u.disabled=0 AND s.pts>0 AND " + where + " ORDER BY s.pts DESC, s.updated LIMIT 25", args)

        def ranks(season, pts, reg):
            w = q("SELECT COUNT(*) c FROM season_scores WHERE season=? AND pts>?", (season, pts), one=True)["c"] + 1
            wn = q("SELECT COUNT(*) c FROM season_scores WHERE season=? AND pts>0", (season,), one=True)["c"]
            r = q("SELECT COUNT(*) c FROM season_scores WHERE season=? AND region=? AND pts>?", (season, reg, pts), one=True)["c"] + 1
            rn = q("SELECT COUNT(*) c FROM season_scores WHERE season=? AND region=? AND pts>0", (season, reg), one=True)["c"]
            return {"rank": w, "players": wn, "rankRegion": r, "playersRegion": rn}

        me = dict(pts=mine["pts"], region=mine["region"], **ranks(sid, mine["pts"], mine["region"])) if mine and mine["pts"] > 0 else None
        hist = []
        for h in q("SELECT season, pts, region FROM season_scores WHERE user_id=? AND season<>? AND pts>0 "
                   "ORDER BY season DESC LIMIT 24", (uid, sid)):
            hist.append(dict(season=h["season"], pts=h["pts"], region=h["region"], **ranks(h["season"], h["pts"], h["region"])))
        self.send_json(200, {"season": sid, "scope": scope, "region": region, "top": [dict(r) for r in top],
                             "me": me, "history": hist})

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
        if path == "/api/admin/payments":
            rows = q("SELECT p.ref,p.plan,p.amount,p.currency,p.status,p.method,p.code,p.created,p.updated,p.user_id,u.name,u.username,u.color "
                     "FROM payments p LEFT JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT 200")
            return self.send_json(200, {"payments": [dict(r) for r in rows], "now": now()})
        if path == "/api/admin/players":
            rows = q("SELECT u.id,u.username,u.name,u.company,u.town,u.bg,u.color,u.created,u.last_seen,u.logins,u.disabled,u.email,"
                     "s.nw,s.best,s.cash,s.month,s.rank,s.billion_month,s.bankrupt,s.games,s.months_played,s.detail,"
                     "(SELECT COUNT(*) FROM activity_days a WHERE a.user_id=u.id) AS days_active "
                     "FROM users u LEFT JOIN stats s ON s.user_id=u.id ORDER BY u.last_seen DESC")
            players = []
            for r in rows:
                p = dict(r)
                p["detail"] = json.loads(p["detail"] or "{}")
                b = bill_status(r)
                p["pass"] = {"state": b["state"], "until": b.get("until", 0), "plan": b.get("plan", "")}
                players.append(p)
            return self.send_json(200, {"players": players, "now": now()})
        m = re.match(r"^/api/admin/player/(\d+)$", path)
        if m:
            uid = int(m.group(1))
            u = q("SELECT id,username,name,company,town,bg,color,created,last_seen,logins,disabled,email FROM users WHERE id=?", (uid,), one=True)
            if not u:
                return self.error(404, "No such player.")
            st = q("SELECT * FROM stats WHERE user_id=?", (uid,), one=True)
            game = st["games"] if st else 1
            snaps = q("SELECT month,nw FROM snapshots WHERE user_id=? AND game=? ORDER BY month", (uid, game))
            evs = q("SELECT ts,game_month,kind,text FROM events WHERE user_id=? ORDER BY id DESC LIMIT 200", (uid,))
            stats = dict(st) if st else {}
            if stats:
                stats["detail"] = json.loads(stats.get("detail") or "{}")
            b = bill_status(q("SELECT * FROM users WHERE id=?", (uid,), one=True))
            pays = q("SELECT ref,plan,amount,status,method,created FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 20", (uid,))
            return self.send_json(200, {"user": dict(u), "stats": stats, "snapshots": [dict(s) for s in snaps],
                                        "events": [dict(e) for e in evs], "now": now(),
                                        "pass": {"state": b["state"], "until": b.get("until", 0), "plan": b.get("plan", "")},
                                        "payments": [dict(p) for p in pays]})
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
        k["retention"] = retention(t)
        k["billing"] = billing_overview(t)
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
        body = self.read_json()
        if body is None:
            return
        t = now()
        if action == "password":
            password = body.get("password") if isinstance(body.get("password"), str) else ""
            if len(password) < 8 or len(password) > 128:
                return self.error(400, "The new password needs at least 8 characters.")
            salt, digest = hash_password(password)

            def setpw(db):
                db.execute("UPDATE users SET pw_salt=?, pw_hash=? WHERE id=?", (salt, digest, uid))
                db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
                db.execute("INSERT INTO events(user_id,ts,kind,text) VALUES(?,?,'admin','Password changed by the host')", (uid, t))
            tx(setpw)
            return self.send_json(200, {"ok": True})
        if action == "gift":
            try:
                days = int(body.get("days"))
            except (TypeError, ValueError):
                days = 0
            if days < 1 or days > 3660:
                return self.error(400, "Give between 1 and 3660 days.")
            s = sub_row(uid)
            start = max(t, s["paid_until"] if s else 0)
            q("INSERT INTO subs(user_id,paid_until,plan,updated) VALUES(?,?,'gift',?) ON CONFLICT(user_id) DO UPDATE SET "
              "paid_until=excluded.paid_until, plan=CASE WHEN subs.paid_until>? AND subs.plan<>'' THEN subs.plan ELSE 'gift' END, "
              "updated=excluded.updated", (uid, start + days * 86400, t, t))
            q("INSERT INTO events(user_id,ts,kind,text) VALUES(?,?,'admin',?)", (uid, t, "The host gave %d free pass day%s" % (days, "" if days == 1 else "s")))
            return self.send_json(200, {"ok": True})
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
                for table in ("sessions", "saves", "stats", "events", "snapshots", "activity_days", "resets", "subs", "lives", "season_scores"):
                    db.execute("DELETE FROM %s WHERE user_id=?" % table, (uid,))
                db.execute("DELETE FROM users WHERE id=?", (uid,))
            tx(delete)
        self.send_json(200, {"ok": True})


def main():
    if not ADMIN_PASSWORD or len(ADMIN_PASSWORD) < 10:
        print("Note: admin dashboard is off. Set HUSTLE_ADMIN_PASSWORD (10+ characters) to turn it on.", flush=True)
    if OLD_DOMAINS and SITE_DOMAIN:
        print("Web address: %s (forwarding %s)" % (SITE_DOMAIN, ", ".join(sorted(OLD_DOMAINS))), flush=True)
    print("Password reset emails: %s" % ("on (%s, from %s)" % (MAIL_PROVIDER, MAIL_FROM or "log") if mail_ready() else "off"), flush=True)
    if BILLING_ON:
        print("Hustle Pass: on (start %s, %dh trial, %d x %d gift days, blocked after %d days). Pesapal %s: %s" % (
            time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(billing_start())), TRIAL_HOURS, GIFTS, GIFT_DAYS, BLOCK_DAYS,
            PESAPAL_ENV, "ready" if pesapal_ready() else "NOT SET (add the key, secret and site domain)"), flush=True)
    else:
        print("Hustle Pass: off (everyone plays free). Set HUSTLE_BILLING=1 to turn it on.", flush=True)
    threading.Thread(target=payment_sweeper, daemon=True).start()
    try:
        backfill_lives()
    except Exception as e:  # never stop the game starting over this
        print("Past lives backfill skipped: %s" % e, flush=True)
    ThreadingHTTPServer.request_queue_size = 512
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print("Hustle to an Empire is running on http://%s:%d" % (HOST, PORT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
