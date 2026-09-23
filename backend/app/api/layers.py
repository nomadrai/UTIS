"""GET /api/layers — per-year layer metadata + GEE tile URLs.

Registry-driven (task #4): every analysable layer (lst/ndvi/ndbi) declares
its composite builder, vis params, year limits, and source attribution in
one place. Adding a layer = adding a registry entry + (optionally) a cache
meta entry in lst_stats; endpoints stay untouched.
"""

from __future__ import annotations

import ee
from fastapi import APIRouter, HTTPException

from backend.config.settings import SEASONS
from backend.etl import gee_common
from backend.etl.gee_pulls import pull_landsat_lst, pull_s2_indices

router = APIRouter()

S2_FIRST_YEAR = 2017  # COPERNICUS/S2_SR_HARMONIZED coverage starts 2017-03-28


def _ndvi_composite(year: int, season: str):
    return pull_s2_indices.seasonal_composite(year, season, "ndvi")


def _ndbi_composite(year: int, season: str):
    return pull_s2_indices.seasonal_composite(year, season, "ndbi")


LAYERS: dict[str, dict] = {
    "lst": {
        "composite": pull_landsat_lst.seasonal_composite,
        "vis_params": pull_landsat_lst._lst_vis_params(),
        "min_year": 2013,  # Landsat 8 launch
        "source": "Landsat 8/9 ST_B10, seasonal median composite",
        "units": "Kelvin",
    },
    "ndvi": {
        "composite": _ndvi_composite,
        "vis_params": pull_s2_indices.VIS_PARAMS["ndvi"],
        "min_year": S2_FIRST_YEAR,
        "source": "Sentinel-2 SR NDVI, SCL-masked seasonal median composite",
        "units": "index (-1..1)",
    },
    "ndbi": {
        "composite": _ndbi_composite,
        "vis_params": pull_s2_indices.VIS_PARAMS["ndbi"],
        "min_year": S2_FIRST_YEAR,
        "source": "Sentinel-2 SR NDBI, SCL-masked seasonal median composite",
        "units": "index (-1..1)",
    },
}


@router.get("/api/layers")
def get_layers(year: int, layer: str = "lst", season: str = "pre-monsoon") -> dict:
    """Return {tile_url, vis_params, bbox} for one layer/year.

    Contract (agreed 2026-09-23):
        - layers: "lst" | "ndvi" | "ndbi" ("landcover" lands with a later task)
        - tile URLs come from GEE getMapId; imagery stays server-side.
        - every composite is clipped to the Nagpur polygon (gee_common) —
          the tile URL renders the clip, no bbox filtering client-side.
        - fixed vis ranges so year-to-year renders compare.
        - S2 layers (ndvi/ndbi) reject years before 2017 (no coverage).
    """
    spec = LAYERS.get(layer)
    if spec is None:
        raise HTTPException(
            400, f"layer {layer!r} not available — use {sorted(LAYERS)}"
        )
    if season not in SEASONS:
        raise HTTPException(400, f"season must be one of {sorted(SEASONS)}")
    if year < spec["min_year"] or year > 2026:
        raise HTTPException(
            400,
            f"{layer} covers {spec['min_year']}-2026; {year} has no "
            f"{'Sentinel-2' if spec['min_year'] > 2013 else 'Landsat 8/9'} coverage",
        )

    try:
        composite = spec["composite"](year, season)
        tile_url = gee_common.to_tile_url(composite, spec["vis_params"])
    except (RuntimeError, ee.EEException) as exc:  # auth/project vs GEE compute
        raise HTTPException(503, f"GEE unavailable: {exc}") from exc

    return {
        "layer": layer,
        "year": year,
        "season": season,
        "tile_url": tile_url,
        "vis_params": spec["vis_params"],
        "bbox_wsen": list(gee_common.aoi_bbox_wsen()),
        "units": spec["units"],
        "source": spec["source"],
        "note": "imagery served by GEE tiles, clipped to the Nagpur polygon; "
                "fixed vis range for cross-year comparability",
    }
