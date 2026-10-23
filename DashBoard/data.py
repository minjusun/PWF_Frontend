"""
Data layer for the Whale & Dolphin Tracker dashboard.
Pure pandas — no Streamlit imports, so it can be tested on its own.
"""
import json
import uuid

import numpy as np
import pandas as pd

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ── SQL (edit here if your column names differ) ──────────────────────────────
PROFILE_NAME_COLUMN = "username"  # column in public.profiles that holds a display name

SIGHTINGS_SQL = """
    select sighting_id, creator::text as creator, species_code,
           latitude, longitude, sighting_date_and_time_utc, track_key, variable_data
    from public.sightings
"""
TRACKS_SQL = """
    select track_id, creator::text as creator, start_date_utc, track_key
    from public.tracks
"""
SPECIES_SQL = "select code, name, taxonomy from public.species"
PROFILES_SQL = f'select id::text as id, "{PROFILE_NAME_COLUMN}"::text as display_name from public.profiles'

# Fields pulled out of sightings.variable_data
VD_NUMERIC = ["animals_total", "animals_adult", "animals_juvenile", "animals_calf", "animals_unknown_age"]
VD_TEXT = ["boat_name", "recorder_name", "wind_speed_knots", "swell_height_meters", "cloud_cover_percent"]


def load_db(url: str):
    """Read the four tables from Postgres/Supabase."""
    from sqlalchemy import create_engine, text

    eng = create_engine(url, pool_pre_ping=True)
    with eng.connect() as c:
        s = pd.read_sql(text(SIGHTINGS_SQL), c)
        t = pd.read_sql(text(TRACKS_SQL), c)
        sp = pd.read_sql(text(SPECIES_SQL), c)
    try:  # profiles is optional — fall back to recorder_name / uuid
        with eng.connect() as c:
            p = pd.read_sql(text(PROFILES_SQL), c)
    except Exception:
        p = pd.DataFrame(columns=["id", "display_name"])
    return s, t, sp, p


SIGHTINGS_COLS = "sighting_id,creator,species_code,latitude,longitude,sighting_date_and_time_utc,track_key,variable_data"
TRACKS_COLS = "track_id,creator,start_date_utc,track_key"
SPECIES_COLS = "code,name,taxonomy"


def load_api(url: str, key: str, page: int = 1000):
    """Read the four tables with the Supabase API (project URL + API key).

    Supabase returns at most 1000 rows per request, so each table is fetched in pages."""
    from supabase import create_client

    sb = create_client(url, key)

    def fetch(table, cols, order):
        rows, start = [], 0
        while True:
            batch = (sb.table(table).select(cols).order(order)
                     .range(start, start + page - 1).execute().data) or []
            rows.extend(batch)
            if len(batch) < page:
                break
            start += page
        return pd.DataFrame(rows, columns=cols.split(","))

    s = fetch("sightings", SIGHTINGS_COLS, "sighting_id")
    t = fetch("tracks", TRACKS_COLS, "track_id")
    sp = fetch("species", SPECIES_COLS, "code")
    try:  # profiles is optional — fall back to recorder_name / uuid
        p = fetch("profiles", f"id,{PROFILE_NAME_COLUMN}", "id").rename(columns={PROFILE_NAME_COLUMN: "display_name"})
    except Exception:
        p = pd.DataFrame(columns=["id", "display_name"])
    return s, t, sp, p


