"""
Map API for the Mapbox front end.

Reads sightings live from Supabase and cleans them exactly like the Streamlit
dashboard (data.prepare(real=True) + the whale_regions land mask), then serves:

    /api/points.geojson   the cleaned sightings (refreshed at most once an hour)
    /api/map-load  (POST) asks to open the map: counts one Mapbox map load and returns
                          the Mapbox token, or says no once this month's limit is reached
    /api/map-load  (GET)  this month's count, without adding to it
    /api/stats.json       numbers for the stats page (same hourly refresh as the points)
    /stats                stats page with all three charts; /stats/active-users,
                          /stats/sightings and /stats/contributors show one chart each (for iframes)
    /                     webmap.html, App.js, species_description.csv, imgs/ ...

No demo / mock data: if Supabase credentials are missing, it stops with an error.

Put this file next to data.py and whale_regions.py (the dashboard folder).

Run the server:      python map_api.py                  -> http://localhost:8000
One-off static file: python map_api.py --export points_allspeciesv5.geojson
In production:       gunicorn map_api:app --workers 2 --threads 8
                     (any number of workers is fine: the counter lives in MongoDB)

Settings, from env vars or .streamlit/secrets.toml (same file as the dashboard):
  SUPABASE_URL + SUPABASE_KEY   (secrets.toml: supabase_url / supabase_key)
      or DATABASE_URL           (secrets.toml: db_url)
  MAPBOX_TOKEN                  (secrets.toml: mapbox_token)  your PUBLIC pk. token
  MONGODB_URI                   (secrets.toml: mongodb_uri)   Atlas connection string, e.g.
                                mongodb+srv://USER:PASS@cluster0.xxxxx.mongodb.net/
Optional env vars:
  CONTRIBUTOR_NAMES=short       "short" shows top contributors as "First L.", "full" shows whole names
  STATS_UNKNOWN_CODES=OTH       species codes counted as "Unknown" on the stats page
  MAP_LOAD_LIMIT=45000          map loads allowed per billing month (Mapbox free tier is 50,000)
  MAPBOX_BILLING_DAY=1          day of the month your Mapbox billing period starts
  PER_VISITOR_DAILY_LIMIT=300   map loads one visitor (one internet address) can use per day
  MONGODB_DB=whale_map          database that holds the counter collections
  MAP_LOAD_COUNTER_FILE=...     old file-based count; if it exists, it's copied into MongoDB once
                                at startup so the current month's count isn't lost
Needs: pip install pymongo
"""
import argparse
import gzip
import hashlib
import json
import os
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
from flask import Flask, Response, jsonify, request, send_from_directory

import data as d
import whale_regions as R

HERE = os.path.dirname(os.path.abspath(__file__))
# Folder holding webmap.html / App.js / species_description.csv / imgs. Change if yours lives elsewhere.
FRONTEND_DIR = os.path.abspath(os.environ.get("FRONTEND_DIR", os.path.join(HERE, "..", "Frontend")))
CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", 3600))   # same 1-hour refresh as the dashboard

MAP_LOAD_LIMIT = int(os.environ.get("MAP_LOAD_LIMIT", 45000))
MAPBOX_BILLING_DAY = min(max(int(os.environ.get("MAPBOX_BILLING_DAY", 1)), 1), 28)
PER_VISITOR_DAILY_LIMIT = int(os.environ.get("PER_VISITOR_DAILY_LIMIT", 300))
COUNTER_FILE = os.environ.get("MAP_LOAD_COUNTER_FILE", os.path.join(HERE, "map_loads.json"))
MONGODB_DB = os.environ.get("MONGODB_DB", "whale_map")

# The map popup shows general_notes, which the dashboard doesn't pull out of variable_data.
# Adding it here keeps data.py shared and unchanged; it doesn't affect any cleaning rule.
if "general_notes" not in d.VD_TEXT:
    d.VD_TEXT.append("general_notes")


# ── Settings / credentials ───────────────────────────────────────────────────
def _read_secrets_toml():
    try:
        import tomllib                      # Python 3.11+
    except ModuleNotFoundError:
        import tomli as tomllib             # pip install tomli on older Pythons
    for folder in (HERE, os.getcwd(), os.path.expanduser("~")):
        path = os.path.join(folder, ".streamlit", "secrets.toml")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return tomllib.load(f)
    return {}


def setting(env_name, toml_name):
    return os.environ.get(env_name) or _read_secrets_toml().get(toml_name)


