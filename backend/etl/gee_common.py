"""Shared helpers for every GEE interaction in this project.

AOI / compute policy (agreed 2026-09-23, see PLAN.md):
    1. AOI is the static polygon in backend/config/aoi/nagpur_city.geojson
       (OSM relation 10330977, Nagpur city extent) — never a bbox, never the
       district.
    2. Every collection/image query must pass through the helpers below so
       .filterBounds(aoi) and .clip(aoi) are applied in ONE place.
    3. Server-side compute only: reduceRegion/reduceColumns for numeric
       summaries, getMapId for tile URLs. No raw-imagery downloads.
"""

from __future__ import annotations

import json
from typing import Any

from backend.config.settings import GEE_PROJECT_ID, load_nagpur_aoi

_ee: Any = None  # module-level cache so ee.Initialize runs once per process


def load_nagpur_aoi_geometry() -> dict:
    """Return the AOI geometry dict (GeoJSON MultiPolygon)."""
    return load_nagpur_aoi()["geometry"]


def get_ee() -> Any:
    """Initialize and return the ee module bound to GEE_PROJECT_ID.

    Credentials come from the local `earthengine authenticate` flow; the
    project is forced server-side so no code path can silently use another.
    """
    global _ee
    if _ee is not None:
        return _ee

    if not GEE_PROJECT_ID:
        raise RuntimeError(
            "GEE_PROJECT_ID is not set. Copy backend/.env.example to "
            "backend/.env and set it to your Earth Engine Cloud project ID."
        )

    import ee  # deferred so non-GEE code paths don't pay the import

    ee.Initialize(project=GEE_PROJECT_ID)
    _ee = ee
    return _ee


def aoi_geometry() -> Any:
    """Return ee.Geometry for the Nagpur polygon (for clip)."""
    ee = get_ee()
    return ee.Geometry(load_nagpur_aoi_geometry())


def aoi_feature() -> Any:
    """Return ee.Feature wrapping the Nagpur polygon (for filterBounds)."""
    ee = get_ee()
    return ee.Feature(load_nagpur_aoi(), None)


def scope_to_nagpur(collection: Any) -> Any:
    """Apply .filterBounds(aoi) + .map(clip) to a collection — the ONLY
    sanctioned way to scope imagery in this project."""
    ee = get_ee()
    aoi = aoi_geometry()
    return (
        collection.filterBounds(aoi).map(
            lambda image: image.clip(aoi)  # noqa: W0106 — clip is policy, not optimization
        )
    )


def clip_to_nagpur(image: Any) -> Any:
    """Clip a single ee.Image to the Nagpur polygon."""
    return image.clip(aoi_geometry())


def reduce_over_zones(image: Any, scale: int) -> Any:
    """Server-side reduceRegion over the AOI; returns small numeric
    summaries only (never pixel dumps).

    Note: zonal (per-ward) reductions land with PLAN.md task #3; today the
    platform reduces over the single city polygon.
    """
    ee = get_ee()
    reducer = ee.Reducer.mean()
    return image.reduceRegion(
        reducer=reducer,
        geometry=aoi_geometry(),
        scale=scale,
        maxPixels=1e9,
        bestEffort=True,
    )


def to_tile_url(image: Any, vis_params: dict) -> str:
    """Return a GEE-hosted tile URL for one image (getMapId)."""
    ee = get_ee()
    map_id = image.getMapId(vis_params)
    return map_id["tile_fetcher"].url_format


def geojson_to_ee_geometry(geojson: dict) -> Any:
    """Convert a GeoJSON geometry dict to an ee.Geometry (for ad-hoc zones)."""
    ee = get_ee()
    return ee.Geometry(geojson)


def aoi_geojson() -> dict:
    """Return the raw AOI GeoJSON Feature dict (static file, no GEE)."""
    return load_nagpur_aoi()


def aoi_bbox_wsen() -> tuple[float, float, float, float]:
    """(west, south, east, north) — coarse map-fitting ONLY, never filtering."""
    from backend.config.settings import nagpur_bbox

    return nagpur_bbox()


def export_json(payload: Any) -> str:
    """Serialize a small computed payload for data/processed outputs."""
    return json.dumps(payload, sort_keys=True, default=str)
