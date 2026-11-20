"""
Numbers for the stats pages (/stats/active-users, /stats/sightings, /stats/contributors), built with
the same data.py functions and the same default view as the Streamlit dashboard (app.py), so the
three embedded charts show exactly what the dashboard's cards show:

    Active users       -> dashboard "Active users" card      (Whole world, all species, default period)
    Animals counted    -> dashboard "Animals counted" card
    Top 5 contributors -> dashboard "Top 5 Contributors (Past Year)" card (boats, last 12 months)

map_api.py calls build_dashboard_stats(s, t) when it refreshes the snapshot and stores the result
under "dashboard" in /api/stats.json.

STATS_PERIOD env var: "All time" (default, the dashboard's default preset) or "Last 12 months".
Keep it the same as the dashboard's DEFAULTS["sb_preset"] in app.py.
"""
import os

import pandas as pd

import data as d
import whale_regions as R

STATS_PERIOD = os.environ.get("STATS_PERIOD", "All time")


def _series(sr):
    """Monthly series -> [{"month": "2025-11-01", "value": 123}, ...]"""
    idx = sr.index
    if isinstance(idx, pd.PeriodIndex):
        idx = idx.to_timestamp()
    idx = pd.to_datetime(idx)
    return [{"month": ts.strftime("%Y-%m-%d"), "value": float(v) if pd.notna(v) else 0.0}
            for ts, v in zip(idx, sr.values)]


def _top_boats_past_year(s, now, n=5):
    """Same as top_boats_past_year() in app.py."""
    recent = s[s["ts"] >= now - pd.DateOffset(years=1)]
    boats = recent["boat_name"].astype("string").str.strip()
    recent = recent[boats.notna() & (boats != "")]
    counts = recent.assign(boat=boats).groupby("boat").size().sort_values(ascending=False).head(n)
    return [{"rank": i, "boat": str(b), "sightings": int(c)} for i, (b, c) in enumerate(counts.items(), 1)]


def _with_regions(s):
    """Give each sighting its region exactly like load() in app.py (2-decimal cells, same boundaries)."""
    try:
        regions = R.load_regions()
    except Exception:                       # offline: same 1-degree squares the dashboard falls back to
        regions = R.grid_regions(s["lat"], s["lon"])
    cells = s[["lat", "lon"]].round(2).drop_duplicates()
    cells["region"] = R.assign(cells["lat"], cells["lon"], regions)
    return (s.assign(_la=s["lat"].round(2), _lo=s["lon"].round(2))
             .merge(cells.rename(columns={"lat": "_la", "lon": "_lo"}), on=["_la", "_lo"], how="left")
             .drop(columns=["_la", "_lo"]))


def build_dashboard_stats(s: pd.DataFrame, t: pd.DataFrame) -> dict:
    now = pd.Timestamp.now()
    day = pd.Timedelta(days=1)
    if STATS_PERIOD == "Last 12 months":
        start, end = (now - pd.DateOffset(years=1)).normalize(), now
        prev = (start - pd.DateOffset(years=1), start)
    else:                                    # "All time": no earlier period, so no "vs prev." badge
        start, end, prev = s["ts"].min().normalize(), now.normalize() + day, None

    # Whole world + all species, exactly like the dashboard's default view
    s_scope, t_scope = d.slice_data(s, t, start, end, tracks_follow_sightings=False)
    cur = d.kpis(s_scope, t_scope)
    old = d.kpis(*d.slice_data(s, t, *prev, tracks_follow_sightings=False)) if prev else None
    ms = d.monthly_series(s_scope, t_scope, start, end)

    def delta(k):
        if not old or old[k] == 0:
            return None
        change = (cur[k] - old[k]) / old[k]
        return {"text": f"{change:+.0%} vs prev.", "up": change >= 0}

    # Animals counted for each region: same as picking that region in the dashboard's sidebar
    months = [p["month"] for p in _series(ms["animals"])]
    by_region = []
    try:
        sr = _with_regions(s)
        order = [r for r in sr["region"].value_counts().index if r != R.OPEN_OCEAN]
        if R.OPEN_OCEAN in set(sr["region"]):
            order.append(R.OPEN_OCEAN)                       # last, like the dashboard's list
        for name in order:
            s_reg = sr[sr["region"] == name]
            rs, rt = d.slice_data(s_reg, t, start, end, tracks_follow_sightings=True)
            rcur = d.kpis(rs, rt)
            rold = d.kpis(*d.slice_data(s_reg, t, *prev, tracks_follow_sightings=True)) if prev else None
            vals = {p["month"]: p["value"] for p in _series(d.monthly_series(rs, rt, start, end)["animals"])}
            rdelta = None
            if rold and rold["animals"]:
                ch = (rcur["animals"] - rold["animals"]) / rold["animals"]
                rdelta = {"text": f"{ch:+.0%} vs prev.", "up": ch >= 0}
            by_region.append({"name": str(name), "value": int(rcur["animals"]), "delta": rdelta,
                              "monthly": [vals.get(m, 0.0) for m in months]})
    except Exception as e:                   # keep the rest of the stats even if regions fail
        print(f"Animals by region skipped ({type(e).__name__}: {e}).")

    return {
        "period": STATS_PERIOD,
        "animals_by_region": {"months": months, "regions": by_region},
        "active_users": {"value": int(cur["users"]), "delta": delta("users"), "monthly": _series(ms["users"])},
        "animals": {"value": int(cur["animals"]), "delta": delta("animals"), "monthly": _series(ms["animals"])},
        "contributors": _top_boats_past_year(s, now),
    }