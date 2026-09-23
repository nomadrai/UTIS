# UHI Intelligence Platform — Nagpur

A geospatial intelligence platform that analyzes multi-temporal satellite
imagery (Google Earth Engine) to study **Urban Heat Island (UHI)** patterns in
Nagpur, and estimates how land-cover changes (vegetation, built-up area) could
shift surface temperature distribution.

- **What this project is / is not:** [PROJECT.md](PROJECT.md)
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

# 4. Sanity-check that GEE works (pulls a tiny image collection count)
python -m backend.etl.gee_pulls.pull_landsat_lst --sanity-check

# 5. Start the API server
uvicorn backend.app.main:app --reload
#    Swagger UI: http://localhost:8000/docs

# 6. Frontend — open in a browser (or serve statically):
frontend/index.html
```

## Project structure

```
├── PROJECT.md              # Problem statement, scope, stack & data sources
├── PLAN.md                 # Living session log + task board
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