def mapbox_token():
    token = setting("MAPBOX_TOKEN", "mapbox_token")
    if token and token.startswith("sk."):
        raise RuntimeError("MAPBOX_TOKEN is a secret (sk.) token. Use your public pk. token for the map.")
    return token


def load_raw():
    """The four raw tables from Supabase. Never falls back to demo data."""
    url, key = setting("SUPABASE_URL", "supabase_url"), setting("SUPABASE_KEY", "supabase_key")
    if url and key:
        return d.load_api(url, key)
    db = setting("DATABASE_URL", "db_url")
    if db:
        return d.load_db(db)
    raise RuntimeError("No Supabase credentials found. Set SUPABASE_URL and SUPABASE_KEY, "
                       "or add supabase_url / supabase_key to .streamlit/secrets.toml.")


# ── Cleaning (mirrors load() in the dashboard's app.py) ──────────────────────
_land = None


def land():
    global _land
    if _land is None:
        try:
            _land = R.load_land()
        except Exception as e:              # offline / shapely missing: keep every sighting, like the dashboard
            print(f"Warning: land mask unavailable ({e}); keeping all sightings.")
            _land = False
    return _land or None


def load_clean_data():
    """Cleaned sightings and trips, plus the species table (for whale / dolphin groups)."""
    s_raw, t_raw, species, profiles = load_raw()
    s, t = d.prepare(s_raw, t_raw, species, profiles, real=True)
    lnd = land()
    if lnd is not None and len(s):          # only keep sightings on the water
        pts = s[["lat", "lon"]].round(4).drop_duplicates()
        pts["inland"] = R.inland_mask(pts["lat"], pts["lon"], lnd)
        s = (s.assign(_la=s["lat"].round(4), _lo=s["lon"].round(4))
              .merge(pts.rename(columns={"lat": "_la", "lon": "_lo"}), on=["_la", "_lo"], how="left"))
        s = s[~s["inland"].fillna(False).astype(bool)].drop(columns=["_la", "_lo", "inland"])
    return s, t, species


def load_clean_sightings() -> pd.DataFrame:
    return load_clean_data()[0]


# ── GeoJSON in the shape App.js expects ──────────────────────────────────────
def _txt(v):
    return None if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)


def _int(v):
    return None if v is None or pd.isna(v) else int(v)


def to_feature_collection(s: pd.DataFrame) -> dict:
    feats = []
    for r in s.itertuples(index=False):
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(float(r.lon), 6), round(float(r.lat), 6)]},
            "properties": {
                "sighting_id": _int(r.sighting_id),
                "species_code": _txt(r.species_code),
                "species_name": _txt(r.species_name),
                "sighting_date_and_time_utc": r.ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "animals_total": _int(r.animals_total),
                "animals_calf": _int(r.animals_calf),
                "boat_name": _txt(r.boat_name),
                "general_notes": _txt(r.general_notes),
            },
        })
    return {"type": "FeatureCollection", "features": feats}


# ── Stats page (active users, whale & dolphin sightings, top contributors) ──
# Species codes counted as "Unknown" (e.g. OTH = other / unidentified). Comma-separated env var.
UNKNOWN_CODES = {c.strip().upper() for c in os.environ.get("STATS_UNKNOWN_CODES", "OTH").split(",") if c.strip()}
# "short" shows contributors as "First L."; "full" shows the whole display name.
CONTRIBUTOR_NAMES = os.environ.get("CONTRIBUTOR_NAMES", "short").strip().lower()
GROUPS = ["Whales", "Dolphins", "Unknown"]


def _species_group(code, name, taxonomy):
    """Whales / Dolphins / Unknown, or None for everything else (marine debris, seals, sharks...)."""
    code = (code or "").strip().upper()
    name = (name or "").strip().lower()
    tax = (taxonomy or "").strip().lower()
    if code in UNKNOWN_CODES or name in ("unknown", "unidentified"):
        return "Unknown"
    if "debris" in name or "debris" in code.lower() or tax == "other" or "shark" in name or "seal" in name:
        return None
    if "dolphin" in name or "porpoise" in name or tax in ("dolphin", "porpoise"):
        return "Dolphins"
    if "whale" in name or "whale" in tax:
        return "Whales"
    return None


def _short_name(name: str) -> str:
    name = (name or "").strip()
    if not name or name.startswith("user-"):
        return "Anonymous contributor"
    if CONTRIBUTOR_NAMES == "full":
        return name
    parts = name.split()
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0].upper()}."


