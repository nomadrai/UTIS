"""GET /api/landcover-stats — per-ward WorldCover class shares (task #4).

Categorical layer, so it does NOT participate in /api/comparison (mean of
class codes is meaningless); this serves the cached class-share table from
data/processed/worldcover_ward_stats.json (built by
python -m backend.etl.gee_pulls.pull_worldcover --zonal-stats).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from backend.config.settings import DATA_PROCESSED_DIR
from backend.etl.gee_pulls.pull_worldcover import CLASSES, WORLDCOVER_YEAR

router = APIRouter()

STATS_PATH = DATA_PROCESSED_DIR / "worldcover_ward_stats.json"


@router.get("/api/landcover-stats")
def get_landcover_stats() -> dict:
    """{year, classes: {value: label}, wards: [{ward_no, shares, dominant}]}."""
    if not STATS_PATH.exists():
        raise HTTPException(
            404,
            "worldcover ward stats not computed yet — run: python -m "
            "backend.etl.gee_pulls.pull_worldcover --zonal-stats",
        )
    payload = json.loads(STATS_PATH.read_text())
    payload["class_colors"] = {str(k): v[1] for k, v in CLASSES.items()}
    return payload