# ── Demo data (same shape as the real tables) ────────────────────────────────
def load_demo(seed: int = 42):
    rng = np.random.default_rng(seed)
    species = pd.DataFrame(
        [
            ("HUWH", "Humpback whale", "Mysticeti"),
            ("BLWH", "Blue whale", "Mysticeti"),
            ("SPWH", "Sperm whale", "Odontoceti"),
            ("SPDO", "Spinner dolphin", "Odontoceti"),
            ("BODO", "Common bottlenose dolphin", "Odontoceti"),
            ("PSDO", "Pantropical spotted dolphin", "Odontoceti"),
            ("FKWH", "False killer whale", "Odontoceti"),
            ("ORCA", "Killer whale", "Odontoceti"),
            ("RIDO", "Risso's dolphin", "Odontoceti"),
        ],
        columns=["code", "name", "taxonomy"],
    )
    dolphins = {"SPDO", "BODO", "PSDO", "RIDO", "FKWH", "ORCA"}
    # region: lat, lon, spread (deg), share of trips, {species: peak month or None for resident}
    regions = {
        "Maui": (20.80, -156.55, 0.18, 0.45, {"HUWH": 2, "SPDO": None, "BODO": None, "PSDO": None, "FKWH": 10}),
        "Monterey Bay": (36.80, -122.00, 0.22, 0.25, {"HUWH": 8, "BLWH": 7, "RIDO": None, "ORCA": 4}),
        "Azores": (38.50, -28.40, 0.35, 0.15, {"SPWH": None, "BLWH": 4, "BODO": None, "RIDO": None}),
        "Vava'u": (-18.65, -173.98, 0.15, 0.15, {"HUWH": 8, "SPDO": None}),
    }
    first = ["Jessica", "Kai", "Leilani", "Marco", "Ana", "Noah", "Mele", "Sofia", "Liam", "Keoni", "Ines", "Tomas"]
    last = ["Rickard", "Kahale", "Silva", "Nguyen", "Okafor", "Brooks", "Medeiros", "Tanaka", "Reyes", "Fonoti"]
    boats = ["Ocean Intrigue", "Trilogy V", "Pacific Whale", "Kai Kanani", "Sea Spirit", "Blue Horizon"]

    n_users = 60
    users = [str(uuid.UUID(bytes=rng.bytes(16))) for _ in range(n_users)]
    names = {u: f"{rng.choice(first)} {rng.choice(last)}" for u in users}
    uw = rng.pareto(1.3, n_users) + 0.05
    uw /= uw.sum()

    end = pd.Timestamp.now().normalize()
    start = end - pd.DateOffset(years=4)
    span_days = (end - start).days
    reg_names = list(regions)
    rw = np.array([regions[r][3] for r in reg_names])
    rw /= rw.sum()

    tracks, sightings, sid = [], [], 1
    for tid in range(1, 3201):
        reg = reg_names[rng.choice(len(reg_names), p=rw)]
        lat0, lon0, spread, _, peaks = regions[reg]
        creator = users[rng.choice(n_users, p=uw)]
        day = start + pd.Timedelta(days=int(rng.integers(0, span_days)), hours=float(rng.uniform(7, 15)))
        key = f"trk_{tid:05d}"
        tracks.append((tid, creator, day.strftime("%Y-%m-%dT%H:%M:%SZ"), key))

        drift = 0.35 * (day.year - start.year)  # seasons shift slightly later each year
        codes = list(peaks)
        w = np.array(
            [1.0 if pk is None else np.exp(2.5 * np.cos(2 * np.pi * (day.month - (pk + drift)) / 12)) for pk in peaks.values()]
        )
        w /= w.sum()
        for _ in range(rng.poisson(1.5)):
            code = codes[rng.choice(len(codes), p=w)]
            adults = int(rng.integers(4, 60)) if code in dolphins else int(rng.integers(1, 5))
            calves = int(rng.integers(1, 3)) if (code == "HUWH" and rng.random() < 0.45) else (
                int(rng.integers(0, 4)) if code in dolphins and rng.random() < 0.3 else 0)
            vd = {
                "activity_codes": [],
                "boat_name": str(rng.choice(boats)),
                "swell_height_meters": str(rng.choice(["RIPPLES", "0.5", "1", "2"])),
                "wind_speed_knots": str(rng.choice(["CALM", "5", "10", "15"])),
                "wind_direction": None,
                "cloud_cover_percent": str(int(rng.integers(0, 10)) * 10),
                "animals_adult": adults,
                "animals_juvenile": None,
                "animals_calf": calves or None,
                "animals_unknown_age": None,
                "animals_total": adults + calves,
                "inter_species_interaction": None,
                "general_notes": "",
                "sight_distance": None,
                "official_departure_time": None,
                "recorder_name": names[creator],
            }
            when = day + pd.Timedelta(minutes=int(rng.integers(10, 240)))
            sightings.append(
                (
                    sid, creator, code,
                    f"{lat0 + rng.normal(0, spread):.5f}", f"{lon0 + rng.normal(0, spread):.5f}",
                    when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    key if rng.random() > 0.08 else None,
                    json.dumps(vd),
                )
            )
            sid += 1

    s = pd.DataFrame(sightings, columns=["sighting_id", "creator", "species_code", "latitude", "longitude",
                                         "sighting_date_and_time", "track_key", "variable_data"])
    t = pd.DataFrame(tracks, columns=["track_id", "creator", "start_date_utc", "track_key"])
    p = pd.DataFrame({"id": list(names), "display_name": list(names.values())})
    return s, t, species, p