def build_stats(s: pd.DataFrame, t: pd.DataFrame, species: pd.DataFrame) -> dict:
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    months = pd.period_range(end=now.to_period("M"), periods=12, freq="M")

    # Active users: anyone who logged a sighting or a trip
    who = pd.concat([s[["ts", "creator"]], t[["ts", "creator"]]], ignore_index=True)
    per_month = who.groupby(who["ts"].dt.to_period("M"))["creator"].nunique()
    active = {
        "this_month": int(per_month.get(months[-1], 0)),
        "last_30_days": int(who.loc[who["ts"] >= now - pd.Timedelta(days=30), "creator"].nunique()),
        "all_time": int(who["creator"].nunique()),
        "monthly": [{"period": str(m), "users": int(per_month.get(m, 0))} for m in months],
    }

    # Whale & dolphin sightings (no marine debris)
    tax = {}
    if species is not None and "taxonomy" in species.columns:
        tax = dict(zip(species["code"].astype(str).str.upper(), species["taxonomy"].astype(str)))
    groups = [_species_group(c, n, tax.get(str(c).upper()))
              for c, n in zip(s["species_code"].astype(str), s["species_name"].astype(str))]
    cet = s.assign(group=groups).dropna(subset=["group"])
    cet = cet.assign(animals=pd.to_numeric(cet["animals_total"], errors="coerce").fillna(0))

    def by_period(periods, labels):
        table = (cet.assign(p=periods).groupby(["p", "group"])["animals"].sum()
                 .unstack(fill_value=0).reindex(columns=GROUPS, fill_value=0))
        return [{"period": lab, **{g: int(table.loc[p, g]) if p in table.index else 0 for g in GROUPS}}
                for p, lab in labels]

    years = sorted(cet["ts"].dt.year.unique())
    sightings = {
        "total_sightings": int(len(cet)),
        "total_animals": int(cet["animals"].sum()),
        "groups": [{"group": g, "sightings": int((cet["group"] == g).sum()),
                    "animals": int(cet.loc[cet["group"] == g, "animals"].sum())} for g in GROUPS],
        "by_year": by_period(cet["ts"].dt.year, [(y, str(y)) for y in years]),
        "by_month": by_period(cet["ts"].dt.to_period("M"), [(m, str(m)) for m in months]),
    }

    # Top 5 contributors worldwide, by whale & dolphin sightings
    g = cet.groupby("contributor").agg(sightings=("sighting_id", "count"), animals=("animals", "sum"),
                                       species=("species_code", "nunique"))
    trips = t.groupby("contributor")["track_id"].nunique().rename("trips")
    g = g.join(trips, how="left").fillna(0).sort_values(["sightings", "animals"], ascending=False).head(5)
    contributors = [{"name": _short_name(n), "sightings": int(r.sightings), "animals": int(r.animals),
                     "species": int(r.species), "trips": int(r.trips)} for n, r in g.iterrows()]

    return {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "active_users": active, "sightings": sightings, "contributors": contributors}


# ── Cached JSON (map points + stats share one hourly Supabase read) ───────────
# A background thread loads the data when the server starts and refreshes it every hour,
# so visitors are always served the saved copy and never wait for Supabase.
# Each response is also kept gzipped (the sightings shrink from ~14 MB to ~1.5 MB).
_cache = {"body": None, "body_gz": None, "stats": None, "stats_gz": None, "at": 0.0, "count": 0}
_lock = threading.Lock()
_ready = threading.Event()


