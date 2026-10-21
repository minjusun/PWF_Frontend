"""
Whale & Dolphin Tracker Dashboard — Streamlit dashboard
Run:  streamlit run app.py
"""
import base64
import html
import json
import os
import re

import folium
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

import data as d
import regions as R

st.set_page_config(page_title="Whale & Dolphin Tracker Dashboard", layout="wide", initial_sidebar_state="collapsed")

GLOBAL = "Global"
DEEP, TEAL, SEAFOAM, MIST, SAND, CORAL = "#0E4D64", "#1B7F8C", "#4FB0A5", "#9FD3C7", "#E0A458", "#C8553D"
OCEAN = [DEEP, TEAL, SEAFOAM, SAND, CORAL, "#6C5B7B", "#355C7D", MIST, "#99B898"]
HEAT = ["#F2F7F8", MIST, TEAL, DEEP]
px.defaults.color_discrete_sequence = OCEAN
PLOT_CFG = {"displayModeBar": False}

st.markdown("""
<style>
html {font-size: 14px;}
.block-container, [data-testid="stMainBlockContainer"] {padding: 2.6rem 4.5rem 2rem; max-width: 100%;}
[data-testid="stVerticalBlock"] {gap: 0.55rem;}
[class*="st-key-card"] {background:#FFFFFF; border:1px solid #DCE7EA; border-radius:10px; padding:14px 16px 14px;}
[class*="st-key-card"] [data-testid="stVerticalBlock"] {gap: 0.5rem;}
[class*="st-key-card"] [data-testid="stMarkdownContainer"] p {margin-bottom: 0;}
.card-head {padding: 0 0 10px; line-height: 1.35;}
.card-title {font-size:0.92rem; font-weight:600; color:#12303B;}
.card-sub {color:#5B7680; font-size:0.74rem; line-height:1.35; margin:2px 0 0;}
[class*="st-key-card_kpi"] {padding:12px 16px 10px;}
[class*="st-key-card_kpi"] [data-testid="stMetricValue"] {font-size:1.4rem; color:#0E4D64;}
[class*="st-key-card_kpi"] [data-testid="stMetricLabel"] p {font-size:0.76rem; color:#5B7680;}
[class*="st-key-card_kpi"] [data-testid="stMetricDelta"] {font-size:0.72rem;}
.scope {color:#5B7680; font-size:0.82rem; margin:0.25rem 0 0;}
h1 {font-size:1.35rem !important; padding:0 !important;}
.snap {display:grid; grid-template-columns:1fr 1fr; gap:12px 14px; padding:0 0 14px;}
.snap span {display:block; color:#5B7680; font-size:0.72rem;}
.snap b {display:block; color:#0E4D64; font-size:1.05rem; font-weight:600; line-height:1.25;
         overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {display:none;}
/* Page background: one smooth gradient, light blue at the top to dark navy at the bottom */
[data-testid="stApp"] {background: #06142C;}   /* matches the bottom colour, so the page end blends in */
.block-container, [data-testid="stMainBlockContainer"] {
  min-height: 100vh;
  background: linear-gradient(180deg, #CFE9F7 0%, #A8D5EE 14%, #78B9DF 28%, #4A97C8 42%,
                              #2A74AA 56%, #1A5487 70%, #113964 84%, #06142C 100%);
}
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] {background: transparent;}
[data-testid="stAppViewContainer"], [data-testid="stMain"] {overflow-x: hidden;}
.brand {display:flex; align-items:center; gap:14px; flex-wrap:nowrap; padding:0 0 4px; min-width:0;}
/* Header bar: full width, flush with the top and sides, dark blue */
.st-key-header {background: linear-gradient(180deg, #1E5F8F 0%, #12446F 45%, #0B3358 100%);
                width: 100vw !important; max-width: 100vw; box-sizing: border-box;
                position: relative; left: 50%; margin-left: -50vw !important;
                margin-top: -3.8rem; margin-bottom: 48px;
                padding: 2.2rem 4.5rem 18px; border-radius: 0;
                box-shadow: 0 6px 20px rgba(6,26,48,0.25);}
.st-key-header [data-baseweb="select"] > div {background: rgba(255,255,255,0.12) !important;
                                              border-color: rgba(255,255,255,0.25) !important;}
.st-key-header [data-baseweb="select"] > div:hover {background: rgba(255,255,255,0.2) !important;}
.st-key-header [data-baseweb="select"] div, .st-key-header [data-baseweb="select"] input,
.st-key-header [data-baseweb="select"] svg {color: #FFFFFF !important; fill: #FFFFFF !important;}
[data-testid="stToolbar"] button, [data-testid="stToolbar"] a, [data-testid="stToolbar"] span {color: #E6EEF3 !important;}
.brand-logo {height:42px; width:auto; display:block;}
.brand-divider {width:1px; height:30px; background:rgba(255,255,255,0.35);}
.brand-logo, .brand-divider {flex-shrink:0;}
.summary {color:#C9DAE7; font-size:0.92rem; line-height:1.4; white-space:nowrap; overflow:hidden;
          text-overflow:ellipsis; min-width:0;}
.summary b {color:#FFFFFF; font-weight:700;}
.summary-dot {margin:0 9px; color:rgba(255,255,255,0.4);}
.st-key-header [data-testid="stWidgetLabel"] p {color: #C9DAE7 !important;}

.quote {font-size:2.4rem; font-weight:800; color:#0B2540; text-align:center; letter-spacing:0.02em;
        line-height:1.2; padding:10px 0;}
.quote-spaced {margin: 30px 0 34px;}
.quote-on-blue {color:#FFFFFF; text-shadow:0 2px 12px rgba(6,52,90,0.45);}
/* Dropdowns: see-through blue tint instead of solid white/grey */
[data-baseweb="select"] > div {background: rgba(42,120,174,0.12) !important;
                               border: 1px solid rgba(11,37,64,0.14) !important; border-radius: 8px !important;}
[data-baseweb="select"] > div:hover {background: rgba(42,120,174,0.2) !important;}
.st-key-kpi_row {margin-bottom: 22px;}
/* Swimming whale: starts parked top-right; the script below moves it and bounces it off the edges */
.whale-swim {position: fixed; top: 120px; right: 28px; z-index: 50; cursor: pointer; will-change: left, top;}
.whale-bob {animation: whale-bob 4s ease-in-out infinite;}
/* shown at its real size (never stretched bigger), so it stays sharp */
.whale-swim img {display: block; width: auto; height: auto; max-width: 220px; zoom: 0.7;}  /* 0.7 = 70% size */
[class*="st-key-card"] {transition: box-shadow .3s ease, border-color .3s ease;}
[class*="st-key-card"].Humphrey-highlight {border-color: #4FB0A5 !important;
    box-shadow: 0 0 0 3px rgba(79,176,165,0.55), 0 0 26px rgba(79,176,165,0.45) !important;}
/* No fullscreen (enlarge) button on tables and charts */
[data-testid="stElementToolbar"] button[aria-label*="ullscreen" i],
[data-testid="stElementToolbar"] button[title*="ullscreen" i],
[data-testid="stElementToolbarButton"]:has(button[aria-label*="ullscreen" i]),
[data-testid="stElementToolbarButton"]:has(button[title*="ullscreen" i]) {display: none !important;}
.Humphrey-dock {position: fixed; left: -9999px; top: -9999px; z-index: 49; cursor: pointer;
               box-sizing: border-box; border-radius: 18px;
               background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.55);
               box-shadow: 0 6px 22px rgba(6,26,48,0.18), inset 0 1px 0 rgba(255,255,255,0.5);
               backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
               transition: background .25s, opacity .25s;}
.Humphrey-dock:hover {background: rgba(255,255,255,0.3);}
.Humphrey-dock span {position: absolute; left: 0; right: 0; bottom: 5px; text-align: center;
                   font-size: 0.85rem; font-weight: 600; letter-spacing: 0.04em; color: #0E4D64; opacity: 0.75;}
.Humphrey-dock.empty {background: rgba(255,255,255,0.10); opacity: 0.7;}   /* his empty home while he's out */
.Humphrey-lock {position: fixed; left: -9999px; top: -9999px; z-index: 51; width: 24px; height: 24px;
               padding: 0; border-radius: 50%; border: 1px solid rgba(14,77,100,0.25); cursor: pointer;
               display: flex; align-items: center; justify-content: center;
               background: rgba(255,255,255,0.85); color: #5B7680;
               box-shadow: 0 2px 8px rgba(6,26,48,0.2); transition: background .2s, color .2s;}
.Humphrey-lock:hover {background: #FFFFFF; color: #0E4D64;}
.Humphrey-lock.on {background: #0E4D64; color: #FFFFFF; border-color: #0E4D64;}
.Humphrey-bubble {position: fixed; left: -9999px; top: -9999px; z-index: 60; max-width: 250px;
                 background: #FFFFFF; color: #12303B; font-size: 0.82rem; line-height: 1.4;
                 padding: 9px 12px; border-radius: 12px; border: 1px solid #DCE7EA;
                 box-shadow: 0 8px 24px rgba(6,26,48,0.25); pointer-events: none;
                 opacity: 0; transform: translateY(6px); transition: opacity .25s, transform .25s;}
.Humphrey-bubble.show {opacity: 1; transform: translateY(0);}
.Humphrey-bubble b {color: #0E4D64;}
@keyframes whale-bob {0%, 100% {transform: translateY(0);} 50% {transform: translateY(-12px);}}
@media (prefers-reduced-motion: reduce) {.whale-bob {animation: none;}}
.st-key-more_btn button {background:#FFFFFF; border:1px solid #DCE7EA; border-radius:10px; min-height:2.4rem;}
.st-key-more_btn button:hover {border-color:#1B7F8C; color:#1B7F8C;}
.st-key-more_btn [data-testid="stIconMaterial"] {font-size:1.8rem;}
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────────────
def card(key, title=None, sub=None):
    c = st.container(key=f"card_{key}")
    if title or sub:
        t = f"<div class='card-title'>{html.escape(title)}</div>" if title else ""
        s_ = f"<div class='card-sub'>{sub}</div>" if sub else ""
        c.markdown(f"<div class='card-head'>{t}{s_}</div>", unsafe_allow_html=True)
    return c


AXIS_FONT = dict(size=11, color="#0B2233")   # axis titles
TICK_FONT = dict(size=11, color="#0B2233")   # months / numbers along the axes


def style(fig, h=280, legend=False, x=None, y=None):
    fig.update_layout(height=h, margin=dict(l=4, r=4, t=6, b=4), title_text="",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="-apple-system, Segoe UI, Inter, sans-serif", size=11, color="#0B2233"),
                      showlegend=legend, legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text=""),
                      hoverlabel=dict(bgcolor="white"))
    fig.update_xaxes(showgrid=False, title_text=x or "", title_font=AXIS_FONT, title_standoff=14,
                     tickfont=TICK_FONT, linecolor="#B7C7CF", automargin=True)
    fig.update_yaxes(gridcolor="#EAF1F3", title_text=y or "", title_font=AXIS_FONT, title_standoff=14,
                     tickfont=TICK_FONT, zeroline=False, automargin=True)
    fig.update_layout(legend_font=dict(color="#0B2233", size=11))
    return fig


def sparkline(series, color=TEAL, h=40, axes=False, x=None, y=None):
    fig = go.Figure(go.Scatter(x=series.index, y=series.values, mode="lines", fill="tozeroy",
                               line=dict(color=color, width=2), fillcolor="rgba(79,176,165,0.18)",
                               hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra></extra>"))
    fig.update_layout(height=h, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    if axes:   # small month labels along the bottom and counts up the side
        fig.update_layout(margin=dict(l=52, r=10, t=6, b=42),
                          font=dict(family="-apple-system, Segoe UI, Inter, sans-serif", size=10, color="#0B2233"))
        fig.update_xaxes(visible=True, showgrid=False, linecolor="#DCE7EA", tickformat="%b %y", nticks=7, tickfont=TICK_FONT,
                         title_text=x or "", title_font=dict(size=11, color="#0B2233"), title_standoff=12,
                         automargin=True)
        fig.update_yaxes(visible=True, rangemode="tozero", gridcolor="#EAF1F3", nticks=4, zeroline=False, tickfont=TICK_FONT,
                         title_text=y or "", title_font=dict(size=11, color="#0B2233"), title_standoff=12,
                         automargin=True)
    else:
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False, rangemode="tozero")
    return fig


def logo_html():
    """Logo from logo.svg or logo.png next to this file (white version suits the dark header)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for name, mime in (("logo.svg", "image/svg+xml"), ("logo.png", "image/png")):
        path = os.path.join(here, name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            return (f"<img class='brand-logo' src='data:{mime};base64,{b64}' alt='Pacific Whale Foundation'>"
                    "<span class='brand-divider'></span>")
    return ""


def whale_gif_html():
    """A swimming whale from whalegif.gif (or .webp/.png) next to this file; empty if missing."""
    here = os.path.dirname(os.path.abspath(__file__))
    for name, mime in (("whalegif.gif", "image/gif"), ("whalegif.GIF", "image/gif"),
                       ("whalegif.webp", "image/webp"), ("whalegif.png", "image/png")):
        path = os.path.join(here, name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            return (f"<div class='whale-swim'><div class='whale-bob'>"
                    f"<img src='data:{mime};base64,{b64}' alt='Whale'></div></div>")
    return ""


def snapshot(items):
    cells = "".join(f"<div><span>{html.escape(k)}</span><b title='{html.escape(str(v))}'>{html.escape(str(v))}</b></div>"
                    for k, v in items)
    st.markdown(f"<div class='snap'>{cells}</div>", unsafe_allow_html=True)


def db_url():
    try:
        return st.secrets.get("db_url")
    except Exception:
        return None


@st.cache_resource(show_spinner="Loading region boundaries (first run downloads them once)…")
def load_boundaries():
    try:
        return R.load_regions(), None
    except Exception as e:  # offline etc. — fall back to 1° grid squares
        return None, str(e)


@st.cache_data(ttl=600, show_spinner="Loading sightings and trips…")
def load(source: str):
    raw = d.load_db(db_url()) if source == "live" else d.load_demo()
    s, t = d.prepare(*raw)
    regions, err = load_boundaries()
    if regions is None:
        regions = R.grid_regions(s["lat"], s["lon"])
    cells = s[["lat", "lon"]].round(2).drop_duplicates()
    cells["region"] = R.assign(cells["lat"], cells["lon"], regions)
    s = s.assign(_la=s["lat"].round(2), _lo=s["lon"].round(2)).merge(
        cells.rename(columns={"lat": "_la", "lon": "_lo"}), on=["_la", "_lo"], how="left").drop(columns=["_la", "_lo"])
    used = set(s["region"])
    return s, t, [r for r in regions if r["name"] in used], err


s_all, t_all, region_shapes, boundary_err = load("live" if db_url() else "demo")
shape_by_name = {r["name"]: r for r in region_shapes}
now = pd.Timestamp.now()
ss = st.session_state
ss.setdefault("region_pick", GLOBAL)
if "pending_region" in ss:                      # set by a map click on the previous run
    ss.region_pick = ss.pop("pending_region")


def go_global():
    ss.region_pick = GLOBAL


# ── Header: title + filters ──────────────────────────────────────────────────
header_box = st.container(key="header")
h1, h2, h3, h4 = header_box.columns([5.6, 1.3, 2.2, 1.6], vertical_alignment="center")
with h1:
    brand_slot = st.empty()
years = sorted(s_all["year"].unique(), reverse=True)
window = h2.selectbox("Period", ["Last 12 months", *[str(y) for y in years], "All time"])
sp_filter = h3.multiselect("Species", s_all["species_name"].value_counts().index.tolist(), placeholder="All species")
who = h4.selectbox("Contributor", ["Everyone", *s_all["contributor"].value_counts().index.tolist()])

if window == "Last 12 months":
    start, end = (now - pd.DateOffset(years=1)).normalize(), now
    prev = (start - pd.DateOffset(years=1), start)
elif window == "All time":
    start, end, prev = s_all["ts"].min().normalize(), now + pd.Timedelta(days=1), None
else:
    y = int(window)
    start, end = pd.Timestamp(y, 1, 1), pd.Timestamp(y + 1, 1, 1)
    prev = (pd.Timestamp(y - 1, 1, 1), start)
hist_start, hist_end = s_all["ts"].min(), now + pd.Timedelta(days=1)

s, t = s_all, t_all
if sp_filter:
    s = s[s["species_name"].isin(sp_filter)]
if who != "Everyone":
    s, t = s[s["contributor"] == who], t[t["contributor"] == who]
follow = bool(sp_filter)
s_period, t_period = d.slice_data(s, t, start, end, tracks_follow_sightings=follow)
region_counts = s_period["region"].value_counts()

kpi_row = st.container(key="kpi_row")
left, center, right = st.columns([3, 4, 3])

# ── Center: region search + choropleth map ───────────────────────────────────
with center:
    with card("map"):
        options = [GLOBAL] + [r for r in s_all["region"].value_counts().index if r != R.OPEN_OCEAN]
        if R.OPEN_OCEAN in set(s_all["region"]):
            options.append(R.OPEN_OCEAN)
        if ss.region_pick not in options:
            ss.region_pick = GLOBAL
        c1, c2 = st.columns([5, 1.3], vertical_alignment="bottom")
        c1.selectbox("Region", options, key="region_pick", label_visibility="collapsed",
                     format_func=lambda r: "Global, all regions" if r == GLOBAL
                     else f"{r}  ({int(region_counts.get(r, 0)):,})")
        c2.button("Global", on_click=go_global, disabled=ss.region_pick == GLOBAL, use_container_width=True)
        region_sel = None if ss.region_pick == GLOBAL else ss.region_pick

        m = folium.Map(location=[20, -100], zoom_start=2, tiles=None, world_copy_jump=True, min_zoom=2,
                       control_scale=True)
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}",
            attr="Tiles &copy; Esri — GEBCO, NOAA, Garmin, HERE and other contributors",
            name="Ocean", max_native_zoom=10, max_zoom=18).add_to(m)
        gj = R.to_geojson(region_shapes, region_counts, region_sel)
        vmax = np.log1p(max(1, region_counts.drop(R.OPEN_OCEAN, errors="ignore").max() if len(region_counts) else 1))
        scale = px.colors.sample_colorscale([[0, MIST], [0.5, TEAL], [1, DEEP]], 101)

        def region_style(feat):
            p = feat["properties"]
            colour = scale[int(round(100 * np.log1p(p["sightings"]) / vmax))]
            if p["selected"]:
                return {"fillColor": colour, "color": CORAL, "weight": 3, "fillOpacity": 0.8}
            return {"fillColor": colour, "color": "#FFFFFF", "weight": 1,
                    "fillOpacity": 0.3 if region_sel else 0.7}

        if gj["features"]:
            folium.GeoJson(gj, name="Regions", style_function=region_style,
                           highlight_function=lambda f: {"weight": 3, "color": DEEP, "fillOpacity": 0.85},
                           tooltip=folium.GeoJsonTooltip(fields=["region", "sightings"],
                                                         aliases=["", "Sightings"], localize=True)).add_to(m)
        if region_sel in shape_by_name:
            x0, y0, x1, y1 = shape_by_name[region_sel]["bbox"]
            m.fit_bounds([[y0, x0], [y1, x1]], padding=(20, 20))

        map_key = f"map_{region_sel or GLOBAL}"
        map_state = st_folium(m, key=map_key, height=400, use_container_width=True,
                              returned_objects=["last_active_drawing"])
        clicked = ((map_state or {}).get("last_active_drawing") or {}).get("properties", {}).get("region")
        if clicked and ss.get("last_click") != (map_key, clicked):
            ss.last_click = (map_key, clicked)
            ss.pending_region = GLOBAL if clicked == region_sel else clicked
            st.rerun()
        st.markdown("<div class='card-sub' style='padding-bottom:6px'>Click a region, or search above, to see its "
                    "stats. Click it again or press Global to go back.</div>", unsafe_allow_html=True)
        if boundary_err:
            st.caption("Couldn't download region boundaries, so 1° squares are shown instead.")

is_global = region_sel is None
short_name = GLOBAL if is_global else region_sel.split(",")[0]
s_reg = s if is_global else s[s["region"] == region_sel]
follow_r = follow or not is_global
s_scope, t_scope = d.slice_data(s_reg, t, start, end, tracks_follow_sightings=follow_r)
s_hist, t_hist = d.slice_data(s_reg, t, hist_start, hist_end, tracks_follow_sightings=follow_r)
s_hist_all = d.slice_data(s, t, hist_start, hist_end)[0]

# ── Header: logo + one-line summary (replaces the old Global view box) ───────
rc = region_counts.drop(R.OPEN_OCEAN, errors="ignore")
esc = html.escape
if is_global:
    top_r = rc.index[0].split(",")[0] if len(rc) else "—"
    parts = ["<b>Global</b>",
             f"<b>{len(rc):,}</b> regions with sightings",
             f"Top region <b>{esc(top_r)}</b>",
             f"<b>{t_period['track_id'].nunique():,}</b> total trips",
             f"<b>{s_period['creator'].nunique():,}</b> contributors"]
else:
    rank = (list(rc.index).index(region_sel) + 1) if region_sel in rc.index else None
    first = s_hist["ts"].min()
    top_sp = s_scope["species_name"].mode().iat[0] if len(s_scope) else "—"
    parts = [f"<b>{esc(short_name)}</b>",
             f"<b>{t_scope['track_id'].nunique():,}</b> total trips",
             f"Ranked <b>#{rank}</b> of {len(rc)}" if rank else "Not ranked",
             f"Top species <b>{esc(top_sp)}</b>",
             f"First sighting <b>{first.strftime('%b %Y') if pd.notna(first) else '—'}</b>"]
summary = "<span class='summary-dot'>·</span>".join(parts)
tooltip = esc(re.sub(r"<[^>]+>", "", " · ".join(parts)))   # plain text shown on hover
brand_slot.markdown(f"<div class='brand'>{logo_html()}<div class='summary' title='{tooltip}'>"
                    f"{summary}</div></div>", unsafe_allow_html=True)


# ── KPI strip ────────────────────────────────────────────────────────────────
cur = d.kpis(s_scope, t_scope)
old = d.kpis(*d.slice_data(s_reg, t, *prev, tracks_follow_sightings=follow_r)) if prev else None
ms = d.monthly_series(s_scope, t_scope, start, end)


def delta(k):
    if not old or old[k] == 0:
        return None
    return f"{(cur[k] - old[k]) / old[k]:+.0%} vs prev."


with kpi_row:
    k_animals, k_quote = st.columns(2, vertical_alignment="center")
    with k_animals:
        with card("kpi_animals"):
            st.metric("Animals counted", f"{cur['animals']:,}", delta("animals"))
            st.plotly_chart(sparkline(ms["animals"], h=135, axes=True, x="Month", y="Animals"),
                            config=PLOT_CFG, theme=None, key="spark_animals")
    with k_quote:   # QUOTE 1
        st.markdown("<div class='quote quote-on-blue'><i>&ldquo;This is a placeholder for a quote&rdquo;</i></div>",
                    unsafe_allow_html=True)


# ── Left of map: top 5 contributors (red bars) + active users ────────────────
with left:
    with card("contrib", "Top 5 contributors"):
        view = GLOBAL
        if not is_global:
            view = st.segmented_control("Contributor scope", [short_name, GLOBAL], default=short_name,
                                        key="contrib_scope", label_visibility="collapsed") or short_name
        tc = d.top_contributors(s_period, t_period) if view == GLOBAL else d.top_contributors(s_scope, t_scope)
        st.dataframe(tc[["Contributor", "Sightings", "Trips", "Species"]], hide_index=True, height=181, row_height=29,
                     column_config={"Sightings": st.column_config.ProgressColumn(
                         "Sightings", format="%d", max_value=int(max(1, tc["Sightings"].max() if len(tc) else 1)))})

    with card("kpi_users"):
        st.metric("Active users", f"{cur['users']:,}", delta("users"))
        st.plotly_chart(sparkline(ms["users"], h=135, axes=True, x="Month", y="Users"),
                        config=PLOT_CFG, theme=None, key="spark_users")


# ── Right of map: species spotted (red bars) + image placeholder ─────────────
with right:
    with card("species_list", "Top 5 Species Spotted"):
        sp_all = d.species_table(s_scope, start, end)      # every species, most-sighted first
        sp_tab = sp_all.head(5)
        st.dataframe(sp_tab, hide_index=True, height=181, row_height=29, column_config={   # same size as Top 5 contributors
            "Sightings": st.column_config.ProgressColumn(
                format="%d", max_value=int(max(1, sp_tab["Sightings"].max() if len(sp_tab) else 1))),
            "Trend": st.column_config.AreaChartColumn("Trend (per month)", y_min=0, help="Sightings per month across the selected period"),
            "Last seen": st.column_config.TextColumn("Last seen", width="small"),
        })

    st.markdown("<div class='quote quote-on-blue quote-spaced'>This is a placeholder for an img</div>",
                unsafe_allow_html=True)


# QUOTE 2!!!!--------------------------------------------------------------------
st.markdown("<div class='quote quote-on-blue quote-spaced'><i>&ldquo;This is a placeholder for a quote&rdquo;</i></div>",
            unsafe_allow_html=True)

# ── Row line 1: activity over time + best time to see ────────────────────────
sp_rank = s_hist["species_name"].value_counts()
c_activity, c_best = st.columns([5, 5])
data_start, data_end = s_all["ts"].min(), now

with c_activity:
    with card("activity", "Activity over time"):
        c1, c2 = st.columns([3, 2])
        what = c1.segmented_control("Show", ["Trips & sightings", "Species"], default="Trips & sightings",
                                    key="act_what", label_visibility="collapsed") or "Trips & sightings"
        gran = c2.selectbox("Group by", ["Month", "Week", "Quarter"], key="act_gran",
                            label_visibility="collapsed")
        ot = d.over_time(s_hist, t_hist, {"Week": "W", "Month": "M", "Quarter": "Q"}[gran])
        fig = go.Figure()
        if what == "Trips & sightings":
            fig.add_bar(x=ot["period"], y=ot["Trips"], name="Trips", marker_color=MIST)
            fig.add_scatter(x=ot["period"], y=ot["Sightings"], name="Sightings", mode="lines",
                            line=dict(color=DEEP, width=2))
        else:
            fig.add_bar(x=ot["period"], y=ot["Species"], name="Seen in period", marker_color=MIST)
            fig.add_scatter(x=ot["period"], y=ot["Species recorded to date"], name="Recorded to date",
                            mode="lines", line=dict(color=CORAL, width=2, shape="hv"))
        fig.update_layout(barmode="overlay", hovermode="x unified")
        st.plotly_chart(style(fig, h=207, legend=True, x=gran, y="Trips & sightings" if what == "Trips & sightings" else "Species"),
                        config=PLOT_CFG, theme=None, key="activity_chart")

with c_best:
    if sp_rank.empty:
        st.info("No sightings here yet. Pick another region or widen the filters.")
    else:
        with card("season", "Best time to see"):
            sel = st.selectbox("Species", sp_rank.index.tolist(), key="season_species",
                               label_visibility="collapsed")
            sd = s_hist[s_hist["species_name"] == sel]
            tm = d.typical_month(sd, data_start, data_end)
            top3 = tm.nlargest(3, "Average")
            top3 = top3[top3["Average"] > 0]
            if len(top3):
                months_txt = ", ".join(top3.sort_values("month")["Month"].tolist()[:-1])
                months_txt = (f"{months_txt} and {top3.sort_values('month')['Month'].iloc[-1]}"
                              if len(top3) > 1 else top3["Month"].iloc[0])
                st.markdown(f"<div class='card-sub' style='font-size:0.82rem'>{html.escape(d.plural(sel))} "
                            f"are seen most in <b>{months_txt}</b>.</div>", unsafe_allow_html=True)
            tm["colour"] = np.where(tm["month"].isin(top3["month"]), "Best months", "Other months")
            fig = px.bar(tm, x="Month", y="Average", color="colour",
                         color_discrete_map={"Best months": DEEP, "Other months": MIST},
                         category_orders={"Month": d.MONTHS})
            fig.update_traces(hovertemplate="%{x}: about %{y:.0f} sightings in a typical year<extra></extra>")
            st.plotly_chart(style(fig, h=185, x="Month", y="Sightings (typical month)"),
                            config=PLOT_CFG, theme=None, key="season_best")

# ── Row line 2: this year vs past + typical group size ───────────────────────
c_year, c_group = st.columns([5, 5])
if sp_rank.empty:
    with c_year:
        st.info("No sightings here yet. Pick another region or widen the filters.")
else:
    with c_year:
        with card("curve", f"{now.year} so far vs past years", f"{sel}, sightings per month"):
            ty = d.this_year_vs_past(sd, data_start, now)
            fig = go.Figure()
            fig.add_scatter(x=ty["Month"], y=ty["Past average"], name="Past years (average)", mode="lines",
                            line=dict(color=MIST, width=3, dash="dot"),
                            hovertemplate="%{x}: about %{y:.0f}<extra>Past years</extra>")
            fig.add_scatter(x=ty["Month"], y=ty["This year"], name=str(now.year), mode="lines+markers",
                            line=dict(color=DEEP, width=2.5), marker=dict(size=6),
                            hovertemplate="%{x}: %{y:.0f}<extra>" + str(now.year) + "</extra>")
            fig.update_xaxes(categoryorder="array", categoryarray=d.MONTHS)
            st.plotly_chart(style(fig, h=210, legend=True, x="Month", y="Sightings"), config=PLOT_CFG, theme=None, key="season_vs")

with c_group:
    with card("group", "Typical group size", "Median animals per sighting"):
        grp = (s_scope.groupby("species_name")["animals_total"].median().dropna().sort_values().tail(8)
               .rename_axis("Species").reset_index(name="Median"))
        if grp.empty:
            st.caption("No group counts recorded.")
        else:
            fig = px.bar(grp, x="Median", y="Species", orientation="h", color_discrete_sequence=[SEAFOAM])
            fig.update_layout(bargap=0.45)   # more space between the bars
            st.plotly_chart(style(fig, h=210, x="Median animals per sighting", y="Species"), config=PLOT_CFG, theme=None, key="group_size")

# ── More charts (hidden until the button is pressed) ─────────────────────────
def toggle_more():
    ss.show_more = not ss.get("show_more", False)


st.button("", key="more_btn", on_click=toggle_more, use_container_width=True,
          icon=":material/keyboard_arrow_up:" if ss.get("show_more") else ":material/keyboard_arrow_down:",
          help="Hide extra charts" if ss.get("show_more") else "Show more charts")

if ss.get("show_more"):
    c_hot, c_peak, c_calf = st.columns([3.2, 2.4, 2.4])
    with c_hot:
        if is_global:
            with card("hot", "Busiest region by year"):
                st.dataframe(d.busiest_region_by_year(s_hist), hide_index=True, height=249,
                             column_config={"Year": st.column_config.NumberColumn(format="%d"),
                                            "Share of year": None})
        else:
            with card("hot", f"{short_name} vs. Global"):
                st.dataframe(d.region_rank_by_year(s_hist_all, region_sel), hide_index=True, height=249,
                             column_config={"Year": st.column_config.NumberColumn(format="%d"),
                                            "Share of global": st.column_config.ProgressColumn(
                                                format="percent", min_value=0, max_value=1)})

    with c_peak:
        with card("shift", "Busiest month each year", None if sp_rank.empty else sel):
            if sp_rank.empty:
                st.caption("No sightings here yet.")
            else:
                st.dataframe(d.peak_month_by_year(sd, data_start, data_end), hide_index=True, height=230,
                             column_config={"Sightings that year": None})

    with c_calf:
        with card("calf", "Calves by month", "Calves counted in a typical month"):
            calf_counts = s_hist.groupby("species_name")["animals_calf"].sum().sort_values(ascending=False)
            calf_counts = calf_counts[calf_counts > 0]
            if calf_counts.empty:
                st.caption("No calves have been recorded here yet.")
            else:
                calf_sp = st.selectbox("Species", calf_counts.index.tolist(), key="calf_species",
                                       label_visibility="collapsed",
                                       help="Only species with calves recorded are listed.")
                tc_ = d.typical_calves(s_hist[s_hist["species_name"] == calf_sp], s_all["ts"].min(), now)
                best = tc_.loc[tc_["Calves"].idxmax(), "Month"]
                st.markdown(f"<div class='card-sub' style='font-size:0.82rem'>Most {html.escape(calf_sp.lower())} "
                            f"calves are spotted in <b>{best}</b>.</div>", unsafe_allow_html=True)
                fig = px.bar(tc_, x="Month", y="Calves", color_discrete_sequence=[SAND],
                             category_orders={"Month": d.MONTHS})
                fig.update_traces(hovertemplate="%{x}: about %{y:.0f} calves in a typical year<extra></extra>")
                fig.update_xaxes(tickangle=0, tickfont=dict(size=10, color="#0B2233"))
                st.plotly_chart(style(fig, h=170, x="Month", y="Calves (typical month)"), config=PLOT_CFG, theme=None, key="calf_chart")


# ── Humphrey's facts: what he says when you click each card ────────────────────
place = "around the world" if is_global else f"in {short_name}"
Humphrey = {
    "kpi_users": f"{cur['users']:,} people logged trips or sightings {place} this period!",
    "kpi_animals": f"{cur['animals']:,} animals counted {place}!",
    "map": ("This map shows regions where sightings were collected on our Whale & Dolphin Tracker app."),
    "activity": "Bars are trips, the line is sightings. Hover over any point to see the exact count.",
    "hot": "Each row is one year and the place with the most sightings that year.",
    "shift": "This shows the busiest month for the species you picked, year by year.",
    "calf": "Calves are baby whales and dolphins! This shows when the most are spotted.",
}
if len(tc):
    Humphrey["contrib"] = (f"These are the top spotters {place}. {tc.iloc[0]['Contributor']} leads with "
                         f"{int(tc.iloc[0]['Sightings']):,} sightings!")
else:
    Humphrey["contrib"] = f"No one has logged sightings {place} yet. Be the first!"
if len(sp_tab):
    Humphrey["species_list"] = (f"These are the 5 most-spotted species {place} ({len(sp_all)} in total). "
                              f"The most common is the {sp_tab.iloc[0]['Species'].lower()}.")
else:
    Humphrey["species_list"] = f"No species spotted {place} yet for this period."
if not sp_rank.empty:
    best_txt = f" They show up most in {months_txt}." if len(top3) else ""
    Humphrey["season"] = f"Want to see {d.plural(sel).lower()}?{best_txt}"
    Humphrey["curve"] = (f"The dark line is {now.year}, the dotted line is the past-years average. "
                       f"Above the dots means a busier month than usual!")
if not grp.empty:
    Humphrey["group"] = (f"{d.plural(grp.iloc[-1]['Species'])} travel in the biggest groups, about "
                       f"{grp.iloc[-1]['Median']:.0f} per sighting.")
# bottom charts (under the arrow): live facts too, with a simple fallback if there's no data
try:
    if is_global:
        hr = d.busiest_region_by_year(s_hist)
        if len(hr):
            r0 = hr.iloc[0]
            Humphrey["hot"] = (f"In {int(r0['Year'])}, {r0['Region'].split(',')[0]} had the most sightings: "
                             f"{int(r0['Sightings']):,}. The top species there was the {str(r0['Top species']).lower()}.")
    else:
        rr = d.region_rank_by_year(s_hist_all, region_sel)
        if len(rr):
            r0 = rr.iloc[0]
            Humphrey["hot"] = (f"In {int(r0['Year'])}, {short_name} ranked {r0['Global rank']} worldwide "
                             f"with {int(r0['Sightings']):,} sightings.")
    if not sp_rank.empty:
        pk = d.peak_month_by_year(sd, data_start, data_end)
        if len(pk):
            p0 = pk.iloc[0]
            Humphrey["shift"] = (f"In {str(p0['Year']).split(' ')[0]}, {d.plural(sel).lower()} were busiest in {p0['Busiest month']}, "
                               f"with {int(p0['Sightings that month']):,} sightings that month.")
    cc = s_hist.groupby("species_name")["animals_calf"].sum()
    cc = cc[cc > 0]
    if len(cc):
        csp = ss.get("calf_species") if ss.get("calf_species") in cc.index else cc.idxmax()
        tcv = d.typical_calves(s_hist[s_hist["species_name"] == csp], s_all["ts"].min(), now)
        Humphrey["calf"] = (f"Most {csp.lower()} calves are spotted in {tcv.loc[tcv['Calves'].idxmax(), 'Month']}. "
                        )
except Exception:
    pass   # keep the general messages set above

Humphrey_json = json.dumps(Humphrey).replace("</", "<\\/")

# ── Swimming whale (whalegif.gif next to app.py) ─────────────────────────────
st.markdown(whale_gif_html(), unsafe_allow_html=True)


components_whale = """
<script>
(function () {
  const win = window.parent, doc = win.document;
  // x = left edge on screen; py = top edge measured on the PAGE, so Humphrey scrolls with the content
  const st = win.__Humphrey || (win.__Humphrey = {x: null, py: null, vx: -95, vy: 32, running: false,
                                               goto: null, returning: false, greeting: false, bubbleUntil: 0});
  const GREETING = "Hi, I'm Humphrey! Click on a chart to hear some facts.";
  // his home: the top-right of the page, inside a see-through "dock" square
  const DOCK_PAD = 12;
  function home(bw, bh, scrollY) {
    return {x: Math.max(PAD + DOCK_PAD, win.innerWidth - bw - 28 - DOCK_PAD), y: 128, under: false};
  }
  const LOCKED_ICON = '<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path fill="currentColor" d="M7 10V7a5 5 0 0 1 10 0v3h1a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1h1zm2 0h6V7a3 3 0 0 0-6 0v3z"/></svg>';
  const OPEN_ICON = '<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path fill="currentColor" d="M9 10h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1h1V7a5 5 0 0 1 9.6-2l-1.8.9A3 3 0 0 0 9 7v3z"/></svg>';
  let lock = doc.querySelector(".Humphrey-lock");
  if (!lock) { lock = doc.createElement("button"); lock.className = "Humphrey-lock"; lock.type = "button"; doc.body.appendChild(lock); }
  function showLock() {
    lock.innerHTML = st.locked ? LOCKED_ICON : OPEN_ICON;
    lock.classList.toggle("on", !!st.locked);
    lock.title = st.locked ? "Humphrey stays home (click to let him swim to charts)"
                           : "Lock Humphrey at home";
  }
  showLock();
  if (lock.__HumphreyHandler) lock.removeEventListener("click", lock.__HumphreyHandler);
  lock.__HumphreyHandler = (e) => {
    e.stopPropagation();
    st.locked = !st.locked; showLock();
    if (st.locked && (st.goto || st.returning || st.bubbleUntil)) { hush(); st.goto = null; st.returning = true; }
  };
  lock.addEventListener("click", lock.__HumphreyHandler);
  let dock = doc.querySelector(".Humphrey-dock");
  if (!dock) {
    dock = doc.createElement("div"); dock.className = "Humphrey-dock";
    dock.innerHTML = "<span>Humphrey</span>";
    doc.body.appendChild(dock);
  }
  win.__HumphreyMsgs = __MSGS__;
  const loopId = (win.__whaleLoopId || 0) + 1;
  win.__whaleLoopId = loopId;
  const reduce = win.matchMedia && win.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const TOP_LIMIT = 100, PAD = 4, DASH = 340;   // DASH = speed (px/s) when swimming to a card
  let last = null;

  // whichever element actually scrolls (Streamlit scrolls an inner container, not the window)
  function scroller() {
    const c = [doc.querySelector('[data-testid="stMain"]'),
               doc.querySelector('[data-testid="stAppViewContainer"]'), doc.scrollingElement];
    for (const e of c) if (e && e.scrollTop > 0) return e;
    for (const e of c) if (e && e.scrollHeight > e.clientHeight + 1) return e;
    return doc.scrollingElement;
  }

  // speech bubble (one, shared)
  let bubble = doc.querySelector(".Humphrey-bubble");
  if (!bubble) { bubble = doc.createElement("div"); bubble.className = "Humphrey-bubble"; doc.body.appendChild(bubble); }
  function say(text) {
    bubble.innerHTML = "";
    const name = doc.createElement("b"); name.textContent = "Humphrey: ";
    bubble.appendChild(name); bubble.appendChild(doc.createTextNode(text));
    bubble.classList.add("show");
  }
  function hush() { bubble.classList.remove("show"); st.bubbleUntil = 0; st.greeting = false; }
  function unhighlight() {
    doc.querySelectorAll(".Humphrey-highlight").forEach((n) => n.classList.remove("Humphrey-highlight"));
  }

  // clicking a card sends Humphrey to it (one listener, always calls the latest handler)
  win.__HumphreyOnClick = function (e) {
    if (e.target.closest && e.target.closest(".whale-swim, .Humphrey-dock, .Humphrey-lock")) return;
    const card = e.target.closest && e.target.closest('[class*="st-key-card_"]');
    if (card) win.__HumphreyVisit(card);
  };
  // the map lives in its own frame, so the page never sees clicks inside it; instead we notice
  // the page losing focus to that frame and treat it as a click on the map card
  if (win.__HumphreyBlurHandler) win.removeEventListener("blur", win.__HumphreyBlurHandler);
  win.__HumphreyBlurHandler = () => setTimeout(() => {
    const a = doc.activeElement;
    if (!a || a.tagName !== "IFRAME") return;
    const card = a.closest('[class*="st-key-card_map"]');
    if (card) win.__HumphreyVisit(card);
  }, 0);
  win.addEventListener("blur", win.__HumphreyBlurHandler);

  win.__HumphreyVisit = function (card) {
    const m = card.className.match(/st-key-card_([A-Za-z0-9_-]+)/);
    if (!m) return;
    unhighlight(); card.classList.add("Humphrey-highlight");   // glow around the clicked card
    st.highlightUntil = win.performance.now() + 9000;
    if (!(m[1] in win.__HumphreyMsgs)) return;
    if (st.locked || reduce) {                    // locked: he stays home and tells you from there
      hush(); say(win.__HumphreyMsgs[m[1]]); st.bubbleUntil = win.performance.now() + 7000;
      return;
    }
    st.running = false; st.returning = false; st.goto = m[1]; hush();
  };
  // re-attach on every reload: a listener left over from an old copy of this script stops firing
  if (win.__HumphreyClickHandler) doc.removeEventListener("click", win.__HumphreyClickHandler, true);
  win.__HumphreyClickHandler = (e) => win.__HumphreyOnClick(e);
  doc.addEventListener("click", win.__HumphreyClickHandler, true);

  function wireDock(handler) {
    if (dock.dataset.wired === String(loopId)) return;
    if (dock.__HumphreyHandler) dock.removeEventListener("click", dock.__HumphreyHandler);
    dock.__HumphreyHandler = handler; dock.addEventListener("click", handler);
    dock.dataset.wired = String(loopId);
  }

  function el() {
    const w = doc.querySelector(".whale-swim");
    if (w && w.dataset.wired !== String(loopId)) {
      if (w.__HumphreyHandler) w.removeEventListener("click", w.__HumphreyHandler);
      w.__HumphreyHandler = () => {           // click Humphrey: say hello at home, or head home if he's out
        const busy = st.goto || st.bubbleUntil || st.returning;
        hush(); st.goto = null; st.running = false;
        if (busy) { st.returning = true; }
        else { say(GREETING); st.bubbleUntil = win.performance.now() + 6000; }
      };
      w.addEventListener("click", w.__HumphreyHandler);
      w.dataset.wired = String(loopId);
    }
    if (w && w.__HumphreyHandler) wireDock(w.__HumphreyHandler);
    return w;
  }

  function moveTo(tx, ty, dt) {               // glide toward a point; true once there
    const dx = tx - st.x, dy = ty - st.py, dist = Math.hypot(dx, dy);
    const step = Math.max(DASH, dist * 1.6) * dt;   // far away: swim faster
    if (Math.abs(dx) > 2) st.vx = dx < 0 ? -Math.abs(st.vx) : Math.abs(st.vx);   // face the way he swims
    if (dist <= step || dist < 2) { st.x = tx; st.py = ty; return true; }
    st.x += dx / dist * step; st.py += dy / dist * step; return false;
  }

  function frame(t) {
    if (win.__whaleLoopId !== loopId) return;            // a newer copy of this script took over
    const w = el();
    if (w) {
      const sc = scroller(), scrollY = sc ? sc.scrollTop : 0;
      const pageH = Math.max(sc ? sc.scrollHeight : 0, win.innerHeight);
      const bw = w.offsetWidth, bh = w.offsetHeight;
      const maxX = win.innerWidth - bw - PAD, maxPY = pageH - bh - PAD;
      const hm = home(bw, bh, scrollY), homeX = hm.x, homeY = hm.y;
      if (st.x === null) { st.x = homeX; st.py = homeY; }
      const dt = last === null ? 0 : Math.min((t - last) / 1000, 0.05);
      if (!win.__HumphreyGreeted && last !== null) {         // only when the page first loads
        win.__HumphreyGreeted = true;
        say(GREETING); st.bubbleUntil = t + 8000;
      }

      if (st.goto) {                                       // 1) swimming to a clicked card
        const card = doc.querySelector(".st-key-card_" + st.goto);
        if (!card) { st.goto = null; st.returning = true; }
        else {
          const r = card.getBoundingClientRect();
          let tx = r.right - bw * 0.55;                    // perch on the card's top-right corner...
          if (tx > maxX) tx = r.left - bw * 0.45;          // ...or top-left if there's no room
          let ty = r.top + scrollY - bh * 0.55;
          tx = Math.min(Math.max(tx, PAD), maxX);
          ty = Math.min(Math.max(ty, TOP_LIMIT), Math.max(TOP_LIMIT, maxPY));
          if (moveTo(tx, ty, dt)) {
            say(win.__HumphreyMsgs[st.goto] || "");
            st.goto = null; st.bubbleUntil = t + 7000;
          }
        }
      } else if (st.bubbleUntil) {                         // 2) talking about the card
        if (t > st.bubbleUntil) { hush(); st.returning = true; }
      } else if (st.returning) {                           // 3) done: swim back home
        if (moveTo(homeX, homeY, dt)) { st.returning = false; st.vx = -Math.abs(st.vx); }
      } else {                                             // 5) resting at home
        st.x = homeX; st.py = homeY;
      }
      if (st.highlightUntil && t > st.highlightUntil && !st.goto && !st.bubbleUntil) {
        unhighlight(); st.highlightUntil = 0;               // glow fades once Humphrey is done
      }
      st.x = Math.min(Math.max(st.x, PAD), Math.max(PAD, maxX));
      st.py = Math.min(Math.max(st.py, TOP_LIMIT), Math.max(TOP_LIMIT, maxPY));
      const y = st.py - scrollY;                           // page position -> screen position
      dock.style.left = (homeX - DOCK_PAD) + "px";
      dock.style.top = (homeY - DOCK_PAD - scrollY) + "px";
      dock.style.width = (bw + DOCK_PAD * 2) + "px";
      dock.style.height = (bh + DOCK_PAD * 2 + 14) + "px";
      lock.style.left = (homeX - DOCK_PAD + bw + DOCK_PAD * 2 - 14) + "px";
      lock.style.top = (homeY - DOCK_PAD - scrollY - 9) + "px";
      dock.classList.toggle("empty", !(Math.abs(st.x - homeX) < 3 && Math.abs(st.py - homeY) < 3));
      w.style.right = "auto"; w.style.left = st.x + "px"; w.style.top = y + "px";
      w.style.transform = st.vx < 0 ? "scaleX(1)" : "scaleX(-1)";   // the GIF faces left

      if (bubble.classList.contains("show")) {            // bubble above Humphrey, or beside him near the top
        const bwid = bubble.offsetWidth, bhgt = bubble.offsetHeight;
        let lx = st.x + bw / 2 - bwid / 2, ly = y - bhgt - 8;
        const atHome = hm.under && Math.abs(st.x - homeX) < 3 && Math.abs(st.py - homeY) < 3;
        if (atHome) {
          ly = y + bh + 8;                                 // below him, so it doesn't cover the table
        } else if (ly < 110) {                                    // would cover the header: put it at his side
          ly = y + bh / 2 - bhgt / 2;
          lx = st.x - bwid - 10;
          if (lx < 8) lx = st.x + bw + 10;
        }
        lx = Math.min(Math.max(lx, 8), win.innerWidth - bwid - 8);
        bubble.style.left = lx + "px"; bubble.style.top = ly + "px";
      }
    }
    last = t;
    win.requestAnimationFrame(frame);
  }
  win.requestAnimationFrame(frame);
})();
</script>
"""

# ── Trim the table column menu to: sort, pin, hide ───────────────────────────
# Streamlit has no option for this, so a tiny script hides the other menu rows
# (column name/copy row, Format, Autosize) whenever a column menu opens.
import streamlit.components.v1 as components  # noqa: E402

components.html(components_whale.replace("__MSGS__", Humphrey_json), height=0)

components.html("""
<script>
(function () {
  const doc = window.parent.document;
  if (window.parent.__menuTrimObserver) window.parent.__menuTrimObserver.disconnect();
  const KEEP = /Sort ascending|Sort descending|Pin column|Unpin column|Hide column/;
  const DROP = /Format|Autosize/;
  function prune(node) {
    for (const child of Array.from(node.children)) {
      const text = child.textContent || "";
      if (!KEEP.test(text)) child.style.display = "none";
      else if (DROP.test(text)) prune(child);
    }
  }
  function lca(a, b) {
    const seen = new Set();
    for (let n = a; n; n = n.parentElement) seen.add(n);
    for (let n = b; n; n = n.parentElement) if (seen.has(n)) return n;
    return null;
  }
  function findIn(root, label) {
    const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) if (n.nodeValue.trim() === label) return n.parentElement;
    return null;
  }
  function trim(root) {
    const a = findIn(root, "Sort ascending");
    const b = findIn(root, "Hide column") || findIn(root, "Pin column") || findIn(root, "Unpin column");
    if (!a || !b) return;
    const menu = lca(a, b);
    if (menu) prune(menu);
  }
  const observer = new MutationObserver((records) => {
    for (const r of records) {
      for (const node of r.addedNodes) {
        if (node.nodeType === 1 && (node.textContent || "").includes("Sort ascending")) trim(node);
      }
    }
  });
  observer.observe(doc.body, { childList: true, subtree: true });
  window.parent.__menuTrimObserver = observer;
})();
</script>
""", height=0)