# ── Real-data filters (same rules as the team's SQL query) ───────────────────
AUTHORIZED_USERNAMES = {
    "oceandiscovery", "oceanexplorer", "oceanodyssey", "oceanspirit", "oceanquest", "oceanvoyager",
    "oceanguardian", "oceanintrigue", "oceanjourney", "oceanlegacy", "oceancelebration",
    "oceanliberty", "oceanadventurer", "kaiko", "logging", "oceandefender",
}
AUTHORIZED_IDS = {
    "3646ff33-c102-46a1-8ce0-26f40734aac9",
    "16318a84-434b-4151-b152-f9bba075663a",
    "9d6db01c-b3f1-451f-94ab-30e37b450528",
    "2aa9e013-8965-49aa-a82f-a3b12c8059c6",
    "22a42349-3e9e-416e-88cc-28b983645e94",
}
MAX_ANIMALS = 7000   # sightings with more animals than this are dropped as entry errors

_DECIMAL = r"^-?[0-9]+(\.[0-9]+)?$"                 # e.g. 20.7845
_DEG_MIN = r"^(-?)([0-9]+)[ .]([0-9]+\.[0-9]+)$"    # e.g. "20 47.07" or "20.47.07" (degrees + decimal minutes)


def clean_coordinate(col: pd.Series, force_west: bool = False, force_north: bool = False) -> pd.Series:
    """Decimal degrees, or degrees + decimal minutes -> decimal degrees (rounded to 6 places).
    force_west=True makes every value negative (west of Greenwich), like -abs() in the SQL.
    force_north=True makes every value positive (north of the equator)."""
    s = col.astype("string").str.strip()
    dec = pd.to_numeric(s.where(s.str.match(_DECIMAL, na=False)), errors="coerce").astype(float)
    parts = s.str.extract(_DEG_MIN)
    dm = (pd.to_numeric(parts[1], errors="coerce") + pd.to_numeric(parts[2], errors="coerce") / 60).astype(float)
    if force_west:
        out = -dec.abs()
        out = out.fillna(-dm.abs())
    else:
        sign = np.where((parts[0] == "-").fillna(False).astype(bool), -1.0, 1.0)
        out = dec.fillna(dm * sign)
    if force_north:
        out = out.abs()
    return out.round(6)


def authorized_ids(profiles: pd.DataFrame) -> set:
    names = profiles.get("display_name", pd.Series(dtype=object)).astype(str).str.lower()
    ok = set(profiles.loc[names.isin(AUTHORIZED_USERNAMES), "id"].astype(str)) if len(profiles) else set()
    return ok | AUTHORIZED_IDS


def apply_real_filters(s: pd.DataFrame, t: pd.DataFrame, profiles: pd.DataFrame):
    """Authorized accounts only, no test entries, cleaned coordinates."""
    ids = authorized_ids(profiles)
    s = s[s["creator"].astype(str).isin(ids)].copy()
    t = t[t["creator"].astype(str).isin(ids)].copy()
    vd = s["variable_data"].astype("string")
    s = s[~vd.str.contains("test", case=False, na=False)].copy()     # drop anything marked as a test
    s["latitude"] = clean_coordinate(s["latitude"], force_north=True)     # latitudes are never negative
    s["longitude"] = clean_coordinate(s["longitude"], force_west=True)
    return s, t


