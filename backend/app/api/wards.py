"""GET /api/wards — the georeferenced ward polygons (static geometry layer).

Serves backend/config/aoi/nagpur_wards.geojson (114 CIS-2005 wards,
georeferenced to the OSM city polygon — see the `georef` block in the file
and PLAN.md session 4 for the accepted ~100–300 m peripheral uncertainty).
The frontend draws the choropleth from this; per-ward VALUES come from
/api/comparison and are joined client-side by ward_no.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.etl.analysis.lst_stats import load_wards_geojson

router = APIRouter()


@router.get("/api/wards")
def get_wards() -> dict:
    """Return the ward FeatureCollection (114 features, ward_no may be null)."""
    return load_wards_geojson()