def _gz(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"), compresslevel=6)


def refresh_data():
    """Read Supabase and rebuild everything. Keeps the previous copy if it fails."""
    try:
        s, t, species = load_clean_data()
        fc = to_feature_collection(s)
        body = json.dumps(fc, separators=(",", ":"))
        new = {"body": body, "body_gz": _gz(body), "at": time.time(), "count": len(fc["features"])}
    except Exception as e:
        print(f"Refresh failed ({e}); serving the previous data.")
        return
    try:                                    # a stats bug must never take the map down
        stats = json.dumps(build_stats(s, t, species), separators=(",", ":"))
        new.update(stats=stats, stats_gz=_gz(stats))
    except Exception as e:
        print(f"Stats failed ({e}); keeping the previous stats.")
    with _lock:
        _cache.update(new)
    _ready.set()
    print(f"Loaded {new['count']:,} cleaned sightings from Supabase.")


def _background_refresh():
    while True:
        refresh_data()
        time.sleep(CACHE_SECONDS if _ready.is_set() else 60)   # retry sooner if the first load failed


_bg_started = False


def start_background_refresh():
    global _bg_started
    if not _bg_started:
        _bg_started = True
        threading.Thread(target=_background_refresh, daemon=True).start()


def _wait_for_data(key: str):
    """The saved copy; on a fresh start, waits (up to 2 minutes) for the first load."""
    start_background_refresh()
    if not _ready.wait(timeout=120):
        raise RuntimeError("The data is still loading. Try again in a minute.")
    with _lock:
        if _cache[key] is None:
            raise RuntimeError("Stats aren't available yet.")
        return _cache[key], _cache[key + "_gz"]


def points_json() -> str:
    return _wait_for_data("body")[0]


def stats_json() -> str:
    return _wait_for_data("stats")[0]


def _json_response(key: str, mimetype: str, cache_control: str):
    try:
        plain, packed = _wait_for_data(key)
    except Exception as e:
        return Response(json.dumps({"error": str(e)}), status=502, mimetype="application/json")
    headers = {"Cache-Control": cache_control, "Vary": "Accept-Encoding"}
    if "gzip" in request.headers.get("Accept-Encoding", ""):
        headers["Content-Encoding"] = "gzip"
        return Response(packed, mimetype=mimetype, headers=headers)
    return Response(plain, mimetype=mimetype, headers=headers)


# ── Mapbox map-load counter in MongoDB (hard monthly cap) ────────────────────
# Collections (created automatically):
#   map_loads       one document per billing month:  {_id: "2026-11-01", count: 1234}
#   visitor_loads   one per visitor per day:         {_id: "2026-11-13:<hashed IP>", count, expires}
#                   (a TTL index deletes these after a couple of days)
# Every check-and-add is a single atomic MongoDB update, so the count can never pass the
# limit, even with several server workers or several servers sharing one database.
_mongo = None
_mongo_lock = threading.Lock()


def mongo_db():
    global _mongo
    with _mongo_lock:
        if _mongo is None:
            uri = setting("MONGODB_URI", "mongodb_uri")
            if not uri:
                raise RuntimeError("No MONGODB_URI set. Add mongodb_uri to .streamlit/secrets.toml.")
            client = MongoClient(uri, serverSelectionTimeoutMS=5000, appname="whale-map")
            db = client[MONGODB_DB]
            db.visitor_loads.create_index("expires", expireAfterSeconds=0)
            _mongo = db
        return _mongo


def billing_period_start(today=None) -> date:
    """First day of the current Mapbox billing period."""
    today = today or datetime.now(timezone.utc).date()
    y, m = today.year, today.month
    if today.day < MAPBOX_BILLING_DAY:
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return date(y, m, MAPBOX_BILLING_DAY)


def next_reset(start: date) -> date:
    y, m = (start.year, start.month + 1) if start.month < 12 else (start.year + 1, 1)
    return date(y, m, MAPBOX_BILLING_DAY)


def _visitor_key(visitor: str) -> str:
    # Store a hash, not the raw internet address.
    return hashlib.sha256(visitor.encode()).hexdigest()[:24]


def _try_increment(coll, doc_id: str, limit: int, extra=None):
    """Add 1 to doc_id's count only if it's below limit. Returns the new count, or None if full.

    If the document exists and is full, the filter doesn't match, so the upsert tries to
    insert a second document with the same _id and MongoDB refuses: that means "full".
    """
    try:
        doc = coll.find_one_and_update(
            {"_id": doc_id, "count": {"$lt": limit}},
            {"$inc": {"count": 1}, **({"$setOnInsert": extra} if extra else {})},
            upsert=True, return_document=ReturnDocument.AFTER)
        return doc["count"]
    except DuplicateKeyError:
        return None


def current_count() -> dict:
    start = billing_period_start()
    doc = mongo_db().map_loads.find_one({"_id": start.isoformat()}) or {}
    return {"period": start.isoformat(), "count": doc.get("count", 0)}


def claim_map_load(visitor: str) -> dict:
    db = mongo_db()
    start = billing_period_start()
    resets = next_reset(start)
    info = {"limit": MAP_LOAD_LIMIT, "resets": resets.isoformat()}
    now = datetime.now(timezone.utc)

    # 1. This visitor's daily allowance.
    visitor_id = f"{now.date().isoformat()}:{_visitor_key(visitor)}"
    expires = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=2)
    if _try_increment(db.visitor_loads, visitor_id, PER_VISITOR_DAILY_LIMIT, {"expires": expires}) is None:
        return {**info, "count": current_count()["count"], "allowed": False, "reason": "visitor_limit",
                "message": "You've opened the map many times today. Please try again tomorrow."}

    # 2. The monthly cap.
    count = _try_increment(db.map_loads, start.isoformat(), MAP_LOAD_LIMIT)
    if count is None:
        db.visitor_loads.update_one({"_id": visitor_id}, {"$inc": {"count": -1}})  # give the visit back
        return {**info, "count": MAP_LOAD_LIMIT, "allowed": False, "reason": "monthly_limit",
                "message": f"The map has reached its monthly viewing limit. "
                           f"It will be back on {resets.strftime('%B %d, %Y').replace(' 0', ' ')}."}
    return {**info, "count": count, "allowed": True}