# ---------------------------------------------------------------------------
# Animal-count cleaning (from the team notebook)
# ---------------------------------------------------------------------------

ANIMAL_COLS = [
    'animals_adult',
    'animals_juvenile',
    'animals_calf',
    'animals_unknown_age',
    'animals_total',
]


def coerce_animal_counts(df, cols=ANIMAL_COLS):
    """Force animal-count columns to numeric, filling anything unparseable (or missing) with 0."""
    df = df.copy()
    df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
    df[cols] = df[cols].fillna(0)
    return df


def reconcile_animal_totals(
    df,
    adult_col='animals_adult',
    juvenile_col='animals_juvenile',
    calf_col='animals_calf',
    unknown_col='animals_unknown_age',
    total_col='animals_total',
    known_max=40,       # adult+juvenile+calf below this...
    total_min=9999,     # ...while total is above this -> treat total as a typo
):
    """
    Reconcile animals_total against the sum of its parts.

    - total < sum(parts): raise total to match the sum.
    - total > sum(parts) AND adult+juvenile+calf < known_max AND total > total_min:
        total is treated as an entry error -> reset total to sum(parts).
    - total > sum(parts) otherwise: add the difference to animals_unknown_age.

    Returns (df, mismatched) -- corrected copy, and one row per changed record.
    """
    df = df.copy()
    known_cols = [adult_col, juvenile_col, calf_col]
    part_cols = known_cols + [unknown_col]
    cols = part_cols + [total_col]

    known_sum = df[known_cols].sum(axis=1)
    parts_sum = df[part_cols].sum(axis=1)

    mismatch_mask = parts_sum != df[total_col]
    under = mismatch_mask & (df[total_col] < parts_sum)
    over = mismatch_mask & (df[total_col] > parts_sum)
    reset_total = over & (known_sum < known_max) & (df[total_col] > total_min)
    fill_unknown = over & ~reset_total

    before = df.loc[mismatch_mask, cols].copy()
    df.loc[under, total_col] = parts_sum[under]
    df.loc[reset_total, total_col] = parts_sum[reset_total]
    df.loc[fill_unknown, unknown_col] += (df[total_col] - parts_sum)[fill_unknown]
    after = df.loc[mismatch_mask, cols]

    mismatched = before.add_suffix('_before').join(after.add_suffix('_after'))
    mismatched['known_sum'] = known_sum[mismatch_mask]
    mismatched['parts_sum_before'] = parts_sum[mismatch_mask]
    mismatched['fix'] = np.select(
        [under[mismatch_mask], reset_total[mismatch_mask]],
        ['raised_total', 'reset_total_to_parts'],
        default='added_to_unknown',
    )
    id_cols = [c for c in ['sighting_id', 'sighting_date_and_time_utc'] if c in df.columns]
    mismatched = df.loc[mismatch_mask, id_cols].join(mismatched)
    return df, mismatched


def is_marine_debris(df):
    """True for marine-debris reports (matched on the species name or code, any capitals)."""
    name = df.get("species_name", pd.Series("", index=df.index)).astype("string")
    code = df.get("species_code", pd.Series("", index=df.index)).astype("string")
    return (name.str.contains("debris", case=False, na=False) |
            code.str.contains("debris", case=False, na=False) |
            code.str.upper().eq("DEB").fillna(False))          # your species table: DEB = Marine Debris


def drop_zero_sightings(df, total_col='animals_total'):
    """Drop rows with no animals recorded at all -- except marine debris, which has no animals."""
    return df.loc[(df[total_col] > 0) | is_marine_debris(df)].copy()


def drop_large_counts(df, total_col='animals_total', max_total=MAX_ANIMALS):
    """The only rows removed for their counts: sightings with more than max_total animals."""
    return df.loc[df[total_col] <= max_total].copy()


# ── Cleaning ─────────────────────────────────────────────────────────────────
def _parse_json(x):
    if isinstance(x, dict):
        return x
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return {}
    try:
        v = json.loads(x)
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}


