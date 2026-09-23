"""GET /api/layers — per-year LST layer metadata + GEE tile URLs."""

from __future__ import annotations

import ee
from fastapi import APIRouter, HTTPException

from backend.config.settings import SEASONS
from backend.etl import gee_common
from backend.etl.gee_pulls import pull_landsat_lst

router = APIRouter()


@router.get("/api/layers")
def get_layers(year: int, layer: str = "lst", season: str = "pre-monsoon") -> dict:
    """Return {tile_url, vis_params, bbox} for one layer/year.

    Contract (agreed 2026-09-23):
        - layers: "lst" | "ndvi" | "ndbi" | "landcover" — only "lst" for now;
          NDVI/NDBI land with PLAN.md task #4.
        - tile URLs come from GEE getMapId; imagery stays server-side.
        - every composite is clipped to the Nagpur polygon (gee_common) —
          the tile URL renders the clip, no bbox filtering client-side.
        - fixed vis range (min/max/palette) so year-to-year renders compare.
    """
    if layer != "lst":
        raise HTTPException(
            400, f"layer {layer!r} not available yet — only 'lst' (NDVI/NDBI "
                 "land with task #4)"
        )
    if season not in SEASONS:
        raise HTTPException(400, f"season must be one of {sorted(SEASONS)}")
    if year < 2013 or year > 2026:
        raise HTTPException(400, "year must be within Landsat 8/9 coverage (2013-2026)")

    try:
        composite = pull_landsat_lst.seasonal_composite(year, season)
        tile_url = gee_common.to_tile_url(composite, pull_landsat_lst._lst_vis_params())
    except (RuntimeError, ee.EEException) as exc:  # auth/project vs GEE compute
        raise HTTPException(503, f"GEE unavailable: {exc}") from exc

    return {
        "layer": "lst",
        "year": year,
        "season": season,
        "tile_url": tile_url,
        "vis_params": pull_landsat_lst._lst_vis_params(),
        "bbox_wsen": list(gee_common.aoi_bbox_wsen()),
        "units": "Kelvin",
        "note": "imagery served by GEE tiles, clipped to the Nagpur polygon; "
                "fixed vis range for cross-year comparability",
    }
