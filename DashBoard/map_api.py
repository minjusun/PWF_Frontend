"""
Map API for the Mapbox front end.

Reads sightings live from Supabase and cleans them exactly like the Streamlit
dashboard (data.prepare(real=True) + the whale_regions land mask), then serves:

    /api/points.geojson   the cleaned sightings (refreshed at most once an hour)
    /api/map-load  (POST) asks to open the map: counts one Mapbox map load and returns
                          the Mapbox token, or says no once this month's limit is reached
    /api/map-load  (GET)  this month's count, without adding to it
    /                     webmap.html, App.js, species_description.csv, imgs/ ...

No demo / mock data: if Supabase credentials are missing, it stops with an error.

Put this file next to data.py and whale_regions.py (the dashboard folder).

Run the server:      python map_api.py                  -> http://localhost:8000
One-off static file: python map_api.py --export points_allspeciesv5.geojson
In production:       gunicorn map_api:app --workers 1 --threads 8
                     (keep ONE worker: the map-load counter is shared through one process)

Settings, from env vars or .streamlit/secrets.toml (same file as the dashboard):
  SUPABASE_URL + SUPABASE_KEY   (secrets.toml: supabase_url / supabase_key)
      or DATABASE_URL           (secrets.toml: db_url)
  MAPBOX_TOKEN                  (secrets.toml: mapbox_token)  your PUBLIC pk. token
Optional env vars:
  MAP_LOAD_LIMIT=45000          map loads allowed per billing month (Mapbox free tier is 50,000)
  MAPBOX_BILLING_DAY=1          day of the month your Mapbox billing period starts
  PER_VISITOR_DAILY_LIMIT=300   map loads one visitor (one internet address) can use per day
  MAP_LOAD_COUNTER_FILE=...     where the count is saved (default: map_loads.json next to this file)
"""
import argparse
import json
import os
import threading
import time
from datetime import date, datetime, timezone

import pandas as pd
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


def load_clean_sightings() -> pd.DataFrame:
    s, _ = d.prepare(*load_raw(), real=True)
    lnd = land()
    if lnd is not None and len(s):          # only keep sightings on the water
        pts = s[["lat", "lon"]].round(4).drop_duplicates()
        pts["inland"] = R.inland_mask(pts["lat"], pts["lon"], lnd)
        s = (s.assign(_la=s["lat"].round(4), _lo=s["lon"].round(4))
              .merge(pts.rename(columns={"lat": "_la", "lon": "_lo"}), on=["_la", "_lo"], how="left"))
        s = s[~s["inland"].fillna(False).astype(bool)].drop(columns=["_la", "_lo", "inland"])
    return s


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


# ── Cached JSON ──────────────────────────────────────────────────────────────
_cache = {"body": None, "at": 0.0, "count": 0}
_lock = threading.Lock()


def points_json() -> str:
    with _lock:
        stale = _cache["body"] is None or time.time() - _cache["at"] > CACHE_SECONDS
        if stale:
            try:
                fc = to_feature_collection(load_clean_sightings())
                _cache.update(body=json.dumps(fc, separators=(",", ":")), at=time.time(),
                              count=len(fc["features"]))
                print(f"Loaded {_cache['count']:,} cleaned sightings from Supabase.")
            except Exception:
                if _cache["body"] is None:
                    raise                   # nothing to fall back on
                print("Refresh failed; serving the previous data.")
        return _cache["body"]


# ── Mapbox map-load counter (hard monthly cap) ───────────────────────────────
_counter_lock = threading.Lock()
_visitors = {"day": None, "counts": {}}     # per-visitor daily counts, kept in memory


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


def _read_counter() -> dict:
    try:
        with open(COUNTER_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _write_counter(data: dict):
    tmp = COUNTER_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, COUNTER_FILE)           # swap in whole, so a crash never leaves half a file


def _current_counter() -> dict:
    start = billing_period_start()
    data = _read_counter()
    if data.get("period") != start.isoformat():   # new billing month: start from zero
        data = {"period": start.isoformat(), "count": 0}
    return data


def claim_map_load(visitor: str) -> dict:
    with _counter_lock:
        today = datetime.now(timezone.utc).date().isoformat()
        if _visitors["day"] != today:
            _visitors.update(day=today, counts={})
        data = _current_counter()
        resets = next_reset(date.fromisoformat(data["period"]))
        info = {"count": data["count"], "limit": MAP_LOAD_LIMIT, "resets": resets.isoformat()}

        if data["count"] >= MAP_LOAD_LIMIT:
            return {**info, "allowed": False, "reason": "monthly_limit",
                    "message": f"The map has reached its monthly viewing limit. "
                               f"It will be back on {resets.strftime('%B %d, %Y').replace(' 0', ' ')}."}
        if _visitors["counts"].get(visitor, 0) >= PER_VISITOR_DAILY_LIMIT:
            return {**info, "allowed": False, "reason": "visitor_limit",
                    "message": "You've opened the map many times today. Please try again tomorrow."}

        data["count"] += 1
        _write_counter(data)
        _visitors["counts"][visitor] = _visitors["counts"].get(visitor, 0) + 1
        return {**info, "count": data["count"], "allowed": True}


# ── Web server ───────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=None)


def _no_store(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/points.geojson")
def points():
    try:
        body = points_json()
    except Exception as e:
        return Response(json.dumps({"error": str(e)}), status=502, mimetype="application/json")
    return Response(body, mimetype="application/geo+json", headers={"Cache-Control": "no-store"})


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
    result = claim_map_load(visitor)
    if result["allowed"]:
        result["token"] = token
    return _no_store(jsonify(result))


@app.get("/api/map-load")
def map_load_status():
    with _counter_lock:
        data = _current_counter()
    resets = next_reset(date.fromisoformat(data["period"]))
    return _no_store(jsonify(count=data["count"], limit=MAP_LOAD_LIMIT, period_start=data["period"],
                             resets=resets.isoformat()))


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "webmap.html")


@app.get("/<path:path>")
def frontend_files(path):
    return send_from_directory(FRONTEND_DIR, path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Serve the whale map with cleaned Supabase data.")
    ap.add_argument("--export", metavar="FILE", help="write the cleaned GeoJSON to FILE and exit")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    args = ap.parse_args()

    if args.export:
        with open(args.export, "w", encoding="utf-8") as f:
            f.write(points_json())
        print(f"Wrote {_cache['count']:,} sightings to {args.export}")
    else:
        if not os.path.exists(os.path.join(FRONTEND_DIR, "webmap.html")):
            print(f"Warning: no webmap.html in {FRONTEND_DIR}. Set FRONTEND_DIR to your front-end folder.")
        if not mapbox_token():
            print("Warning: no MAPBOX_TOKEN set; the map won't open. Add mapbox_token to .streamlit/secrets.toml.")
        print(f"Map loads this billing month: {_current_counter()['count']:,} of {MAP_LOAD_LIMIT:,}")
        threading.Thread(target=points_json, daemon=True).start()   # warm the cache while the page loads
        print(f"Serving {FRONTEND_DIR} on http://localhost:{args.port}")
        app.run(host="127.0.0.1", port=args.port)