def parse_variable_data(series: pd.Series) -> pd.DataFrame:
    """Expand the variable_data JSON into columns we chart on."""
    parsed = pd.DataFrame([_parse_json(x) for x in series], index=series.index)
    parsed = parsed.reindex(columns=VD_NUMERIC + VD_TEXT)
    for c in VD_NUMERIC:
        parsed[c] = pd.to_numeric(parsed[c], errors="coerce")
    # if animals_total is missing, rebuild it from the age classes
    parts = parsed[["animals_adult", "animals_juvenile", "animals_calf", "animals_unknown_age"]]
    parsed["animals_total"] = parsed["animals_total"].fillna(parts.sum(axis=1, min_count=1))
    for c in VD_TEXT:
        parsed[c] = parsed[c].astype("object").where(parsed[c].notna(), None)
        parsed[c] = parsed[c].map(lambda v: v.strip() if isinstance(v, str) else v).replace("", None)
    return parsed


def _parse_ts(col: pd.Series) -> pd.Series:
    return pd.to_datetime(col, errors="coerce", utc=True, format="mixed").dt.tz_localize(None)


def prepare(s_raw, t_raw, species, profiles, real=False):
    s = s_raw.copy()
    t_raw = t_raw.copy()
    if real:                                   # authorized accounts, no tests, cleaned coordinates
        s, t_raw = apply_real_filters(s, t_raw, profiles)
    s["lat"] = pd.to_numeric(s["latitude"], errors="coerce")
    s["lon"] = pd.to_numeric(s["longitude"], errors="coerce")
    time_col = "sighting_date_and_time_utc" if "sighting_date_and_time_utc" in s.columns else "sighting_date_and_time"
    s["ts"] = _parse_ts(s[time_col])
    s = s.dropna(subset=["lat", "lon", "ts"])
    s = s[s["lat"].between(-90, 90) & s["lon"].between(-180, 180)].copy()
    s = s.join(parse_variable_data(s["variable_data"])).drop(columns=["variable_data"])
    s = coerce_animal_counts(s)                # counts -> numbers, blanks -> 0
    s, _ = reconcile_animal_totals(s)          # make animals_total = sum of its parts
    s = drop_large_counts(s)                   # drop sightings with more than 7000 animals

    sp = species.rename(columns={"code": "species_code", "name": "species_name"})[["species_code", "species_name"]]
    s = s.merge(sp, on="species_code", how="left")
    s["species_name"] = s["species_name"].fillna(s["species_code"]).fillna("Unknown")
    s = drop_zero_sightings(s)                 # drop sightings with no animals recorded (except marine debris)
    s["year"] = s["ts"].dt.year
    s["month"] = s["ts"].dt.month
    s["creator"] = s["creator"].astype(str)

    t = t_raw.copy()
    t["ts"] = _parse_ts(t["start_date_utc"])
    t = t.dropna(subset=["ts"]).copy()
    t["creator"] = t["creator"].astype(str)

    # Display names: profiles → most common recorder_name → short uuid
    lookup = {}
    p = profiles.dropna(subset=["display_name"])
    p = p[p["display_name"].astype(str).str.strip() != ""]
    lookup.update(dict(zip(p["id"].astype(str), p["display_name"].astype(str))))
    rec = s.dropna(subset=["recorder_name"]).groupby("creator")["recorder_name"].agg(lambda x: x.mode().iat[0])
    for c, n in rec.items():
        lookup.setdefault(c, n)
    name = lambda c: lookup.get(c) or f"user-{c[:8]}"  # noqa: E731
    s["contributor"] = s["creator"].map(name)
    t["contributor"] = t["creator"].map(name)
    return s, t


# ── Geography helpers ────────────────────────────────────────────────────────
def valid_bounds(b) -> bool:
    try:
        return all(b[k][j] is not None for k in ("_southWest", "_northEast") for j in ("lat", "lng"))
    except (TypeError, KeyError):
        return False


