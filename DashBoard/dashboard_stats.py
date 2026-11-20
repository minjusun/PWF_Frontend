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

    return {
        "period": STATS_PERIOD,
        "active_users": {"value": int(cur["users"]), "delta": delta("users"), "monthly": _series(ms["users"])},
        "animals": {"value": int(cur["animals"]), "delta": delta("animals"), "monthly": _series(ms["animals"])},
        "contributors": _top_boats_past_year(s, now),
    }
