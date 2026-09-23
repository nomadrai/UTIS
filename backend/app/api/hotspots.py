"""GET /api/hotspots — persistent UHI hotspot zones for the study period."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/hotspots")
def get_hotspots(pct: int = 90, min_year_frac: float = 0.7) -> dict:
    """Return hotspot markers/GeoJSON within the Nagpur polygon only.

    Detection contract (agreed 2026-09-23):
        - pixels in the top LST percentile across most study years
        - returned as small GeoJSON (marker/zone geometries + stats),
          never raw pixel dumps
    """
    raise NotImplementedError("Hotspots endpoint lands with PLAN.md task #7")
