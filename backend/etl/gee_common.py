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

from typing import Any

from backend.config.settings import load_nagpur_aoi


def load_nagpur_aoi_geometry() -> dict:
    """Return the AOI geometry dict (GeoJSON MultiPolygon)."""
    return load_nagpur_aoi()["geometry"]


def get_ee() -> Any:
    """Initialize and return the ee module bound to GEE_PROJECT_ID.

    Implementation lands with PLAN.md task #1 (auth + first pull).
    """
    raise NotImplementedError("GEE init lands with PLAN.md task #1")


def aoi_feature() -> Any:
    """Return ee.Feature wrapping the Nagpur polygon (for filterBounds)."""
    raise NotImplementedError("Wired in PLAN.md task #1")


def aoi_geometry() -> Any:
    """Return ee.Geometry for the Nagpur polygon (for clip)."""
    raise NotImplementedError("Wired in PLAN.md task #1")


def scope_to_nagpur(collection: Any) -> Any:
    """Apply .filterBounds(aoi) + .map(clip) to a collection — the ONLY
    sanctioned way to scope imagery in this project."""
    raise NotImplementedError("Wired in PLAN.md task #1")


def clip_to_nagpur(image: Any) -> Any:
    """Clip a single ee.Image to the Nagpur polygon."""
    raise NotImplementedError("Wired in PLAN.md task #1")


def reduce_over_zones(image: Any, scale: int) -> Any:
    """Server-side reduceRegion/reduceToVectors over AOI zones; returns
    small numeric summaries only (never pixel dumps)."""
    raise NotImplementedError("Wired in PLAN.md task #3")