def in_bounds(df: pd.DataFrame, b) -> pd.DataFrame:
    """Filter rows to a Leaflet bounds dict, handling the antimeridian."""
    south, north = b["_southWest"]["lat"], b["_northEast"]["lat"]
    west, east = b["_southWest"]["lng"], b["_northEast"]["lng"]
    lat_ok = df["lat"].between(south, north)
    if east - west >= 360:
        return df[lat_ok]
    w, e = ((west + 180) % 360) - 180, ((east + 180) % 360) - 180
    lon_ok = df["lon"].between(w, e) if w <= e else (df["lon"] >= w) | (df["lon"] <= e)
    return df[lat_ok & lon_ok]


def slice_data(s, t, start, end, bounds=None, tracks_follow_sightings=False):
    """Period + (optional) map-area slice. Trips in an area = trips with a sighting in that area."""
    s2 = s[(s["ts"] >= start) & (s["ts"] < end)]
    t2 = t[(t["ts"] >= start) & (t["ts"] < end)]
    if bounds is not None:
        s2 = in_bounds(s2, bounds)
        tracks_follow_sightings = True
    if tracks_follow_sightings:
        t2 = t2[t2["track_key"].isin(s2["track_key"].dropna())]
    return s2, t2


# ── Metrics ──────────────────────────────────────────────────────────────────
def kpis(s, t) -> dict:
    return {
        "users": len(set(s["creator"]) | set(t["creator"])),
        "trips": int(t["track_id"].nunique()),
        "sightings": int(len(s)),
        "species": int(s["species_code"].nunique()),
        "animals": int(np.nansum(s["animals_total"])) if len(s) else 0,
    }


def top_contributors(s, t, n=5) -> pd.DataFrame:
    cols = ["Contributor", "Sightings", "Trips", "Species", "Animals"]
    if s.empty and t.empty:
        return pd.DataFrame(columns=cols)
    g = s.groupby("contributor").agg(
        Sightings=("sighting_id", "count"), Species=("species_code", "nunique"), Animals=("animals_total", "sum")
    )
    trips = t.groupby("contributor")["track_id"].nunique().rename("Trips")
    g = g.join(trips, how="outer").fillna(0).astype(int)
    g = g.sort_values(["Sightings", "Trips"], ascending=False).head(n)
    return g.reset_index().rename(columns={"contributor": "Contributor"})[cols]


def top_species(s, n=5) -> pd.DataFrame:
    if s.empty:
        return pd.DataFrame(columns=["Species", "Sightings", "Animals", "Share"])
    g = s.groupby("species_name").agg(Sightings=("sighting_id", "count"), Animals=("animals_total", "sum"))
    g["Share"] = g["Sightings"] / len(s)
    g["Animals"] = g["Animals"].fillna(0).astype(int)
    return g.sort_values("Sightings", ascending=False).head(n).reset_index().rename(columns={"species_name": "Species"})


def hotspots_by_year(s, grid=0.1) -> pd.DataFrame:
    """Busiest ~grid° cell for each year."""
    if s.empty:
        return pd.DataFrame(columns=["year", "cell_lat", "cell_lon", "Sightings", "Species", "Top species"])
    d = s.assign(cell_lat=(s["lat"] / grid).round() * grid, cell_lon=(s["lon"] / grid).round() * grid)
    g = (
        d.groupby(["year", "cell_lat", "cell_lon"])
        .agg(Sightings=("sighting_id", "count"), Species=("species_code", "nunique"),
             **{"Top species": ("species_name", lambda x: x.mode().iat[0])})
        .reset_index()
    )
    g = g.loc[g.groupby("year")["Sightings"].idxmax()]
    return g.sort_values("year", ascending=False).reset_index(drop=True)


def season_centre(ts: pd.Series) -> str:
    """Circular mean of day-of-year — handles seasons that wrap across New Year."""
    if ts.empty:
        return "—"
    ang = 2 * np.pi * ts.dt.dayofyear.to_numpy() / 365.25
    m = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())
    d = (m / (2 * np.pi) * 365.25) % 365.25
    return (pd.Timestamp("2001-01-01") + pd.Timedelta(days=float(d))).strftime("%b %d")