def import_old_counter_file():
    """One-time carry-over from map_loads.json, so this month's earlier loads still count."""
    try:
        with open(COUNTER_FILE, encoding="utf-8") as f:
            old = json.load(f)
    except (FileNotFoundError, ValueError):
        return
    if old.get("period") == billing_period_start().isoformat() and old.get("count"):
        # $max never lowers the count, so running this again is harmless.
        mongo_db().map_loads.update_one({"_id": old["period"]}, {"$max": {"count": int(old["count"])}},
                                        upsert=True)


# ── Web server ───────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=None)


def _no_store(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/points.geojson")
def points():
    return _json_response("body", "application/geo+json", "public, max-age=600")


@app.post("/api/map-load")
def map_load():
    try:
        token = mapbox_token()
    except RuntimeError as e:
        return _no_store(jsonify(allowed=False, message=str(e))), 500
    if not token:
        return _no_store(jsonify(allowed=False, message="Server has no MAPBOX_TOKEN set.")), 500
    route = request.access_route
    visitor = route[0] if route else (request.remote_addr or "unknown")
    try:
        result = claim_map_load(visitor)
    except (PyMongoError, RuntimeError) as e:
        # Can't confirm the count, so don't open the map: better a short outage than a Mapbox bill.
        print(f"Map-load counter unavailable: {e}")
        return _no_store(jsonify(allowed=False, message="The map is unavailable right now. "
                                                         "Please try again in a few minutes.")), 503
    if result["allowed"]:
        result["token"] = token
    return _no_store(jsonify(result))


@app.get("/api/map-load")
def map_load_status():
    try:
        data = current_count()
    except (PyMongoError, RuntimeError) as e:
        return _no_store(jsonify(error=str(e))), 503
    resets = next_reset(date.fromisoformat(data["period"]))
    return _no_store(jsonify(count=data["count"], limit=MAP_LOAD_LIMIT, period_start=data["period"],
                             resets=resets.isoformat()))


@app.get("/api/stats.json")
def stats():
    return _json_response("stats", "application/json", "public, max-age=600")


STATS_VIEWS = {"active-users", "sightings", "contributors"}


@app.get("/stats")
@app.get("/stats/<view>")
def stats_page(view=None):
    if view is not None and view not in STATS_VIEWS:
        return Response("Not found", status=404)
    return send_from_directory(FRONTEND_DIR, "stats.html")


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "webmap.html")


@app.get("/<path:path>")
def frontend_files(path):
    return send_from_directory(FRONTEND_DIR, path)


if "--export" not in sys.argv:
    start_background_refresh()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Serve the whale map with cleaned Supabase data.")
    ap.add_argument("--export", metavar="FILE", help="write the cleaned GeoJSON to FILE and exit")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    args = ap.parse_args()

    if args.export:
        refresh_data()
        with open(args.export, "w", encoding="utf-8") as f:
            f.write(_cache["body"])
        print(f"Wrote {_cache['count']:,} sightings to {args.export}")
    else:
        if not os.path.exists(os.path.join(FRONTEND_DIR, "webmap.html")):
            print(f"Warning: no webmap.html in {FRONTEND_DIR}. Set FRONTEND_DIR to your front-end folder.")
        if not mapbox_token():
            print("Warning: no MAPBOX_TOKEN set; the map won't open. Add mapbox_token to .streamlit/secrets.toml.")
        try:
            import_old_counter_file()
            print(f"Map loads this billing month: {current_count()['count']:,} of {MAP_LOAD_LIMIT:,}")
        except (PyMongoError, RuntimeError) as e:
            print(f"Warning: can't reach MongoDB ({e}); the map won't open until it can.")
        print(f"Serving {FRONTEND_DIR} on http://localhost:{args.port}")
        app.run(host="127.0.0.1", port=args.port)