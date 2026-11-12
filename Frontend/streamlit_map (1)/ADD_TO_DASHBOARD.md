# Adding the map to the Streamlit dashboard

This adds a **Map** page to the existing dashboard. It has the same map and features as the
`map_api.py` version, but uses a **snapshot** of the sightings data instead of live Supabase data.

## 1. Copy the files into the dashboard repo

```
your-dashboard-repo/
├── app.py                     ← your existing dashboard file (any name)
├── pages/
│   └── Map.py                 ← NEW
├── map/                       ← NEW
│   ├── webmap.html
│   ├── App.js
│   ├── species_description.csv
│   ├── points_snapshot.json.gz
│   └── imgs/                  ← optional: species photos named <SPECIES_CODE>.png
└── make_snapshot.py           ← NEW (only used to refresh the data)
```

If the dashboard already uses a `pages/` folder, just add `Map.py` to it. If it uses
`st.navigation`, add `st.Page("pages/Map.py", title="Map", icon="🐋")` to your page list.

No new packages are needed in `requirements.txt`.

## 2. Add the Mapbox token

In Streamlit Community Cloud: open the app → **Settings → Secrets** and add:

```toml
MAPBOX_TOKEN = "pk.your_public_mapbox_token"
```

For running locally, put the same line in `.streamlit/secrets.toml` (don't commit it).

If the token has URL restrictions in Mapbox, add your `*.streamlit.app` address.

## 3. Push

Commit and push. Streamlit Cloud redeploys automatically and the **Map** page shows up in the sidebar.

## Updating the data

1. Run `map_api.py` locally and open `http://localhost:<PORT>/api/points.geojson`.
2. Save it as `points.geojson`.
3. Run `python make_snapshot.py points.geojson`. This rewrites `map/points_snapshot.json.gz`.
4. Commit and push.

## Notes

- The monthly map-load cap from `map_api.py` does not apply here. Each visit to the Map page
  is one Mapbox map load, so set a usage alert in your Mapbox account.
- Change `MAP_HEIGHT` in `pages/Map.py` if the map is too tall or short for your screen.
- `App.js` still works with `map_api.py` too: it only uses the snapshot when it's loaded by
  the Streamlit page.
