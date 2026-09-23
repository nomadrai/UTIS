"""Central project settings.

Loads environment variables from backend/.env (if present) and exposes
shared constants: the Nagpur AOI, GEE dataset IDs, and data paths.

AOI POLICY (hard rule, agreed 2026-09-23 — see PLAN.md):
    Every GEE query and frontend view is scoped to the polygon in
    backend/config/aoi/nagpur_city.geojson — NEVER a bounding box and
    never the wider district. BBOX below exists only for coarse sanity
    checks (e.g. map view fitting) and must not be used for filtering.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

try:  # optional dependency; env vars still work without it
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:  # pragma: no cover
    pass

# --- Paths -----------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW_DIR = REPO_ROOT / os.getenv("DATA_RAW_DIR", "data/raw")
DATA_PROCESSED_DIR = REPO_ROOT / os.getenv("DATA_PROCESSED_DIR", "data/processed")

AOI_GEOJSON_PATH = Path(__file__).resolve().parent / "aoi" / "nagpur_city.geojson"

# --- AOI: static Nagpur city polygon (OSM relation 10330977) ----------------
@lru_cache(maxsize=1)
def load_nagpur_aoi() -> dict:
    """Return the static AOI GeoJSON Feature (Nagpur city boundary)."""
    with open(AOI_GEOJSON_PATH) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def nagpur_bbox() -> tuple[float, float, float, float]:
    """(west, south, east, north) of the AOI — for coarse checks ONLY
    (e.g. fitting the frontend map view), never for data filtering."""
    rings = [poly[0] for poly in load_nagpur_aoi()["geometry"]["coordinates"]]
    lons = [c[0] for r in rings for c in r]
    lats = [c[1] for r in rings for c in r]
    return (min(lons), min(lats), max(lons), max(lats))


# --- GEE dataset IDs (see PROJECT.md §4) ------------------------------------
DATASETS = {
    "landsat8": "LANDSAT/LC08/C02/T1_L2",   # LST source: ST_B10 (pre-corrected)
    "landsat9": "LANDSAT/LC09/C02/T1_L2",   # LST source: ST_B10 (pre-corrected)
    "sentinel2": "COPERNICUS/S2_SR_HARMONIZED",  # NDVI/NDBI source (10 m)
    "worldcover": "ESA/WorldCover/v200",    # land-cover reference (10 m)
}

# --- Study windows ----------------------------------------------------------
# Primary analysis window: pre-monsoon (Mar–May), when UHI intensity peaks
# in central India and cloud cover is lowest. Same-season median composites
# per year keep comparisons consistent (never mix seasons across years).
SEASONS = {
    "pre-monsoon": {"start_mmdd": "03-01", "end_mmdd": "05-31"},
    "monsoon": {"start_mmdd": "06-01", "end_mmdd": "09-30"},
    "post-monsoon": {"start_mmdd": "10-01", "end_mmdd": "11-30"},
    "winter": {"start_mmdd": "12-01", "end_mmdd": "02-28"},
}