def peak_table(sp_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for y, g in sp_df.groupby("year"):
        mc = g["month"].value_counts()
        rows.append({
            "Year": int(y),
            "Sightings": len(g),
            "Peak month": MONTHS[int(mc.idxmax()) - 1],
            "Share in peak month": mc.max() / len(g),
            "Season centre": season_centre(g["ts"]),
            "Months seen": int(g["month"].nunique()),
        })
    return pd.DataFrame(rows).sort_values("Year", ascending=False)


def _month_index(start, end):
    return pd.period_range(pd.Timestamp(start), pd.Timestamp(end) - pd.Timedelta(seconds=1), freq="M").start_time


def monthly_series(s, t, start, end) -> pd.DataFrame:
    """One row per month in the window — feeds the KPI sparklines."""
    idx = _month_index(start, end)
    sm = s["ts"].dt.to_period("M").dt.start_time
    tm = t["ts"].dt.to_period("M").dt.start_time
    out = pd.DataFrame(index=idx)
    out["sightings"] = s.groupby(sm).size()
    out["species"] = s.groupby(sm)["species_code"].nunique()
    out["animals"] = s.groupby(sm)["animals_total"].sum()
    out["trips"] = t.groupby(tm)["track_id"].nunique()
    who = pd.concat([pd.DataFrame({"p": sm.values, "c": s["creator"].values}),
                     pd.DataFrame({"p": tm.values, "c": t["creator"].values})])
    out["users"] = who.groupby("p")["c"].nunique()
    return out.fillna(0)


def species_table(s, start, end) -> pd.DataFrame:
    """Every distinct species with count, monthly trend list and last-seen date."""
    if s.empty:
        return pd.DataFrame(columns=["Species", "Sightings", "Trend", "Last seen"])
    idx = _month_index(start, end)
    piv = (s.assign(m=s["ts"].dt.to_period("M").dt.start_time)
           .pivot_table(index="species_name", columns="m", values="sighting_id", aggfunc="count", fill_value=0)
           .reindex(columns=idx, fill_value=0))
    g = s.groupby("species_name").agg(Sightings=("sighting_id", "count"), last=("ts", "max"))
    g["Trend"] = [piv.loc[n].tolist() for n in g.index]
    g["Last seen"] = g.pop("last").dt.strftime("%d %b %Y")
    return g.sort_values("Sightings", ascending=False).reset_index().rename(columns={"species_name": "Species"})


def season_centre_doy(ts: pd.Series) -> float:
    ang = 2 * np.pi * ts.dt.dayofyear.to_numpy() / 365.25
    m = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())
    return float((m / (2 * np.pi) * 365.25) % 365.25)


def over_time(s, t, freq="M") -> pd.DataFrame:
    sp = s["ts"].dt.to_period(freq).dt.start_time
    tp = t["ts"].dt.to_period(freq).dt.start_time
    a = s.assign(period=sp).groupby("period").agg(Sightings=("sighting_id", "count"),
                                                   Species=("species_code", "nunique"))
    b = t.assign(period=tp).groupby("period")["track_id"].nunique().rename("Trips")
    out = a.join(b, how="outer").fillna(0).astype(int).sort_index()
    first_seen = s.groupby("species_code")["ts"].min().dt.to_period(freq).dt.start_time
    out["Species recorded to date"] = first_seen.value_counts().reindex(out.index, fill_value=0).cumsum()
    return out.reset_index()


# ── Region comparisons ───────────────────────────────────────────────────────
def _mode(x):
    return x.mode().iat[0] if len(x) else None


def busiest_region_by_year(s, exclude="Open ocean") -> pd.DataFrame:
    cols = ["Year", "Region", "Sightings", "Share of year", "Top species"]
    s = s[s["region"] != exclude]
    if s.empty:
        return pd.DataFrame(columns=cols)
    g = s.groupby(["year", "region"]).agg(Sightings=("sighting_id", "count"),
                                          top=("species_name", _mode)).reset_index()
    tot = s.groupby("year").size()
    g = g.loc[g.groupby("year")["Sightings"].idxmax()]
    g["Share of year"] = (g["Sightings"] / g["year"].map(tot)).map("{:.0%}".format)
    g = g.rename(columns={"year": "Year", "region": "Region", "top": "Top species"})
    return g.sort_values("Year", ascending=False)[cols].reset_index(drop=True)


