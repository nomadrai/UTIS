# UHI Intelligence Platform — Nagpur

A geospatial intelligence platform that analyzes multi-temporal satellite
imagery (Google Earth Engine) to study **Urban Heat Island (UHI)** patterns in
Nagpur, and estimates how land-cover changes (vegetation, built-up area) could
shift surface temperature distribution.

**Live features:** 4 satellite layers (LST / NDVI / NDBI / land cover), 114-ward
choropleth, multi-year comparison, persistent hotspot detection, scenario
what-if sliders with a fully explainable fitted model.

**Phase 2 (planned):** what-if map (city recolored by predicted per-ward ΔLST),
AI chat assistant about the city's temperature change (Groq / Google AI /
OpenRouter fallback — grounded in this platform's own data, never inventing
numbers), trend charts, population-weighted exposure ranking, ΔLST layers,
report export. See the task board in [PLAN.md](PLAN.md).

- **What this project is / is not:** [PROJECT.md](PROJECT.md)
- **How the analysis works — methodology, fitted model, caveats:** [docs/METHODOLOGY.md](docs/METHODOLOGY.md)
- **Session log & task board:** [PLAN.md](PLAN.md)

## Stack

Python · Google Earth Engine (Python API) · FastAPI · Leaflet · OpenStreetMap.
Details and rationale in [PROJECT.md](PROJECT.md#3-tech-stack--why).

## Prerequisites

- **Python 3.10+** (3.11 recommended)
- **Google Earth Engine access** (free noncommercial registration):
  1. Sign up at [code.earthengine.google.com/register](https://code.earthengine.google.com/register) with a Google account.
  2. Register a **Google Cloud project** for Earth Engine use (choose
     *noncommercial* if this is research/personal). Google walks you through
     creating or selecting a Cloud project during registration.
  3. Note the **project ID** — you'll need it for authentication below.
- Node.js is **not required** for v1 (frontend is a static Leaflet app).
- Optional: a Google Maps/Mapbox token if you want a fancier basemap than OSM.

## Authenticate with Earth Engine (one-time)

```bash
earthengine authenticate
```

This opens a browser sign-in flow and stores credentials locally.

## Install & run

```bash
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your GEE project ID
cp backend/.env.example backend/.env
#    then edit backend/.env and set GEE_PROJECT_ID=<your project id>
#    (optional, Phase 2 AI chat: also set GROQ_API_KEY / GOOGLE_AI_API_KEY /
#    OPENROUTER_API_KEY there — any one enables the chat assistant)

# 4. Sanity-check that GEE works (pulls a tiny image collection count)
python -m backend.etl.gee_pulls.pull_landsat_lst --sanity-check

# 5. Start the API server (it serves the frontend too)
uvicorn backend.app.main:app --reload
#    App:     http://127.0.0.1:8000   (use 127.0.0.1 — some systems resolve
#    Swagger: http://127.0.0.1:8000/docs   localhost to IPv6 first)
```

## Data caches & verification

The API serves per-ward statistics from JSON caches in `data/processed/`.
Missing years compute on demand via GEE on first request; regenerate
deliberately with `--refresh`:

```bash
python -m backend.etl.gee_pulls.pull_landsat_lst --zonal-stats --years 2019 2020 2021 2022 2023 2024 2025
python -m backend.etl.gee_pulls.pull_s2_indices   --zonal-stats --years 2020 2021 2022 2023 2024 2025
python -m backend.etl.gee_pulls.pull_worldcover   --zonal-stats
```

Full end-to-end verification (boots the server in-process, checks every
endpoint + a real tile per layer + a headless-browser render; needs GEE
auth):

```bash
python -m scripts.smoke_api
```

How every published number is computed — compositing, masking, the
scenario fit, and all caveats: [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Project structure

```
├── PROJECT.md              # Problem statement, scope, stack & data sources
├── PLAN.md                 # Living session log + task board
├── docs/
│   └── METHODOLOGY.md      # How every number is computed + caveats
├── backend/
│   ├── app/                # API layer (FastAPI) — routes, services
│   ├── etl/
│   │   ├── gee_common.py   # Shared GEE helpers — AOI clip policy lives HERE
│   │   ├── gee_pulls/      # GEE data-pull scripts (Landsat/Sentinel/WorldCover)
│   │   └── analysis/       # LST/NDVI/NDBI stats, hotspots, scenario logic
│   └── config/             # Static AOI polygon (nagpur_city.geojson), settings
├── frontend/               # Static Leaflet web app (index.html, src/)
├── data/
│   ├── raw/                # As-pulled GEE exports (GeoTIFF, JSON)
│   └── processed/          # Cleaned/computed outputs the API serves
└── docs/                   # Methodology notes, deeper documentation
```

More detail on what each piece does: [PROJECT.md](PROJECT.md).
