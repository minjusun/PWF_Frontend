"""
Turn a sightings GeoJSON export into the small snapshot the Streamlit map uses.

    python make_snapshot.py points.geojson

To refresh the data with the latest sightings: run map_api.py locally, open
http://localhost:<PORT>/api/points.geojson, save it, and run this script on it.
Writes map/points_snapshot.json.gz (only the fields the map uses, coordinates
rounded to ~1 m, gzipped, so it stays small enough for GitHub and Streamlit).
"""
import gzip
import json
import sys
from pathlib import Path

KEEP = [
    "species_code", "species_name", "sighting_date_and_time_utc", "date",
    "animals_total", "boat_name", "general_notes",
]

src = Path(sys.argv[1] if len(sys.argv) > 1 else "points.geojson")
out = Path(__file__).resolve().parent / "map" / "points_snapshot.json.gz"

data = json.loads(src.read_text(encoding="utf-8"))
features = []
for f in data["features"]:
    geom = f.get("geometry") or {}
    if geom.get("type") != "Point":
        continue
    props = f.get("properties") or {}
    extra = props.get("variable_data") or {}  # some exports nest fields here
    picked = {}
    for k in KEEP:
        v = props.get(k)
        if v is None:
            v = extra.get(k)
        if v is not None:
            picked[k] = v
    features.append({
        "type": "Feature",
        "properties": picked,
        "geometry": {"type": "Point", "coordinates": [round(c, 5) for c in geom["coordinates"][:2]]},
    })

snapshot = {"type": "FeatureCollection", "features": features}
with gzip.open(out, "wt", encoding="utf-8") as fh:
    json.dump(snapshot, fh, separators=(",", ":"), ensure_ascii=False)

print(f"{len(features)} sightings -> {out} ({out.stat().st_size / 1e6:.1f} MB)")
