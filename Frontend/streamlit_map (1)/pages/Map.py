"""
Sightings map page for the Streamlit dashboard.

Embeds the same map (map/webmap.html + map/App.js) with a data snapshot
(map/points_snapshot.json.gz) instead of the live map_api.py server.
Needs MAPBOX_TOKEN in Streamlit secrets.
"""
import base64
import gzip
import json
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Sightings Map", page_icon="🐋", layout="wide")

MAP_DIR = Path(__file__).resolve().parent.parent / "map"
MAP_HEIGHT = 820  # px; change to fit your screen


def safe_json(obj) -> str:
    """JSON that can sit inside a <script> tag (user notes can't close the tag)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


@st.cache_data(show_spinner="Loading map…")
def build_map_html(token: str) -> str:
    html = (MAP_DIR / "webmap.html").read_text(encoding="utf-8")
    app_js = (MAP_DIR / "App.js").read_text(encoding="utf-8")
    csv_text = (MAP_DIR / "species_description.csv").read_text(encoding="utf-8-sig")

    with gzip.open(MAP_DIR / "points_snapshot.json.gz", "rt", encoding="utf-8") as fh:
        points = json.load(fh)

    # Optional species photos: map/imgs/<SPECIES_CODE>.png
    images = {}
    img_dir = MAP_DIR / "imgs"
    if img_dir.is_dir():
        for png in img_dir.glob("*.png"):
            images[png.stem] = "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()

    embed = {"token": token, "points": points, "csv": csv_text, "images": images}
    app_js = app_js.replace("</script", "<\\/script")
    scripts = (
        "<script>window.EMBED = " + safe_json(embed) + ";</script>\n"
        "<script>" + app_js + "</script>"
    )

    html, n = re.subn(r'<script src="App\.js[^"]*"></script>', lambda _: scripts, html)
    if n != 1:
        raise RuntimeError('Could not find <script src="App.js"> in webmap.html')
    return html


try:
    token = st.secrets["MAPBOX_TOKEN"]
except Exception:
    st.error("Add MAPBOX_TOKEN to your Streamlit secrets to show the map.")
    st.stop()

# Less padding so the map uses more of the page.
st.markdown(
    "<style>.block-container{padding-top:1rem;padding-bottom:0;max-width:100%;}</style>",
    unsafe_allow_html=True,
)

st.caption("Showing a snapshot of sightings data (not live).")
components.html(build_map_html(token), height=MAP_HEIGHT, scrolling=False)
