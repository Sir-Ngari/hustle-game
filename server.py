#!/usr/bin/env python3
"""Hustlempires - game server.

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
  HUSTLE_BILLING          no longer used: the Hustle Pass was retired, the game is free, and players can tip instead
  HUSTLE_PESAPAL_KEY / HUSTLE_PESAPAL_SECRET   the consumer key and secret from your Pesapal account
  HUSTLE_PESAPAL_ENV      "live" (default) or "sandbox" for Pesapal's test system
  HUSTLE_TRIAL_HOURS / HUSTLE_GIFT_DAYS / HUSTLE_GIFTS / HUSTLE_BLOCK_DAYS   trial length and the "more free days" offers
  HUSTLE_PRICE_WEEK / HUSTLE_PRICE_MONTH / HUSTLE_PRICE_YEAR   pass prices in Kenya shillings (70 / 250 / 2000)
"""
import base64
import calendar
import datetime
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
# The Hustle Pass was retired: the game is free for everyone, and players can tip the developers instead.
BILLING_ON = False
# Meta (Facebook and Instagram) ads: read-only ad results, pulled every hour into the admin Marketing tab
META_TOKEN = os.environ.get("HUSTLE_META_TOKEN", "").strip()
META_ACCOUNT = re.sub(r"[^0-9]", "", os.environ.get("HUSTLE_META_ACCOUNT", ""))
META_APP_SECRET = os.environ.get("HUSTLE_META_APP_SECRET", "").strip()
META_API = os.environ.get("HUSTLE_META_API", "v25.0").strip() or "v25.0"
META_URL = os.environ.get("HUSTLE_META_URL", "https://graph.facebook.com").strip().rstrip("/")
META_PAGE = re.sub(r"[^0-9]", "", os.environ.get("HUSTLE_META_PAGE", ""))   # optional: which Facebook Page to post to
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(os.environ.get("HUSTLE_DB", "") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hustle.db"))), "media")
PESAPAL_KEY = os.environ.get("HUSTLE_PESAPAL_KEY", "").strip()
PESAPAL_SECRET = os.environ.get("HUSTLE_PESAPAL_SECRET", "").strip()
PESAPAL_ENV = "sandbox" if os.environ.get("HUSTLE_PESAPAL_ENV", "").strip().lower() == "sandbox" else "live"
PESAPAL_URL = (os.environ.get("HUSTLE_PESAPAL_URL", "").strip().rstrip("/") or
               ("https://cybqa.pesapal.com/pesapalv3" if PESAPAL_ENV == "sandbox" else "https://pay.pesapal.com/v3"))
TRIAL_HOURS = env_int("HUSTLE_TRIAL_HOURS", 24)   # free trial from sign-up (or from the day billing was switched on)
GIFT_DAYS = env_int("HUSTLE_GIFT_DAYS", 2)        # extra free days offered to a player who leaves the payment screen
GIFTS = env_int("HUSTLE_GIFTS", 2)                # how many times that offer is made
BLOCK_DAYS = env_int("HUSTLE_BLOCK_DAYS", 7)      # after this many days, no more free time: pay to play
REF_TRIAL_DAYS = env_int("HUSTLE_REF_TRIAL_DAYS", 3)    # free days for a player who joins with a friend's link
REF_ACTIVE_DAYS = env_int("HUSTLE_REF_ACTIVE_DAYS", 3)  # pass days the inviter earns when that friend comes back on a 2nd day
REF_PAID_DAYS = env_int("HUSTLE_REF_PAID_DAYS", 7)      # pass days the inviter earns when that friend first buys a pass
REF_MONTHLY_CAP = env_int("HUSTLE_REF_MONTHLY_CAP", 10) # most "came back" rewards one inviter can earn in 30 days
PLANS = {
    "week": {"name": "Weekly pass", "days": 7, "kes": env_int("HUSTLE_PRICE_WEEK", 70)},
    "month": {"name": "Monthly pass", "days": 30, "kes": env_int("HUSTLE_PRICE_MONTH", 250)},
    "year": {"name": "Yearly pass", "days": 365, "kes": env_int("HUSTLE_PRICE_YEAR", 2000)},
}
TIP_AMOUNTS = [50, 100, 250, 500, 1000]   # the suggested tips, in KSh
TIP_MIN, TIP_MAX = 20, 100000

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
CREATE TABLE IF NOT EXISTS lifeboard(
  user_id INTEGER NOT NULL,
  game INTEGER NOT NULL,
  gen INTEGER NOT NULL DEFAULT 1,
  who TEXT NOT NULL DEFAULT '',
  region TEXT NOT NULL DEFAULT '',
  best REAL NOT NULL DEFAULT 0,
  ms_m INTEGER,
  ms_b INTEGER,
  ms_t INTEGER,
  ms_q INTEGER,
  updated INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(user_id, game)
);
CREATE INDEX IF NOT EXISTS lifeboard_gen ON lifeboard(gen, best);
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
CREATE TABLE IF NOT EXISTS referrals(
  user_id INTEGER PRIMARY KEY,
  inviter_id INTEGER NOT NULL,
  created INTEGER NOT NULL,
  active_at INTEGER NOT NULL DEFAULT 0,
  paid_at INTEGER NOT NULL DEFAULT 0,
  days_given INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS referrals_inviter ON referrals(inviter_id);
CREATE TABLE IF NOT EXISTS visitors(
  vid TEXT PRIMARY KEY,
  first INTEGER NOT NULL,
  last INTEGER NOT NULL,
  visits INTEGER NOT NULL DEFAULT 1,
  stage TEXT NOT NULL DEFAULT 'landed',
  user_id INTEGER NOT NULL DEFAULT 0,
  src TEXT NOT NULL DEFAULT '',
  device TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS visitors_first ON visitors(first);
CREATE TABLE IF NOT EXISTS meta_daily(
  day TEXT NOT NULL,
  ad_id TEXT NOT NULL,
  campaign_id TEXT NOT NULL DEFAULT '',
  campaign_name TEXT NOT NULL DEFAULT '',
  adset_name TEXT NOT NULL DEFAULT '',
  ad_name TEXT NOT NULL DEFAULT '',
  spend REAL NOT NULL DEFAULT 0,
  impressions INTEGER NOT NULL DEFAULT 0,
  reach INTEGER NOT NULL DEFAULT 0,
  clicks INTEGER NOT NULL DEFAULT 0,
  link_clicks INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(day, ad_id)
);
CREATE INDEX IF NOT EXISTS meta_daily_camp ON meta_daily(campaign_id, day);
CREATE TABLE IF NOT EXISTS meta_ads(
  ad_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  code TEXT NOT NULL DEFAULT '',
  updated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta_adsets(
  adset_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL DEFAULT '',
  onoff TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  daily_budget REAL NOT NULL DEFAULT 0,
  lifetime_budget REAL NOT NULL DEFAULT 0,
  end_time TEXT NOT NULL DEFAULT '',
  updated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta_campaigns(
  campaign_id TEXT PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  code TEXT NOT NULL DEFAULT '',
  manual INTEGER NOT NULL DEFAULT 0,
  updated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS posts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created INTEGER NOT NULL,
  due INTEGER NOT NULL,
  kind TEXT NOT NULL DEFAULT 'photo',
  caption TEXT NOT NULL DEFAULT '',
  media TEXT NOT NULL DEFAULT '',
  link INTEGER NOT NULL DEFAULT 1,
  fb_status TEXT NOT NULL DEFAULT '',
  fb_id TEXT NOT NULL DEFAULT '',
  fb_url TEXT NOT NULL DEFAULT '',
  fb_error TEXT NOT NULL DEFAULT '',
  ig_status TEXT NOT NULL DEFAULT '',
  ig_container TEXT NOT NULL DEFAULT '',
  ig_id TEXT NOT NULL DEFAULT '',
  ig_url TEXT NOT NULL DEFAULT '',
  ig_error TEXT NOT NULL DEFAULT '',
  ig_tries INTEGER NOT NULL DEFAULT 0,
  updated INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS posts_due ON posts(due);
CREATE TABLE IF NOT EXISTS ad_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created INTEGER NOT NULL,
  kind TEXT NOT NULL,
  post_id INTEGER NOT NULL DEFAULT 0,
  name TEXT NOT NULL DEFAULT '',
  caption TEXT NOT NULL DEFAULT '',
  headline TEXT NOT NULL DEFAULT '',
  media TEXT NOT NULL DEFAULT '',
  cta TEXT NOT NULL DEFAULT 'PLAY_GAME',
  countries TEXT NOT NULL DEFAULT 'KE',
  age_min INTEGER NOT NULL DEFAULT 18,
  age_max INTEGER NOT NULL DEFAULT 45,
  platforms TEXT NOT NULL DEFAULT 'all',
  daily_kes INTEGER NOT NULL DEFAULT 0,
  start_ts INTEGER NOT NULL DEFAULT 0,
  end_ts INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'creating',
  campaign_id TEXT NOT NULL DEFAULT '',
  adset_id TEXT NOT NULL DEFAULT '',
  creative_id TEXT NOT NULL DEFAULT '',
  ad_id TEXT NOT NULL DEFAULT '',
  video_id TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  tries INTEGER NOT NULL DEFAULT 0,
  updated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audiences(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  spec TEXT NOT NULL DEFAULT '{}',
  created INTEGER NOT NULL,
  updated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS post_stats(
  post_id INTEGER NOT NULL,
  platform TEXT NOT NULL,
  fetched INTEGER NOT NULL DEFAULT 0,
  data TEXT NOT NULL DEFAULT '{}',
  error TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(post_id, platform)
);
CREATE TABLE IF NOT EXISTS campaigns(
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  channel TEXT NOT NULL DEFAULT 'other',
  cost REAL NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  created INTEGER NOT NULL,
  archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ev_log(
  ts INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  ev TEXT NOT NULL,
  choice INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ev_log_ev ON ev_log(ev, ts);
CREATE INDEX IF NOT EXISTS ev_log_ts ON ev_log(ts);
CREATE TABLE IF NOT EXISTS bank_lots(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seller_id INTEGER NOT NULL,
  region TEXT NOT NULL DEFAULT '',
  data TEXT NOT NULL,
  value REAL NOT NULL,
  price REAL NOT NULL,
  created INTEGER NOT NULL,
  expires INTEGER NOT NULL,
  buyer_id INTEGER NOT NULL DEFAULT 0,
  sold INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS bank_lots_open ON bank_lots(region, sold, expires);
CREATE TABLE IF NOT EXISTS market(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seller_id INTEGER NOT NULL,
  region TEXT NOT NULL DEFAULT '',
  g TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL,
  data TEXT NOT NULL,
  value REAL NOT NULL,
  price REAL NOT NULL,
  created INTEGER NOT NULL,
  expires INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  buyer_id INTEGER NOT NULL DEFAULT 0,
  sold_ts INTEGER NOT NULL DEFAULT 0,
  settled INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS market_open ON market(status, expires);
CREATE INDEX IF NOT EXISTS market_seller ON market(seller_id, status);
CREATE TABLE IF NOT EXISTS xc_list(
  user_id INTEGER PRIMARY KEY,
  float_pct REAL NOT NULL,
  sold REAL NOT NULL DEFAULT 0,
  created INTEGER NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS xc_hold(
  investor_id INTEGER NOT NULL,
  company_id INTEGER NOT NULL,
  shares REAL NOT NULL,
  cost REAL NOT NULL,
  PRIMARY KEY(investor_id, company_id)
);
CREATE INDEX IF NOT EXISTS xc_hold_co ON xc_hold(company_id);
CREATE TABLE IF NOT EXISTS xc_px(
  user_id INTEGER NOT NULL,
  day TEXT NOT NULL,
  px REAL NOT NULL,
  PRIMARY KEY(user_id, day)
);
CREATE TABLE IF NOT EXISTS xc_pay(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  amount REAL NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  ts INTEGER NOT NULL,
  paid INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS xc_pay_user ON xc_pay(user_id, paid);
CREATE TABLE IF NOT EXISTS friends(
  user_id INTEGER NOT NULL,
  friend_id INTEGER NOT NULL,
  created INTEGER NOT NULL,
  PRIMARY KEY(user_id, friend_id)
);
CREATE INDEX IF NOT EXISTS friends_friend ON friends(friend_id);
CREATE TABLE IF NOT EXISTS gifts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_id INTEGER NOT NULL,
  to_id INTEGER NOT NULL,
  ts INTEGER NOT NULL,
  claimed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS gifts_to ON gifts(to_id, claimed);
CREATE INDEX IF NOT EXISTS gifts_from ON gifts(from_id, ts);
CREATE TABLE IF NOT EXISTS push_subs(
  endpoint TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  p256dh TEXT NOT NULL,
  auth TEXT NOT NULL,
  tz TEXT NOT NULL DEFAULT '',
  created INTEGER NOT NULL,
  fails INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS push_subs_user ON push_subs(user_id);
CREATE TABLE IF NOT EXISTS push_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  ts INTEGER NOT NULL,
  kind TEXT NOT NULL,
  delivered INTEGER NOT NULL DEFAULT 0,
  opened INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS push_log_user ON push_log(user_id, ts);
CREATE INDEX IF NOT EXISTS push_log_ts ON push_log(ts);
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
if "ref_code" not in [r[1] for r in _db.execute("PRAGMA table_info(users)").fetchall()]:
    _db.execute("ALTER TABLE users ADD COLUMN ref_code TEXT NOT NULL DEFAULT ''")
_db.execute("CREATE INDEX IF NOT EXISTS users_ref_code ON users(ref_code)")
if "co" not in [r[1] for r in _db.execute("PRAGMA table_info(lifeboard)").fetchall()]:
    _db.execute("ALTER TABLE lifeboard ADD COLUMN co REAL NOT NULL DEFAULT 0")
if "ver" not in [r[1] for r in _db.execute("PRAGMA table_info(saves)").fetchall()]:
    _db.execute("ALTER TABLE saves ADD COLUMN ver INTEGER NOT NULL DEFAULT 0")
if "company_renamed" not in [r[1] for r in _db.execute("PRAGMA table_info(users)").fetchall()]:
    _db.execute("ALTER TABLE users ADD COLUMN company_renamed INTEGER NOT NULL DEFAULT 0")
# marketing: which campaign link brought each visitor and player
if "camp" not in [r[1] for r in _db.execute("PRAGMA table_info(users)").fetchall()]:
    _db.execute("ALTER TABLE users ADD COLUMN camp TEXT NOT NULL DEFAULT ''")
if "camp" not in [r[1] for r in _db.execute("PRAGMA table_info(visitors)").fetchall()]:
    _db.execute("ALTER TABLE visitors ADD COLUMN camp TEXT NOT NULL DEFAULT ''")
_db.execute("CREATE INDEX IF NOT EXISTS users_camp ON users(camp)")
# Ad builder: objective, budget level, gender, interests and what this run created
_old_runs = False
for _c, _d in (("objective", "TEXT NOT NULL DEFAULT 'OUTCOME_TRAFFIC'"), ("budget_level", "TEXT NOT NULL DEFAULT 'campaign'"),
               ("genders", "TEXT NOT NULL DEFAULT ''"), ("interests", "TEXT NOT NULL DEFAULT '[]'"), ("campaign_name", "TEXT NOT NULL DEFAULT ''"),
               ("adset_name", "TEXT NOT NULL DEFAULT ''"), ("made_campaign", "INTEGER NOT NULL DEFAULT 0"), ("made_adset", "INTEGER NOT NULL DEFAULT 0"),
               ("adset_daily", "INTEGER NOT NULL DEFAULT 0"), ("batch", "TEXT NOT NULL DEFAULT ''"), ("bset", "INTEGER NOT NULL DEFAULT 0")):
    if _c not in [r[1] for r in _db.execute("PRAGMA table_info(ad_runs)").fetchall()]:
        _db.execute("ALTER TABLE ad_runs ADD COLUMN %s %s" % (_c, _d))
        if _c == "made_campaign":
            _old_runs = True
if _old_runs:   # ads from before the builder made their own campaign and ad set
    _db.execute("UPDATE ad_runs SET made_campaign=1, made_adset=1")
# Ads Manager view: ad set ids on daily rows, on/off and budgets on campaigns and ads
for _t, _c, _d in (("meta_daily", "adset_id", "TEXT NOT NULL DEFAULT ''"), ("meta_campaigns", "onoff", "TEXT NOT NULL DEFAULT ''"),
                   ("meta_campaigns", "objective", "TEXT NOT NULL DEFAULT ''"), ("meta_campaigns", "daily_budget", "REAL NOT NULL DEFAULT 0"),
                   ("meta_campaigns", "lifetime_budget", "REAL NOT NULL DEFAULT 0"), ("meta_ads", "adset_id", "TEXT NOT NULL DEFAULT ''"),
                   ("meta_ads", "onoff", "TEXT NOT NULL DEFAULT ''")):
    if _c not in [r[1] for r in _db.execute("PRAGMA table_info(%s)" % _t).fetchall()]:
        _db.execute("ALTER TABLE %s ADD COLUMN %s %s" % (_t, _c, _d))
_db.execute("CREATE INDEX IF NOT EXISTS visitors_camp ON visitors(camp)")
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
LIFE_NUM = ("months", "age", "nw", "best", "start", "kids", "inds", "props", "teams", "ts", "gen", "bcw")


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
    ms = clean_ms(d.get("ms"))
    if ms:
        out["ms"] = ms
    ba = d.get("billionAge")
    out["billionAge"] = int(ba) if isinstance(ba, (int, float)) and not isinstance(ba, bool) and 0 < ba < 200 else None
    if out.get("end") not in ("died", "bankrupt", "restarted", "vanished"):
        out["end"] = "restarted"
    ob = clean_obit(d.get("ob"))
    if ob:
        out["ob"] = ob
    return out


OBIT_TEXT = {"name": 60, "dek": 200, "role": 120, "lead": 600, "surv": 300}


def clean_obit(o):
    """Keep the obituary written when a life ended, so it can be read and downloaded later."""
    if not isinstance(o, dict):
        return None
    out = {k: clean_text(o.get(k), n) for k, n in OBIT_TEXT.items() if isinstance(o.get(k), str)}
    for k, many, n in (("high", 6, 160), ("ach", 8, 60)):
        v = o.get(k)
        if isinstance(v, list):
            out[k] = [clean_text(x, n) for x in v[:many] if isinstance(x, str)]
    for k in ("bornY", "diedY", "years"):
        v = o.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and -100000 < v < 100000:
            out[k] = int(v)
    return out or None


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


def retention(t, rg=None):
    """Of players who signed up in the range (default: the last 90 days), the share who came back N or more days later."""
    t0, t1 = (rg["t0"], rg["t1"]) if rg else (t - 90 * 86400, t + 1)
    users = q("SELECT id, created FROM users WHERE created>=? AND created<?", (t0, t1))
    days = {}
    for r in q("SELECT a.user_id, a.day FROM activity_days a JOIN users u ON u.id=a.user_id WHERE u.created>=? AND u.created<?",
               (t0, t1)):
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


DROP_BUCKETS = [(0, 0, "Never finished a month"), (1, 3, "Months 1 to 3"), (4, 12, "Months 4 to 12"),
                (13, 36, "Years 2 to 3"), (37, 120, "Years 4 to 10"), (121, 10 ** 9, "Over 10 years")]
FUNNEL = [(1, "Played a month"), (12, "Played a full year"), (60, "Played 5 years"), (240, "Played 20 years")]


QUIET_DAYS = 2

# the admin's date range: whole days in the admin's own time zone (Nairobi unless HUSTLE_ADMIN_TZ says otherwise)
ADMIN_TZ = int(float(os.environ.get("HUSTLE_ADMIN_TZ", "3")) * 3600)
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def admin_range(path, t, default_days=30):
    qs = parse_qs(urlparse(path).query)
    today = time.strftime("%Y-%m-%d", time.gmtime(t + ADMIN_TZ))
    d1 = (qs.get("to") or [""])[0]
    d1 = d1 if DAY_RE.match(d1) else today
    d0 = (qs.get("from") or [""])[0]
    if not DAY_RE.match(d0):
        try:
            days = int((qs.get("days") or [str(default_days)])[0])
        except ValueError:
            days = default_days
        days = max(1, min(3660, days))
        d0 = time.strftime("%Y-%m-%d", time.gmtime(calendar.timegm(time.strptime(d1, "%Y-%m-%d")) - (days - 1) * 86400))
    try:
        t0 = calendar.timegm(time.strptime(d0, "%Y-%m-%d")) - ADMIN_TZ
        t1 = calendar.timegm(time.strptime(d1, "%Y-%m-%d")) + 86400 - ADMIN_TZ
    except ValueError:
        return admin_range("/", t, default_days)
    if t1 <= t0:
        t0, t1, d0, d1 = t1 - 86400, t0 + 86400, d1, d0
    return {"t0": t0, "t1": t1, "d0": d0, "d1": d1, "days": max(1, (t1 - t0) // 86400)}


def range_days(rg, cap=92):
    """The days in the range (the last `cap` of them), as (YYYY-MM-DD, start, end) in the admin's time zone."""
    n = min(cap, rg["days"])
    out = []
    for i in range(n - 1, -1, -1):
        s = rg["t1"] - (i + 1) * 86400
        out.append((time.strftime("%Y-%m-%d", time.gmtime(s + ADMIN_TZ)), s, s + 86400))
    return out


def cohorts(t, weeks=10, rg=None):
    """New players grouped by the week they signed up (weeks start on Monday, UTC), and the share who came back 1 and 7 days later."""
    def week_of(ts):
        d = int(ts // 86400) * 86400
        return d - time.gmtime(d).tm_wday * 86400
    monday = week_of(min(t, rg["t1"] - 1) if rg else t)
    if rg:
        weeks = min(26, int((monday - week_of(rg["t0"])) // (7 * 86400)) + 1)
    start = monday - (weeks - 1) * 7 * 86400
    users = q("SELECT id, created FROM users WHERE disabled=0 AND created>=? AND created<?", (start, monday + 7 * 86400))
    days = {}
    for r in q("SELECT a.user_id, a.day FROM activity_days a JOIN users u ON u.id=a.user_id WHERE u.created>=?", (start,)):
        days.setdefault(r["user_id"], []).append(r["day"])
    out = []
    for w in range(weeks):
        ws = start + w * 7 * 86400
        grp = [u for u in users if ws <= u["created"] < ws + 7 * 86400]
        row = {"week": time.strftime("%Y-%m-%d", time.gmtime(ws)), "n": len(grp)}
        for n in (1, 7):
            el = [u for u in grp if u["created"] <= t - n * 86400]
            back = sum(1 for u in el if any(d >= time.strftime("%Y-%m-%d", time.gmtime(u["created"] + n * 86400)) for d in days.get(u["id"], [])))
            row["d%d" % n] = {"el": len(el), "back": back}
        out.append(row)
    return out[::-1]


G10_NAMES = ["Own 3 businesses", "Try Auto-play", "Reach $5,000", "Open a bigger business", "Reach $25,000", "Reach $100,000"]


def first_session(t, days=30, rg=None):
    """Players who signed up in the range (default: the last N days): how far each one got through the start of the game."""
    t0, t1 = (rg["t0"], rg["t1"]) if rg else (t - days * 86400, t + 1)
    if rg:
        days = rg["days"]
    rows = q("SELECT u.id, COALESCE(s.months_played,0) mp, COALESCE(s.detail,'{}') detail, s.user_id sid FROM users u "
             "LEFT JOIN stats s ON s.user_id=u.id WHERE u.disabled=0 AND u.created>=? AND u.created<?", (t0, t1))
    base = []
    for r in rows:
        try:
            d = json.loads(r["detail"] or "{}") or {}
        except ValueError:
            d = {}
        base.append((r, d))
    n = len(base)
    steps = [{"label": "Created an account", "n": n},
             {"label": "Started a game", "n": sum(1 for r, d in base if r["sid"] is not None)},
             {"label": "Bought a first business", "n": sum(1 for r, d in base if (d.get("units") or 0) >= 1 or r["mp"] >= 1)},
             {"label": "Finished the first month", "n": sum(1 for r, d in base if r["mp"] >= 1)}]
    goals = [(r, d) for r, d in base if isinstance(d.get("g10"), (int, float)) and d.get("g10") >= 0]
    for i, nm in enumerate(G10_NAMES):
        steps.append({"label": "Starter goal %d: %s" % (i + 1, nm), "n": sum(1 for r, d in goals if d["g10"] >= i + 1), "goal": 1})
    steps.append({"label": "Played a full game year", "n": sum(1 for r, d in base if r["mp"] >= 12)})
    return {"days": days, "players": n, "goalPlayers": len(goals), "steps": steps}


def last_screen(t, rg=None):
    """Players who went quiet (last seen in the range, default the last 60 days): the tab they were on and any card left open."""
    t0, t1 = (rg["t0"], rg["t1"]) if rg else (t - 60 * 86400, t)
    rows = q("SELECT s.detail FROM users u JOIN stats s ON s.user_id=u.id WHERE u.disabled=0 AND u.last_seen<? AND u.last_seen>=? AND u.last_seen<?",
             (t - QUIET_DAYS * 86400, t0, t1))
    tabs, cards, n, open_n = {}, {}, 0, 0
    for r in rows:
        try:
            d = json.loads(r["detail"] or "{}") or {}
        except ValueError:
            continue
        n += 1
        tb = d.get("tab") or "unknown"
        tabs[tb] = tabs.get(tb, 0) + 1
        c = d.get("card") or ""
        if c:
            open_n += 1
            cards[c] = cards.get(c, 0) + 1
    return {"players": n, "openCard": open_n,
            "tabs": [{"tab": k, "n": v} for k, v in sorted(tabs.items(), key=lambda x: -x[1])],
            "cards": [{"ev": k, "n": v} for k, v in sorted(cards.items(), key=lambda x: -x[1])[:10]]}


def dropoff(t, rg=None):
    """Where players stop: how far players got before going quiet, and the last decision they made (players who signed up in the range)."""
    t0, t1 = (rg["t0"], rg["t1"]) if rg else (0, t + 1)
    base = q("SELECT u.id, u.last_seen, COALESCE(s.months_played,0) mp, COALESCE(s.best,0) best, COALESCE(s.games,1) games "
             "FROM users u LEFT JOIN stats s ON s.user_id=u.id WHERE u.disabled=0 AND u.created>=? AND u.created<?", (t0, t1))
    n = len(base)
    lived = {r["user_id"] for r in q("SELECT DISTINCT user_id FROM lives")}
    funnel = [{"label": "Created an account", "n": n}]
    for m, label in FUNNEL:
        funnel.append({"label": label, "n": sum(1 for r in base if r["mp"] >= m)})
    funnel.append({"label": "Became a billionaire", "n": sum(1 for r in base if r["best"] >= 1e9)})
    funnel.append({"label": "Finished a whole life", "n": sum(1 for r in base if r["id"] in lived)})
    gone = [r for r in base if r["last_seen"] < t - QUIET_DAYS * 86400]
    buckets = [{"label": label, "n": sum(1 for r in gone if lo <= r["mp"] <= hi)} for lo, hi, label in DROP_BUCKETS]
    last = {}
    ids = [r["id"] for r in gone if r["last_seen"] > t - 120 * 86400]
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for r in q("SELECT e.user_id, e.ev, e.choice FROM ev_log e JOIN (SELECT user_id, MAX(ts) mt FROM ev_log WHERE user_id IN (%s) GROUP BY user_id) m "
                   "ON m.user_id=e.user_id AND m.mt=e.ts" % ",".join("?" * len(chunk)), tuple(chunk)):
            last.setdefault(r["user_id"], (r["ev"], r["choice"]))
    tally = {}
    for ev, ch in last.values():
        k = (ev, ch)
        tally[k] = tally.get(k, 0) + 1
    lastev = [{"ev": k[0], "choice": k[1], "n": v} for k, v in sorted(tally.items(), key=lambda x: -x[1])[:10]]
    return {"players": n, "gone": len(gone), "quietDays": QUIET_DAYS, "funnel": funnel, "buckets": buckets, "lastEv": lastev, "lastEvN": len(last),
            "cohorts": cohorts(t, rg=rg), "first": first_session(t, rg=rg), "screen": last_screen(t, rg=rg)}


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


MS_KEYS = (("m", 1e6), ("b", 1e9), ("t", 1e12), ("q", 1e15))


def clean_ms(d):
    """Age in months when a life first reached $1M, $1B, $1T and $1Q."""
    out = {}
    if isinstance(d, dict):
        for k, _ in MS_KEYS:
            v = d.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and 12 * 12 <= v <= 140 * 12:
                out[k] = int(v)
    return out


def ms_from_state(st):
    """Work out the milestone ages of a saved game from its net worth history."""
    hist = st.get("hist") if isinstance(st.get("hist"), list) else []
    a0 = st.get("age0") if isinstance(st.get("age0"), (int, float)) else 24
    out = {}
    for k, v in MS_KEYS:
        for i, x in enumerate(hist):
            if isinstance(x, (int, float)) and x >= v:
                out[k] = int(a0 * 12 + i)
                break
    return out


def lifeboard_put(db, uid, game, gen, who, region, best, ms, t, co=None):
    """Record one life for the hall of fame, keeping its best worth and earliest milestones."""
    db.execute("INSERT INTO lifeboard(user_id,game,gen,who,region,best,ms_m,ms_b,ms_t,ms_q,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?) "
               "ON CONFLICT(user_id,game) DO UPDATE SET gen=excluded.gen, who=CASE WHEN excluded.who<>'' THEN excluded.who ELSE lifeboard.who END, "
               "region=CASE WHEN excluded.region<>'' THEN excluded.region ELSE lifeboard.region END, best=MAX(lifeboard.best,excluded.best), "
               "ms_m=COALESCE(MIN(lifeboard.ms_m,excluded.ms_m),lifeboard.ms_m,excluded.ms_m), "
               "ms_b=COALESCE(MIN(lifeboard.ms_b,excluded.ms_b),lifeboard.ms_b,excluded.ms_b), "
               "ms_t=COALESCE(MIN(lifeboard.ms_t,excluded.ms_t),lifeboard.ms_t,excluded.ms_t), "
               "ms_q=COALESCE(MIN(lifeboard.ms_q,excluded.ms_q),lifeboard.ms_q,excluded.ms_q), updated=excluded.updated",
               (uid, game, max(1, int(gen or 1)), clean_text(who or "", 40), clean_text(region or "", 3), float(best or 0),
                ms.get("m"), ms.get("b"), ms.get("t"), ms.get("q"), t))
    if co is not None:
        db.execute("UPDATE lifeboard SET co=? WHERE user_id=? AND game=?", (max(0.0, min(1e30, float(co))), uid, game))


def backfill_lifeboard():
    """Fill the hall of fame from past lives and games in progress."""
    def run(db):
        if db.execute("SELECT 1 FROM lifeboard LIMIT 1").fetchone():
            return
        t = now()
        for r in db.execute("SELECT user_id, game, ended, data FROM lives").fetchall():
            try:
                d = json.loads(r["data"] or "{}")
            except ValueError:
                continue
            ms = clean_ms(d.get("ms"))
            if not ms and d.get("billionAge"):
                ms = {"b": int(d["billionAge"]) * 12}
            lifeboard_put(db, r["user_id"], r["game"], d.get("gen") or 1, d.get("who") or "", d.get("region") or "",
                          num(d.get("best")), ms, r["ended"] or t)
        for r in db.execute("SELECT s.user_id, s.games, s.best, s.detail, v.state FROM stats s JOIN saves v ON v.user_id=s.user_id").fetchall():
            try:
                st = json.loads(r["state"] or "{}")
            except ValueError:
                continue
            if not isinstance(st, dict) or not st.get("month"):
                continue
            gen = 2 if st.get("headstart") else (st.get("gnum") or 1)
            lifeboard_put(db, r["user_id"], r["games"], gen, st.get("who") or "", st.get("region") or "",
                          max(num(r["best"]), max([x for x in (st.get("hist") or []) if isinstance(x, (int, float))] or [0])),
                          ms_from_state(st), t)
    tx(run)


def company_key(name):
    """Two company names clash if they match ignoring case, spaces and punctuation."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def company_taken(name, except_uid=None):
    k = company_key(name)
    if not k:
        return False
    for r in q("SELECT id, company FROM users"):
        if r["id"] != except_uid and company_key(r["company"]) == k:
            return True
    return False


def company_default(person, username=""):
    """A unique brand for players who leave the company name blank: their username first, then their first name."""
    u = " ".join(w.capitalize() for w in re.split(r"[._]+", username or "") if w)[:16].strip()
    if u and not company_taken(u):
        return u
    first = re.sub(r"[^A-Za-z]", "", (person or "").split(" ")[0])[:9].capitalize() or "Hustle"
    for suffix in (" Group", " Holdings", " Ventures", " Capital", " & Co", " Empire"):
        c = (first + suffix)[:16]
        if not company_taken(c):
            return c
    for n in range(2, 10000):
        c = ("%s Group %d" % (first, n))[:16]
        if not company_taken(c):
            return c
    return "Hustle %s" % secrets.token_hex(3)


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
            "town": u["town"], "bg": u["bg"], "color": u["color"], "email": u["email"],
            "renamed": bool(u["company_renamed"]) if "company_renamed" in u.keys() else False}


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
    sender_name = "Hustlempires"
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
    text = ("Someone asked to reset the password for your Hustlempires account%s.\n\n"
            "Open this link to choose a new password:\n%s\n\n"
            "The link works once and expires in 1 hour. If you didn't ask for this, ignore this email; "
            "your password stays the same.\n" % ("s" if len(accounts) > 1 else "", lines))
    buttons = "".join(
        '<p style="margin:18px 0"><a href="%s" style="background:#14261f;color:#ffffff;padding:12px 20px;border-radius:4px;'
        'text-decoration:none;font-weight:bold;display:inline-block">Reset password for @%s</a></p>' % (html_escape(link), html_escape(u))
        for u, n, link in accounts)
    html = ('<div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.5;color:#14261f;max-width:520px">'
            '<h2 style="margin:0 0 12px">Reset your password</h2>'
            '<p>Someone asked to reset the password for your <b>Hustlempires</b> account%s.</p>%s'
            '<p style="color:#5b6660;font-size:13px">The link works once and expires in 1 hour. If you didn\'t ask for this, '
            'ignore this email; your password stays the same.</p></div>') % ("s" if len(accounts) > 1 else "", buttons)
    send_mail(email, "Reset your Hustlempires password", text, html)


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
        return {"on": False, "state": "off", "tips": pesapal_ready(), "tipAmounts": TIP_AMOUNTS, "now": now()}
    t = now()
    s = sub_row(user["id"])
    paid_until = s["paid_until"] if s else 0
    gifts = s["gifts"] if s else 0
    gift_until = s["gift_until"] if s else 0
    base = max(user["created"], billing_start())
    referred = q("SELECT 1 FROM referrals WHERE user_id=?", (user["id"],), one=True) is not None
    trial_end = base + (REF_TRIAL_DAYS * 86400 if referred and REF_TRIAL_DAYS * 86400 > TRIAL_HOURS * 3600 else TRIAL_HOURS * 3600)
    hard = max(base + BLOCK_DAYS * 86400, trial_end)
    out = {"on": True, "invited": referred, "refActiveDays": REF_ACTIVE_DAYS, "refPaidDays": REF_PAID_DAYS, "plans": plans_public(), "payReady": pesapal_ready(), "giftDays": GIFT_DAYS,
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
        if p["plan"] == "tip":
            st = db.execute("SELECT games FROM stats WHERE user_id=?", (p["user_id"],)).fetchone()
            db.execute("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'account',?)",
                       (p["user_id"], t, st["games"] if st else 1, "Tipped the developers KSh %s%s" % (
                           "{:,.0f}".format(p["amount"]), " via " + method if method else "")))
            return -p["user_id"]
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
        return p["user_id"]
    uid = tx(run)
    if uid and uid < 0:
        return True
    if uid:
        try:
            referral_paid(uid)
        except Exception as e:
            print("Invite reward after payment failed: %s" % e, flush=True)
    return bool(uid)


def reverse_payment(ref):
    t = now()

    def run(db):
        p = db.execute("SELECT * FROM payments WHERE ref=?", (ref,)).fetchone()
        if not p or p["status"] != "paid":
            return
        db.execute("UPDATE payments SET status='reversed', updated=? WHERE ref=?", (t, ref))
        db.execute("UPDATE subs SET paid_until=MAX(0, paid_until-?), updated=? WHERE user_id=?", (p["days"] * 86400, t, p["user_id"]))
        db.execute("INSERT INTO events(user_id,ts,kind,text) VALUES(?,?,'account',?)", (p["user_id"], t, "A tip was reversed" if p["plan"] == "tip" else "A pass payment was reversed"))
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


# ---- push notifications (Web Push with VAPID; needs the python3-cryptography package) ----
PUSH_STEPS = [1, 3, 7, 14, 30]          # days away before each nudge; at most one per step, then silence
PUSH_HOURS = (10, 20)                   # only between 10:00 and 20:00 in the player's own time zone
PUSH_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", "updates.push.services.mozilla.com", "push.services.mozilla.com",
              "web.push.apple.com", ".push.apple.com", ".notify.windows.com")
_push_lock = threading.Lock()


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s):
    s = str(s or "")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _crypto():
    try:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return {"be": default_backend(), "hashes": hashes, "ser": serialization, "ec": ec, "utils": utils, "AESGCM": AESGCM}
    except Exception:
        return None


def push_ready():
    return _crypto() is not None


def push_on():
    return push_ready() and meta_get("push_off") != "1"


def vapid_keys():
    """The server's own signing key for notifications, made once and kept in the database."""
    c = _crypto()
    with _push_lock:
        raw = meta_get("vapid_priv")
        if raw:
            key = c["ser"].load_pem_private_key(raw.encode(), password=None, backend=c["be"])
        else:
            key = c["ec"].generate_private_key(c["ec"].SECP256R1(), c["be"])
            meta_set("vapid_priv", key.private_bytes(c["ser"].Encoding.PEM, c["ser"].PrivateFormat.PKCS8,
                                                     c["ser"].NoEncryption()).decode())
    pub = key.public_key().public_bytes(c["ser"].Encoding.X962, c["ser"].PublicFormat.UncompressedPoint)
    return key, pub


def _hkdf(salt, ikm, info, n):
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:n]


def push_encrypt(payload, p256dh, auth):
    """RFC 8291 message encryption (aes128gcm), so only the player's browser can read the notification."""
    c = _crypto()
    ua_pub = unb64u(p256dh)
    secret = unb64u(auth)
    eph = c["ec"].generate_private_key(c["ec"].SECP256R1(), c["be"])
    as_pub = eph.public_key().public_bytes(c["ser"].Encoding.X962, c["ser"].PublicFormat.UncompressedPoint)
    peer = c["ec"].EllipticCurvePublicKey.from_encoded_point(c["ec"].SECP256R1(), ua_pub)
    shared = eph.exchange(c["ec"].ECDH(), peer)
    ikm = _hkdf(secret, shared, b"WebPush: info\x00" + ua_pub + as_pub, 32)
    salt = os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    body = c["AESGCM"](cek).encrypt(nonce, payload + b"\x02", None)
    return salt + (4096).to_bytes(4, "big") + bytes([len(as_pub)]) + as_pub + body


def vapid_header(endpoint):
    c = _crypto()
    key, pub = vapid_keys()
    u = urlparse(endpoint)
    claims = {"aud": "%s://%s" % (u.scheme, u.netloc), "exp": now() + 12 * 3600,
              "sub": "https://" + SITE_DOMAIN if SITE_DOMAIN else "mailto:admin@hustlempires.com"}
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps(claims, separators=(",", ":")).encode())
    der = key.sign((head + "." + body).encode(), c["ec"].ECDSA(c["hashes"].SHA256()))
    r, s_ = c["utils"].decode_dss_signature(der)
    sig = b64u(r.to_bytes(32, "big") + s_.to_bytes(32, "big"))
    return "vapid t=%s.%s.%s, k=%s" % (head, body, sig, b64u(pub))


def push_endpoint_ok(endpoint):
    try:
        u = urlparse(endpoint)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return u.scheme == "https" and len(endpoint) < 1000 and any(host == h or (h.startswith(".") and host.endswith(h)) for h in PUSH_HOSTS)


def push_send(sub, msg):
    """Send one notification to one browser. Returns True if the push service accepted it."""
    data = push_encrypt(json.dumps(msg, separators=(",", ":")).encode(), sub["p256dh"], sub["auth"])
    req = urllib.request.Request(sub["endpoint"], data=data, method="POST", headers={
        "Authorization": vapid_header(sub["endpoint"]), "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream", "TTL": "86400", "Urgency": "normal"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            ok = 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            q("DELETE FROM push_subs WHERE endpoint=?", (sub["endpoint"],))
            return False
        print("Notification to %s failed: HTTP %s %s" % (urlparse(sub["endpoint"]).hostname, e.code, e.read()[:200]), flush=True)
        ok = False
    except Exception as e:
        print("Notification to %s failed: %s" % (urlparse(sub["endpoint"]).hostname, e), flush=True)
        ok = False
    if ok:
        q("UPDATE push_subs SET fails=0 WHERE endpoint=?", (sub["endpoint"],))
    else:
        q("UPDATE push_subs SET fails=fails+1 WHERE endpoint=?", (sub["endpoint"],))
        q("DELETE FROM push_subs WHERE endpoint=? AND fails>=5", (sub["endpoint"],))
    return ok


def push_to_user(uid, kind, title, body):
    subs = q("SELECT * FROM push_subs WHERE user_id=?", (uid,))
    if not subs:
        return None
    pid = tx(lambda db: db.execute("INSERT INTO push_log(user_id, ts, kind) VALUES(?,?,?)", (uid, now(), kind)).lastrowid)
    msg = {"title": title, "body": body, "url": "/?push=%d" % pid, "tag": "hustle-" + kind, "id": pid}
    sent = sum(1 for sub in subs if push_send(sub, msg))
    if sent:
        q("UPDATE push_log SET delivered=1 WHERE id=?", (pid,))
    return sent


def _local(tz, t):
    """The player's own clock. tz is "Area/City|minutes-east-of-UTC"; the offset is the backup when the time-zone database is missing."""
    name, _, off = str(tz or "").partition("|")
    try:
        from zoneinfo import ZoneInfo
        import datetime
        return datetime.datetime.fromtimestamp(t, ZoneInfo(name or "Africa/Nairobi")).timetuple()
    except Exception:
        try:
            mins = max(-840, min(840, int(off)))
        except ValueError:
            mins = 180
        return time.gmtime(t + mins * 60)


def local_hour(tz, t):
    return _local(tz, t).tm_hour


def local_day(tz, t):
    return time.strftime("%Y-%m-%d", _local(tz, t))


GENERIC_PUSH = [
    ("{co} is waiting for its boss", "Big decisions are piling up on your desk. Pick up where you left off."),
    ("Your rivals did not take a week off", "Every month you wait, someone else is building. Get back in the game."),
    ("Still the boss?", "Your empire is right where you left it. One tap to carry on."),
    ("We kept your empire safe", "Everything you built is still here. Come back and finish what you started."),
]
MILESTONES = [1e6, 1e7, 1e8, 1e9, 1e10, 1e11, 1e12, 1e13, 1e14, 1e15]


def push_message(uid, n, done, tz, t):
    """Pick the most relevant true thing to tell this player about their own game."""
    u = q("SELECT name, company FROM users WHERE id=?", (uid,), one=True)
    st = q("SELECT nw FROM stats WHERE user_id=?", (uid,), one=True)
    sv = q("SELECT state FROM saves WHERE user_id=?", (uid,), one=True)
    try:
        S = json.loads(sv["state"]) if sv else {}
    except ValueError:
        S = {}
    co = (u["company"] if u else "") or "Your company"
    out = []
    daily = S.get("daily") or {}
    yday = local_day(tz, t - 86400)
    if n == 0 and int(daily.get("streak") or 0) >= 2 and daily.get("last") == yday and not S.get("won") and not S.get("over"):
        out.append(("streak", "Your %d-day streak ends tonight" % int(daily["streak"]),
                    "Claim today's daily bonus before midnight, or your streak goes back to zero."))
    if S.get("over") and S.get("died") and S.get("kids") and not S.get("noHeir"):
        out.append(("heir", "Your empire needs an heir", "Your story ended, but your family's has not. Choose who takes over everything you built."))
    if isinstance(S.get("ill"), dict) and S["ill"].get("id"):
        out.append(("health", "Your doctor is waiting", "Your treatment cannot wait. Your health and your empire are on the line."))
    nw = st["nw"] if st else 0
    nxt = next((m for m in MILESTONES if m > nw), None)
    if nxt and nw >= 0.5 * nxt and not S.get("over"):
        out.append(("milestone", "%d%% of the way to your next milestone" % int(100 * nw / nxt),
                    "One good month could get you there. Your empire is ready when you are."))
    sid = season_now()
    me = q("SELECT pts, region FROM season_scores WHERE user_id=? AND season=?", (uid, sid), one=True)
    if me and me["pts"] > 0 and me["region"]:
        ahead = q("SELECT u.name, s.pts FROM season_scores s JOIN users u ON u.id=s.user_id WHERE s.season=? AND s.region=? "
                  "AND s.pts>? AND u.disabled=0 ORDER BY s.pts ASC LIMIT 1", (sid, me["region"], me["pts"]), one=True)
        if ahead:
            rank = q("SELECT COUNT(*) c FROM season_scores WHERE season=? AND region=? AND pts>?", (sid, me["region"], me["pts"]), one=True)["c"] + 1
            out.append(("rival", "You are #%d in your country this season" % rank,
                        "%s is just %d points ahead of you. Take the spot back." % ((ahead["name"] or "A rival").split(" ")[0], ahead["pts"] - me["pts"])))
    if S.get("teams"):
        out.append(("team", "Your club needs its owner", "The season is under way. Matches, transfers and trophies are waiting for you."))
    for kind, title, body in out:
        if kind not in done:
            return kind, title, body
    g = GENERIC_PUSH[min(max(n - 1, 0), len(GENERIC_PUSH) - 1)] if n < len(PUSH_STEPS) - 1 else GENERIC_PUSH[-1]
    return "away%d" % n, g[0].format(co=co), g[1]


def push_due(t):
    """Players who have been away long enough for their next nudge, inside their daytime hours."""
    for r in q("SELECT u.id, u.last_seen, MIN(p.tz) tz FROM push_subs p JOIN users u ON u.id=p.user_id WHERE u.disabled=0 GROUP BY u.id"):
        away = (t - r["last_seen"]) / 86400
        log = q("SELECT ts, kind FROM push_log WHERE user_id=? AND ts>?", (r["id"], r["last_seen"]))
        n = len(log)
        if n >= len(PUSH_STEPS) or away < PUSH_STEPS[n]:
            continue
        if log and max(x["ts"] for x in log) > t - 20 * 3600:
            continue
        h = local_hour(r["tz"], t)
        if not (PUSH_HOURS[0] <= h < PUSH_HOURS[1]):
            continue
        yield r["id"], n, {x["kind"] for x in log}, r["tz"]


def push_sweeper():
    """Every 10 minutes, send the nudges that are due."""
    time.sleep(60)
    while True:
        try:
            if push_on():
                t = now()
                for uid, n, done, tz in list(push_due(t)):
                    kind, title, body = push_message(uid, n, done, tz, t)
                    push_to_user(uid, kind, title, body)
                    time.sleep(0.2)
        except Exception as e:
            print("Notification round failed: %s" % e, flush=True)
        time.sleep(600)


BANK_TYPES = {"serviced", "logistics", "apartments", "resort", "mall", "hotel", "office", "supertall"}
BANK_CITIES = {"nairobi", "mombasa", "kigali", "zanzibar", "cairo", "lagos", "joburg", "dubai", "mumbai", "maldives", "miami",
               "singapore", "tokyo", "paris", "london", "newyork"}
BANK_DAYS = 14


def clean_lot(d):
    """Only the known fields of a seized building, within sane limits."""
    if not isinstance(d, dict) or d.get("type") not in BANK_TYPES or d.get("city") not in BANK_CITIES:
        return None
    try:
        value = float(d.get("value"))
        af = float(d.get("af"))
        occ = float(d.get("occ", 0.9))
        total = int(d.get("total", 18))
    except (TypeError, ValueError):
        return None
    if not (0 < value < 1e16 and 0 < af < 1e4 and 0 <= occ <= 1.5 and 0 < total < 1000):
        return None
    return {"type": d["type"], "city": d["city"], "name": clean_text(d.get("name"), 60) or "A building", "af": af, "occ": occ,
            "total": total, "value": round(value)}


MARKET_ITEMS = {"car1", "car2", "car3", "car4", "car5", "car6", "jet", "h0", "h1", "h2", "h3", "h4", "h5", "h6", "a1", "a2", "a3",
                "shoes", "bags", "wardrobe", "birkin", "jewels", "watch", "horses", "villa", "art", "yacht", "vineyard", "golfclub",
                "island", "superyacht", "trophyhotel", "masterpiece"}
HOME_CITIES = {"nairobi", "mombasa"}
MARKET_DAYS = 7
MARKET_FEE = 0.05
MARKET_OPEN_MAX = 20


def clean_item(kind, d):
    if kind == "p":
        return clean_lot(d)
    if kind == "a" and isinstance(d, dict) and d.get("id") in MARKET_ITEMS:
        try:
            value, af = float(d.get("value")), float(d.get("af", 1))
            gen = int(d.get("gen") or 0)
        except (TypeError, ValueError):
            return None
        if 0 < value < 1e16 and 0 < af < 1e4 and 0 <= gen < 50:
            return {"id": d["id"], "name": clean_text(d.get("name"), 60) or "An item", "af": af, "gen": gen, "value": round(value)}
    return None


def market_row(r, t):
    try:
        d = json.loads(r["data"])
    except ValueError:
        return None
    d.update({"lid": r["id"], "k": r["kind"], "value": r["value"], "price": r["price"], "region": r["region"], "g": r["g"],
              "daysLeft": max(0, int((r["expires"] - t) // 86400)), "status": r["status"]})
    if "seller" in r.keys():
        d["from"] = (r["seller"] or "").split(" ")[0]
    return d


XC_SHARES = 1_000_000
XC_MIN_NW = 1e7
XC_FEE = 0.02


def xc_price(nw, bankrupt=0):
    return 0.0 if bankrupt or not nw or nw <= 0 else round(nw / XC_SHARES, 4)


def xc_companies(t):
    """Every listed player company with today's price; records one price a day for the 7-day change."""
    rows = q("SELECT l.user_id, l.float_pct, l.sold, l.created, u.name, u.company, u.color, u.disabled, COALESCE(s.nw,0) nw, "
             "COALESCE(s.bankrupt,0) bankrupt, COALESCE(s.detail,'{}') detail FROM xc_list l JOIN users u ON u.id=l.user_id "
             "LEFT JOIN stats s ON s.user_id=l.user_id WHERE l.active=1")
    day, wk = today(), time.strftime("%Y-%m-%d", time.gmtime(t - 7 * 86400))
    out = []
    for r in rows:
        px = 0.0 if r["disabled"] else xc_price(r["nw"], r["bankrupt"])
        q("INSERT OR IGNORE INTO xc_px(user_id, day, px) VALUES(?,?,?)", (r["user_id"], day, px))
        old = q("SELECT px FROM xc_px WHERE user_id=? AND day<=? ORDER BY day DESC LIMIT 1", (r["user_id"], wk), one=True) or \
            q("SELECT px FROM xc_px WHERE user_id=? ORDER BY day ASC LIMIT 1", (r["user_id"],), one=True)
        try:
            region = (json.loads(r["detail"] or "{}") or {}).get("region") or ""
        except ValueError:
            region = ""
        avail = max(0.0, r["float_pct"] * XC_SHARES - r["sold"])
        out.append({"id": r["user_id"], "company": r["company"], "founder": (r["name"] or "").split(" ")[0], "color": r["color"],
                    "region": region, "px": px, "chg": (px / old["px"] - 1) if old and old["px"] > 0 else 0,
                    "cap": px * XC_SHARES, "float": r["float_pct"], "avail": avail, "since": r["created"]})
    out.sort(key=lambda c: -c["cap"])
    return out


FRIEND_MAX = 100
GIFTS_PER_DAY = 5


def befriend(a, b, t=None):
    """Make two players friends both ways (used for invites)."""
    if a and b and a != b:
        t = t or now()
        q("INSERT OR IGNORE INTO friends(user_id, friend_id, created) VALUES(?,?,?)", (a, b, t))
        q("INSERT OR IGNORE INTO friends(user_id, friend_id, created) VALUES(?,?,?)", (b, a, t))


def backfill_friends():
    """Everyone who joined with an invite link becomes friends with the person who invited them."""
    if meta_get("friends_backfill") == "1":
        return
    for r in q("SELECT user_id, inviter_id, created FROM referrals"):
        befriend(r["user_id"], r["inviter_id"], r["created"])
    meta_set("friends_backfill", "1")


def seen_label(last, t):
    a = t - (last or 0)
    if a < 600:
        return "Playing now"
    if a < 86400 and time.strftime("%Y-%m-%d", time.gmtime(last + 3 * 3600)) == time.strftime("%Y-%m-%d", time.gmtime(t + 3 * 3600)):
        return "Played today"
    d = max(1, int(a // 86400))
    return "Played yesterday" if d == 1 else "Played %d days ago" % d


def push_overview(t, rg=None):
    a, b = (rg["t0"], rg["t1"]) if rg else (t - 7 * 86400, t + 1)
    a30 = rg["t0"] if rg else t - 30 * 86400
    s7 = q("SELECT COUNT(*) n, SUM(delivered) d, SUM(opened) o FROM push_log WHERE ts>=? AND ts<?", (a, b), one=True)
    s30 = q("SELECT COUNT(*) n, SUM(delivered) d, SUM(opened) o FROM push_log WHERE ts>=? AND ts<?", (a30, b), one=True)
    kinds = [dict(r) for r in q("SELECT kind, COUNT(*) n, SUM(delivered) d, SUM(opened) o FROM push_log WHERE ts>=? AND ts<? GROUP BY kind ORDER BY n DESC", (a30, b))]
    return {"ready": push_ready(), "on": push_on(), "players": q("SELECT COUNT(DISTINCT user_id) c FROM push_subs", one=True)["c"],
            "devices": q("SELECT COUNT(*) c FROM push_subs", one=True)["c"],
            "sent7": s7["d"] or 0, "opened7": s7["o"] or 0, "sent30": s30["d"] or 0, "opened30": s30["o"] or 0, "kinds": kinds}


def payment_sweeper():
    """Every few minutes, re-check recent unpaid orders, in case a notification from Pesapal went missing."""
    while True:
        time.sleep(300)
        if not pesapal_ready():
            continue
        t = now()
        for r in q("SELECT ref FROM payments WHERE status IN ('pending','failed') AND tracking<>'' AND created>? AND created<? "
                   "ORDER BY id DESC LIMIT 30", (t - 2 * 86400, t - 60)):
            try:
                check_payment(r["ref"])
            except Exception as e:
                print("Payment check for %s failed: %s" % (r["ref"], e), flush=True)


def billing_overview(t, rg=None):
    a, b = (rg["t0"], rg["t1"]) if rg else (t - 30 * 86400, t + 1)
    if not BILLING_ON:
        tip = lambda since, until: q("SELECT COALESCE(SUM(amount),0) a, COUNT(*) c, COUNT(DISTINCT user_id) u FROM payments "
                                     "WHERE status='paid' AND plan='tip' AND updated>=? AND updated<?", (since, until), one=True)
        t30, tall = tip(a, b), tip(0, t + 1)
        opened = q("SELECT COUNT(*) c FROM payments WHERE plan='tip' AND created>=? AND created<?", (a, b), one=True)["c"]
        passes = q("SELECT COALESCE(SUM(amount),0) a, COUNT(*) c FROM payments WHERE status='paid' AND plan<>'tip'", one=True)
        return {"on": False, "ready": pesapal_ready(), "env": PESAPAL_ENV, "tips30": t30["a"], "tipN30": t30["c"], "tippers30": t30["u"],
                "tipsAll": tall["a"], "tipNAll": tall["c"], "tippersAll": tall["u"], "opened30": opened,
                "passRev": passes["a"], "passN": passes["c"], "tipAmounts": TIP_AMOUNTS}
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
    rev = lambda since, until: q("SELECT COALESCE(SUM(amount),0) a, COUNT(*) c FROM payments WHERE status='paid' AND updated>=? AND updated<?", (since, until), one=True)
    r30, rall = rev(a, b), rev(0, t + 1)
    k.update(on=True, ready=pesapal_ready(), env=PESAPAL_ENV, since=bs, rev30=r30["a"], pay30=r30["c"], revAll=rall["a"], payAll=rall["c"],
             byPlan={r["plan"]: r["c"] for r in q("SELECT plan, COUNT(*) c FROM payments WHERE status='paid' AND updated>=? AND updated<? GROUP BY plan", (a, b))},
             trialHours=TRIAL_HOURS, giftDays=GIFT_DAYS, gifts=GIFTS, blockDays=BLOCK_DAYS, plans=plans_public())
    return k


# ---- event tuning: how often each kind of event pops up ----
EV_ID_RE = re.compile(r"^[a-z0-9_]{1,40}$")
TUNE_DEFAULT = {"freq": 1, "gap": 2, "w": {}, "cat": {}}


def tuning():
    try:
        t = json.loads(meta_get("tuning") or "null")
    except ValueError:
        t = None
    return t if isinstance(t, dict) else dict(TUNE_DEFAULT)


def clean_tuning(d):
    def mult(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return round(min(5.0, max(0.0, v)), 2)
    try:
        freq = round(min(3.0, max(0.25, float(d.get("freq", 1)))), 2)
    except (TypeError, ValueError):
        freq = 1
    try:
        gap = int(min(12, max(1, int(d.get("gap", 2)))))
    except (TypeError, ValueError):
        gap = 2
    w = {k: mult(v) for k, v in (d.get("w") or {}).items() if isinstance(k, str) and EV_ID_RE.match(k) and mult(v) is not None and mult(v) != 1}
    cat = {k[:40]: mult(v) for k, v in (d.get("cat") or {}).items() if isinstance(k, str) and mult(v) is not None and mult(v) != 1}
    c = d.get("crisis") if isinstance(d.get("crisis"), dict) else {}
    crisis = {}
    for k in ("world", "nature"):
        if mult(c.get(k)) is not None and mult(c.get(k)) != 1:
            crisis[k] = mult(c.get(k))
    try:
        cg = int(min(15, max(1, int(c.get("gap", 5)))))
    except (TypeError, ValueError):
        cg = 5
    if cg != 5:
        crisis["gap"] = cg
    off = [x for x in (c.get("off") or []) if x in ("pandemic", "war", "crash", "drought", "floods", "storm", "earthquake", "wildfire")]
    if off:
        crisis["off"] = sorted(set(off))
    out = {"freq": freq, "gap": gap, "w": dict(list(w.items())[:500]), "cat": dict(list(cat.items())[:60])}
    pd = d.get("pace") if isinstance(d.get("pace"), dict) else {}
    pace = {}
    try:
        pcd = int(min(120, max(1, int(pd.get("cd", 24)))))
    except (TypeError, ValueError):
        pcd = 24
    try:
        pgr = int(min(24, max(0, int(pd.get("grp", 9)))))
    except (TypeError, ValueError):
        pgr = 9
    pst = 0 if str(pd.get("stage", 1)) in ("0", "False", "false") else 1
    try:
        pdw = round(min(3.0, max(0.0, float(pd.get("dw", 1)))), 2)
    except (TypeError, ValueError):
        pdw = 1.0
    if pst != 1:
        pace["stage"] = pst
    if pdw != 1:
        pace["dw"] = pdw
    if pcd != 24:
        pace["cd"] = pcd
    if pgr != 9:
        pace["grp"] = pgr
    if pace:
        out["pace"] = pace
    if crisis:
        out["crisis"] = crisis
    dd = d.get("death") if isinstance(d.get("death"), dict) else {}
    death = {}
    for k in DEATH_TUNABLE:
        if mult(dd.get(k)) is not None and mult(dd.get(k)) != 1:
            death[k] = mult(dd.get(k))
    try:
        bk = round(min(1.0, max(0.0, float(dd.get("bankrupt", 1)))), 2)
    except (TypeError, ValueError):
        bk = 1.0
    if bk != 1.0:
        death["bankrupt"] = bk
    try:
        ma = int(min(130, max(80, int(dd.get("maxAge", 100)))))
    except (TypeError, ValueError):
        ma = 100
    if ma != 100:
        death["maxAge"] = ma
    if death:
        out["death"] = death
    ed = d.get("econ") if isinstance(d.get("econ"), dict) else {}
    econ = {}
    for k, lo, hi, dflt in (("ret", 0.2, 1.5, 0.6), ("unlock", 0.2, 5.0, 2.5), ("reg", 0.1, 1.5, 0.8)):
        try:
            v = round(min(hi, max(lo, float(ed.get(k, dflt)))), 2)
        except (TypeError, ValueError):
            v = dflt
        if v != dflt:
            econ[k] = v
    if ed.get("bank") in (0, False, "0"):
        econ["bank"] = 0
    if econ:
        out["econ"] = econ
    hd = d.get("heir") if isinstance(d.get("heir"), dict) else {}
    heir = {}
    try:
        hr = round(min(1.0, max(0.0, float(hd.get("repeat", 0.35)))), 2)
    except (TypeError, ValueError):
        hr = 0.35
    if hr != 0.35:
        heir["repeat"] = hr
    try:
        hg = int(min(24, max(1, int(hd.get("gap", 3)))))
    except (TypeError, ValueError):
        hg = 3
    if hg != 3:
        heir["gap"] = hg
    try:
        hg1 = int(min(24, max(1, int(hd.get("gap1", 2)))))
    except (TypeError, ValueError):
        hg1 = 2
    if hg1 != 2:
        heir["gap1"] = hg1
    if heir:
        out["heir"] = heir
    sd = d.get("sport") if isinstance(d.get("sport"), dict) else {}
    try:
        sg = int(min(24, max(1, int(sd.get("gap", 2)))))
    except (TypeError, ValueError):
        sg = 2
    if sg != 2:
        out["sport"] = {"gap": sg}
    return out


DEATH_TUNABLE = ("natural", "illness", "road", "jet", "hit",
                 "lungc", "pancc", "bloodc", "colonc", "sexc", "liverf", "kidneyf", "heartf", "als", "alz",
                 "burnout", "stress", "despair", "overdose", "kidnap", "poison", "spouse", "yacht", "heli",
                 "raid", "cartel", "prison", "rocket", "selftest", "adventure")

DEATH_KINDS = [("lungc", ("lung cancer",)), ("pancc", ("pancreatic cancer",)), ("bloodc", ("leukaemia",)),
               ("colonc", ("colon cancer",)), ("sexc", ("breast cancer", "prostate cancer")), ("liverf", ("liver failure",)),
               ("kidneyf", ("kidney failure",)), ("heartf", ("heart failure",)), ("als", ("motor neurone",)),
               ("alz", ("alzheimer",)), ("burnout", ("board meeting",)), ("stress", ("massive stroke",)),
               ("despair", ("loneliness and unhappiness",)), ("overdose", ("overdose",)), ("kidnap", ("kidnappers",)),
               ("poison", ("found poison",)), ("spouse", ("gunman police caught",)), ("yacht", ("caught your yacht",)),
               ("heli", ("helicopter came down",)), ("raid", ("raided your home",)), ("cartel", ("cartel you once",)),
               ("prison", ("prison fight",)), ("rocket", ("riding your own rocket",)), ("selftest", ("ageing treatment on yourself",)),
               ("adventure", ("everest", "shark cage", "walking safari", "desert rally")),
               ("bankrupt", ("creditors", "bankrupt")), ("hit", ("gunmen", "mob had warned")), ("jet", ("jet went down",)),
               ("road", ("ran a red light", "road")), ("aliens", ("mars", "ships arrived")),
               ("illness", ("left untreated", "second heart attack", "spread too far", "could not save you", "in hospital", "at home, surrounded")),
               ("maxage", ("you lived to",)), ("natural", ("heart gave out", "short illness", "collapsed at your desk"))]


# ---- visitors: people who open the game, whether or not they create an account ----
VID_RE = re.compile(r"^[A-Za-z0-9]{12,40}$")
STAGE_RANK = {"landed": 0, "played": 1, "asked": 2, "form": 3, "login": 4, "signed": 5}
LEFT_STAGES = "('landed','played','asked','form')"


def visit_mark(vid, stage, src="", device="", user_id=0, camp=""):
    """Record an anonymous visit. A visit more than 30 minutes after the last one counts as a new visit.
    Existing players are never counted: a browser that logs in is marked 'login' and left out of every visitor number."""
    if not isinstance(vid, str) or not VID_RE.match(vid) or stage not in STAGE_RANK:
        return
    t = now()
    r = q("SELECT stage, last FROM visitors WHERE vid=?", (vid,), one=True)
    if not r:
        q("INSERT OR IGNORE INTO visitors(vid,first,last,visits,stage,user_id,src,device,camp) VALUES(?,?,?,1,?,?,?,?,?)",
          (vid, t, t, stage, user_id, src[:40], device[:10], camp))
        return
    if camp:
        q("UPDATE visitors SET camp=? WHERE vid=? AND camp=''", (camp, vid))
    st = stage if STAGE_RANK[stage] > STAGE_RANK.get(r["stage"], 0) else r["stage"]
    q("UPDATE visitors SET last=?, visits=visits+?, stage=?, user_id=CASE WHEN ?>0 THEN ? ELSE user_id END WHERE vid=?",
      (t, 1 if t - r["last"] > 1800 else 0, st, user_id, user_id, vid))


def src_of(ref):
    """Where a visitor came from, as a short name: whatsapp, facebook, google... or direct."""
    h = (urlparse(ref).hostname or "").lower() if isinstance(ref, str) and ref else ""
    if not h or (SITE_DOMAIN and h.endswith(SITE_DOMAIN.split(":")[0])):
        return "direct"
    for k in ("whatsapp", "facebook", "instagram", "tiktok", "twitter", "t.co", "x.com", "google", "linkedin", "youtube", "telegram", "bing"):
        if k in h:
            return {"t.co": "x", "x.com": "x", "twitter": "x"}.get(k, k)
    return h[4:] if h.startswith("www.") else h


def visitors_overview(t, rg=None):
    def span(since, until=None):
        r = q("SELECT COUNT(*) n, SUM(stage='signed') signed, SUM(stage='login') login, SUM(stage='form') form, SUM(stage='landed') landed, "
              "SUM(stage='played') played, SUM(stage='asked') asked "
              "FROM visitors WHERE first>=? AND first<? AND stage<>'login'", (since, until or t + 1), one=True)
        return {k: (r[k] or 0) for k in ("n", "signed", "login", "form", "landed", "played", "asked")}
    rg = rg or admin_range("/", t, 14)
    days = []
    for day, d0, d1 in range_days(rg):
        r = q("SELECT COUNT(*) n, SUM(stage='signed') signed, SUM(stage IN " + LEFT_STAGES + ") lft FROM visitors WHERE first>=? AND first<? AND stage<>'login'",
              (d0, d1), one=True)
        days.append({"day": day, "n": r["n"] or 0, "signed": r["signed"] or 0, "left": r["lft"] or 0})
    srcs = [dict(r) for r in q("SELECT src, COUNT(*) n, SUM(stage='signed') signed FROM visitors WHERE first>=? AND first<? AND stage<>'login' GROUP BY src ORDER BY n DESC LIMIT 8",
                               (rg["t0"], rg["t1"]))]
    dev = {r["device"] or "?": r["n"] for r in q("SELECT device, COUNT(*) n FROM visitors WHERE first>=? AND first<? AND stage IN " + LEFT_STAGES + " GROUP BY device",
                                                  (rg["t0"], rg["t1"]))}
    since = q("SELECT MIN(first) m FROM visitors", one=True)["m"]
    rs = span(rg["t0"], rg["t1"])
    return {"d1": span(t - 86400), "d7": rs, "d30": rs, "range": rs, "all": span(0), "days": days, "srcs": srcs, "leftDevice": dev, "since": since}


# ---- marketing: campaign links and where players come from ----
CAMP_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,29}$")
CHANNELS = ["tiktok", "instagram", "facebook", "whatsapp", "x", "youtube", "creator", "poster", "ads", "other"]


def clean_camp(v):
    v = (v if isinstance(v, str) else "").strip().lower()
    return v if CAMP_RE.match(v) else ""


def marketing_report(t, days, rg=None):
    """Sign-ups, return rates and tips by where players came from, in the date range (default: the last `days` days)."""
    rg = rg or admin_range("/?days=%d" % days, t)
    since, until, days = rg["t0"], rg["t1"], rg["days"]
    camps = {r["code"]: dict(r) for r in q("SELECT * FROM campaigns")}
    users = q("SELECT u.id, u.created, u.last_seen, u.camp, "
              "(SELECT 1 FROM referrals r WHERE r.user_id=u.id) AS invited, "
              "(SELECT v.src FROM visitors v WHERE v.user_id=u.id ORDER BY v.first LIMIT 1) AS src "
              "FROM users u WHERE u.created>=? AND u.created<?", (since, until))
    ids = [u["id"] for u in users]
    act, tips = {}, {}
    if ids:
        for r in q("SELECT a.user_id, a.day FROM activity_days a JOIN users u ON u.id=a.user_id WHERE u.created>=? AND u.created<?", (since, until)):
            act.setdefault(r["user_id"], []).append(r["day"])
        for r in q("SELECT p.user_id, SUM(p.amount) a FROM payments p JOIN users u ON u.id=p.user_id "
                   "WHERE u.created>=? AND u.created<? AND p.status='paid' AND p.plan='tip' GROUP BY p.user_id", (since, until)):
            tips[r["user_id"]] = r["a"] or 0

    def source(u):
        if u["invited"]:
            return "invite"
        if u["camp"]:
            return "c:" + u["camp"]
        return "r:" + (u["src"] or "unknown")

    def back(u, n):
        if u["created"] > t - n * 86400:
            return None
        cut = time.strftime("%Y-%m-%d", time.gmtime(u["created"] + n * 86400))
        return any(d >= cut for d in act.get(u["id"], []))

    rows = {}
    for u in users:
        k = source(u)
        r = rows.setdefault(k, {"key": k, "players": 0, "e1": 0, "b1": 0, "e7": 0, "b7": 0, "active7": 0, "tips": 0.0, "tippers": 0, "visitors": 0})
        r["players"] += 1
        for n in (1, 7):
            b = back(u, n)
            if b is not None:
                r["e%d" % n] += 1
                r["b%d" % n] += 1 if b else 0
        if u["last_seen"] > t - 7 * 86400:
            r["active7"] += 1
        if tips.get(u["id"]):
            r["tips"] += tips[u["id"]]
            r["tippers"] += 1
    for v in q("SELECT camp, src, COUNT(*) n FROM visitors WHERE first>=? AND first<? AND stage<>'login' GROUP BY camp, src", (since, until)):
        k = ("c:" + v["camp"]) if v["camp"] else ("r:" + (v["src"] or "unknown"))
        r = rows.setdefault(k, {"key": k, "players": 0, "e1": 0, "b1": 0, "e7": 0, "b7": 0, "active7": 0, "tips": 0.0, "tippers": 0, "visitors": 0})
        r["visitors"] += v["n"]
    # campaigns with no traffic yet still get a row
    for c in camps.values():
        if not c["archived"]:
            rows.setdefault("c:" + c["code"], {"key": "c:" + c["code"], "players": 0, "e1": 0, "b1": 0, "e7": 0, "b7": 0, "active7": 0, "tips": 0.0, "tippers": 0, "visitors": 0})
    out_c, out_s = [], []
    for k, r in rows.items():
        if k.startswith("c:"):
            c = camps.get(k[2:])
            r.update({"code": k[2:], "name": c["name"] if c else k[2:], "channel": c["channel"] if c else "other",
                      "cost": c["cost"] if c else 0, "note": c["note"] if c else "", "created": c["created"] if c else 0,
                      "archived": c["archived"] if c else 0, "known": bool(c)})
            # all-time numbers for the cost per player, since spend is entered as a total
            r["playersAll"] = q("SELECT COUNT(*) c FROM users WHERE camp=?", (k[2:],), one=True)["c"]
            out_c.append(r)
        out_s.append(r)
    out_c.sort(key=lambda r: (r["archived"], -r["players"], -r["created"]))
    out_s.sort(key=lambda r: -r["players"])
    daily = []
    for day, d0, d1 in range_days(rg):
        n = {"camp": 0, "invite": 0, "other": 0}
        for u in users:
            if d0 <= u["created"] < d1:
                k = source(u)
                n["invite" if k == "invite" else "camp" if k.startswith("c:") else "other"] += 1
        daily.append(dict(n, day=day))
    tot = {"players": len(users), "camp": sum(1 for u in users if source(u).startswith("c:")),
           "invite": sum(1 for u in users if u["invited"]),
           "e1": sum(1 for u in users if back(u, 1) is not None), "b1": sum(1 for u in users if back(u, 1)),
           "tips": sum(tips.values()), "spend": sum(c["cost"] for c in camps.values() if not c["archived"]),
           "visitors": sum(r["visitors"] for r in rows.values())}
    return {"days": days, "from": rg["d0"], "to": rg["d1"], "campaigns": out_c, "sources": out_s, "daily": daily, "totals": tot, "channels": CHANNELS,
            "site": SITE_DOMAIN or "hustlempires.com", "now": t}


def challenge_report(t, month_offset, region):
    """The #HustlempiresChallenge check: each player's best net worth at age 40 (game month 192) in a calendar month."""
    g = time.gmtime(t)
    y, m = g.tm_year, g.tm_mon - month_offset
    while m < 1:
        m += 12
        y -= 1
    start = int(calendar.timegm((y, m, 1, 0, 0, 0)))
    end = int(calendar.timegm((y + (m == 12), m % 12 + 1, 1, 0, 0, 0)))
    best = {}
    for r in q("SELECT s.user_id, s.game, s.nw, s.month, s.ts FROM snapshots s WHERE s.month BETWEEN 189 AND 192 AND s.ts>=? AND s.ts<? "
               "AND NOT EXISTS (SELECT 1 FROM snapshots x WHERE x.user_id=s.user_id AND x.game=s.game AND x.month>s.month AND x.month<=192)",
               (start, end)):
        b = best.get(r["user_id"])
        if not b or r["nw"] > b["nw"]:
            best[r["user_id"]] = dict(r)
    regions = {}
    rows = []
    for uid, b in best.items():
        u = q("SELECT u.id, u.name, u.username, u.company, u.color, u.disabled, s.detail FROM users u LEFT JOIN stats s ON s.user_id=u.id WHERE u.id=?", (uid,), one=True)
        if not u or u["disabled"]:
            continue
        try:
            reg = (json.loads(u["detail"] or "{}") or {}).get("region") or ""
        except (TypeError, ValueError):
            reg = ""
        regions[reg] = regions.get(reg, 0) + 1
        if region and reg != region:
            continue
        rows.append({"user_id": uid, "name": u["name"], "username": u["username"], "company": u["company"], "color": u["color"],
                     "region": reg, "nw": b["nw"], "when": b["ts"], "game": b["game"]})
    rows.sort(key=lambda r: -r["nw"])
    return {"month": "%04d-%02d" % (y, m), "region": region, "regions": regions, "rows": rows[:25], "entries": len(rows), "now": t}


# ---- Meta ads: pull spend and results from the Marketing API (read only) ----
META_LOCK = threading.Lock()
LINK_CODE_RES = [re.compile(r"/go/([A-Za-z0-9-]{1,30})"), re.compile(r"[?&]c=([A-Za-z0-9-]{1,30})")]


def meta_ready():
    return bool(META_TOKEN and META_ACCOUNT)


def graph_get(path, params=None, url=None):
    """One read-only Graph API call. The token never appears in errors or logs."""
    if url is None:
        params = dict(params or {})
        params.setdefault("access_token", META_TOKEN)
        if META_APP_SECRET:
            params["appsecret_proof"] = hmac.new(META_APP_SECRET.encode(), params["access_token"].encode(), hashlib.sha256).hexdigest()
        url = "%s/%s/%s?%s" % (META_URL, META_API, path.lstrip("/"), urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Hustlempires/1"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = (json.loads(e.read().decode("utf-8")) or {}).get("error") or {}
        except Exception:
            err = {}
        msg = err.get("error_user_msg") or err.get("message") or ("HTTP %s" % e.code)
        msg = re.sub(r"EAA[A-Za-z0-9]{20,}", "[token]", msg)
        raise RuntimeError("Meta said: %s (code %s)" % (msg[:300], err.get("code", e.code)))
    except urllib.error.URLError as e:
        raise RuntimeError("Could not reach Meta: %s" % getattr(e, "reason", e))


def graph_post(path, data):
    """One Graph API write (used only for publishing posts to the Page and Instagram)."""
    data = dict(data)
    data.setdefault("access_token", META_TOKEN)
    if META_APP_SECRET:
        data["appsecret_proof"] = hmac.new(META_APP_SECRET.encode(), data["access_token"].encode(), hashlib.sha256).hexdigest()
    url = "%s/%s/%s" % (META_URL, META_API, path.lstrip("/"))
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST",
                                 headers={"Accept": "application/json", "User-Agent": "Hustlempires/1",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = (json.loads(e.read().decode("utf-8")) or {}).get("error") or {}
        except Exception:
            err = {}
        msg = re.sub(r"EAA[A-Za-z0-9]{20,}", "[token]", err.get("error_user_msg") or err.get("message") or ("HTTP %s" % e.code))
        raise RuntimeError("Meta said: %s (code %s)" % (msg[:300], err.get("code", e.code)))
    except urllib.error.URLError as e:
        raise RuntimeError("Could not reach Meta: %s" % getattr(e, "reason", e))


def graph_delete(obj):
    try:
        graph_post(obj, {"method": "delete"})
    except Exception as e:
        print("Could not remove %s on Meta: %s" % (obj, e), flush=True)


def graph_all(path, params):
    """Follow Meta's pages of results (at most 40 pages)."""
    out, d, n = [], graph_get(path, params), 0
    while True:
        out.extend(d.get("data") or [])
        nxt = ((d.get("paging") or {}).get("next"))
        n += 1
        if not nxt or n >= 40:
            return out
        d = graph_get(None, url=nxt)


def link_code(blob):
    for rx in LINK_CODE_RES:
        m = rx.search(blob or "")
        if m:
            c = clean_camp(m.group(1).lower())
            if c:
                return c
    return ""


def meta_sync(full=False):
    """Fetch the last days of ad results (90 days the first time) and which campaign link each ad points to."""
    if not meta_ready():
        return False
    if not META_LOCK.acquire(blocking=False):
        return False
    t = now()
    try:
        acct = "act_" + META_ACCOUNT
        info = graph_get(acct, {"fields": "name,currency,timezone_name,account_status"})
        last = q("SELECT MAX(day) d FROM meta_daily", one=True)["d"]
        back = 90 if full or not last else 4
        since = time.strftime("%Y-%m-%d", time.gmtime(t - back * 86400))
        until = time.strftime("%Y-%m-%d", time.gmtime(t + 86400))
        rows = graph_all(acct + "/insights", {
            "level": "ad", "time_increment": 1, "limit": 500,
            "fields": "campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,spend,impressions,reach,clicks,inline_link_clicks",
            "time_range": json.dumps({"since": since, "until": until})})
        ads = graph_all(acct + "/ads", {"limit": 200, "fields": "id,name,campaign_id,adset_id,status,effective_status,creative{object_story_spec,asset_feed_spec,url_tags}"})
        camps = graph_all(acct + "/campaigns", {"limit": 200, "fields": "id,name,status,effective_status,objective,daily_budget,lifetime_budget"})
        sets = graph_all(acct + "/adsets", {"limit": 200, "fields": "id,name,campaign_id,status,effective_status,daily_budget,lifetime_budget,end_time"})

        def write(db):
            db.execute("DELETE FROM meta_daily WHERE day>=?", (since,))
            for r in rows:
                n = lambda k: int(float(r.get(k) or 0))
                db.execute("INSERT OR REPLACE INTO meta_daily(day,ad_id,campaign_id,campaign_name,adset_name,ad_name,spend,impressions,reach,clicks,link_clicks,adset_id) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (r.get("date_start", "")[:10], str(r.get("ad_id", "")), str(r.get("campaign_id", "")),
                           (r.get("campaign_name") or "")[:120], (r.get("adset_name") or "")[:120], (r.get("ad_name") or "")[:120],
                           float(r.get("spend") or 0), n("impressions"), n("reach"), n("clicks"), n("inline_link_clicks"), str(r.get("adset_id", ""))))
            for a in ads:
                code = link_code(json.dumps(a.get("creative") or {}))
                db.execute("INSERT INTO meta_ads(ad_id,campaign_id,name,status,code,updated,adset_id,onoff) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(ad_id) DO UPDATE SET "
                           "campaign_id=excluded.campaign_id,name=excluded.name,status=excluded.status,code=excluded.code,updated=excluded.updated,"
                           "adset_id=excluded.adset_id,onoff=excluded.onoff",
                           (str(a.get("id", "")), str(a.get("campaign_id", "")), (a.get("name") or "")[:120], a.get("effective_status") or "", code, t,
                            str(a.get("adset_id", "")), a.get("status") or ""))
            for a in sets:
                db.execute("INSERT INTO meta_adsets(adset_id,campaign_id,name,onoff,status,daily_budget,lifetime_budget,end_time,updated) VALUES(?,?,?,?,?,?,?,?,?) "
                           "ON CONFLICT(adset_id) DO UPDATE SET campaign_id=excluded.campaign_id,name=excluded.name,onoff=excluded.onoff,status=excluded.status,"
                           "daily_budget=excluded.daily_budget,lifetime_budget=excluded.lifetime_budget,end_time=excluded.end_time,updated=excluded.updated",
                           (str(a.get("id", "")), str(a.get("campaign_id", "")), (a.get("name") or "")[:120], a.get("status") or "", a.get("effective_status") or "",
                            float(a.get("daily_budget") or 0) / 100, float(a.get("lifetime_budget") or 0) / 100, a.get("end_time") or "", t))
            for c in camps:
                cid = str(c.get("id", ""))
                codes = [r["code"] for r in db.execute("SELECT code FROM meta_ads WHERE campaign_id=? AND code<>''", (cid,)).fetchall()]
                auto = max(set(codes), key=codes.count) if codes else ""
                db.execute("INSERT INTO meta_campaigns(campaign_id,name,status,code,updated,onoff,objective,daily_budget,lifetime_budget) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(campaign_id) DO UPDATE SET "
                           "name=excluded.name,status=excluded.status,updated=excluded.updated,code=CASE WHEN meta_campaigns.manual=1 THEN meta_campaigns.code ELSE excluded.code END,"
                           "onoff=excluded.onoff,objective=excluded.objective,daily_budget=excluded.daily_budget,lifetime_budget=excluded.lifetime_budget",
                           (cid, (c.get("name") or "")[:120], c.get("effective_status") or "", auto, t, c.get("status") or "", c.get("objective") or "",
                            float(c.get("daily_budget") or 0) / 100, float(c.get("lifetime_budget") or 0) / 100))
            # anything Meta no longer lists was deleted there
            for tbl in ("meta_campaigns", "meta_adsets", "meta_ads"):
                db.execute("UPDATE %s SET status='DELETED' WHERE updated<?" % tbl, (t,))
        tx(write)
        meta_set("meta_sync", json.dumps({"at": t, "ok": True, "rows": len(rows), "name": info.get("name") or "", "currency": info.get("currency") or "",
                                           "tz": info.get("timezone_name") or "", "status": info.get("account_status")}))
        try:
            dbg = graph_get("debug_token", {"input_token": META_TOKEN}).get("data") or {}
            meta_set("meta_token", json.dumps({"expires": dbg.get("expires_at") or 0, "valid": dbg.get("is_valid"), "scopes": dbg.get("scopes") or []}))
        except Exception:
            pass
        page_discover()
        return True
    except Exception as e:
        old = meta_get_state()
        old.update({"errorAt": t, "error": str(e)[:400]})
        meta_set("meta_sync", json.dumps(old))
        print("Meta ads sync failed: %s" % e, flush=True)
        return False
    finally:
        META_LOCK.release()


def meta_get_state():
    try:
        return json.loads(meta_get("meta_sync") or "{}")
    except (TypeError, ValueError):
        return {}


def meta_sweeper():
    """Pull ad results shortly after start, then every hour."""
    time.sleep(20)
    first = True
    while True:
        if meta_ready():
            meta_sync(full=first)
            first = False
        time.sleep(3600)


# ---- scheduled posts: Facebook Page and Instagram ----
POST_SCOPES = ["pages_show_list", "pages_read_engagement", "pages_manage_posts", "instagram_basic", "instagram_content_publish"]
STATS_SCOPES = ["read_insights", "instagram_manage_insights"]
POST_LOCK = threading.Lock()
MEDIA_TYPES = {"image/jpeg": "jpg", "video/mp4": "mp4", "video/quicktime": "mov"}
MEDIA_MAX = {"jpg": 8 * 1024 * 1024, "mp4": 300 * 1024 * 1024, "mov": 300 * 1024 * 1024}
MEDIA_RE = re.compile(r"^[a-z0-9]{24}\.(jpg|mp4|mov)$")


def page_discover():
    """Find the Facebook Page (and the Instagram account linked to it) this token can post to. No tokens are stored."""
    try:
        pages = graph_all("me/accounts", {"fields": "id,name,instagram_business_account{id,username}", "limit": 50})
        pick = next((p for p in pages if META_PAGE and p.get("id") == META_PAGE), pages[0] if pages else None)
        if not pick:
            meta_set("meta_pages", json.dumps({"at": now(), "error": "No Facebook Page is shared with this token yet."}))
            return None
        ig = pick.get("instagram_business_account") or {}
        info = {"at": now(), "page": {"id": pick.get("id"), "name": pick.get("name") or ""},
                "ig": {"id": ig.get("id"), "username": ig.get("username") or ""} if ig.get("id") else None,
                "pages": [{"id": p.get("id"), "name": p.get("name")} for p in pages][:10]}
        meta_set("meta_pages", json.dumps(info))
        return info
    except Exception as e:
        meta_set("meta_pages", json.dumps({"at": now(), "error": str(e)[:300]}))
        return None


def pages_info():
    try:
        return json.loads(meta_get("meta_pages") or "{}")
    except (TypeError, ValueError):
        return {}


def page_token(page_id):
    return (graph_get(page_id, {"fields": "access_token"}) or {}).get("access_token") or ""


def media_url(name):
    return "https://%s/media/%s" % (SITE_DOMAIN or "hustlempires.com", name)


def post_caption(p, platform):
    cap = p["caption"]
    if p["link"]:
        code = ("fb-post-%d" if platform == "fb" else "ig-post-%d") % p["id"]
        site = SITE_DOMAIN or "hustlempires.com"
        cap = (cap.rstrip() + "\n\n" if cap.strip() else "") + ("Play free: https://%s/go/%s" % (site, code) if platform == "fb" else "Play free at %s/go/%s" % (site, code))
    return cap


def post_set(pid, **kw):
    kw["updated"] = now()
    q("UPDATE posts SET %s WHERE id=?" % ", ".join("%s=?" % k for k in kw), tuple(kw.values()) + (pid,))


def publish_post(p):
    """Move one due post forward: publish to Facebook, and create, check or publish its Instagram container."""
    info = pages_info()
    page = (info.get("page") or {}).get("id")
    if not page:
        raise RuntimeError(info.get("error") or "No Facebook Page found for this token.")
    ptok = page_token(page)
    if not ptok:
        raise RuntimeError("Meta did not give a Page token. Check the token has pages_manage_posts and the Page is assigned to hustle-server.")
    mu = media_url(p["media"]) if p["media"] else ""
    if p["fb_status"] == "scheduled":
        try:
            if p["kind"] == "photo":
                r = graph_post(page + "/photos", {"url": mu, "caption": post_caption(p, "fb"), "access_token": ptok})
                pid = r.get("post_id") or r.get("id") or ""
                post_set(p["id"], fb_status="posted", fb_id=pid, fb_url="https://www.facebook.com/" + pid, fb_error="")
            elif p["kind"] == "video":
                r = graph_post(page + "/videos", {"file_url": mu, "description": post_caption(p, "fb"), "access_token": ptok})
                post_set(p["id"], fb_status="posted", fb_id=r.get("id", ""), fb_url="https://www.facebook.com/%s/videos/%s" % (page, r.get("id", "")), fb_error="")
            else:
                d = {"message": post_caption(p, "fb"), "access_token": ptok}
                if p["link"]:
                    d["link"] = "https://%s/go/fb-post-%d" % (SITE_DOMAIN or "hustlempires.com", p["id"])
                r = graph_post(page + "/feed", d)
                post_set(p["id"], fb_status="posted", fb_id=r.get("id", ""), fb_url="https://www.facebook.com/" + r.get("id", ""), fb_error="")
        except Exception as e:
            post_set(p["id"], fb_status="failed", fb_error=str(e)[:300])
    if p["ig_status"] in ("scheduled", "processing"):
        ig = (info.get("ig") or {}).get("id")
        try:
            if not ig:
                raise RuntimeError("No Instagram business account is linked to the Facebook Page.")
            cont = p["ig_container"]
            if p["ig_status"] == "scheduled":
                d = {"caption": post_caption(p, "ig"), "access_token": ptok}
                if p["kind"] == "video":
                    d.update({"media_type": "REELS", "video_url": mu, "share_to_feed": "true"})
                else:
                    d["image_url"] = mu
                cont = graph_post(ig + "/media", d).get("id", "")
                post_set(p["id"], ig_status="processing", ig_container=cont, ig_tries=0, ig_error="")
            st = graph_get(cont, {"fields": "status_code,status", "access_token": ptok})
            code = st.get("status_code") or ""
            if code == "FINISHED":
                mid = graph_post(ig + "/media_publish", {"creation_id": cont, "access_token": ptok}).get("id", "")
                link = ""
                try:
                    link = graph_get(mid, {"fields": "permalink", "access_token": ptok}).get("permalink") or ""
                except Exception:
                    pass
                post_set(p["id"], ig_status="posted", ig_id=mid, ig_url=link, ig_error="")
            elif code in ("ERROR", "EXPIRED"):
                raise RuntimeError("Instagram could not process the file: %s" % (st.get("status") or code))
            else:
                tries = q("SELECT ig_tries FROM posts WHERE id=?", (p["id"],), one=True)["ig_tries"] + 1
                if tries > 80:
                    raise RuntimeError("Instagram took more than 40 minutes to process the video.")
                post_set(p["id"], ig_tries=tries)
        except Exception as e:
            post_set(p["id"], ig_status="failed", ig_error=str(e)[:300])


def post_sweeper():
    """Every 30 seconds, publish posts that are due and move Instagram videos along."""
    time.sleep(15)
    while True:
        try:
            if meta_ready() and POST_LOCK.acquire(blocking=False):
                try:
                    if not pages_info().get("page"):
                        page_discover()
                    for p in q("SELECT * FROM posts WHERE due<=? AND (fb_status='scheduled' OR ig_status IN ('scheduled','processing')) ORDER BY due LIMIT 10", (now(),)):
                        try:
                            publish_post(p)
                        except Exception as e:
                            msg = str(e)[:300]
                            q("UPDATE posts SET fb_status=CASE WHEN fb_status='scheduled' THEN 'failed' ELSE fb_status END, "
                              "fb_error=CASE WHEN fb_status='scheduled' THEN ? ELSE fb_error END, "
                              "ig_status=CASE WHEN ig_status IN ('scheduled','processing') THEN 'failed' ELSE ig_status END, "
                              "ig_error=CASE WHEN ig_status IN ('scheduled','processing') THEN ? ELSE ig_error END, updated=? WHERE id=?",
                              (msg, msg, now(), p["id"]))
                    # tidy: media of posts finished more than 14 days ago
                    for r in q("SELECT id, media FROM posts WHERE media<>'' AND updated<? AND fb_status NOT IN ('scheduled') "
                               "AND ig_status NOT IN ('scheduled','processing')", (now() - 14 * 86400,)):
                        if not q("SELECT 1 FROM posts WHERE media=? AND (fb_status='scheduled' OR ig_status IN ('scheduled','processing'))", (r["media"],), one=True):
                            try:
                                os.remove(os.path.join(MEDIA_DIR, r["media"]))
                            except OSError:
                                pass
                finally:
                    POST_LOCK.release()
        except Exception as e:
            print("Post sweeper problem: %s" % e, flush=True)
        time.sleep(30)


# ---- how each published post performed on Facebook and Instagram ----
BAD_METRICS = set()      # metric names Meta rejected for an object type; skipped from then on
STATS_LOCK = threading.Lock()


def _metric_value(v):
    if isinstance(v, dict):
        return sum(x for x in v.values() if isinstance(x, (int, float)))
    return v if isinstance(v, (int, float)) else 0


def graph_metrics(obj, edge, kind, names, tok):
    """Ask Meta for several insight metrics at once; if it refuses one, ask one by one and remember which names it rejects."""
    names = [n for n in names if (kind, n) not in BAD_METRICS]
    out = {}
    if not names:
        return out

    def read(ns):
        d = graph_get("%s/%s" % (obj, edge), {"metric": ",".join(ns), "access_token": tok})
        for m in d.get("data") or []:
            vals = m.get("values") or []
            v = vals[-1].get("value") if vals else m.get("total_value", {}).get("value")
            if v is None and isinstance(m.get("total_value"), dict):
                v = m["total_value"].get("value")
            out[m.get("name")] = _metric_value(v)
    try:
        read(names)
    except RuntimeError:
        for n in names:
            try:
                read([n])
            except RuntimeError as e:
                if "(code 100)" in str(e) or "metric" in str(e).lower():
                    BAD_METRICS.add((kind, n))
    return out


def graph_fields(obj, fields, tok):
    out = {}
    for f in fields:
        try:
            out.update(graph_get(obj, {"fields": f, "access_token": tok}))
        except RuntimeError:
            pass
    return out


def first(d, *names):
    for n in names:
        if d.get(n):
            return d[n]
    return 0


def fb_post_stats(p, tok):
    if p["kind"] == "video":
        vid = p["fb_id"]
        f = graph_fields(vid, ["likes.summary(true).limit(0)", "comments.summary(true).limit(0)", "views"], tok)
        m = graph_metrics(vid, "video_insights", "fbvideo",
                          ["total_video_views", "total_video_media_view_unique", "total_video_impressions_unique",
                           "total_video_avg_time_watched", "total_video_reactions_by_type_total", "total_video_stories_by_action_type"], tok)
        acts = m.get("total_video_stories_by_action_type") or 0
        return {"views": first(m, "total_video_views") or f.get("views") or 0,
                "reach": first(m, "total_video_media_view_unique", "total_video_impressions_unique"),
                "likes": first(m, "total_video_reactions_by_type_total") or ((f.get("likes") or {}).get("summary") or {}).get("total_count", 0),
                "comments": ((f.get("comments") or {}).get("summary") or {}).get("total_count", 0),
                "shares": 0, "saves": 0,
                "watch": round((m.get("total_video_avg_time_watched") or 0) / 1000.0, 1),
                "clicks": 0, "actions": acts}
    pid = p["fb_id"]
    f = graph_fields(pid, ["reactions.summary(total_count).limit(0)", "comments.summary(total_count).limit(0)", "shares"], tok)
    m = graph_metrics(pid, "insights", "fbpost",
                      ["post_media_view", "post_total_media_view_unique", "post_impressions", "post_impressions_unique",
                       "post_clicks", "post_video_views", "post_video_avg_time_watched"], tok)
    reach = first(m, "post_total_media_view_unique", "post_impressions_unique")
    return {"views": first(m, "post_media_view", "post_impressions", "post_video_views") or reach,   # Meta stopped some view counts; reach is the closest
            "reach": reach,
            "likes": ((f.get("reactions") or {}).get("summary") or {}).get("total_count", 0),
            "comments": ((f.get("comments") or {}).get("summary") or {}).get("total_count", 0),
            "shares": (f.get("shares") or {}).get("count", 0), "saves": 0,
            "watch": round((m.get("post_video_avg_time_watched") or 0) / 1000.0, 1),
            "clicks": m.get("post_clicks") or 0}


def ig_post_stats(p, tok):
    mid = p["ig_id"]
    f = graph_fields(mid, ["like_count,comments_count,media_product_type"], tok)
    reel = (f.get("media_product_type") or "").upper() == "REELS" or p["kind"] == "video"
    names = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions"]
    if reel:
        names += ["ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]
    m = graph_metrics(mid, "insights", "igreel" if reel else "igpost", names, tok)
    return {"views": m.get("views") or 0, "reach": m.get("reach") or 0,
            "likes": m.get("likes") or f.get("like_count") or 0,
            "comments": m.get("comments") or f.get("comments_count") or 0,
            "shares": m.get("shares") or 0, "saves": m.get("saved") or 0,
            "watch": round((m.get("ig_reels_avg_watch_time") or 0) / 1000.0, 1),
            "clicks": 0, "interactions": m.get("total_interactions") or 0}


def stats_refresh(force_ids=()):
    """Read the numbers for published posts: hourly for the first 3 days, then every 6 hours up to 30 days, then daily up to 90 days."""
    if not meta_ready() or not STATS_LOCK.acquire(blocking=False):
        return 0
    n = 0
    try:
        info = pages_info()
        page = (info.get("page") or {}).get("id")
        if not page:
            return 0
        tok = page_token(page)
        if not tok:
            return 0
        t = now()
        for p in q("SELECT * FROM posts WHERE (fb_status='posted' OR ig_status='posted') AND due>? ORDER BY due DESC LIMIT 60", (t - 90 * 86400,)):
            age = t - p["due"]
            gap = 3600 if age < 3 * 86400 else 6 * 3600 if age < 30 * 86400 else 86400
            for pf, fn in (("fb", fb_post_stats), ("ig", ig_post_stats)):
                if p[pf + "_status"] != "posted" or not p[pf + "_id"]:
                    continue
                old = q("SELECT fetched FROM post_stats WHERE post_id=? AND platform=?", (p["id"], pf), one=True)
                if old and t - old["fetched"] < gap and p["id"] not in force_ids:
                    continue
                try:
                    d = fn(p, tok)
                    q("INSERT INTO post_stats(post_id,platform,fetched,data,error) VALUES(?,?,?,?,'') ON CONFLICT(post_id,platform) DO UPDATE SET "
                      "fetched=excluded.fetched, data=excluded.data, error=''", (p["id"], pf, t, json.dumps(d)))
                except Exception as e:
                    q("INSERT INTO post_stats(post_id,platform,fetched,error) VALUES(?,?,?,?) ON CONFLICT(post_id,platform) DO UPDATE SET "
                      "fetched=excluded.fetched, error=excluded.error", (p["id"], pf, t, str(e)[:300]))
                n += 1
    finally:
        STATS_LOCK.release()
    return n


def stats_sweeper():
    time.sleep(60)
    while True:
        try:
            stats_refresh()
        except Exception as e:
            print("Post stats problem: %s" % e, flush=True)
        time.sleep(900)


# ---- running ads from the admin: boost a published post, or a new ad from a photo/video ----
AD_DAILY_CAP = env_int("HUSTLE_AD_DAILY_CAP", 2000)   # KSh; no ad can be set to spend more than this a day
AD_MAX_DAYS = 30
AD_CTAS = {"PLAY_GAME": "Play game", "LEARN_MORE": "Learn more", "SIGN_UP": "Sign up"}
AD_MAX_SETS, AD_MAX_PER_SET, AD_MAX_ADS = 5, 6, 12   # one publish: ad sets, ads in each, ads in all
AD_MAX_INTERESTS = 50
AD_COUNTRIES = {"KE": "Kenya", "UG": "Uganda", "TZ": "Tanzania", "RW": "Rwanda", "NG": "Nigeria", "GH": "Ghana", "ZA": "South Africa"}
AD_LOCK = threading.Lock()


def ad_set(aid, **kw):
    kw["updated"] = now()
    q("UPDATE ad_runs SET %s WHERE id=?" % ", ".join("%s=?" % k for k in kw), tuple(kw.values()) + (aid,))


def ad_link(aid):
    return "https://%s/go/ad-%d" % (SITE_DOMAIN or "hustlempires.com", aid)


def account_currency():
    return (meta_get_state() or {}).get("currency") or ""


def fb_post_id_for(p):
    """The Facebook post behind a published post (videos are stored by video id)."""
    if p["kind"] != "video":
        return p["fb_id"]
    page = (pages_info().get("page") or {}).get("id")
    tok = page_token(page) if page else ""
    try:
        d = graph_get(p["fb_id"], {"fields": "post_id", "access_token": tok})
        if d.get("post_id"):
            return d["post_id"] if "_" in d["post_id"] else "%s_%s" % (page, d["post_id"])
    except RuntimeError:
        pass
    raise RuntimeError("Meta did not say which Page post this video belongs to. Boost this video from Ads Manager, or run it as a new ad.")


AD_OBJECTIVES = {"OUTCOME_TRAFFIC": "Traffic: people tap through to the game", "OUTCOME_AWARENESS": "Awareness: show it to as many people as possible"}


def targeting_spec(r):
    """Meta targeting from an ad run (or a saved audience): countries, ages, gender, interests and placements."""
    tg = {"geo_locations": {"countries": [x for x in (r["countries"] or "KE").split(",") if x]},
          "age_min": int(r["age_min"]), "age_max": int(r["age_max"]), "targeting_automation": {"advantage_audience": 0}}
    if r["genders"] in ("1", "2"):
        tg["genders"] = [int(r["genders"])]
    try:
        ints = json.loads(r["interests"] or "[]")
    except (TypeError, ValueError):
        ints = []
    ints = [{"id": str(i["id"]), "name": str(i.get("name") or "")} for i in ints if isinstance(i, dict) and re.match(r"^\d{5,25}$", str(i.get("id") or ""))][:AD_MAX_INTERESTS]
    if ints:
        tg["flexible_spec"] = [{"interests": ints}]
    if r["platforms"] in ("facebook", "instagram"):
        tg["publisher_platforms"] = [r["platforms"]]
    return tg


def ad_build(r):
    """Create whatever this run needs on Meta (a new campaign and/or ad set, then the creative and ad), paused, then switch
    on only what it made. If a step fails, remove only what this run made; existing campaigns and ad sets are never touched."""
    r = dict(r)
    acct = "act_" + META_ACCOUNT
    info = pages_info()
    page = (info.get("page") or {}).get("id")
    ig = (info.get("ig") or {}).get("id")
    if not page:
        raise RuntimeError("No Facebook Page found for this token.")
    objective = r.get("objective") or "OUTCOME_TRAFFIC"
    try:
        if not r["campaign_id"]:
            c = {"name": r.get("campaign_name") or "Hustlempires · %s" % r["name"], "objective": objective, "status": "PAUSED",
                 "special_ad_categories": "[]", "buying_type": "AUCTION"}
            if r.get("budget_level") == "adset":
                c["is_adset_budget_sharing_enabled"] = "false"
            else:
                c.update({"daily_budget": str(r["daily_kes"] * 100), "bid_strategy": "LOWEST_COST_WITHOUT_CAP"})
            c = graph_post(acct + "/campaigns", c)
            ad_set(r["id"], campaign_id=c["id"], made_campaign=1); r.update(campaign_id=c["id"], made_campaign=1)
        if not r["adset_id"]:
            a = {"name": r.get("adset_name") or "%s · %s" % (r["name"], ", ".join(AD_COUNTRIES.get(x, x) for x in r["countries"].split(","))),
                 "campaign_id": r["campaign_id"], "status": "PAUSED", "billing_event": "IMPRESSIONS",
                 "optimization_goal": "REACH" if objective == "OUTCOME_AWARENESS" else "LINK_CLICKS",
                 "targeting": json.dumps(targeting_spec(r)), "start_time": str(r["start_ts"]), "end_time": str(r["end_ts"])}
            if objective != "OUTCOME_AWARENESS":
                a["destination_type"] = "WEBSITE"
            if r.get("adset_daily"):
                a.update({"daily_budget": str(r["adset_daily"] * 100), "bid_strategy": "LOWEST_COST_WITHOUT_CAP"})
            a = graph_post(acct + "/adsets", a)
            ad_set(r["id"], adset_id=a["id"], made_adset=1); r.update(adset_id=a["id"], made_adset=1)
        if not r["creative_id"]:
            link = ad_link(r["id"])
            cta = {"type": r["cta"], "value": {"link": link}}
            if r["kind"] == "boost_fb":
                p = q("SELECT * FROM posts WHERE id=?", (r["post_id"],), one=True)
                spec = {"name": r["name"], "object_story_id": fb_post_id_for(p)}
            elif r["kind"] == "boost_ig":
                p = q("SELECT * FROM posts WHERE id=?", (r["post_id"],), one=True)
                if not ig:
                    raise RuntimeError("No Instagram account is linked to the Page.")
                spec = {"name": r["name"], "object_id": page, "instagram_user_id": ig,
                        "source_instagram_media_id": p["ig_id"], "call_to_action": json.dumps(cta)}
            else:
                story = {"page_id": page}
                if ig:
                    story["instagram_user_id"] = ig
                if r["media"].endswith(".jpg"):
                    with open(os.path.join(MEDIA_DIR, r["media"]), "rb") as f:
                        img = graph_post(acct + "/adimages", {"bytes": base64.b64encode(f.read()).decode()})
                    h = list((img.get("images") or {}).values())[0]["hash"]
                    story["link_data"] = {"link": link, "message": r["caption"], "image_hash": h, "call_to_action": cta}
                    if r["headline"]:
                        story["link_data"]["name"] = r["headline"]
                else:
                    if not r["video_id"]:
                        v = graph_post(acct + "/advideos", {"file_url": media_url(r["media"]), "name": r["name"]})
                        ad_set(r["id"], video_id=v["id"], status="processing", tries=0)
                        return "processing"
                    v = graph_get(r["video_id"], {"fields": "status,picture"})
                    st = ((v.get("status") or {}).get("video_status") or "").lower()
                    if st in ("error", "expired"):
                        raise RuntimeError("Meta could not process the video for the ad.")
                    if st != "ready" or not v.get("picture"):
                        tries = (r["tries"] or 0) + 1
                        if tries > 80:
                            raise RuntimeError("Meta took more than 40 minutes to process the video.")
                        ad_set(r["id"], status="processing", tries=tries)
                        return "processing"
                    story["video_data"] = {"video_id": r["video_id"], "message": r["caption"], "image_url": v["picture"], "call_to_action": cta}
                    if r["headline"]:
                        story["video_data"]["title"] = r["headline"]
                spec = {"name": r["name"], "object_story_spec": json.dumps(story)}
            cr = graph_post(acct + "/adcreatives", spec)
            ad_set(r["id"], creative_id=cr["id"]); r.update(creative_id=cr["id"])
        if not r["ad_id"]:
            ad = graph_post(acct + "/ads", {"name": r["name"], "adset_id": r["adset_id"],
                                            "creative": json.dumps({"creative_id": r["creative_id"]}), "status": "PAUSED"})
            ad_set(r["id"], ad_id=ad["id"]); r.update(ad_id=ad["id"])
        graph_post(r["ad_id"], {"status": "ACTIVE"})
        if r.get("batch"):
            # an ad in a batch also switches on the campaign and ad set its batch made, so it can start delivering
            if not r.get("made_adset") and q("SELECT 1 FROM ad_runs WHERE batch=? AND made_adset=1 AND adset_id=? AND id<>?", (r["batch"], r["adset_id"], r["id"]), one=True):
                graph_post(r["adset_id"], {"status": "ACTIVE"})
            if not r.get("made_campaign") and q("SELECT 1 FROM ad_runs WHERE batch=? AND made_campaign=1 AND campaign_id=? AND id<>?", (r["batch"], r["campaign_id"], r["id"]), one=True):
                graph_post(r["campaign_id"], {"status": "ACTIVE"})
        if r.get("made_adset"):
            graph_post(r["adset_id"], {"status": "ACTIVE"})
        if r.get("made_campaign"):
            graph_post(r["campaign_id"], {"status": "ACTIVE"})
        ad_set(r["id"], status="active", error="")
        return "active"
    except Exception as e:
        if r.get("batch") and (r.get("made_campaign") or r.get("made_adset")):
            # other ads in this batch already sit in the campaign or ad set this ad made: keep those, hand them over
            sib_c = r.get("made_campaign") and r.get("campaign_id") and q("SELECT id FROM ad_runs WHERE batch=? AND campaign_id=? AND id<>? AND status<>'failed' ORDER BY id LIMIT 1",
                                                                          (r["batch"], r["campaign_id"], r["id"]), one=True)
            sib_s = r.get("made_adset") and r.get("adset_id") and q("SELECT id FROM ad_runs WHERE batch=? AND adset_id=? AND id<>? AND status<>'failed' ORDER BY id LIMIT 1",
                                                                       (r["batch"], r["adset_id"], r["id"]), one=True)
            if sib_c:
                if r.get("budget_level") == "adset":
                    ad_set(sib_c["id"], made_campaign=1)
                else:
                    ad_set(sib_c["id"], made_campaign=1, daily_kes=r.get("daily_kes") or 0)
                ad_set(r["id"], made_campaign=0)
                r["made_campaign"] = 0
            if sib_s:
                if r.get("adset_daily"):
                    ad_set(sib_s["id"], made_adset=1, adset_daily=r["adset_daily"], daily_kes=r["adset_daily"])
                else:
                    ad_set(sib_s["id"], made_adset=1)
                ad_set(r["id"], made_adset=0)
                r["made_adset"] = 0
        if r.get("made_campaign") and r.get("campaign_id"):
            graph_delete(r["campaign_id"])      # removes its ad set and ad too
            ad_set(r["id"], campaign_id="", adset_id="", creative_id="", ad_id="")
        elif r.get("made_adset") and r.get("adset_id"):
            graph_delete(r["adset_id"])
            ad_set(r["id"], adset_id="", creative_id="", ad_id="")
        elif r.get("ad_id"):
            graph_delete(r["ad_id"])
            ad_set(r["id"], ad_id="")
        ad_set(r["id"], status="failed", error=str(e)[:300])
        raise


def clean_audience(au):
    """Countries, ages, gender, interests and placements, checked."""
    cs = [c for c in (au.get("countries") or []) if c in AD_COUNTRIES][:7] or ["KE"]
    def num(v, df):
        try:
            return max(13, min(65, int(v)))
        except (TypeError, ValueError):
            return df
    lo = num(au.get("age_min"), 18)
    hi = max(lo, num(au.get("age_max"), 45))
    g = str(au.get("genders") or "")
    ints = []
    for i in (au.get("interests") or [])[:AD_MAX_INTERESTS]:
        if isinstance(i, dict) and re.match(r"^\d{5,25}$", str(i.get("id") or "")):
            ints.append({"id": str(i["id"]), "name": clean_text(i.get("name"), 80)})
    return {"countries": ",".join(cs), "age_min": lo, "age_max": hi, "genders": g if g in ("1", "2") else "",
            "interests": json.dumps(ints), "platforms": au.get("platforms") if au.get("platforms") in ("all", "facebook", "instagram") else "all"}


def interest_search(qtext):
    d = graph_get("search", {"type": "adinterest", "q": qtext[:60], "limit": 20, "locale": "en_US"})
    out = []
    for i in d.get("data") or []:
        out.append({"id": str(i.get("id")), "name": i.get("name") or "", "lo": i.get("audience_size_lower_bound") or i.get("audience_size") or 0,
                    "hi": i.get("audience_size_upper_bound") or 0, "path": " › ".join((i.get("path") or [])[:-1]), "topic": i.get("topic") or ""})
    return out


PIXEL_CODE = "<!-- Meta Pixel --><script>!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');fbq('init','%s');fbq('track','PageView');</script><!-- End Meta Pixel -->"


def pixel_id():
    v = meta_get("pixel_id") or ""
    return v if re.match(r"^\d{8,20}$", v) else ""


def interests_invalid(r):
    """Interests in an audience that Meta no longer lets ads target (old or merged interests can still turn up in search)."""
    try:
        ints = [i for i in json.loads(r.get("interests") or "[]") if isinstance(i, dict) and i.get("id")]
    except (TypeError, ValueError):
        return []
    if not ints:
        return []
    try:
        d = graph_get("search", {"type": "adinterestvalid", "interest_fbid_list": json.dumps([str(i["id"]) for i in ints])})
    except RuntimeError:
        return []
    bad = {str(x.get("id")) for x in (d.get("data") or []) if x.get("valid") is False}
    return [{"id": str(i["id"]), "name": i.get("name") or str(i["id"])} for i in ints if str(i["id"]) in bad]


def audience_estimate(r):
    bad = interests_invalid(r)
    if bad:
        return {"error": "Meta no longer accepts %s. Remove %s and try again." % (", ".join(b["name"] for b in bad), "it" if len(bad) == 1 else "them"), "invalid": bad}
    try:
        d = graph_get("act_%s/delivery_estimate" % META_ACCOUNT, {"optimization_goal": "REACH" if r.get("objective") == "OUTCOME_AWARENESS" else "LINK_CLICKS",
                                                                 "targeting_spec": json.dumps(targeting_spec(r))})
        e = (d.get("data") or [{}])[0]
        return {"lo": e.get("estimate_mau_lower_bound") or 0, "hi": e.get("estimate_mau_upper_bound") or 0, "ready": e.get("estimate_ready", True)}
    except RuntimeError as e:
        return {"error": str(e)[:200]}


def ad_sweeper():
    """Finish ads waiting on a video, and mark ads that reached their end date."""
    time.sleep(25)
    while True:
        try:
            if meta_ready() and AD_LOCK.acquire(blocking=False):
                try:
                    for r in q("SELECT * FROM ad_runs WHERE status='processing' LIMIT 5"):
                        try:
                            ad_build(dict(r))
                        except Exception as e:
                            print("Ad %d failed: %s" % (r["id"], e), flush=True)
                    q("UPDATE ad_runs SET status='ended', updated=? WHERE status IN ('active','paused') AND end_ts<?", (now(), now()))
                finally:
                    AD_LOCK.release()
        except Exception as e:
            print("Ad sweeper problem: %s" % e, flush=True)
        time.sleep(30)


def manager_report(t, days, rg=None):
    """Ads Manager view: every campaign, ad set and ad on the account with its results for the period, plus game results."""
    rg = rg or admin_range("/?days=%d" % days, t)
    since, until_day, days = rg["d0"], rg["d1"], rg["days"]
    def agg(col):
        out = {}
        for r in q("SELECT %s k, SUM(spend) spend, SUM(impressions) imp, SUM(reach) reach, SUM(clicks) clicks, SUM(link_clicks) lc "
                   "FROM meta_daily WHERE day>=? AND day<=? GROUP BY %s" % (col, col), (since, until_day)):
            out[r["k"]] = {"spend": r["spend"] or 0, "impressions": r["imp"] or 0, "reach": r["reach"] or 0, "clicks": r["clicks"] or 0, "link_clicks": r["lc"] or 0}
        return out
    zero = {"spend": 0, "impressions": 0, "reach": 0, "clicks": 0, "link_clicks": 0}
    ac, aa, ad = agg("campaign_id"), agg("adset_id"), agg("ad_id")
    since_ts, until_ts = rg["t0"], rg["t1"]
    def game(code):
        if not code:
            return {"visitors": None, "players": None}
        return {"visitors": q("SELECT COUNT(*) n FROM visitors WHERE camp=? AND first>=? AND first<? AND stage<>'login'", (code, since_ts, until_ts), one=True)["n"],
                "players": q("SELECT COUNT(*) n FROM users WHERE camp=? AND created>=? AND created<?", (code, since_ts, until_ts), one=True)["n"]}
    camps = []
    for c in q("SELECT * FROM meta_campaigns ORDER BY name"):
        if c["status"] in ("DELETED", "ARCHIVED") and not ac.get(c["campaign_id"]):
            continue
        d = {"id": c["campaign_id"], "name": c["name"], "onoff": c["onoff"], "status": c["status"], "objective": c["objective"],
             "daily": c["daily_budget"], "lifetime": c["lifetime_budget"], "code": c["code"]}
        d.update(ac.get(c["campaign_id"], zero)); d.update(game(c["code"]))
        camps.append(d)
    sets = []
    for a in q("SELECT * FROM meta_adsets ORDER BY name"):
        if a["status"] in ("DELETED", "ARCHIVED") and not aa.get(a["adset_id"]):
            continue
        d = {"id": a["adset_id"], "campaign_id": a["campaign_id"], "name": a["name"], "onoff": a["onoff"], "status": a["status"],
             "daily": a["daily_budget"], "lifetime": a["lifetime_budget"], "end": a["end_time"]}
        d.update(aa.get(a["adset_id"], zero))
        sets.append(d)
    ads = []
    for a in q("SELECT * FROM meta_ads ORDER BY name"):
        if a["status"] in ("DELETED", "ARCHIVED") and not ad.get(a["ad_id"]):
            continue
        d = {"id": a["ad_id"], "campaign_id": a["campaign_id"], "adset_id": a["adset_id"], "name": a["name"], "onoff": a["onoff"],
             "status": a["status"], "code": a["code"]}
        d.update(ad.get(a["ad_id"], zero)); d.update(game(a["code"]))
        ads.append(d)
    try:
        tok = json.loads(meta_get("meta_token") or "{}")
    except (TypeError, ValueError):
        tok = {}
    return {"campaigns": camps, "adsets": sets, "ads": ads, "days": days, "from": rg["d0"], "to": rg["d1"], "cap": AD_DAILY_CAP, "currency": account_currency(),
            "canEdit": "ads_management" in (tok.get("scopes") or []), "sync": meta_get_state(), "now": t}


def ads_runs_report(t):
    rows = []
    for r in q("SELECT * FROM ad_runs WHERE created>? OR status IN ('active','paused','processing') ORDER BY id DESC LIMIT 60", (t - 120 * 86400,)):
        d = dict(r)
        # count only what this run made: its campaign, its ad set, or just its ad
        # each ad's own results, so ads that share a campaign or ad set are not counted twice
        sp = q("SELECT COALESCE(SUM(spend),0) s, COALESCE(SUM(impressions),0) i, COALESCE(SUM(reach),0) re, COALESCE(SUM(link_clicks),0) c "
               "FROM meta_daily WHERE ad_id=?", (r["ad_id"],), one=True) if r["ad_id"] else None
        cn = q("SELECT name FROM meta_campaigns WHERE campaign_id=?", (r["campaign_id"],), one=True) if r["campaign_id"] else None
        sn = q("SELECT name FROM meta_adsets WHERE adset_id=?", (r["adset_id"],), one=True) if r["adset_id"] else None
        d["campaign_label"] = (cn and cn["name"]) or r["campaign_name"]
        d["adset_label"] = (sn and sn["name"]) or r["adset_name"]
        d.update({"spend": sp["s"] if sp else 0, "impressions": sp["i"] if sp else 0, "reach": sp["re"] if sp else 0, "clicks": sp["c"] if sp else 0})
        code = "ad-%d" % r["id"]
        d["visitors"] = q("SELECT COUNT(*) n FROM visitors WHERE camp=? AND stage<>'login'", (code,), one=True)["n"]
        d["players"] = q("SELECT COUNT(*) n FROM users WHERE camp=?", (code,), one=True)["n"]
        d["link"] = ad_link(r["id"])
        if r["post_id"]:
            p = q("SELECT caption, media, kind FROM posts WHERE id=?", (r["post_id"],), one=True)
            if p:
                d["post"] = dict(p)
        rows.append(d)
    try:
        tok = json.loads(meta_get("meta_token") or "{}")
    except (TypeError, ValueError):
        tok = {}
    scopes = tok.get("scopes") or []
    auds = []
    for a in q("SELECT * FROM audiences ORDER BY name"):
        try:
            sp = json.loads(a["spec"] or "{}")
        except ValueError:
            sp = {}
        auds.append({"id": a["id"], "name": a["name"], "spec": sp})
    return {"runs": rows, "cap": AD_DAILY_CAP, "maxDays": AD_MAX_DAYS, "ctas": AD_CTAS, "countries": AD_COUNTRIES, "objectives": AD_OBJECTIVES,
            "audiences": auds, "currency": account_currency(), "canRun": "ads_management" in scopes, "now": t}


def posts_report(t):
    try:
        tok = json.loads(meta_get("meta_token") or "{}")
    except (TypeError, ValueError):
        tok = {}
    scopes = tok.get("scopes") or []
    rows = []
    for r in q("SELECT * FROM posts WHERE due>? OR fb_status='scheduled' OR ig_status IN ('scheduled','processing') ORDER BY due DESC LIMIT 150",
               (t - 60 * 86400,)):
        d = dict(r)
        for pf in ("fb", "ig"):
            if d[pf + "_status"]:
                code = "%s-post-%d" % (pf, d["id"])
                d[pf + "_players"] = q("SELECT COUNT(*) n FROM users WHERE camp=?", (code,), one=True)["n"]
                d[pf + "_visitors"] = q("SELECT COUNT(*) n FROM visitors WHERE camp=? AND stage<>'login'", (code,), one=True)["n"]
                d[pf + "_code"] = code
        d.pop("ig_container", None)
        for sr in q("SELECT platform, fetched, data, error FROM post_stats WHERE post_id=?", (d["id"],)):
            try:
                d[sr["platform"] + "_stats"] = json.loads(sr["data"] or "{}")
            except ValueError:
                d[sr["platform"] + "_stats"] = {}
            d[sr["platform"] + "_stats_at"] = sr["fetched"]
            d[sr["platform"] + "_stats_error"] = sr["error"]
        rows.append(d)
    return {"ready": meta_ready(), "pages": pages_info(), "scopes": scopes,
            "missing": [x for x in POST_SCOPES if scopes and x not in scopes],
            "missingStats": [x for x in STATS_SCOPES if scopes and x not in scopes],
            "posts": rows, "site": SITE_DOMAIN or "hustlempires.com", "now": t}


def ads_report(t, days, rg=None):
    rg = rg or admin_range("/?days=%d" % days, t)
    days = rg["days"]
    st = meta_get_state()
    try:
        tok = json.loads(meta_get("meta_token") or "{}")
    except (TypeError, ValueError):
        tok = {}
    out = {"ready": meta_ready(), "account": META_ACCOUNT, "sync": st, "token": tok, "days": days, "from": rg["d0"], "to": rg["d1"], "now": t,
           "links": [dict(r) for r in q("SELECT code, name FROM campaigns WHERE archived=0 ORDER BY name")]}
    if not meta_ready():
        return out
    since_day, until_day = rg["d0"], rg["d1"]
    since_ts, until_ts = rg["t0"], rg["t1"]
    camps = []
    for c in q("SELECT d.campaign_id, MAX(d.campaign_name) name, SUM(d.spend) spend, SUM(d.impressions) impressions, SUM(d.reach) reach, "
               "SUM(d.clicks) clicks, SUM(d.link_clicks) link_clicks, COUNT(DISTINCT d.ad_id) ads FROM meta_daily d WHERE d.day>=? AND d.day<=? "
               "GROUP BY d.campaign_id ORDER BY spend DESC", (since_day, until_day)):
        r = dict(c)
        m = q("SELECT name, status, code, manual FROM meta_campaigns WHERE campaign_id=?", (c["campaign_id"],), one=True)
        r.update({"status": m["status"] if m else "", "code": m["code"] if m else "", "manual": bool(m and m["manual"])})
        if m and m["name"]:
            r["name"] = m["name"]
        if r["code"]:
            u = q("SELECT COUNT(*) n FROM users WHERE camp=? AND created>=? AND created<?", (r["code"], since_ts, until_ts), one=True)["n"]
            v = q("SELECT COUNT(*) n FROM visitors WHERE camp=? AND first>=? AND first<? AND stage<>'login'", (r["code"], since_ts, until_ts), one=True)["n"]
            back = 0
            elig = 0
            for x in q("SELECT id, created FROM users WHERE camp=? AND created>=? AND created<? AND created<=?", (r["code"], since_ts, until_ts, t - 86400)):
                elig += 1
                cut = time.strftime("%Y-%m-%d", time.gmtime(x["created"] + 86400))
                if q("SELECT 1 FROM activity_days WHERE user_id=? AND day>=?", (x["id"], cut), one=True):
                    back += 1
            r.update({"players": u, "visitors": v, "b1": back, "e1": elig})
        camps.append(r)
    daily = []
    for d, _a, _b in range_days(rg):
        x = q("SELECT COALESCE(SUM(spend),0) s, COALESCE(SUM(link_clicks),0) c FROM meta_daily WHERE day=?", (d,), one=True)
        daily.append({"day": d, "spend": x["s"], "clicks": x["c"]})
    tot = q("SELECT COALESCE(SUM(spend),0) spend, COALESCE(SUM(impressions),0) impressions, COALESCE(SUM(reach),0) reach, "
            "COALESCE(SUM(link_clicks),0) link_clicks FROM meta_daily WHERE day>=? AND day<=?", (since_day, until_day), one=True)
    out.update({"campaigns": camps, "daily": daily, "totals": dict(tot),
                "linkedPlayers": sum(c.get("players", 0) for c in camps), "linkedSpend": sum(c["spend"] for c in camps if c.get("code"))})
    return out


def death_kind(cause):
    c = (cause or "").lower()
    for k, words in DEATH_KINDS:
        if any(w in c for w in words):
            return k
    return "other"


# ---- app version: lets open games know an update is ready ----
_ver = {"mtime": None, "v": ""}


def app_version():
    path = os.path.join(PUBLIC, "index.html")
    try:
        mt = os.path.getmtime(path)
        if mt != _ver["mtime"]:
            with open(path, encoding="utf-8") as f:
                m = re.search(r"const APP_VER='([0-9a-f]{12})'", f.read())
            _ver.update(mtime=mt, v=m.group(1) if m else "")
    except OSError:
        pass
    return _ver["v"]


# ---- invite a friend --------------------------------------------------------
REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def ref_code_for(uid):
    """Each player's invite code, made the first time they ask for it."""
    r = q("SELECT ref_code FROM users WHERE id=?", (uid,), one=True)
    if r and r["ref_code"]:
        return r["ref_code"]
    for _ in range(20):
        code = "".join(secrets.choice(REF_ALPHABET) for _ in range(6))
        if not q("SELECT 1 FROM users WHERE ref_code=?", (code,), one=True):
            q("UPDATE users SET ref_code=? WHERE id=? AND ref_code=''", (code, uid))
            break
    return q("SELECT ref_code FROM users WHERE id=?", (uid,), one=True)["ref_code"]


def inviter_by_code(code):
    code = clean_text(code, 12).upper()
    if not re.match(r"^[A-Z0-9]{4,12}$", code or ""):
        return None
    return q("SELECT id, name, company, disabled FROM users WHERE ref_code=? AND disabled=0", (code,), one=True)


def give_days(uid, days, why):
    """Add free pass days to a player (stacks on top of any pass they have)."""
    t = now()
    s = q("SELECT paid_until, plan FROM subs WHERE user_id=?", (uid,), one=True)
    start = max(t, s["paid_until"] if s else 0)
    plan = s["plan"] if s and s["paid_until"] > t and s["plan"] else "invite"
    q("INSERT INTO subs(user_id,paid_until,plan,updated) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
      "paid_until=excluded.paid_until, plan=excluded.plan, updated=excluded.updated", (uid, start + days * 86400, plan, t))
    st = q("SELECT games FROM stats WHERE user_id=?", (uid,), one=True)
    q("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'account',?)", (uid, t, st["games"] if st else 1, why))


def referral_progress(uid):
    """Called as a referred player plays: reward their inviter once the friend comes back on a second day."""
    r = q("SELECT inviter_id, active_at FROM referrals WHERE user_id=?", (uid,), one=True)
    if not r or r["active_at"]:
        return
    if q("SELECT COUNT(*) c FROM activity_days WHERE user_id=?", (uid,), one=True)["c"] < 2:
        return
    t = now()

    def claim(db):
        if db.execute("UPDATE referrals SET active_at=? WHERE user_id=? AND active_at=0", (t, uid)).rowcount != 1:
            return 0
        recent = db.execute("SELECT COUNT(*) c FROM referrals WHERE inviter_id=? AND active_at>? AND user_id<>? AND days_given>0",
                            (r["inviter_id"], t - 30 * 86400, uid)).fetchone()["c"]
        if recent >= REF_MONTHLY_CAP or REF_ACTIVE_DAYS <= 0:
            return 0
        db.execute("UPDATE referrals SET days_given=days_given+? WHERE user_id=?", (REF_ACTIVE_DAYS, uid))
        return REF_ACTIVE_DAYS
    days = tx(claim)
    if days:
        friend = q("SELECT name FROM users WHERE id=?", (uid,), one=True)
        give_days(r["inviter_id"], days, "Earned %d free pass days: %s, who you invited, came back to play" % (
            days, friend["name"] if friend else "a friend"))


def referral_paid(uid):
    if REF_PAID_DAYS <= 0:
        return
    r = q("SELECT inviter_id FROM referrals WHERE user_id=?", (uid,), one=True)
    if not r:
        return
    t = now()
    ok = tx(lambda db: db.execute("UPDATE referrals SET paid_at=?, days_given=days_given+? WHERE user_id=? AND paid_at=0",
                                  (t, REF_PAID_DAYS, uid)).rowcount == 1)
    if ok:
        friend = q("SELECT name FROM users WHERE id=?", (uid,), one=True)
        give_days(r["inviter_id"], REF_PAID_DAYS, "Earned %d free pass days: %s, who you invited, bought a pass" % (
            REF_PAID_DAYS, friend["name"] if friend else "a friend"))


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
                         "default-src 'self'; script-src 'self' 'unsafe-inline' https://connect.facebook.net; "
                         "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                         "font-src https://fonts.gstatic.com; img-src 'self' data: blob: https://www.facebook.com; media-src 'self' blob:; "
                         "connect-src 'self' https://www.facebook.com https://connect.facebook.net; "
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
        if name == "index.html":
            pid = pixel_id()
            if pid:   # Meta Pixel on the game page: visits and new accounts, no personal details
                data = data.replace(b"</head>", (PIXEL_CODE % pid).encode() + b"</head>", 1)
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

    def serve_media(self, name):
        """Images and videos uploaded for scheduled posts. Meta downloads them from here when it publishes."""
        if not MEDIA_RE.match(name or ""):
            return self.send_error(404)
        path = os.path.join(MEDIA_DIR, name)
        if not os.path.isfile(path):
            return self.send_error(404)
        size = os.path.getsize(path)
        start, end = 0, size - 1
        rng = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
        if rng and size:
            if rng.group(1):
                start = int(rng.group(1))
                end = min(size - 1, int(rng.group(2))) if rng.group(2) else size - 1
            elif rng.group(2):
                start = max(0, size - int(rng.group(2)))
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.end_headers()
                return
        self.send_response(206 if rng and size else 200)
        self.send_header("Content-Type", {"jpg": "image/jpeg", "mp4": "video/mp4", "mov": "video/quicktime"}[name.rsplit(".", 1)[1]])
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        if rng and size:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass   # the viewer stopped loading (normal for video previews)

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
        if path in ("/privacy", "/privacy/", "/privacy-policy"):
            return self.serve_file("privacy.html")
        if path in ("/data-deletion", "/data-deletion/", "/delete-data"):
            return self.serve_file("data-deletion.html")
        if path == "/healthz":
            return self.send_json(200, {"ok": True})
        if path.startswith("/media/"):
            return self.serve_media(path[7:])
        m = re.match(r"^/go/([A-Za-z0-9-]{1,30})/?$", path)
        if m:
            # short campaign link for bios and posters: /go/tiktok opens the game as /?c=tiktok
            code = clean_camp(m.group(1))
            self.send_response(302)
            self.send_header("Location", "/?c=" + code if code else "/")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path == "/api/me":
            return self.api_me()
        if path == "/api/save/ver":
            return self.api_save_ver()
        if path == "/api/username/check":
            un = clean_text((parse_qs(urlparse(self.path).query).get("name") or [""])[0], 40).lower()
            if rate_limited("uncheck:" + self.client_ip(), limit=120, window=600):
                return self.error(429, "Too many checks. Wait a moment.")
            ok = bool(USERNAME_RE.match(un))
            return self.send_json(200, {"name": un, "valid": ok, "taken": ok and bool(q("SELECT 1 FROM users WHERE username=?", (un,), one=True))})
        if path == "/api/company/check":
            nm = clean_text((parse_qs(urlparse(self.path).query).get("name") or [""])[0], 16)
            if rate_limited("cocheck:" + self.client_ip(), limit=120, window=600):
                return self.error(429, "Too many checks. Wait a moment.")
            me = self.session_user()
            return self.send_json(200, {"name": nm, "taken": bool(nm) and company_taken(nm, me["id"] if me else None)})
        if path == "/api/leaderboard":
            return self.api_leaderboard()
        if path == "/api/lives":
            return self.api_lives()
        if path == "/api/season":
            return self.api_season()
        if path == "/api/config":
            return self.send_json(200, {"mail": mail_ready()})
        if path == "/api/tuning":
            return self.send_json(200, tuning())
        if path == "/api/version":
            return self.send_json(200, {"v": app_version()})
        if path == "/api/billing":
            return self.api_billing()
        if path == "/api/invite":
            return self.api_invite()
        if path == "/api/invite/check":
            return self.api_invite_check()
        if path == "/api/pesapal/ipn":
            return self.api_pesapal_ipn()
        if path == "/api/friends":
            return self.api_friends()
        if path == "/api/bank/lots":
            return self.api_bank_lots()
        if path == "/api/market":
            return self.api_market()
        if path == "/api/xchg":
            return self.api_xchg()
        if path == "/api/market/mine":
            return self.api_market_mine()
        if path == "/api/push/key":
            return self.send_json(200, {"on": push_on(), "key": b64u(vapid_keys()[1]) if push_on() else ""})
        if path.startswith("/api/admin/"):
            return self.api_admin_get(path)
        if path.startswith("/api/"):
            return self.error(404, "Not found.")
        return self.serve_file(path.lstrip("/"))

    def do_HEAD(self):
        path = urlparse(self.path).path
        if path.startswith("/media/"):
            return self.serve_media(path[7:])
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        routes = {"/api/visit": self.api_visit, "/api/signup": self.api_signup, "/api/login": self.api_login, "/api/logout": self.api_logout,
                  "/api/forgot": self.api_forgot, "/api/reset": self.api_reset, "/api/email": self.api_email, "/api/company": self.api_company,
                  "/api/admin/login": self.api_admin_login, "/api/admin/logout": self.api_admin_logout,
                  "/api/billing/checkout": self.api_checkout, "/api/billing/confirm": self.api_confirm,
                  "/api/billing/later": self.api_later, "/api/billing/gift": self.api_gift,
                  "/api/push/subscribe": self.api_push_sub, "/api/push/unsubscribe": self.api_push_unsub, "/api/push/open": self.api_push_open,
                  "/api/admin/push": self.api_admin_push, "/api/friends/add": self.api_friend_add,
                  "/api/friends/remove": self.api_friend_remove, "/api/friends/gift": self.api_friend_gift,
                  "/api/friends/claim": self.api_gift_claim, "/api/bank/list": self.api_bank_list, "/api/bank/buy": self.api_bank_buy,
                  "/api/market/list": self.api_market_list, "/api/market/buy": self.api_market_buy,
                  "/api/market/cancel": self.api_market_cancel, "/api/market/settle": self.api_market_settle,
                  "/api/xchg/list": self.api_xchg_list, "/api/xchg/buy": self.api_xchg_buy, "/api/xchg/sell": self.api_xchg_sell,
                  "/api/xchg/settle": self.api_xchg_settle}
        if path in routes:
            return routes[path]()
        if path == "/api/admin/campaign":
            return self.api_admin_campaign()
        if path == "/api/admin/media/chunk":
            return self.api_admin_media_chunk()
        if path.startswith("/api/admin/media/") or path.startswith("/api/admin/posts"):
            return self.api_admin_posts(path)
        if path.startswith("/api/admin/adruns/"):
            return self.api_admin_adruns(path)
        if path.startswith("/api/admin/audiences/"):
            return self.api_admin_audiences(path)
        if path == "/api/admin/pixel":
            if not self.is_admin():
                return self.error(401, "Log in as admin.")
            d = self.read_json()
            if d is None:
                return
            v = re.sub(r"\s", "", str(d.get("id") or ""))
            m = re.search(r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{8,20})", v)   # the whole pixel code pasted
            v = m.group(1) if m else v
            if v and not re.match(r"^\d{8,20}$", v):
                return self.error(400, "That doesn't look like a Pixel ID. It is a long number, like 1234567890123456.")
            meta_set("pixel_id", v)
            return self.send_json(200, {"ok": True, "id": pixel_id()})
        if path in ("/api/admin/manager/toggle", "/api/admin/manager/budget"):
            return self.api_admin_manager(path)
        if path in ("/api/admin/ads/sync", "/api/admin/ads/link"):
            return self.api_admin_ads(path)
        if path == "/api/admin/tuning":
            if not self.is_admin():
                return self.error(401, "Log in as admin.")
            d = self.read_json()
            if d is None:
                return
            t = clean_tuning(d)
            meta_set("tuning", json.dumps(t))
            return self.send_json(200, {"ok": True, "tuning": t})
        m = re.match(r"^/api/admin/player/(\d+)/(disable|enable|reset|delete|password|gift)$", path)
        if m:
            return self.api_admin_action(int(m.group(1)), m.group(2))
        self.error(404, "Not found.")

    def do_PUT(self):
        if urlparse(self.path).path == "/api/save":
            return self.api_save()
        self.error(404, "Not found.")

    # ---------- player API ----------
    def api_visit(self):
        """Someone opened the game without being logged in (or started filling in the form). No personal data is kept."""
        if rate_limited("visit:" + self.client_ip(), limit=60, window=3600):
            return self.send_json(200, {"ok": True})
        d = self.read_json()
        if d is None:
            return
        ua = (self.headers.get("User-Agent") or "").lower()
        device = "phone" if any(k in ua for k in ("iphone", "android", "mobile")) else "tablet" if "ipad" in ua else "computer"
        stage = d.get("stage") if d.get("stage") in ("landed", "played", "asked", "form") else "landed"
        visit_mark(d.get("vid"), stage, src_of(d.get("ref")), device, camp=clean_camp(d.get("camp")))
        self.send_json(200, {"ok": True})

    def api_signup(self):
        if rate_limited("signup:" + self.client_ip(), limit=8, window=3600):
            return self.error(429, "Too many new accounts from your network. Try again later.")
        d = self.read_json()
        if d is None:
            return
        username = clean_text(d.get("username"), 40).lower()
        password = d.get("password") if isinstance(d.get("password"), str) else ""
        name = clean_text(d.get("name"), 24)
        company = clean_text(d.get("company"), 16)
        if company == "Savanna" and company_taken(company):
            company = ""  # the old placeholder: give them their own brand instead
        town = clean_text(d.get("town"), 20) or "Nairobi"
        bg = d.get("bg") if d.get("bg") in BACKGROUNDS else "hustler"
        email = clean_email(d.get("email"))
        inviter = inviter_by_code(d.get("ref")) if d.get("ref") else None
        camp = clean_camp(d.get("camp"))
        if not camp and VID_RE.match(str(d.get("vid") or "")):
            r = q("SELECT camp FROM visitors WHERE vid=?", (d.get("vid"),), one=True)
            camp = r["camp"] if r else ""
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
        if company and company_taken(company):
            return self.error(409, "The company name %s is already taken. Open More options and pick another, or leave it blank and we will make you one." % company)
        if not company:
            company = company_default(name, username)
        salt, digest = hash_password(password)
        t = now()
        token = secrets.token_urlsafe(32)

        def create(db):
            cur = db.execute("INSERT INTO users(username,pw_salt,pw_hash,name,company,town,bg,color,created,last_seen,logins,email,camp) "
                             "VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)", (username, salt, digest, name, company, town, bg, color, t, t, email, camp))
            uid = cur.lastrowid
            db.execute("INSERT INTO stats(user_id, updated) VALUES(?,?)", (uid, t))
            db.execute("INSERT INTO sessions(token,user_id,is_admin,created,expires) VALUES(?,?,0,?,?)",
                       (token, uid, t, t + PLAYER_SESSION_SECONDS))
            db.execute("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,1,'account',?)",
                       (uid, t, "Created an account (%s)" % {"hustler": "street hustler", "grad": "university graduate", "heir": "family business heir"}[bg]))
            db.execute("INSERT OR IGNORE INTO activity_days(user_id, day) VALUES(?,?)", (uid, today()))
            if inviter:
                db.execute("INSERT OR IGNORE INTO referrals(user_id,inviter_id,created) VALUES(?,?,?)", (uid, inviter["id"], t))
                db.execute("INSERT OR IGNORE INTO friends(user_id,friend_id,created) VALUES(?,?,?)", (uid, inviter["id"], t))
                db.execute("INSERT OR IGNORE INTO friends(user_id,friend_id,created) VALUES(?,?,?)", (inviter["id"], uid, t))
                db.execute("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,1,'account',?)",
                           (uid, t, "Joined with an invite from %s" % inviter["name"]))
                ig = db.execute("SELECT games FROM stats WHERE user_id=?", (inviter["id"],)).fetchone()
                db.execute("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'account',?)",
                           (inviter["id"], t, ig["games"] if ig else 1, "%s joined with your invite" % name))
            return uid

        try:
            uid = tx(create)
        except sqlite3.IntegrityError:
            return self.error(409, "That username is taken. Try another.")
        user = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
        try:
            visit_mark(d.get("vid"), "signed", user_id=uid)
        except Exception as e:
            print("Visit record failed: %s" % e, flush=True)
        self.send_json(201, {"user": user_public(user), "save": None, "ver": 0, "bill": bill_status(user)},
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
        try:
            visit_mark(d.get("vid"), "login", user_id=user["id"])
        except Exception as e:
            print("Visit record failed: %s" % e, flush=True)
        q("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'login','Logged in')",
          (user["id"], t, self.current_game(user["id"])))
        self.touch(user["id"])
        save = q("SELECT state, ver FROM saves WHERE user_id=?", (user["id"],), one=True)
        self.send_json(200, {"user": user_public(user), "save": json.loads(save["state"]) if save else None,
                             "ver": save["ver"] if save else 0, "bill": bill_status(user, True)},
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

    def api_bank_list(self):
        """The game reports buildings the bank seized from this player; they go up for auction to others in the same country."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        if rate_limited("banklist:%d" % user["id"], limit=20, window=3600):
            return self.error(429, "Too many auctions. Try again later.")
        d = self.read_json()
        if d is None:
            return
        region = re.sub(r"[^A-Z]", "", str(d.get("region") or "").upper())[:3]
        lots = [x for x in (clean_lot(l) for l in (d.get("lots") or [])[:30]) if x]
        st = q("SELECT best FROM stats WHERE user_id=?", (user["id"],), one=True)
        cap = max(5e7, (st["best"] if st else 0) * 3)
        lots = [l for l in lots if l["value"] <= cap]
        t = now()
        for l in lots:
            q("INSERT INTO bank_lots(seller_id, region, data, value, price, created, expires) VALUES(?,?,?,?,?,?,?)",
              (user["id"], region, json.dumps(l), l["value"], round(l["value"] * 0.7), t, t + BANK_DAYS * 86400))
        self.send_json(200, {"ok": True, "listed": len(lots)})

    def api_bank_lots(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        region = re.sub(r"[^A-Z]", "", ((parse_qs(urlparse(self.path).query).get("region") or [""])[0]).upper())[:3]
        t = now()
        rows = q("SELECT b.id, b.data, b.value, b.price, b.created, b.expires, u.name FROM bank_lots b JOIN users u ON u.id=b.seller_id "
                 "WHERE b.region=? AND b.sold=0 AND b.expires>? AND b.seller_id<>? ORDER BY b.price ASC LIMIT 40", (region, t, user["id"]))
        lots = []
        for r in rows:
            try:
                d = json.loads(r["data"])
            except ValueError:
                continue
            d.update({"id": r["id"], "value": r["value"], "price": r["price"], "from": (r["name"] or "").split(" ")[0],
                      "daysLeft": max(1, int((r["expires"] - t) // 86400))})
            lots.append(d)
        recent = q("SELECT COUNT(*) c FROM bank_lots WHERE region=? AND sold>?", (region, t - 7 * 86400), one=True)["c"]
        self.send_json(200, {"lots": lots, "soldWeek": recent})

    def api_bank_buy(self):
        """First come, first served: the lot goes to whoever asks first."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        d = self.read_json()
        if d is None:
            return
        lid, t = int(d.get("id") or 0), now()

        def take(db):
            r = db.execute("SELECT * FROM bank_lots WHERE id=?", (lid,)).fetchone()
            if not r or r["sold"] or r["expires"] <= t:
                return None, "Too late: someone else bought it, or the auction ended."
            if r["seller_id"] == user["id"]:
                return None, "You cannot buy back your own seized building."
            db.execute("UPDATE bank_lots SET sold=?, buyer_id=? WHERE id=?", (t, user["id"], lid))
            return r, ""
        r, err = tx(take)
        if not r:
            return self.error(409, err)
        lot = json.loads(r["data"])
        lot.update({"id": r["id"], "price": r["price"], "value": r["value"]})
        self.send_json(200, {"ok": True, "lot": lot})

    def api_market_list(self):
        """A player puts a building or a luxury item up for sale. The game has already taken it out of their empire."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        if rate_limited("mklist:%d" % user["id"], limit=30, window=3600):
            return self.error(429, "Too many listings. Try again later.")
        d = self.read_json()
        if d is None:
            return
        kind = d.get("k")
        item = clean_item(kind, d.get("item"))
        if not item:
            return self.error(400, "That item cannot be sold here.")
        try:
            price = float(d.get("price"))
        except (TypeError, ValueError):
            return self.error(400, "Choose a price.")
        if not (item["value"] * 0.5 - 1 <= price <= item["value"] * 1.5 + 1):
            return self.error(400, "The price must be between half and one and a half times what it is worth.")
        st = q("SELECT best FROM stats WHERE user_id=?", (user["id"],), one=True)
        if item["value"] > max(5e7, (st["best"] if st else 0) * 3):
            return self.error(400, "That is worth more than your empire. It cannot be listed.")
        if q("SELECT COUNT(*) c FROM market WHERE seller_id=? AND status='open'", (user["id"],), one=True)["c"] >= MARKET_OPEN_MAX:
            return self.error(409, "You already have %d items for sale. Wait for some to sell, or cancel one." % MARKET_OPEN_MAX)
        region = re.sub(r"[^A-Z]", "", str(d.get("region") or "").upper())[:3]
        g = "f" if d.get("g") == "f" else "m" if d.get("g") == "m" else ""
        t = now()
        lid = tx(lambda db: db.execute("INSERT INTO market(seller_id, region, g, kind, data, value, price, created, expires) VALUES(?,?,?,?,?,?,?,?,?)",
                                       (user["id"], region, g, kind, json.dumps(item), item["value"], round(price), t, t + MARKET_DAYS * 86400)).lastrowid)
        self.send_json(200, {"ok": True, "id": lid})

    def api_market(self):
        """Items for sale. Local: your own country. World: every country (buildings in home cities stay local)."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        qs = parse_qs(urlparse(self.path).query)
        scope = "world" if (qs.get("scope") or [""])[0] == "world" else "local"
        region = re.sub(r"[^A-Z]", "", ((qs.get("region") or [""])[0]).upper())[:3]
        t = now()
        sql = ("SELECT m.*, u.name seller FROM market m JOIN users u ON u.id=m.seller_id WHERE m.status='open' AND m.expires>? "
               "AND m.seller_id<>? AND u.disabled=0 ")
        args = [t, user["id"]]
        if scope == "local":
            sql += "AND m.region=? "
            args.append(region)
        sql += "ORDER BY m.created DESC LIMIT 200"
        out = []
        for r in q(sql, tuple(args)):
            d = market_row(r, t)
            if not d:
                continue
            if scope == "world" and d["k"] == "p" and d.get("city") in HOME_CITIES and r["region"] != region:
                continue
            out.append(d)
            if len(out) >= 60:
                break
        self.send_json(200, {"items": out, "scope": scope, "fee": MARKET_FEE})

    def api_market_mine(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        t = now()
        rows = q("SELECT * FROM market WHERE seller_id=? AND (status='open' OR (status='sold' AND sold_ts>?)) ORDER BY id DESC LIMIT 60",
                 (user["id"], t - 14 * 86400))
        self.send_json(200, {"items": [x for x in (market_row(r, t) for r in rows) if x], "fee": MARKET_FEE})

    def api_market_buy(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        d = self.read_json()
        if d is None:
            return
        lid, t = int(d.get("id") or 0), now()

        def take(db):
            r = db.execute("SELECT * FROM market WHERE id=?", (lid,)).fetchone()
            if not r or r["status"] != "open" or r["expires"] <= t:
                return None, "Too late: it has been sold or taken off the market."
            if r["seller_id"] == user["id"]:
                return None, "That is your own listing."
            db.execute("UPDATE market SET status='sold', buyer_id=?, sold_ts=? WHERE id=?", (user["id"], t, lid))
            return r, ""
        r, err = tx(take)
        if not r:
            return self.error(409, err)
        item = market_row(r, t)
        first = (user["name"] or "A player").split(" ")[0]
        if push_on():
            def nudge():
                try:
                    push_to_user(r["seller_id"], "sold", "%s sold" % item.get("name", "Your item"),
                                 "%s bought it. Open Hustlempires to collect your money." % first)
                except Exception as e:
                    print("Sale notification failed: %s" % e, flush=True)
            threading.Thread(target=nudge, daemon=True).start()
        self.send_json(200, {"ok": True, "item": item})

    def api_market_cancel(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        d = self.read_json()
        if d is None:
            return
        lid = int(d.get("id") or 0)

        def take(db):
            r = db.execute("SELECT * FROM market WHERE id=? AND seller_id=? AND status='open'", (lid, user["id"])).fetchone()
            if r:
                db.execute("UPDATE market SET status='cancel', settled=1 WHERE id=?", (lid,))
            return r
        r = tx(take)
        if not r:
            return self.error(409, "It has already been sold, or is no longer for sale.")
        self.send_json(200, {"ok": True, "item": market_row(r, now())})

    def api_market_settle(self):
        """Pay the seller for items that sold (minus the fee) and hand back items that did not sell in time."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        t = now()

        def take(db):
            sold = db.execute("SELECT * FROM market WHERE seller_id=? AND status='sold' AND settled=0", (user["id"],)).fetchall()
            back = db.execute("SELECT * FROM market WHERE seller_id=? AND status='open' AND expires<=?", (user["id"], t)).fetchall()
            for r in sold:
                db.execute("UPDATE market SET settled=1 WHERE id=?", (r["id"],))
            for r in back:
                db.execute("UPDATE market SET status='expired', settled=1 WHERE id=?", (r["id"],))
            return sold, back
        sold, back = tx(take)
        self.send_json(200, {"sold": [dict(market_row(r, t), net=round(r["price"] * (1 - MARKET_FEE))) for r in sold],
                             "back": [market_row(r, t) for r in back]})

    def api_xchg(self):
        """The players' exchange: listed player companies, my holdings and my own listing."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        t = now()
        cos = xc_companies(t)
        byid = {c["id"]: c for c in cos}
        mine = []
        for h in q("SELECT company_id, shares, cost FROM xc_hold WHERE investor_id=? AND shares>0", (user["id"],)):
            c = byid.get(h["company_id"])
            px = c["px"] if c else 0.0
            mine.append({"id": h["company_id"], "company": c["company"] if c else "Delisted company", "shares": h["shares"], "cost": h["cost"],
                         "px": px, "value": h["shares"] * px})
        me = byid.get(user["id"])
        st = q("SELECT nw FROM stats WHERE user_id=?", (user["id"],), one=True)
        holders = q("SELECT COUNT(*) c FROM xc_hold WHERE company_id=? AND shares>0", (user["id"],), one=True)["c"] if me else 0
        raised = q("SELECT COALESCE(SUM(amount),0) a FROM xc_pay WHERE user_id=? AND note='raised'", (user["id"],), one=True)["a"]
        self.send_json(200, {"companies": [c for c in cos if c["id"] != user["id"]], "holdings": mine, "me": me, "holders": holders,
                             "raised": raised, "canList": (st["nw"] if st else 0) >= XC_MIN_NW, "minNw": XC_MIN_NW, "fee": XC_FEE})

    def api_xchg_list(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        d = self.read_json()
        if d is None:
            return
        try:
            fl = float(d.get("float"))
        except (TypeError, ValueError):
            fl = 0
        if fl not in (0.1, 0.2, 0.3):
            return self.error(400, "Choose 10%, 20% or 30%.")
        st = q("SELECT nw, bankrupt FROM stats WHERE user_id=?", (user["id"],), one=True)
        if not st or st["nw"] < XC_MIN_NW or st["bankrupt"]:
            return self.error(409, "Your empire must be worth at least $10M to list on the exchange.")
        ex = q("SELECT active, float_pct, sold FROM xc_list WHERE user_id=?", (user["id"],), one=True)
        if ex and ex["active"]:
            if fl * XC_SHARES < ex["sold"]:
                return self.error(409, "You have already sold more shares than that.")
            q("UPDATE xc_list SET float_pct=? WHERE user_id=?", (max(fl, ex["float_pct"]), user["id"]))
        else:
            q("INSERT OR REPLACE INTO xc_list(user_id, float_pct, sold, created, active) VALUES(?,?,0,?,1)", (user["id"], fl, now()))
        self.send_json(200, {"ok": True})

    def api_xchg_buy(self):
        """Buy new shares in another player's company. The money goes to the founder as capital raised."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        if rate_limited("xcbuy:%d" % user["id"], limit=60, window=3600):
            return self.error(429, "Too many trades. Try again later.")
        d = self.read_json()
        if d is None:
            return
        cid = int(d.get("id") or 0)
        try:
            amt = float(d.get("amount"))
        except (TypeError, ValueError):
            amt = 0
        if cid == user["id"]:
            return self.error(400, "You cannot buy shares in your own company here.")
        t = now()
        co = next((c for c in xc_companies(t) if c["id"] == cid), None)
        if not co or co["px"] <= 0:
            return self.error(409, "That company is not trading.")
        if not (0 < amt < 1e16):
            return self.error(400, "Choose an amount.")
        px = co["px"]

        def take(db):
            l = db.execute("SELECT * FROM xc_list WHERE user_id=? AND active=1", (cid,)).fetchone()
            avail = max(0.0, l["float_pct"] * XC_SHARES - l["sold"]) if l else 0
            sh = min(amt / px, avail)
            if sh <= 0:
                return None
            cost = sh * px
            db.execute("UPDATE xc_list SET sold=sold+? WHERE user_id=?", (sh, cid))
            db.execute("INSERT INTO xc_hold(investor_id, company_id, shares, cost) VALUES(?,?,?,?) "
                       "ON CONFLICT(investor_id, company_id) DO UPDATE SET shares=shares+excluded.shares, cost=cost+excluded.cost",
                       (user["id"], cid, sh, cost))
            db.execute("INSERT INTO xc_pay(user_id, amount, note, ts) VALUES(?,?,?,?)", (cid, cost * (1 - XC_FEE), "raised", t))
            return sh, cost
        r = tx(take)
        if not r:
            return self.error(409, "No shares left for sale in that company.")
        self.send_json(200, {"ok": True, "shares": r[0], "cost": r[1], "px": px})

    def api_xchg_sell(self):
        """Sell shares back to the market at today's price, less the fee."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        d = self.read_json()
        if d is None:
            return
        cid = int(d.get("id") or 0)
        try:
            frac = min(1.0, max(0.0, float(d.get("frac"))))
        except (TypeError, ValueError):
            frac = 0
        t = now()
        co = next((c for c in xc_companies(t) if c["id"] == cid), None)
        px = co["px"] if co else 0.0

        def take(db):
            h = db.execute("SELECT * FROM xc_hold WHERE investor_id=? AND company_id=?", (user["id"], cid)).fetchone()
            if not h or h["shares"] <= 0 or frac <= 0:
                return None
            sh = h["shares"] * frac
            db.execute("UPDATE xc_hold SET shares=shares-?, cost=cost*? WHERE investor_id=? AND company_id=?", (sh, 1 - frac, user["id"], cid))
            db.execute("UPDATE xc_list SET sold=MAX(0, sold-?) WHERE user_id=?", (sh, cid))
            return sh
        sh = tx(take)
        if not sh:
            return self.error(409, "You do not own shares in that company.")
        self.send_json(200, {"ok": True, "shares": sh, "amount": sh * px * (1 - XC_FEE), "px": px})

    def api_xchg_settle(self):
        """Founders collect the money investors put into their company."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")

        def take(db):
            rows = db.execute("SELECT id, amount FROM xc_pay WHERE user_id=? AND paid=0", (user["id"],)).fetchall()
            for r in rows:
                db.execute("UPDATE xc_pay SET paid=? WHERE id=?", (now(), r["id"]))
            return sum(r["amount"] for r in rows)
        self.send_json(200, {"ok": True, "amount": tx(take)})

    def api_friends(self):
        """My friends, how they are doing, who added me, and gifts waiting for me."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        uid, t = user["id"], now()
        sid = season_now()
        day0 = t - 20 * 3600
        rows = q("SELECT u.id, u.username, u.name, u.company, u.color, u.last_seen, COALESCE(s.nw,0) nw, COALESCE(s.best,0) best, "
                 "COALESCE(s.month,0) month, COALESCE(s.rank,'') rank, COALESCE(ss.pts,0) pts, "
                 "(SELECT COUNT(*) FROM gifts g WHERE g.from_id=? AND g.to_id=u.id AND g.ts>?) gifted "
                 "FROM friends f JOIN users u ON u.id=f.friend_id LEFT JOIN stats s ON s.user_id=u.id "
                 "LEFT JOIN season_scores ss ON ss.user_id=u.id AND ss.season=? WHERE f.user_id=? AND u.disabled=0",
                 (uid, day0, sid, uid))
        mine = q("SELECT COALESCE(s.nw,0) nw, COALESCE(ss.pts,0) pts FROM users u LEFT JOIN stats s ON s.user_id=u.id "
                 "LEFT JOIN season_scores ss ON ss.user_id=u.id AND ss.season=? WHERE u.id=?", (sid, uid), one=True)
        sent_today = q("SELECT COUNT(*) c FROM gifts WHERE from_id=? AND ts>?", (uid, day0), one=True)["c"]
        friends = [{"id": r["id"], "username": r["username"], "name": r["name"], "company": r["company"], "color": r["color"],
                    "nw": r["nw"], "best": r["best"], "month": r["month"], "rank": r["rank"], "pts": r["pts"],
                    "seen": seen_label(r["last_seen"], t), "online": t - (r["last_seen"] or 0) < 600,
                    "canGift": not r["gifted"] and sent_today < GIFTS_PER_DAY} for r in rows]
        friends.sort(key=lambda f: -f["nw"])
        added = [dict(r) for r in q("SELECT u.id, u.username, u.name, u.company, u.color FROM friends f JOIN users u ON u.id=f.user_id "
                                    "WHERE f.friend_id=? AND u.disabled=0 AND NOT EXISTS (SELECT 1 FROM friends x WHERE x.user_id=? AND x.friend_id=f.user_id) "
                                    "ORDER BY f.created DESC LIMIT 20", (uid, uid))]
        gifts = [dict(r) for r in q("SELECT g.id, u.name, u.color, u.company, g.ts FROM gifts g JOIN users u ON u.id=g.from_id "
                                    "WHERE g.to_id=? AND g.claimed=0 ORDER BY g.id LIMIT 20", (uid,))]
        self.send_json(200, {"friends": friends, "added": added, "gifts": gifts, "me": {"nw": mine["nw"] if mine else 0, "pts": mine["pts"] if mine else 0},
                             "giftsLeft": max(0, GIFTS_PER_DAY - sent_today)})

    def api_friend_add(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        if rate_limited("friendadd:%d" % user["id"], limit=30, window=3600):
            return self.error(429, "Too many tries. Try again later.")
        d = self.read_json()
        if d is None:
            return
        name = str(d.get("username") or "").strip().lower().lstrip("@")
        f = q("SELECT id, name FROM users WHERE (username=? OR id=?) AND disabled=0", (name, int(d.get("id") or 0)), one=True)
        if not f:
            return self.error(404, "No player with that username. Check the spelling: it is the name they log in with.")
        if f["id"] == user["id"]:
            return self.error(400, "That is you.")
        if q("SELECT COUNT(*) c FROM friends WHERE user_id=?", (user["id"],), one=True)["c"] >= FRIEND_MAX:
            return self.error(409, "You already have %d friends, the most allowed." % FRIEND_MAX)
        q("INSERT OR IGNORE INTO friends(user_id, friend_id, created) VALUES(?,?,?)", (user["id"], f["id"], now()))
        self.send_json(200, {"ok": True, "name": f["name"]})

    def api_friend_remove(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        d = self.read_json()
        if d is None:
            return
        q("DELETE FROM friends WHERE user_id=? AND friend_id=?", (user["id"], int(d.get("id") or 0)))
        self.send_json(200, {"ok": True})

    def api_friend_gift(self):
        """Send a friend a gift: once a day per friend, a few a day in total. Their phone gets a nudge."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        d = self.read_json()
        if d is None:
            return
        fid, t = int(d.get("id") or 0), now()
        if not q("SELECT 1 FROM friends WHERE user_id=? AND friend_id=?", (user["id"], fid), one=True):
            return self.error(404, "You can only send gifts to your friends.")
        day0 = t - 20 * 3600
        if q("SELECT 1 FROM gifts WHERE from_id=? AND to_id=? AND ts>?", (user["id"], fid, day0), one=True):
            return self.error(409, "You already sent them a gift today.")
        if q("SELECT COUNT(*) c FROM gifts WHERE from_id=? AND ts>?", (user["id"], day0), one=True)["c"] >= GIFTS_PER_DAY:
            return self.error(409, "That is all your gifts for today. More tomorrow.")
        q("INSERT INTO gifts(from_id, to_id, ts) VALUES(?,?,?)", (user["id"], fid, t))
        first = (user["name"] or "A friend").split(" ")[0]
        if push_on():
            def nudge():
                try:
                    tz = (q("SELECT tz FROM push_subs WHERE user_id=? LIMIT 1", (fid,), one=True) or {"tz": ""})["tz"]
                    if PUSH_HOURS[0] <= local_hour(tz, t) < PUSH_HOURS[1]:
                        push_to_user(fid, "gift", "%s sent you a gift" % first, "Open Hustlempires to collect it, and send one back.")
                except Exception as e:
                    print("Gift notification failed: %s" % e, flush=True)
            threading.Thread(target=nudge, daemon=True).start()
        self.send_json(200, {"ok": True})

    def api_gift_claim(self):
        """Collect waiting gifts. The game turns each one into a month of the player's own profit."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        d = self.read_json()
        if d is None:
            return

        def take(db):
            rows = db.execute("SELECT g.id, u.name FROM gifts g JOIN users u ON u.id=g.from_id WHERE g.to_id=? AND g.claimed=0 "
                              "ORDER BY g.id LIMIT 5", (user["id"],)).fetchall()
            for r in rows:
                db.execute("UPDATE gifts SET claimed=? WHERE id=?", (now(), r["id"]))
            return [(r["name"] or "").split(" ")[0] for r in rows]
        names = tx(take)
        self.send_json(200, {"ok": True, "n": len(names), "from": names})

    def api_push_sub(self):
        """A player said yes to notifications on this device."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        if rate_limited("push:%d" % user["id"], limit=30, window=3600):
            return self.error(429, "Too many tries. Try again later.")
        d = self.read_json()
        if d is None:
            return
        ep = str(d.get("endpoint") or "")
        keys = d.get("keys") if isinstance(d.get("keys"), dict) else {}
        p256, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
        try:
            ok = push_endpoint_ok(ep) and len(unb64u(p256)) == 65 and len(unb64u(auth)) == 16
        except Exception:
            ok = False
        if not ok:
            return self.error(400, "This browser's notification details were not accepted.")
        tz = str(d.get("tz") or "")[:40]
        if not re.match(r"^[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}$", tz):
            tz = ""
        try:
            tz += "|%d" % max(-840, min(840, int(d.get("off"))))
        except (TypeError, ValueError):
            pass
        q("INSERT INTO push_subs(endpoint,user_id,p256dh,auth,tz,created) VALUES(?,?,?,?,?,?) "
          "ON CONFLICT(endpoint) DO UPDATE SET user_id=excluded.user_id, p256dh=excluded.p256dh, auth=excluded.auth, tz=excluded.tz, fails=0",
          (ep, user["id"], p256, auth, tz, now()))
        self.send_json(200, {"ok": True})

    def api_push_unsub(self):
        d = self.read_json()
        if d is None:
            return
        q("DELETE FROM push_subs WHERE endpoint=?", (str(d.get("endpoint") or ""),))
        self.send_json(200, {"ok": True})

    def api_push_open(self):
        """A player tapped a notification (counted so the admin can see which messages work)."""
        if rate_limited("pushopen:" + self.client_ip(), limit=60, window=3600):
            return self.send_json(200, {"ok": True})
        d = self.read_json()
        if d is None:
            return
        try:
            pid = int(d.get("id"))
        except (TypeError, ValueError):
            return self.send_json(200, {"ok": True})
        q("UPDATE push_log SET opened=1 WHERE id=?", (pid,))
        self.send_json(200, {"ok": True})

    def api_admin_push(self):
        """Switch notifications on or off, or send a test to one player."""
        if not self.is_admin():
            return self.error(401, "Log in as admin.")
        d = self.read_json()
        if d is None:
            return
        if "on" in d:
            meta_set("push_off", "0" if d.get("on") else "1")
        if d.get("test"):
            if not push_ready():
                return self.error(409, "Notifications need the python3-cryptography package on the server.")
            name = str(d.get("test")).strip().lower().lstrip("@")
            u = q("SELECT id FROM users WHERE username=?", (name,), one=True)
            if not u:
                return self.error(404, "No player with that username.")
            sent = push_to_user(u["id"], "test", "Test from Hustlempires", "Notifications are working. Your empire can reach you now.")
            if sent is None:
                return self.error(409, "That player has not switched on notifications on any device.")
            return self.send_json(200, {"ok": True, "sent": sent, "push": push_overview(now())})
        self.send_json(200, {"ok": True, "push": push_overview(now())})

    def api_company(self):
        """A logged-in player renames their company brand. Allowed once per account."""
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        if rate_limited("company:%d" % user["id"], limit=10, window=3600):
            return self.error(429, "Too many tries. Try again later.")
        d = self.read_json()
        if d is None:
            return
        if user["company_renamed"]:
            return self.error(409, "You have already renamed your company once.")
        company = clean_text(d.get("company"), 16)
        if not company:
            return self.error(400, "Enter a company name.")
        if company == user["company"]:
            return self.error(400, "That is already your company name.")
        if company_taken(company, user["id"]):
            return self.error(409, "The company name %s is already taken. Try another." % company)
        q("UPDATE users SET company=?, company_renamed=1 WHERE id=?", (company, user["id"]))
        q("INSERT INTO events(user_id,ts,game,kind,text) VALUES(?,?,?,'account',?)",
          (user["id"], now(), self.current_game(user["id"]), "Renamed their company from %s to %s" % (user["company"], company)))
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
        save = q("SELECT state, ver FROM saves WHERE user_id=?", (user["id"],), one=True)
        self.send_json(200, {"user": user_public(user), "save": json.loads(save["state"]) if save else None,
                             "ver": save["ver"] if save else 0, "bill": bill_status(user, True)},
                       [self.make_cookie("hs", session, PLAYER_SESSION_SECONDS)])

    def api_me(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Not logged in.")
        self.touch(user["id"])
        referral_progress(user["id"])
        save = q("SELECT state, ver FROM saves WHERE user_id=?", (user["id"],), one=True)
        self.send_json(200, {"user": user_public(user), "save": json.loads(save["state"]) if save else None,
                             "ver": save["ver"] if save else 0, "bill": bill_status(user, True)})

    def api_save_ver(self):
        """Cheap check: which version of the saved game does the server hold? Lets other devices catch up."""
        user = self.session_user()
        if not user:
            return self.error(401, "Not logged in.")
        row = q("SELECT ver FROM saves WHERE user_id=?", (user["id"],), one=True)
        self.send_json(200, {"ver": row["ver"] if row else 0})

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
        evlog = d.get("evlog") if isinstance(d.get("evlog"), list) else []
        base = d.get("base") if isinstance(d.get("base"), int) and not isinstance(d.get("base"), bool) else None
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
                       "debt", "married", "kids", "age", "tab", "card", "g10", "race", "foundation", "cities", "gender", "spouse", "health", "died", "streak", "region", "currency", "gen")
        detail = {k: summary.get(k) for k in detail_keys if isinstance(summary.get(k), (int, float, str, bool))}
        detail = {k: (clean_text(v, 40) if isinstance(v, str) else v) for k, v in detail.items()}

        def write(db):
            sv = db.execute("SELECT ver FROM saves WHERE user_id=?", (uid,)).fetchone()
            cur_ver = sv["ver"] if sv else 0
            # a save must say which version it was built on; an old screen that doesn't (or is behind) must not overwrite newer play
            if (base is None and cur_ver > 0) or (base is not None and cur_ver > base):
                return {"conflict": cur_ver}
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
            db.execute("INSERT INTO saves(user_id,state,updated,ver) VALUES(?,?,?,?) "
                       "ON CONFLICT(user_id) DO UPDATE SET state=excluded.state, updated=excluded.updated, ver=excluded.ver",
                       (uid, state_text, t, cur_ver + 1))
            db.execute("INSERT INTO stats(user_id,nw,best,cash,month,rank,billion_month,bankrupt,games,months_played,detail,updated) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET nw=excluded.nw, best=excluded.best, "
                       "cash=excluded.cash, month=excluded.month, rank=excluded.rank, billion_month=excluded.billion_month, "
                       "bankrupt=excluded.bankrupt, games=excluded.games, months_played=stats.months_played+?, "
                       "detail=excluded.detail, updated=excluded.updated",
                       (uid, nw, best, num(summary.get("cash")), month, clean_text(summary.get("rank"), 30), billion,
                        1 if summary.get("over") else 0, game, played, json.dumps(detail), t, played))
            if month > 0:
                lifeboard_put(db, uid, game, num(summary.get("gen"), 1), summary.get("who") if isinstance(summary.get("who"), str) else "",
                              summary.get("region") if isinstance(summary.get("region"), str) else "", best, clean_ms(summary.get("ms")), t,
                              num(summary.get("co")) if summary.get("co") is not None else None)
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
            for e in evlog[:200]:
                if isinstance(e, list) and len(e) == 2 and isinstance(e[0], str) and EV_ID_RE.match(e[0]) and isinstance(e[1], int) and 0 <= e[1] < 10:
                    db.execute("INSERT INTO ev_log(ts,user_id,ev,choice) VALUES(?,?,?,?)", (t, uid, e[0], e[1]))
            sea = summary.get("season")
            if isinstance(sea, dict) and season_ok(sea.get("id")):
                pts = int(max(0, min(1e7, num(sea.get("pts")))))
                region = clean_text(summary.get("region"), 3).upper()
                db.execute("INSERT INTO season_scores(user_id,season,pts,region,updated) VALUES(?,?,?,?,?) "
                           "ON CONFLICT(user_id,season) DO UPDATE SET pts=MAX(season_scores.pts,excluded.pts), "
                           "region=excluded.region, updated=excluded.updated", (uid, sea["id"], pts, region, t))
            return {"game": game, "ver": cur_ver + 1}

        res = tx(write)
        if "conflict" in res:
            return self.send_json(409, {"error": "This game was saved from another device.", "newer": True, "ver": res["conflict"]})
        self.touch(uid)
        referral_progress(uid)
        self.send_json(200, {"ok": True, "game": res["game"], "ver": res["ver"]})

    # ---------- invite a friend ----------
    def api_invite(self):
        user = self.session_user()
        if not user:
            return self.error(401, "Log in first.")
        code = ref_code_for(user["id"])
        rows = q("SELECT u.name, u.company, u.color, r.created, r.active_at, r.paid_at, r.days_given FROM referrals r "
                 "JOIN users u ON u.id=r.user_id WHERE r.inviter_id=? ORDER BY r.created DESC LIMIT 100", (user["id"],))
        friends = [{"name": r["name"], "company": r["company"], "color": r["color"], "joined": r["created"],
                    "active": bool(r["active_at"]), "paid": bool(r["paid_at"]), "days": r["days_given"]} for r in rows]
        self.send_json(200, {"code": code, "link": "https://%s/?ref=%s" % (SITE_DOMAIN or "hustlempires.com", code),
                             "friends": friends, "daysEarned": sum(f["days"] for f in friends),
                             "trialDays": REF_TRIAL_DAYS, "activeDays": REF_ACTIVE_DAYS, "paidDays": REF_PAID_DAYS,
                             "cap": REF_MONTHLY_CAP, "billing": BILLING_ON})

    def api_invite_check(self):
        """Who invited me? Shown on the sign-up screen. Only the first name and company."""
        if rate_limited("refcheck:" + self.client_ip(), limit=60, window=600):
            return self.error(429, "Too many requests.")
        code = (parse_qs(urlparse(self.path).query).get("code") or [""])[0]
        inv = inviter_by_code(code)
        if not inv:
            return self.send_json(200, {"ok": False})
        self.send_json(200, {"ok": True, "name": (inv["name"] or "").split()[0][:24], "company": inv["company"],
                             "trialDays": REF_TRIAL_DAYS if BILLING_ON else 0})

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
        if not pesapal_ready():
            return self.error(503, "Payments aren't switched on yet. Please try again later.")
        if rate_limited("checkout:%d" % user["id"], limit=12, window=3600):
            return self.error(429, "Too many payment attempts. Wait a few minutes and try again.")
        d = self.read_json()
        if d is None:
            return
        if d.get("tip") is not None:
            try:
                amt = int(round(float(d.get("tip"))))
            except (TypeError, ValueError):
                return self.error(400, "Choose an amount.")
            if amt < TIP_MIN or amt > TIP_MAX:
                return self.error(400, "Tips can be from KSh %d to KSh %s." % (TIP_MIN, "{:,}".format(TIP_MAX)))
            plan, p = "tip", {"name": "Tip for the developers", "days": 0, "kes": amt}
        else:
            if not BILLING_ON:
                return self.error(400, "The game is free now. There is no pass to buy.")
            plan = d.get("plan") if d.get("plan") in PLANS else None
            if not plan:
                return self.error(400, "Choose a pass.")
            p = PLANS[plan]
        if not user["email"]:
            return self.error(400, "Add your email first (in your account menu). Pesapal sends your receipt there.")
        t = now()
        ref = "HS%d-%s" % (user["id"], secrets.token_hex(4).upper())
        q("INSERT INTO payments(ref,user_id,plan,days,amount,currency,created,updated) VALUES(?,?,?,?,?,?,?,?)",
          (ref, user["id"], plan, p["days"], float(p["kes"]), "KES", t, t))
        q("INSERT INTO subs(user_id,checkouts,updated) VALUES(?,1,?) ON CONFLICT(user_id) DO UPDATE SET checkouts=subs.checkouts+1, updated=excluded.updated",
          (user["id"], t))
        names = (user["name"] or "Player").split()
        body = {"id": ref, "currency": "KES", "amount": float(p["kes"]),
                "description": "Hustlempires - %s" % p["name"],
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
          (user["id"], t, self.current_game(user["id"]), "Opened the payment page for a KSh %s tip" % "{:,}".format(p["kes"]) if plan == "tip" else
           "Opened the payment page for the %s" % p["name"].lower()))
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
        if me:
            up = q("SELECT u.name, s.pts FROM season_scores s JOIN users u ON u.id=s.user_id WHERE s.season=? AND s.region=? AND s.pts>? "
                   "AND u.disabled=0 ORDER BY s.pts ASC LIMIT 1", (sid, mine["region"], mine["pts"]), one=True)
            if up:
                me["ahead"] = {"name": (up["name"] or "A rival").split(" ")[0], "gap": up["pts"] - mine["pts"]}
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
        out = {"players": [dict(r) for r in rows], "ms": {}, "gens": {}}
        # ?region=KE limits every list to lives played in that country
        region = re.sub(r"[^A-Z]", "", ((parse_qs(urlparse(self.path).query).get("region") or [""])[0]).upper())[:3]
        rw = ("l.region='%s' AND " % region) if region else ""
        base = ("SELECT u.name,u.company,u.color,l.who,l.region,l.gen,l.best,%s FROM lifeboard l JOIN users u ON u.id=l.user_id "
                "WHERE u.disabled=0 AND " + rw + "%s")
        for k, _ in MS_KEYS:
            col = "ms_" + k
            # one entry per player: their youngest founder life to reach it
            out["ms"][k] = [dict(r) for r in q(base % ("MIN(l.%s) age_m" % col, "l.gen=1 AND l.%s IS NOT NULL GROUP BY l.user_id ORDER BY age_m, MIN(l.updated) LIMIT 10" % col))]
        # the company each player runs today, valued by everything it owns
        out["companies"] = [dict(r) for r in q("SELECT u.name,u.company,u.color,l.who,l.region,l.gen,l.co FROM lifeboard l JOIN users u ON u.id=l.user_id "
                                               "JOIN stats s ON s.user_id=l.user_id AND s.games=l.game WHERE u.disabled=0 AND " + rw + "l.co>0 ORDER BY l.co DESC LIMIT 10")]
        out["founders"] = [dict(r) for r in q(base % ("MAX(l.best) top", "l.gen=1 AND l.best>0 GROUP BY l.user_id ORDER BY top DESC LIMIT 15"))]
        for r in q("SELECT DISTINCT gen FROM lifeboard WHERE gen>1 ORDER BY gen LIMIT 12"):
            g = r["gen"]
            out["gens"][str(g)] = [dict(x) for x in q(base % ("MAX(l.best) top", "l.gen=? AND l.best>0 GROUP BY l.user_id ORDER BY top DESC LIMIT 10"), (g,))]
        self.send_json(200, out)

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

    def api_admin_campaign(self):
        """Add, edit, archive or restore a campaign link."""
        if not self.is_admin():
            return self.error(401, "Log in as admin.")
        d = self.read_json()
        if d is None:
            return
        code = clean_camp(d.get("code"))
        if not code:
            return self.error(400, "Link codes are 1 to 30 characters: small letters, numbers and dashes.")
        old = q("SELECT * FROM campaigns WHERE code=?", (code,), one=True)
        if d.get("archive") is not None:
            if not old:
                return self.error(404, "No such campaign.")
            q("UPDATE campaigns SET archived=? WHERE code=?", (1 if d.get("archive") else 0, code))
            return self.send_json(200, {"ok": True})
        if d.get("new") and old:
            return self.error(409, "That link code is already used. Pick another.")
        name = clean_text(d.get("name"), 60) or (old["name"] if old else code)
        channel = d.get("channel") if d.get("channel") in CHANNELS else (old["channel"] if old else "other")
        note = clean_text(d.get("note"), 120) if d.get("note") is not None else (old["note"] if old else "")
        try:
            cost = max(0.0, min(1e9, float(d.get("cost")))) if d.get("cost") not in (None, "") else (old["cost"] if old else 0.0)
        except (TypeError, ValueError):
            return self.error(400, "Spend must be a number of shillings.")
        q("INSERT INTO campaigns(code,name,channel,cost,note,created) VALUES(?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET "
          "name=excluded.name, channel=excluded.channel, cost=excluded.cost, note=excluded.note", (code, name, channel, cost, note, now()))
        self.send_json(200, {"ok": True, "code": code})

    def api_admin_media_chunk(self):
        """One piece (up to 2.5 MB) of an uploaded image or video, sent as raw bytes."""
        if not self.is_admin():
            return self.error(401, "Log in as admin.")
        qs = parse_qs(urlparse(self.path).query)
        name = (qs.get("id") or [""])[0]
        try:
            offset = int((qs.get("offset") or ["-1"])[0])
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.error(400, "Bad upload request.")
        if not MEDIA_RE.match(name) or length <= 0 or length > 3 * 1024 * 1024:
            return self.error(400, "Bad upload request.")
        part = os.path.join(MEDIA_DIR, name + ".part")
        if not os.path.isfile(part):
            return self.error(404, "That upload has expired. Start it again.")
        have = os.path.getsize(part)
        data = self.rfile.read(length)
        if offset != have:
            return self.send_json(409, {"error": "Out of order.", "have": have})
        if have + len(data) > MEDIA_MAX[name.rsplit(".", 1)[1]]:
            os.remove(part)
            return self.error(413, "That file is too large.")
        with open(part, "ab") as f:
            f.write(data)
        self.send_json(200, {"ok": True, "have": have + len(data)})

    def api_admin_posts(self, path):
        if not self.is_admin():
            return self.error(401, "Log in as admin.")
        d = self.read_json()
        if d is None:
            return
        t = now()
        if path == "/api/admin/media/start":
            ext = MEDIA_TYPES.get(str(d.get("type") or "").lower())
            if not ext:
                return self.error(400, "Use a JPG image or an MP4/MOV video.")
            try:
                size = int(d.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            if size <= 0 or size > MEDIA_MAX[ext]:
                return self.error(400, "Images can be up to 8 MB and videos up to 300 MB.")
            os.makedirs(MEDIA_DIR, exist_ok=True)
            for f in os.listdir(MEDIA_DIR):   # clear abandoned uploads
                fp = os.path.join(MEDIA_DIR, f)
                if f.endswith(".part") and os.path.getmtime(fp) < t - 6 * 3600:
                    os.remove(fp)
            name = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(24)) + "." + ext
            open(os.path.join(MEDIA_DIR, name + ".part"), "wb").close()
            return self.send_json(200, {"id": name, "chunk": 2500000})
        if path == "/api/admin/media/done":
            name = str(d.get("id") or "")
            part = os.path.join(MEDIA_DIR, name + ".part")
            if not MEDIA_RE.match(name) or not os.path.isfile(part):
                return self.error(404, "That upload has expired. Start it again.")
            if int(d.get("size") or -1) != os.path.getsize(part):
                return self.error(400, "The upload is incomplete. Try again.")
            os.replace(part, os.path.join(MEDIA_DIR, name))
            return self.send_json(200, {"ok": True, "id": name, "url": "/media/" + name})
        if path == "/api/admin/posts":
            pf = d.get("platforms") if isinstance(d.get("platforms"), list) else []
            fb, ig = "fb" in pf, "ig" in pf
            kind = d.get("kind") if d.get("kind") in ("photo", "video", "text") else "text"
            media = str(d.get("media") or "")
            caption = clean_text(d.get("caption"), 2100) if not isinstance(d.get("caption"), str) else d["caption"].replace("\r", "")[:2100]
            if not (fb or ig):
                return self.error(400, "Choose Facebook, Instagram or both.")
            if kind != "text" and (not MEDIA_RE.match(media) or not os.path.isfile(os.path.join(MEDIA_DIR, media))):
                return self.error(400, "Upload the image or video first.")
            if kind == "text":
                media = ""
                if ig:
                    return self.error(400, "Instagram posts need an image or a video.")
                if not caption.strip():
                    return self.error(400, "Write the post text.")
            if kind == "photo" and not media.endswith(".jpg") or kind == "video" and media.endswith(".jpg"):
                return self.error(400, "The file type doesn't match the post type.")
            try:
                due = int(d.get("due") or 0)
            except (TypeError, ValueError):
                due = 0
            if due < t - 300:
                due = t
            if due > t + 180 * 86400:
                return self.error(400, "Posts can be scheduled up to 6 months ahead.")
            if not (SITE_DOMAIN or "").strip() and kind != "text":
                return self.error(400, "The server needs HUSTLE_SITE_DOMAIN set so Meta can fetch the file.")
            link = 1 if d.get("link", True) else 0
            cur = tx(lambda db: db.execute("INSERT INTO posts(created,due,kind,caption,media,link,fb_status,ig_status,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                                           (t, due, kind, caption, media, link, "scheduled" if fb else "", "scheduled" if ig else "", t)).lastrowid)
            if link:
                title = re.sub(r"\s+", " ", caption).strip()[:40] or ("Video post" if kind == "video" else "Photo post")
                for flag, pfx, ch in ((fb, "fb", "facebook"), (ig, "ig", "instagram")):
                    if flag:
                        q("INSERT OR IGNORE INTO campaigns(code,name,channel,cost,note,created) VALUES(?,?,?,0,?,?)",
                          ("%s-post-%d" % (pfx, cur), "%s post: %s" % ("Facebook" if pfx == "fb" else "Instagram", title), ch, "Scheduled post #%d" % cur, t))
            return self.send_json(200, {"ok": True, "id": cur})
        try:
            pid = int(d.get("id") or 0)
        except (TypeError, ValueError):
            pid = 0
        p = q("SELECT * FROM posts WHERE id=?", (pid,), one=True)
        if not p:
            return self.error(404, "No such post.")
        if path == "/api/admin/posts/cancel":
            q("UPDATE posts SET fb_status=CASE WHEN fb_status='scheduled' THEN 'cancelled' ELSE fb_status END, "
              "ig_status=CASE WHEN ig_status='scheduled' THEN 'cancelled' ELSE ig_status END, updated=? WHERE id=?", (t, pid))
            return self.send_json(200, {"ok": True})
        if path == "/api/admin/posts/retry":
            q("UPDATE posts SET fb_status=CASE WHEN fb_status IN ('failed','cancelled') THEN 'scheduled' ELSE fb_status END, fb_error='', "
              "ig_status=CASE WHEN ig_status IN ('failed','cancelled') THEN 'scheduled' ELSE ig_status END, ig_error='', ig_container=CASE WHEN ig_status IN ('failed','cancelled') THEN '' ELSE ig_container END, "
              "due=CASE WHEN due<? THEN ? ELSE due END, updated=? WHERE id=?", (t, t, t, pid))
            return self.send_json(200, {"ok": True})
        if path == "/api/admin/posts/time":
            try:
                due = int(d.get("due") or 0)
            except (TypeError, ValueError):
                return self.error(400, "Pick a date and time.")
            if p["fb_status"] != "scheduled" and p["ig_status"] != "scheduled":
                return self.error(400, "Only scheduled posts can be moved.")
            q("UPDATE posts SET due=?, updated=? WHERE id=?", (max(due, t), t, pid))
            return self.send_json(200, {"ok": True})
        if path == "/api/admin/posts/delete":
            if p["fb_status"] == "scheduled" or p["ig_status"] in ("scheduled", "processing"):
                return self.error(400, "Cancel the post before removing it.")
            q("DELETE FROM posts WHERE id=?", (pid,))
            q("DELETE FROM post_stats WHERE post_id=?", (pid,))
            return self.send_json(200, {"ok": True})
        if path == "/api/admin/posts/stats":
            if rate_limited("poststats", limit=10, window=3600):
                return self.error(429, "Meta limits how often we can ask. Try again in a few minutes.")
            stats_refresh(force_ids={pid})
            return self.send_json(200, posts_report(t))
        if path == "/api/admin/posts/check":
            page_discover()
            try:
                dbg = graph_get("debug_token", {"input_token": META_TOKEN}).get("data") or {}
                meta_set("meta_token", json.dumps({"expires": dbg.get("expires_at") or 0, "valid": dbg.get("is_valid"), "scopes": dbg.get("scopes") or []}))
            except Exception:
                pass
            return self.send_json(200, posts_report(t))
        self.error(404, "Not found.")

    def api_admin_audiences(self, path):
        if not self.is_admin():
            return self.error(401, "Log in as admin.")
        d = self.read_json()
        if d is None:
            return
        t = now()
        if path.endswith("/save"):
            name = clean_text(d.get("name"), 60)
            if not name:
                return self.error(400, "Give the audience a name.")
            spec = clean_audience(d.get("spec") if isinstance(d.get("spec"), dict) else {})
            spec["interests"] = json.loads(spec["interests"])
            try:
                aid = int(d.get("id") or 0)
            except (TypeError, ValueError):
                aid = 0
            if aid and q("SELECT 1 FROM audiences WHERE id=?", (aid,), one=True):
                q("UPDATE audiences SET name=?, spec=?, updated=? WHERE id=?", (name, json.dumps(spec), t, aid))
            else:
                aid = tx(lambda db: db.execute("INSERT INTO audiences(name,spec,created,updated) VALUES(?,?,?,?)", (name, json.dumps(spec), t, t)).lastrowid)
            return self.send_json(200, {"ok": True, "id": aid, "report": ads_runs_report(now())})
        if path.endswith("/delete"):
            q("DELETE FROM audiences WHERE id=?", (int(d.get("id") or 0),))
            return self.send_json(200, {"ok": True, "report": ads_runs_report(now())})
        if path.endswith("/estimate"):
            if not meta_ready():
                return self.error(400, "Connect Meta first.")
            if rate_limited("estimate", limit=60, window=600):
                return self.error(429, "Too many estimates. Wait a few minutes.")
            r = clean_audience(d.get("spec") if isinstance(d.get("spec"), dict) else {})
            r["objective"] = d.get("objective")
            return self.send_json(200, audience_estimate(r))
        self.error(404, "Not found.")

    def api_admin_manager(self, path):
        """Switch a campaign, ad set or ad on or off, or change a daily budget, with the same KSh cap as ads started here."""
        if not self.is_admin():
            return self.error(401, "Log in as admin.")
        d = self.read_json()
        if d is None:
            return
        if not meta_ready():
            return self.error(400, "Connect Meta first.")
        level = d.get("level")
        oid = re.sub(r"[^0-9]", "", str(d.get("id") or ""))[:30]
        table, col = {"campaign": ("meta_campaigns", "campaign_id"), "adset": ("meta_adsets", "adset_id"), "ad": ("meta_ads", "ad_id")}.get(level, (None, None))
        if not table or not oid:
            return self.error(400, "Bad request.")
        row = q("SELECT * FROM %s WHERE %s=?" % (table, col), (oid,), one=True)
        if not row:
            return self.error(404, "Not found. Press Refresh from Meta first.")
        cur = account_currency()
        if cur and cur != "KES":
            return self.error(400, "The ad account bills in %s. The admin only changes ads on a KES account." % cur)

        def budget_of(camp_id, set_id=None):
            """The daily spend that switching this on could allow, from the campaign or its ad sets."""
            c = q("SELECT daily_budget, lifetime_budget FROM meta_campaigns WHERE campaign_id=?", (camp_id,), one=True)
            if c and (c["daily_budget"] or c["lifetime_budget"]):
                return c["daily_budget"], c["lifetime_budget"]
            rs = q("SELECT daily_budget, lifetime_budget FROM meta_adsets WHERE campaign_id=?" + (" AND adset_id=?" if set_id else ""),
                   (camp_id, set_id) if set_id else (camp_id,))
            return sum(r["daily_budget"] for r in rs), sum(r["lifetime_budget"] for r in rs)
        t = now()
        if path.endswith("toggle"):
            on = bool(d.get("on"))
            if on:
                camp = row["campaign_id"]
                daily, life = budget_of(camp, row["adset_id"] if level == "adset" else None)
                if life:
                    return self.error(400, "This uses a lifetime budget. Switch it on in Ads Manager, or give it a daily budget of up to KSh {:,}.".format(AD_DAILY_CAP))
                if daily > AD_DAILY_CAP:
                    return self.error(400, "Its daily budget is KSh {:,}, above the KSh {:,} limit. Lower the budget first.".format(int(daily), AD_DAILY_CAP))
            graph_post(oid, {"status": "ACTIVE" if on else "PAUSED"})
            q("UPDATE %s SET onoff=?, updated=? WHERE %s=?" % (table, col), ("ACTIVE" if on else "PAUSED", t, oid))
            if level == "campaign":
                q("UPDATE ad_runs SET status=?, updated=? WHERE campaign_id=? AND status IN ('active','paused')", ("active" if on else "paused", t, oid))
        else:
            if level not in ("campaign", "adset"):
                return self.error(400, "Budgets are set on campaigns or ad sets.")
            try:
                b = int(round(float(d.get("daily"))))
            except (TypeError, ValueError):
                b = 0
            if not 100 <= b <= AD_DAILY_CAP:
                return self.error(400, "The daily budget must be between KSh 100 and KSh {:,}.".format(AD_DAILY_CAP))
            if row["lifetime_budget"]:
                return self.error(400, "This uses a lifetime budget. Change it in Ads Manager.")
            if not row["daily_budget"]:
                return self.error(400, "The budget for this is set on its %s. Change it there." % ("ad sets" if level == "campaign" else "campaign"))
            graph_post(oid, {"daily_budget": str(b * 100)})
            q("UPDATE %s SET daily_budget=?, updated=? WHERE %s=?" % (table, col), (b, t, oid))
            if level == "campaign":
                q("UPDATE ad_runs SET daily_kes=?, updated=? WHERE campaign_id=?", (b, t, oid))
        self.send_json(200, {"ok": True})

    def api_admin_adruns(self, path):
        """Start, pause, resume, stop or re-budget an ad run from the admin. Every amount is checked against the daily cap."""
        if not self.is_admin():
            return self.error(401, "Log in as admin.")
        d = self.read_json()
        if d is None:
            return
        if not meta_ready():
            return self.error(400, "Connect Meta first.")
        t = now()
        cur = account_currency()
        if cur and cur != "KES":
            return self.error(400, "The ad account bills in %s. The admin only runs ads on a KES ad account." % cur)

        def budget(v):
            try:
                b = int(round(float(v)))
            except (TypeError, ValueError):
                return None
            return b if 100 <= b <= AD_DAILY_CAP else None
        if path == "/api/admin/adruns/start":
            # One campaign (new or existing) with one or more ad sets (new or existing), each with one or more ads.
            # Older pages send {campaign, adset, ad}; that is one ad set with one ad.
            C = d.get("campaign") if isinstance(d.get("campaign"), dict) else {}
            SETS = d.get("adsets")
            if not isinstance(SETS, list):
                S0 = dict(d.get("adset")) if isinstance(d.get("adset"), dict) else {}
                S0["ads"] = [d.get("ad")] if isinstance(d.get("ad"), dict) else []
                SETS = [S0]
            SETS = [s for s in SETS if isinstance(s, dict)]
            if not SETS:
                return self.error(400, "Add at least one ad set.")
            if len(SETS) > AD_MAX_SETS:
                return self.error(400, "One campaign can get up to %d new ad sets at a time." % AD_MAX_SETS)
            n_ads = sum(len(s.get("ads") or []) for s in SETS)
            if n_ads > AD_MAX_ADS:
                return self.error(400, "Publish up to %d ads at a time." % AD_MAX_ADS)
            # ---- campaign: new, or one already on the account
            camp_id = re.sub(r"[^0-9]", "", str(C.get("id") or ""))[:30]
            objective, budget_level, camp_daily, camp_name = "OUTCOME_TRAFFIC", "campaign", 0, ""
            if camp_id:
                c = q("SELECT * FROM meta_campaigns WHERE campaign_id=?", (camp_id,), one=True)
                if not c:
                    return self.error(404, "That campaign isn't in the list yet. Press Refresh from Meta.")
                objective = c["objective"] if c["objective"] in AD_OBJECTIVES else "OUTCOME_TRAFFIC"
                budget_level = "campaign" if (c["daily_budget"] or c["lifetime_budget"]) else "adset"
                camp_name = c["name"]
            else:
                objective = C.get("objective") if C.get("objective") in AD_OBJECTIVES else "OUTCOME_TRAFFIC"
                budget_level = "adset" if C.get("budget_level") == "adset" else "campaign"
                camp_name = clean_text(C.get("name"), 80)
                if not camp_name:
                    return self.error(400, "Give the campaign a name.")
                if budget_level == "campaign":
                    camp_daily = budget(C.get("daily"))
                    if camp_daily is None:
                        return self.error(400, "The campaign's daily budget must be between KSh 100 and KSh {:,}.".format(AD_DAILY_CAP))
            existing_daily = q("SELECT COALESCE(SUM(daily_budget),0) s FROM meta_adsets WHERE campaign_id=? AND status NOT IN ('DELETED','ARCHIVED')",
                               (camp_id,), one=True)["s"] if camp_id else 0
            plan, new_set_daily, longest = [], 0, 0
            for si, S in enumerate(SETS):
                where = "Ad set %d: " % (si + 1) if len(SETS) > 1 else ""
                set_id = re.sub(r"[^0-9]", "", str(S.get("id") or ""))[:30]
                set_daily, set_name, start, end = 0, "", 0, 0
                aud = {"countries": "KE", "age_min": 18, "age_max": 45, "genders": "", "interests": "[]", "platforms": "all"}
                if set_id:
                    if not camp_id:
                        return self.error(400, where + "an existing ad set can only be used with its own campaign.")
                    sr = q("SELECT * FROM meta_adsets WHERE adset_id=?", (set_id,), one=True)
                    if not sr:
                        return self.error(404, where + "that ad set isn't in the list yet. Press Refresh from Meta.")
                    if sr["campaign_id"] != camp_id:
                        return self.error(400, where + "that ad set belongs to another campaign.")
                    set_name = sr["name"]
                    try:
                        et = sr["end_time"] or ""
                        end = int(datetime.datetime.strptime(et[:24], "%Y-%m-%dT%H:%M:%S%z").timestamp()) if len(et) >= 24 else \
                            int(datetime.datetime.strptime(et[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp()) if et else t + 365 * 86400
                    except ValueError:
                        end = t + 365 * 86400
                    start = t
                else:
                    if budget_level == "adset":
                        set_daily = budget(S.get("daily"))
                        if set_daily is None:
                            return self.error(400, where + "the daily budget must be between KSh 100 and KSh {:,}.".format(AD_DAILY_CAP))
                        new_set_daily += set_daily
                    set_name = clean_text(S.get("name"), 80)
                    aud = clean_audience(S.get("audience") if isinstance(S.get("audience"), dict) else {})
                    try:
                        days = int(S.get("days") or 0)
                    except (TypeError, ValueError):
                        days = 0
                    if not 1 <= days <= AD_MAX_DAYS:
                        return self.error(400, where + "ad sets can run from 1 to %d days." % AD_MAX_DAYS)
                    try:
                        start = max(t + 120, int(S.get("start") or 0))
                    except (TypeError, ValueError):
                        start = t + 120
                    end = start + days * 86400
                    longest = max(longest, days)
                ADS = [a for a in (S.get("ads") or []) if isinstance(a, dict)]
                if not ADS:
                    return self.error(400, where + "add at least one ad.")
                if len(ADS) > AD_MAX_PER_SET:
                    return self.error(400, where + "up to %d ads per ad set." % AD_MAX_PER_SET)
                ads = []
                for ai, A in enumerate(ADS):
                    w2 = where + ("ad %d: " % (ai + 1) if len(ADS) > 1 else "")
                    kind = A.get("kind")
                    if kind not in ("boost_fb", "boost_ig", "new"):
                        return self.error(400, w2 + "choose what the ad shows.")
                    cta = A.get("cta") if A.get("cta") in AD_CTAS else "PLAY_GAME"
                    name = clean_text(A.get("name"), 60)
                    post_id, media, caption, headline = 0, "", "", ""
                    if kind in ("boost_fb", "boost_ig"):
                        try:
                            post_id = int(A.get("post_id") or 0)
                        except (TypeError, ValueError):
                            post_id = 0
                        p = q("SELECT * FROM posts WHERE id=?", (post_id,), one=True)
                        pf = "fb" if kind == "boost_fb" else "ig"
                        if not p or p[pf + "_status"] != "posted" or not p[pf + "_id"]:
                            return self.error(400, w2 + "that post isn't published on %s." % ("Facebook" if pf == "fb" else "Instagram"))
                        name = name or re.sub(r"\s+", " ", p["caption"]).strip()[:40] or "Post %d" % post_id
                    else:
                        media = str(A.get("media") or "")
                        if not MEDIA_RE.match(media) or not os.path.isfile(os.path.join(MEDIA_DIR, media)):
                            return self.error(400, w2 + "upload the photo or video first.")
                        caption = (A.get("caption") if isinstance(A.get("caption"), str) else "").replace("\r", "")[:2000]
                        headline = clean_text(A.get("headline"), 40)
                        if not caption.strip():
                            return self.error(400, w2 + "write the ad text.")
                        name = name or re.sub(r"\s+", " ", caption).strip()[:40]
                    ads.append({"kind": kind, "cta": cta, "name": name, "post_id": post_id, "media": media, "caption": caption, "headline": headline})
                if not set_id:
                    # a boosted post can only run where it was posted, so a new ad set follows its boosts
                    boosts = {a["kind"] for a in ads if a["kind"] != "new"}
                    if len(boosts) > 1:
                        return self.error(400, where + "a boosted Facebook post and a boosted Instagram post can't share an ad set. Put them in separate ad sets.")
                    if boosts:
                        want = "facebook" if "boost_fb" in boosts else "instagram"
                        if aud["platforms"] not in ("all", want):
                            return self.error(400, where + "a boosted %s post can only show on %s." % (want.title(), want.title()))
                        aud["platforms"] = want
                if not set_id:
                    bad = interests_invalid(aud)
                    if bad:
                        return self.error(400, where + "Meta no longer accepts the interest%s %s. Remove %s and publish again." % (
                            "" if len(bad) == 1 else "s", ", ".join(b["name"] for b in bad), "it" if len(bad) == 1 else "them"))
                plan.append({"set_id": set_id, "set_name": set_name, "set_daily": set_daily, "start": start, "end": end, "aud": aud, "ads": ads})
            if budget_level == "adset" and existing_daily + new_set_daily > AD_DAILY_CAP:
                return self.error(400, ("This campaign's ad sets already spend up to KSh {:,} a day. Adding KSh {:,} would pass the KSh {:,} limit." if existing_daily else
                                        "Together these ad sets spend KSh {1:,} a day, more than the KSh {2:,} limit.").format(int(existing_daily), new_set_daily, AD_DAILY_CAP))
            # ---- the most this can add to spending, which must be confirmed
            most = camp_daily * longest if camp_daily else sum(p["set_daily"] * max(1, (p["end"] - p["start"] + 86399) // 86400) for p in plan if p["set_daily"])
            if most and (not str(d.get("confirm") or "").isdigit() or int(d.get("confirm")) != most):
                return self.error(400, "Confirm the most this can spend (KSh {:,}) first.".format(most))
            batch = "b%d%04d" % (t, secrets.randbelow(10000))
            ids = []
            for si, p in enumerate(plan):
                for ai, a in enumerate(p["ads"]):
                    first_camp = not camp_id and not ids
                    first_set = not p["set_id"] and ai == 0
                    aud = p["aud"]
                    aid = tx(lambda db: db.execute(
                        "INSERT INTO ad_runs(created,kind,post_id,name,caption,headline,media,cta,countries,age_min,age_max,platforms,daily_kes,start_ts,end_ts,status,updated,"
                        "objective,budget_level,genders,interests,campaign_name,adset_name,adset_daily,campaign_id,adset_id,batch,bset) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'creating',?,?,?,?,?,?,?,?,?,?,?,?)",
                        (t, a["kind"], a["post_id"], a["name"], a["caption"], a["headline"], a["media"], a["cta"], aud["countries"], aud["age_min"], aud["age_max"],
                         aud["platforms"], camp_daily if (first_camp and camp_daily) else (p["set_daily"] if first_set else 0), p["start"], p["end"], t, objective, budget_level,
                         aud["genders"], aud["interests"], camp_name, p["set_name"], p["set_daily"] if first_set else 0, camp_id, p["set_id"], batch, si)).lastrowid)
                    q("INSERT OR IGNORE INTO campaigns(code,name,channel,cost,note,created) VALUES(?,?,?,0,?,?)",
                      ("ad-%d" % aid, "Ad: %s" % a["name"], "ads", "Run from the admin", t))
                    ids.append((aid, si))
            st, failed, errors = "active", 0, []
            with AD_LOCK:
                for aid, si in ids:
                    r = dict(q("SELECT * FROM ad_runs WHERE id=?", (aid,), one=True))
                    # reuse the campaign and ad set that earlier ads in this batch already made; if those failed, this ad makes them
                    if not r["campaign_id"]:
                        prev = q("SELECT campaign_id FROM ad_runs WHERE batch=? AND campaign_id<>'' AND status<>'failed' LIMIT 1", (batch,), one=True)
                        if prev:
                            r["campaign_id"] = prev["campaign_id"]
                            ad_set(aid, campaign_id=prev["campaign_id"])
                        elif budget_level == "campaign" and not r["daily_kes"]:
                            r["daily_kes"] = camp_daily
                            ad_set(aid, daily_kes=camp_daily)
                    if not r["adset_id"] and not plan[si]["set_id"]:
                        prev = q("SELECT adset_id FROM ad_runs WHERE batch=? AND bset=? AND adset_id<>'' AND status<>'failed' LIMIT 1", (batch, si), one=True)
                        if prev:
                            r["adset_id"] = prev["adset_id"]
                            ad_set(aid, adset_id=prev["adset_id"])
                        elif plan[si]["set_daily"] and not r["adset_daily"]:
                            r["adset_daily"] = plan[si]["set_daily"]
                            ad_set(aid, adset_daily=r["adset_daily"], daily_kes=r["daily_kes"] or r["adset_daily"])
                    try:
                        s1 = ad_build(r)
                        if s1 == "processing":
                            st = "processing"
                    except Exception as e:
                        failed += 1
                        errors.append("%s: %s" % (r["name"], e))
            try:
                meta_sync()
            except Exception:
                pass
            rep = ads_runs_report(now())
            if failed == len(ids):
                return self.send_json(502, {"error": errors[0] if len(errors) == 1 else "None of the ads could be created. " + " · ".join(errors[:3]), "report": rep})
            return self.send_json(200, {"ok": True, "status": st, "made": len(ids) - failed, "failed": failed, "errors": errors[:5], "report": rep})
        try:
            aid = int(d.get("id") or 0)
        except (TypeError, ValueError):
            aid = 0
        r = q("SELECT * FROM ad_runs WHERE id=?", (aid,), one=True)
        if not r:
            return self.error(404, "No such ad.")
        # what to switch: the whole campaign if this run made it, otherwise only this run's ad set or ad
        target = r["campaign_id"] if r["made_campaign"] else r["adset_id"] if r["made_adset"] else r["ad_id"]
        if path == "/api/admin/adruns/pause" or path == "/api/admin/adruns/stop":
            if target:
                graph_post(target, {"status": "PAUSED"})
            ad_set(aid, status="stopped" if path.endswith("stop") else "paused")
        elif path == "/api/admin/adruns/resume":
            if r["status"] not in ("paused",) or r["end_ts"] < t:
                return self.error(400, "Only paused ads that haven't reached their end date can be resumed.")
            graph_post(target, {"status": "ACTIVE"})
            ad_set(aid, status="active")
        elif path == "/api/admin/adruns/budget":
            b = budget(d.get("daily"))
            if b is None:
                return self.error(400, "The daily budget must be between KSh 100 and KSh {:,}.".format(AD_DAILY_CAP))
            if r["made_campaign"] and r["budget_level"] != "adset" and r["campaign_id"]:
                graph_post(r["campaign_id"], {"daily_budget": str(b * 100)})
            elif r["made_adset"] and r["adset_daily"] and r["adset_id"]:
                other = q("SELECT COALESCE(SUM(daily_budget),0) s FROM meta_adsets WHERE campaign_id=? AND adset_id<>? AND status NOT IN ('DELETED','ARCHIVED')",
                          (r["campaign_id"], r["adset_id"]), one=True)["s"]
                if other + b > AD_DAILY_CAP:
                    return self.error(400, "With the campaign's other ad sets that would pass KSh {:,} a day.".format(AD_DAILY_CAP))
                graph_post(r["adset_id"], {"daily_budget": str(b * 100)})
                ad_set(aid, adset_daily=b)
            else:
                return self.error(400, "This ad uses an existing budget. Change it in the Ads Manager table.")
            ad_set(aid, daily_kes=b)
        elif path == "/api/admin/adruns/remove":
            if r["status"] in ("active", "processing", "creating", "paused"):
                return self.error(400, "Stop the ad before removing it from the list.")
            q("DELETE FROM ad_runs WHERE id=?", (aid,))
        else:
            return self.error(404, "Not found.")
        self.send_json(200, {"ok": True, "report": ads_runs_report(now())})

    def api_admin_ads(self, path):
        if not self.is_admin():
            return self.error(401, "Log in as admin.")
        d = self.read_json()
        if d is None:
            return
        if not meta_ready():
            return self.error(400, "Meta ads aren't connected on the server yet.")
        if path.endswith("sync"):
            if rate_limited("metasync", limit=6, window=3600):
                return self.error(429, "Meta limits how often we can ask. Try again in a few minutes.")
            ok = meta_sync(full=bool(d.get("full")))
            st = meta_get_state()
            return self.send_json(200 if ok else 502, {"ok": ok, "error": "" if ok else (st.get("error") or "The sync is already running. Wait a minute.")})
        cid = re.sub(r"[^0-9]", "", str(d.get("campaign_id") or ""))[:30]
        if not cid or not q("SELECT 1 FROM meta_campaigns WHERE campaign_id=?", (cid,), one=True):
            return self.error(404, "No such ad campaign.")
        code = clean_camp(d.get("code"))
        if code:
            q("UPDATE meta_campaigns SET code=?, manual=1 WHERE campaign_id=?", (code, cid))
        else:
            codes = [r["code"] for r in q("SELECT code FROM meta_ads WHERE campaign_id=? AND code<>''", (cid,))]
            q("UPDATE meta_campaigns SET code=?, manual=0 WHERE campaign_id=?", (max(set(codes), key=codes.count) if codes else "", cid))
        self.send_json(200, {"ok": True})

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
        if path == "/api/admin/posts":
            return self.send_json(200, posts_report(now()))
        if path == "/api/admin/adruns":
            return self.send_json(200, ads_runs_report(now()))
        if path == "/api/admin/pixel":
            return self.send_json(200, {"id": pixel_id()})
        if path == "/api/admin/interests":
            qt = clean_text((parse_qs(urlparse(self.path).query).get("q") or [""])[0], 60)
            if len(qt) < 2:
                return self.send_json(200, {"data": []})
            if rate_limited("interests", limit=120, window=600):
                return self.error(429, "Too many searches. Wait a few minutes.")
            try:
                return self.send_json(200, {"data": interest_search(qt)})
            except RuntimeError as e:
                return self.error(502, str(e))
        if path == "/api/admin/manager":
            try:
                days = int((parse_qs(urlparse(self.path).query).get("days") or ["30"])[0])
            except ValueError:
                days = 30
            return self.send_json(200, manager_report(now(), days if days in (1, 7, 30, 90, 365) else 30, admin_range(self.path, now())))
        if path == "/api/admin/ads":
            try:
                days = int((parse_qs(urlparse(self.path).query).get("days") or ["30"])[0])
            except ValueError:
                days = 30
            return self.send_json(200, ads_report(now(), days if days in (7, 30, 90, 365) else 30, admin_range(self.path, now())))
        if path in ("/api/admin/marketing", "/api/admin/challenge"):
            qs = parse_qs(urlparse(self.path).query)
            t = now()
            if path.endswith("marketing"):
                try:
                    days = int((qs.get("days") or ["30"])[0])
                except ValueError:
                    days = 30
                return self.send_json(200, marketing_report(t, days if days in (7, 30, 90, 365) else 30, admin_range(self.path, t)))
            try:
                mo = max(0, min(12, int((qs.get("m") or ["0"])[0])))
            except ValueError:
                mo = 0
            region = re.sub(r"[^A-Z]", "", ((qs.get("region") or ["KE"])[0] or "").upper())[:3]
            return self.send_json(200, challenge_report(t, mo, region))
        if path == "/api/admin/events":
            t = now()
            q("DELETE FROM ev_log WHERE ts<?", (t - 400 * 86400,))
            rg = admin_range(self.path, t)
            rows = {}
            # "d30" is now "shown in the date range"; choices count only the range too
            for r in q("SELECT ev, COUNT(*) n, SUM(ts>=? AND ts<?) n30, COUNT(DISTINCT user_id) players FROM ev_log GROUP BY ev", (rg["t0"], rg["t1"])):
                rows[r["ev"]] = {"all": r["n"], "d30": r["n30"] or 0, "players": r["players"], "choices": {}}
            for r in q("SELECT ev, choice, COUNT(*) n FROM ev_log WHERE ts>=? AND ts<? GROUP BY ev, choice", (rg["t0"], rg["t1"])):
                if r["ev"] in rows:
                    rows[r["ev"]]["choices"][str(r["choice"])] = r["n"]
            tot = q("SELECT COUNT(*) n, SUM(ts>=? AND ts<?) n30, COUNT(DISTINCT user_id) p FROM ev_log", (rg["t0"], rg["t1"]), one=True)
            return self.send_json(200, {"tuning": tuning(), "stats": rows, "total": tot["n"], "total30": tot["n30"] or 0, "players": tot["p"], "now": t,
                                        "from": rg["d0"], "to": rg["d1"]})
        if path == "/api/admin/deaths":
            t = now()
            counts, recent, total = {}, [], 0
            for r in q("SELECT l.ended, l.data, u.name FROM lives l LEFT JOIN users u ON u.id=l.user_id WHERE l.ended>? ORDER BY l.ended DESC LIMIT 5000", (t - 365 * 86400,)):
                try:
                    d = json.loads(r["data"])
                except (TypeError, ValueError):
                    continue
                if d.get("end") != "died":
                    continue
                k = death_kind(d.get("cause"))
                counts[k] = counts.get(k, 0) + 1
                total += 1
                if len(recent) < 15:
                    recent.append({"when": r["ended"], "name": r["name"] or "", "age": d.get("age"), "cause": (d.get("cause") or "")[:160], "kind": k})
            return self.send_json(200, {"counts": counts, "total": total, "recent": recent, "now": t})
        if path == "/api/admin/payments":
            rg = admin_range(self.path, now(), 3660)
            rows = q("SELECT p.ref,p.plan,p.amount,p.currency,p.status,p.method,p.code,p.created,p.updated,p.user_id,u.name,u.username,u.color "
                     "FROM payments p LEFT JOIN users u ON u.id=p.user_id WHERE p.created>=? AND p.created<? ORDER BY p.id DESC LIMIT 500", (rg["t0"], rg["t1"]))
            return self.send_json(200, {"payments": [dict(r) for r in rows], "now": now(), "from": rg["d0"], "to": rg["d1"]})
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
            invby = q("SELECT u.id, u.name FROM referrals r JOIN users u ON u.id=r.inviter_id WHERE r.user_id=?", (uid,), one=True)
            invn = q("SELECT COUNT(*) c FROM referrals WHERE inviter_id=?", (uid,), one=True)["c"]
            return self.send_json(200, {"user": dict(u), "stats": stats, "snapshots": [dict(s) for s in snaps],
                                        "events": [dict(e) for e in evs], "now": now(),
                                        "pass": {"state": b["state"], "until": b.get("until", 0), "plan": b.get("plan", "")},
                                        "payments": [dict(p) for p in pays],
                                        "invitedBy": dict(invby) if invby else None, "invited": invn})
        self.error(404, "Not found.")

    def admin_overview(self):
        t = now()
        rg = admin_range(self.path, t)
        k = {
            "players": q("SELECT COUNT(*) c FROM users", one=True)["c"],
            "active24h": q("SELECT COUNT(*) c FROM users WHERE last_seen>?", (t - 86400,), one=True)["c"],
            # "active7d" and "signups7d" now cover the admin's date range
            "active7d": q("SELECT COUNT(DISTINCT user_id) c FROM activity_days WHERE day>=? AND day<=?", (rg["d0"], rg["d1"]), one=True)["c"],
            "signups7d": q("SELECT COUNT(*) c FROM users WHERE created>=? AND created<?", (rg["t0"], rg["t1"]), one=True)["c"],
            "from": rg["d0"], "to": rg["d1"], "days": rg["days"],
            "monthsPlayed": q("SELECT COALESCE(SUM(months_played),0) c FROM stats", one=True)["c"],
            "billionaires": q("SELECT COUNT(*) c FROM stats WHERE billion_month IS NOT NULL", one=True)["c"],
            "bankrupt": q("SELECT COUNT(*) c FROM stats WHERE bankrupt=1", one=True)["c"],
        }
        k["retention"] = retention(t, rg)
        try:
            k["dropoff"] = dropoff(t, rg)
        except Exception as e:
            print("Drop-off summary failed: %s" % e, flush=True)
            k["dropoff"] = None
        try:
            k["push"] = push_overview(t, rg)
        except Exception as e:
            print("Notification summary failed: %s" % e, flush=True)
            k["push"] = None
        k["billing"] = billing_overview(t, rg)
        try:
            k["visitors"] = visitors_overview(t, rg)
        except Exception as e:
            print("Visitor summary failed: %s" % e, flush=True)
            k["visitors"] = None
        k["invites"] = {"joined": q("SELECT COUNT(*) c FROM referrals", one=True)["c"],
                        "joined7d": q("SELECT COUNT(*) c FROM referrals WHERE created>=? AND created<?", (rg["t0"], rg["t1"]), one=True)["c"],
                        "active": q("SELECT COUNT(*) c FROM referrals WHERE active_at>0", one=True)["c"],
                        "paid": q("SELECT COUNT(*) c FROM referrals WHERE paid_at>0", one=True)["c"],
                        "inviters": q("SELECT COUNT(DISTINCT inviter_id) c FROM referrals", one=True)["c"],
                        "top": [dict(r) for r in q("SELECT u.id AS user_id, u.name, u.company, u.color, COUNT(*) n, SUM(r.active_at>0) active, SUM(r.paid_at>0) paid "
                                                    "FROM referrals r JOIN users u ON u.id=r.inviter_id GROUP BY r.inviter_id ORDER BY n DESC LIMIT 10")]}
        days = []
        for day, start, end in range_days(rg):
            days.append({
                "day": day,
                "active": q("SELECT COUNT(*) c FROM activity_days WHERE day=?", (day,), one=True)["c"],
                "signups": q("SELECT COUNT(*) c FROM users WHERE created>=? AND created<?", (start, end), one=True)["c"],
            })
        feed = q("SELECT e.ts,e.game_month,e.kind,e.text,u.id AS user_id,u.name,u.company,u.color FROM events e "
                 "JOIN users u ON u.id=e.user_id WHERE e.ts>=? AND e.ts<? ORDER BY e.id DESC LIMIT 60", (rg["t0"], rg["t1"]))
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
                for table in ("sessions", "saves", "stats", "events", "snapshots", "activity_days", "resets", "subs", "lives", "season_scores", "referrals", "ev_log"):
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
        print("Free to play. Tips through Pesapal %s: %s" % (PESAPAL_ENV, "ready" if pesapal_ready() else "NOT SET (add the key, secret and site domain)"), flush=True)
    threading.Thread(target=payment_sweeper, daemon=True).start()
    threading.Thread(target=push_sweeper, daemon=True).start()
    threading.Thread(target=meta_sweeper, daemon=True).start()
    threading.Thread(target=post_sweeper, daemon=True).start()
    threading.Thread(target=stats_sweeper, daemon=True).start()
    threading.Thread(target=ad_sweeper, daemon=True).start()
    print("Meta ads: %s" % ("connected to ad account %s, refreshed every hour" % META_ACCOUNT if meta_ready() else "not connected"), flush=True)
    try:
        backfill_friends()
    except Exception as e:
        print("Friends backfill skipped: %s" % e, flush=True)
    print("Notifications: %s" % ("ready" if push_ready() else "off (install python3-cryptography to switch them on)"), flush=True)
    try:
        backfill_lives()
    except Exception as e:  # never stop the game starting over this
        print("Past lives backfill skipped: %s" % e, flush=True)
    try:
        backfill_lifeboard()
    except Exception as e:
        print("Hall of fame backfill skipped: %s" % e, flush=True)
    ThreadingHTTPServer.request_queue_size = 512
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print("Hustlempires is running on http://%s:%d" % (HOST, PORT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
