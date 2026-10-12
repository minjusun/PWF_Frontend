"""
Whale & Dolphin Tracker Dashboard — Streamlit dashboard
Run:  streamlit run app.py
"""
import html

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
.block-container {padding: 3.6rem 1.4rem 1.5rem; max-width: 100%;}
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


def style(fig, h=280, legend=False):
    fig.update_layout(height=h, margin=dict(l=4, r=4, t=6, b=4), title_text="",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="-apple-system, Segoe UI, Inter, sans-serif", size=11, color="#12303B"),
                      showlegend=legend, legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text=""),
                      hoverlabel=dict(bgcolor="white"))
    fig.update_xaxes(showgrid=False, title_text="", linecolor="#DCE7EA")
    fig.update_yaxes(gridcolor="#EAF1F3", title_text="", zeroline=False)
    return fig


def sparkline(series, color=TEAL):
    fig = go.Figure(go.Scatter(x=series.index, y=series.values, mode="lines", fill="tozeroy",
                               line=dict(color=color, width=2), fillcolor="rgba(79,176,165,0.18)",
                               hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra></extra>"))
    fig.update_layout(height=40, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, rangemode="tozero")
    return fig


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
h1, h2, h3, h4 = st.columns([3.4, 1.3, 2.4, 1.7], vertical_alignment="bottom")
with h1:
    st.title("Whale & Dolphin Tracker Dashboard")
    scope_slot = st.empty()
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

kpi_row = st.container()
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
        map_state = st_folium(m, key=map_key, height=420, use_container_width=True,
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

period_txt = "all time" if window == "All time" else window.lower()
source_txt = "Live data" if db_url() else "Mock data"
scope_slot.markdown(f"<p class='scope'>{html.escape(short_name)} &middot; {period_txt} &middot; {source_txt}</p>",
                    unsafe_allow_html=True)

# ── KPI strip ────────────────────────────────────────────────────────────────
cur = d.kpis(s_scope, t_scope)
old = d.kpis(*d.slice_data(s_reg, t, *prev, tracks_follow_sightings=follow_r)) if prev else None
ms = d.monthly_series(s_scope, t_scope, start, end)


def delta(k):
    if not old or old[k] == 0:
        return None
    return f"{(cur[k] - old[k]) / old[k]:+.0%} vs prev."


with kpi_row:
    cols = st.columns(5)
    for col, (k, label) in zip(cols, [("users", "Active users"), ("trips", "Trips"), ("sightings", "Sightings"),
                                      ("species", "Distinct species"), ("animals", "Animals counted")]):
        with col:
            with card(f"kpi_{k}"):
                st.metric(label, f"{cur[k]:,}", delta(k))
                st.plotly_chart(sparkline(ms[k]), config=PLOT_CFG, key=f"spark_{k}")

# ── Left of map: activity + contributors ─────────────────────────────────────
with left:
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
        st.plotly_chart(style(fig, h=205, legend=True), config=PLOT_CFG, key="activity_chart")

    with card("contrib", "Top 5 contributors"):
        view = GLOBAL
        if not is_global:
            view = st.segmented_control("Contributor scope", [short_name, GLOBAL], default=short_name,
                                        key="contrib_scope", label_visibility="collapsed") or short_name
        tc = d.top_contributors(s_period, t_period) if view == GLOBAL else d.top_contributors(s_scope, t_scope)
        st.dataframe(tc[["Contributor", "Sightings", "Trips", "Species"]], hide_index=True, height=212,
                     column_config={"Sightings": st.column_config.ProgressColumn(
                         "Sightings", format="%d", max_value=int(max(1, tc["Sightings"].max() if len(tc) else 1)))})

# ── Right of map: region snapshot, top species, species list ─────────────────
with right:
    with card("snap", "Global view" if is_global else f"{short_name} at a glance"):
        rc = region_counts.drop(R.OPEN_OCEAN, errors="ignore")
        if is_global:
            top_r = rc.index[0].split(",")[0] if len(rc) else "—"
            snapshot([("Regions with sightings", f"{len(rc):,}"),
                      ("Top region", top_r),
                      ("Top region's share", f"{rc.iloc[0] / max(1, len(s_period)):.0%}" if len(rc) else "—"),
                      ("Contributors", f"{s_period['creator'].nunique():,}")])
        else:
            here = int(region_counts.get(region_sel, 0))
            rank = (list(rc.index).index(region_sel) + 1) if region_sel in rc.index else None
            first = s_hist["ts"].min()
            snapshot([("Share of global sightings", f"{here / max(1, len(s_period)):.0%}"),
                      ("Global rank", f"#{rank} of {len(rc)}" if rank else "—"),
                      ("Top species here", s_scope["species_name"].mode().iat[0] if len(s_scope) else "—"),
                      ("First sighting", first.strftime("%b %Y") if pd.notna(first) else "—")])

    with card("topspecies", "Top 5 species"):
        ts5 = d.top_species(s_scope)
        if ts5.empty:
            st.caption("No sightings here for this period.")
        else:
            fig = px.bar(ts5.iloc[::-1], x="Sightings", y="Species", orientation="h", text="Sightings",
                         color_discrete_sequence=[TEAL])
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_xaxes(range=[0, ts5["Sightings"].max() * 1.2])
            st.plotly_chart(style(fig, h=160), config=PLOT_CFG, key="top_species_bar")

    with card("species_list", f"Species spotted ({s_scope['species_code'].nunique()})"):
        sp_tab = d.species_table(s_scope, start, end)
        st.dataframe(sp_tab, hide_index=True, height=180, column_config={
            "Sightings": st.column_config.ProgressColumn(
                format="%d", max_value=int(max(1, sp_tab["Sightings"].max() if len(sp_tab) else 1))),
            "Trend": st.column_config.AreaChartColumn("Trend (per month)", y_min=0, help="Sightings per month across the selected period"),
            "Last seen": st.column_config.TextColumn("Last seen", width="small"),
        })

# ── Row: when to see each species
sp_rank = s_hist["species_name"].value_counts()
c_best, c_year, c_peak = st.columns([4, 3.6, 2.4])
if sp_rank.empty:
    with c_best:
        st.info("No sightings here yet. Pick another region or widen the filters.")
else:
    data_start, data_end = s_all["ts"].min(), now
    with c_best:
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
            fig.update_yaxes(title_text="Sightings in a typical month", title_font_size=10)
            st.plotly_chart(style(fig, h=210), config=PLOT_CFG, key="season_best")

    with c_year:
        with card("curve", f"{now.year} so far vs past years", "Sightings per month"):
            ty = d.this_year_vs_past(sd, data_start, now)
            fig = go.Figure()
            fig.add_scatter(x=ty["Month"], y=ty["Past average"], name="Past years (average)", mode="lines",
                            line=dict(color=MIST, width=3, dash="dot"),
                            hovertemplate="%{x}: about %{y:.0f}<extra>Past years</extra>")
            fig.add_scatter(x=ty["Month"], y=ty["This year"], name=str(now.year), mode="lines+markers",
                            line=dict(color=DEEP, width=2.5), marker=dict(size=6),
                            hovertemplate="%{x}: %{y:.0f}<extra>" + str(now.year) + "</extra>")
            fig.update_xaxes(categoryorder="array", categoryarray=d.MONTHS)
            st.plotly_chart(style(fig, h=228, legend=True), config=PLOT_CFG, key="season_vs")

    with c_peak:
        with card("shift", "Busiest month each year"):
            st.dataframe(d.peak_month_by_year(sd, data_start, data_end), hide_index=True, height=240,
                         column_config={"Sightings that year": None})

# ── Row: hotspots + encounters
c_hot, c_group, c_calf, c_boat = st.columns([3.2, 2.4, 2.4, 2])
with c_hot:
    if is_global:
        with card("hot", "Busiest region by year"):
            st.dataframe(d.busiest_region_by_year(s_hist), hide_index=True, height=205,
                         column_config={"Year": st.column_config.NumberColumn(format="%d")})
    else:
        with card("hot", f"{short_name} vs. Global"):
            st.dataframe(d.region_rank_by_year(s_hist_all, region_sel), hide_index=True, height=205,
                         column_config={"Year": st.column_config.NumberColumn(format="%d"),
                                        "Share of global": st.column_config.ProgressColumn(
                                            format="percent", min_value=0, max_value=1)})

with c_group:
    with card("group", "Typical group size", "Median animals per sighting"):
        grp = (s_scope.groupby("species_name")["animals_total"].median().dropna().sort_values().tail(8)
               .rename_axis("Species").reset_index(name="Median"))
        if grp.empty:
            st.caption("No group counts recorded.")
        else:
            fig = px.bar(grp, x="Median", y="Species", orientation="h", color_discrete_sequence=[SEAFOAM])
            st.plotly_chart(style(fig, h=200), config=PLOT_CFG, key="group_size")

with c_calf:
    with card("calf", "Calves by month", "Calves counted in a typical month"):
        calf_counts = (s_hist.groupby("species_name")["animals_calf"].sum()
                       .sort_values(ascending=False))
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
            fig.update_xaxes(tickangle=0, tickfont_size=9)
            st.plotly_chart(style(fig, h=170), config=PLOT_CFG, key="calf_chart")

with c_boat:
    with card("boats", "Most active boats"):
        boats = s_scope["boat_name"].value_counts().head(6).rename_axis("Boat").reset_index(name="Sightings")
        if boats.empty:
            st.caption("No boat names recorded.")
        else:
            fig = px.bar(boats.iloc[::-1], x="Sightings", y="Boat", orientation="h", color_discrete_sequence=[SAND])
            st.plotly_chart(style(fig, h=215), config=PLOT_CFG, key="boats_chart")


import streamlit.components.v1 as components  # noqa: E402

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