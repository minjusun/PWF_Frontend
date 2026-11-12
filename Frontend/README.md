# Whale & Dolphin Sightings Map

An interactive Mapbox map of live whale and dolphin sightings from the Whale & Dolphin Tracker. The map runs on your own computer: a small Python server (`map_api.py`) pulls live sightings from Supabase, cleans them, and serves them to the map in your browser.

> **You will need keys that are not in this repo.** Ask the project owner for the `.env` file (or the values to put in it) before you start.

## What's in the repo

| File | What it does |
|---|---|
| `map_api.py` | Python server. Serves the web page, the live sightings (`/api/points.geojson`) and the Mapbox token (`/api/map-load`, capped by `MAP_LOAD_LIMIT`). |
| `webmap.html` | The map page. |
| `App.js` | All the map logic (layers, timeline, species list, globe spin). |
| `species_description.csv` | Species names, taxonomy and descriptions shown in the sidebar. |
| `style.json` | Map style. |
| `handle_data.ipynb` | Notebook used to explore and prepare the data. Not needed to run the map. |

## Requirements

- **Python 3.10 or newer**. Check with `python --version` (or `python3 --version` on Mac).
- **Git**. Check with `git --version`.
- An internet connection, which the map needs for the live data and the satellite tiles.

## Setup

### 1. Clone the repo

```bash
git clone <REPO_URL>
cd <REPO_FOLDER>
```

### 2. Create a virtual environment and install the packages

**Mac / Linux**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activate script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.

### 3. Add the keys

Create a file called `.env` in the project folder (next to `map_api.py`) and fill it in with the values from the project owner:

```
SUPABASE_URL=<from project owner>
SUPABASE_KEY=<from project owner>
MAPBOX_TOKEN=<from project owner>
```

<!-- Owner: make sure these names match the ones map_api.py actually reads. -->

**Never commit `.env` to GitHub.** It is already listed in `.gitignore`.

### 4. Run the map

```bash
python map_api.py
```

Leave this terminal window open. Then open the address it prints in your browser (for example **http://localhost:5000**). The map should load with the live sightings.

To stop the server, press `Ctrl + C` in the terminal.

### Running it again later

You don't need to reinstall anything. Open a terminal in the project folder, activate the virtual environment (step 2, the `activate` line only) and run `python map_api.py`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Use `python3` (Mac) or reinstall Python and tick **Add Python to PATH** (Windows). |
| `ModuleNotFoundError` | The virtual environment isn't active, or step 2 was skipped. Activate it and run `pip install -r requirements.txt`. |
| "Could not reach the map server" | `map_api.py` isn't running, or you opened `webmap.html` by double-clicking it. Always use the `localhost` address from the terminal. |
| "Could not load sightings" | Check `SUPABASE_URL` and `SUPABASE_KEY` in `.env`, and your internet connection. |
| "The map is unavailable right now" | The monthly Mapbox load limit was reached, or `MAPBOX_TOKEN` is missing or wrong. Contact the project owner. |
| Map is blank or grey | The Mapbox token may have URL restrictions that don't include `localhost`. Contact the project owner. |
| Port already in use | Another copy is still running. Close it, or stop whatever is using that port. |

## Before a presentation

Do a full test run on the presenting computer at least a day ahead, on the same network you'll present on. Some venue or school Wi-Fi networks block outside connections.