def region_rank_by_year(s_all_regions, region, exclude="Open ocean") -> pd.DataFrame:
    """For one region: its sightings, global rank and share for every year."""
    cols = ["Year", "Sightings", "Global rank", "Share of global", "Top species"]
    s = s_all_regions[s_all_regions["region"] != exclude]
    if s.empty:
        return pd.DataFrame(columns=cols)
    counts = s.groupby(["year", "region"]).size().rename("n").reset_index()
    counts["rank"] = counts.groupby("year")["n"].rank(ascending=False, method="min").astype(int)
    totals = s.groupby("year").size()
    regions_per_year = counts.groupby("year").size()
    mine = counts[counts["region"] == region].set_index("year")
    tops = s[s["region"] == region].groupby("year")["species_name"].agg(_mode)
    out = pd.DataFrame({
        "Year": mine.index,
        "Sightings": mine["n"].values,
        "Global rank": [f"#{r} of {regions_per_year[y]}" for y, r in zip(mine.index, mine["rank"])],
        "Share of global": (mine["n"] / totals.reindex(mine.index)).values,
        "Top species": tops.reindex(mine.index).values,
    })
    return out.sort_values("Year", ascending=False)[cols].reset_index(drop=True)


# ── Plain-language seasonality ───────────────────────────────────────────────
def _months_covered(data_start, data_end):
    """How many times each calendar month (1-12) falls inside the data range."""
    months = pd.period_range(pd.Timestamp(data_start), pd.Timestamp(data_end), freq="M")
    return pd.Series(months.month).value_counts().reindex(range(1, 13), fill_value=0)


def typical_month(sd, data_start, data_end) -> pd.DataFrame:
    """Average sightings per calendar month, fair to partial years."""
    totals = sd.groupby("month").size().reindex(range(1, 13), fill_value=0)
    cover = _months_covered(data_start, data_end).replace(0, np.nan)
    out = pd.DataFrame({"month": range(1, 13), "Month": MONTHS,
                        "Average": (totals / cover).fillna(0).values})
    return out


def this_year_vs_past(sd, data_start, now) -> pd.DataFrame:
    """Monthly sightings this year next to the average of earlier years."""
    yr = now.year
    cur = sd[sd["year"] == yr].groupby("month").size().reindex(range(1, now.month + 1), fill_value=0)
    past = sd[sd["year"] < yr]
    cover = _months_covered(data_start, pd.Timestamp(yr - 1, 12, 31)).replace(0, np.nan)
    avg = (past.groupby("month").size().reindex(range(1, 13), fill_value=0) / cover)
    return pd.DataFrame({"Month": MONTHS, "This year": cur.reindex(range(1, 13)).values,
                         "Past average": avg.values})


def peak_month_by_year(sd, data_start, data_end) -> pd.DataFrame:
    rows = []
    first, last = pd.Timestamp(data_start), pd.Timestamp(data_end)
    for y, g in sd.groupby("year"):
        mc = g["month"].value_counts()
        partial = (y == first.year and first.month > 1) or (y == last.year and last.month < 12)
        rows.append({"Year": f"{int(y)}{' (partial)' if partial else ''}",
                     "Busiest month": MONTHS[int(mc.idxmax()) - 1],
                     "Sightings that month": int(mc.max()),
                     "Sightings that year": len(g)})
    return pd.DataFrame(rows).iloc[::-1].reset_index(drop=True)


def plural(name: str) -> str:
    name = name.strip()
    return name if name.endswith("s") else f"{name}s"


def typical_calves(sd, data_start, data_end) -> pd.DataFrame:
    """Calves counted in a typical month (fair to partial years)."""
    totals = sd.groupby("month")["animals_calf"].sum().reindex(range(1, 13), fill_value=0)
    cover = _months_covered(data_start, data_end).replace(0, np.nan)
    return pd.DataFrame({"month": range(1, 13), "Month": MONTHS,
                         "Calves": (totals / cover).fillna(0).values})