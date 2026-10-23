"""
Region boundaries for the dashboard.

Uses Natural Earth's states/provinces layer (public domain). On first run it is
downloaded once (~40 MB), slimmed down, and saved next to this file as
regions_slim.json, which loads quickly afterwards. Sightings at sea are assigned
to the nearest state/province within MAX_DIST_DEG (e.g. waters off Maui → Hawaii).
"""
import json
import os
import urllib.request

import numpy as np

NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
          "ne_10m_admin_1_states_provinces.geojson")
HERE = os.path.dirname(os.path.abspath(__file__))
RAW_PATH = os.path.join(HERE, "ne_10m_admin_1_states_provinces.geojson")
SLIM_PATH = os.path.join(HERE, "regions_slim.json")

MAX_PTS = 300        # max vertices kept per polygon ring (keeps the map light)
MAX_DIST_DEG = 2.0   # sightings further than this from any coast are "Open ocean"
OPEN_OCEAN = "Open ocean"


def _decimate(ring):
    if len(ring) <= MAX_PTS:
        return ring
    step = int(np.ceil(len(ring) / MAX_PTS))
    out = ring[::step]
    if out[-1] != ring[-1]:
        out.append(ring[-1])
    return out


def build_slim(raw_path=RAW_PATH, out_path=SLIM_PATH):
    with open(raw_path, encoding="utf-8") as f:
        gj = json.load(f)
    merged = {}
    for feat in gj["features"]:
        g, p = feat.get("geometry"), feat.get("properties", {})
        if not g or g["type"] not in ("Polygon", "MultiPolygon"):
            continue
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        name = p.get("name") or p.get("name_en") or p.get("gn_name") or "Unknown"
        admin = p.get("admin") or ""
        label = f"{name}, {admin}" if admin and admin != name else name
        for poly in polys:
            outer = poly[0]
            if len(outer) >= 4:
                merged.setdefault(label, []).append([[round(x, 4), round(y, 4)] for x, y in _decimate(outer)])
    regions = []
    for label, rings in merged.items():
        pts = np.array([pt for r in rings for pt in r])
        regions.append({"name": label, "rings": rings,
                        "bbox": [float(pts[:, 0].min()), float(pts[:, 1].min()),
                                 float(pts[:, 0].max()), float(pts[:, 1].max())]})
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(regions, f)
    return regions


def load_regions():
    """Returns the list of regions, downloading and slimming the source once."""
    if os.path.exists(SLIM_PATH):
        with open(SLIM_PATH, encoding="utf-8") as f:
            return json.load(f)
    if not os.path.exists(RAW_PATH):
        urllib.request.urlretrieve(NE_URL, RAW_PATH)
    regions = build_slim()
    try:
        os.remove(RAW_PATH)  # the slim file is all we need
    except OSError:
        pass
    return regions


def grid_regions(lat, lon, size=1.0):
    """Fallback when boundaries can't be downloaded: 1° grid squares."""
    cells = {(np.floor(a / size) * size, np.floor(b / size) * size) for a, b in zip(lat, lon)}
    out = []
    for la, lo in cells:
        ring = [[lo, la], [lo + size, la], [lo + size, la + size], [lo, la + size], [lo, la]]
        out.append({"name": f"{la:+.0f}°, {lo:+.0f}°", "rings": [ring], "bbox": [lo, la, lo + size, la + size]})
    return out


# ── Point → region assignment (vectorised numpy) ─────────────────────────────
def _inside(px, py, ring):
    x, y = ring[:, 0], ring[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    crosses = (y[None, :] > py[:, None]) != (y2[None, :] > py[:, None])
    xint = (x2 - x)[None, :] * (py[:, None] - y[None, :]) / ((y2 - y)[None, :] + 1e-12) + x[None, :]
    return (crosses & (px[:, None] < xint)).sum(axis=1) % 2 == 1


def _edge_distance(px, py, ring):
    a, b = ring, np.roll(ring, -1, axis=0)
    ab = b - a
    apx, apy = px[:, None] - a[None, :, 0], py[:, None] - a[None, :, 1]
    t = np.clip((apx * ab[:, 0] + apy * ab[:, 1]) / ((ab ** 2).sum(axis=1) + 1e-12), 0, 1)
    dx = (apx - t * ab[:, 0]) * np.cos(np.radians(py))[:, None]
    dy = apy - t * ab[:, 1]
    return np.sqrt(dx * dx + dy * dy).min(axis=1)


def assign(lat, lon, regions, max_dist=MAX_DIST_DEG):
    """Name of the containing (or nearest, within max_dist) region for each point."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    best_d = np.full(len(lat), np.inf)
    best_i = np.full(len(lat), -1)
    for i, r in enumerate(regions):
        x0, y0, x1, y1 = r["bbox"]
        idx = np.where((lon >= x0 - max_dist) & (lon <= x1 + max_dist) &
                       (lat >= y0 - max_dist) & (lat <= y1 + max_dist))[0]
        if not len(idx):
            continue
        px, py = lon[idx], lat[idx]
        d = np.full(len(idx), np.inf)
        for ring in r["rings"]:
            ring = np.asarray(ring, float)
            dist = np.where(_inside(px, py, ring), 0.0, _edge_distance(px, py, ring))
            d = np.minimum(d, dist)
        better = d < best_d[idx]
        best_d[idx[better]] = d[better]
        best_i[idx[better]] = i
    names = np.array([r["name"] for r in regions] + [OPEN_OCEAN], dtype=object)
    best_i[(best_i < 0) | (best_d > max_dist)] = len(regions)
    return names[best_i]


def to_geojson(regions, counts, selected=None):
    """FeatureCollection of the regions that have sightings, with counts for styling."""
    feats = []
    for r in regions:
        n = int(counts.get(r["name"], 0))
        if n == 0:
            continue
        feats.append({
            "type": "Feature",
            "properties": {"region": r["name"], "sightings": n, "selected": r["name"] == selected},
            "geometry": {"type": "MultiPolygon", "coordinates": [[ring] for ring in r["rings"]]},
        })
    return {"type": "FeatureCollection", "features": feats}