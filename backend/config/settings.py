"""Central project settings.

Loads environment variables from backend/.env (if present) and exposes
shared constants: AOI bounds, dataset IDs, and data paths. No logic here
beyond configuration — real GEE work lives in backend/etl/.
"""

from __future__ import annotations

import os
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

# --- AOI (rough bounding box; replace with a proper boundary polygon in a
#     later session — see PLAN.md task #2) ------------------------------------
NAGPUR_BBOX = {
    "west": 78.95,
    "south": 21.00,
    "east": 79.15,
    "north": 21.30,
}

# --- GEE dataset IDs (see PROJECT.md §4) ------------------------------------
DATASETS = {
    "landsat8": "LANDSAT/LC08/C02/T1_L2",
    "landsat9": "LANDSAT/LC09/C02/T1_L2",
    "sentinel2": "COPERNICUS/S2_SR_HARMONIZED",
    "worldcover": "ESA/WorldCover/v200",
}

# --- Study windows ----------------------------------------------------------
# Primary analysis window: pre-monsoon (Mar–May), when UHI intensity peaks
# in central India and cloud cover is lowest.
SEASONS = {
    "pre-monsoon": {"start_mmdd": "03-01", "end_mmdd": "05-31"},
    "monsoon": {"start_mmdd": "06-01", "end_mmdd": "09-30"},
    "post-monsoon": {"start_mmdd": "10-01", "end_mmdd": "11-30"},
    "winter": {"start_mmdd": "12-01", "end_mmdd": "02-28"},
}
