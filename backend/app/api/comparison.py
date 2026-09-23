"""GET /api/comparison — multi-year per-ward stats for change-over-time."""

from __future__ import annotations

import ee
from fastapi import APIRouter, HTTPException

from backend.config.settings import SEASONS
from backend.etl.analysis import lst_stats
from backend.app.api.layers import LAYERS

router = APIRouter()


@router.get("/api/comparison")
def get_comparison(
    years: str,
    layer: str = "lst",
    season: str = lst_stats.DEFAULT_SEASON,  # FastAPI reads plain defaults as query params
    refresh: bool = False,
) -> dict:
    """Return {layer, season, units, years: {year: {wards, city}}} — small
    JSON summaries only (no pixel dumps).

    `years` = comma-separated, e.g. ?years=2020,2022,2024. All years use the
    SAME season window (settings.SEASONS rule — never mix seasons across
    years). Missing years are computed on first request via GEE, then cached
    per layer+season to data/processed; pass refresh=true to force recompute.
    S2 layers (ndvi/ndbi) reject years before 2017.
    """
    spec = LAYERS.get(layer)
    if spec is None:
        raise HTTPException(400, f"layer {layer!r} not available — use {sorted(LAYERS)}")
    if season not in SEASONS:
        raise HTTPException(400, f"season must be one of {sorted(SEASONS)}")

    try:
        parsed = sorted({int(y.strip()) for y in years.split(",") if y.strip()})
    except ValueError:
        raise HTTPException(400, "years must be comma-separated integers, e.g. ?years=2020,2022,2024")
    if not parsed:
        raise HTTPException(400, "provide at least one year, e.g. ?years=2024")
    if any(y < spec["min_year"] or y > 2026 for y in parsed):
        raise HTTPException(
            400,
            f"{layer} covers {spec['min_year']}-2026; "
            f"{'Sentinel-2' if spec['min_year'] > 2013 else 'Landsat 8/9'} has no "
            "coverage for the requested years",
        )

    try:
        payload = lst_stats.compute_yearly_stats(
            parsed, season, refresh=refresh, layer=layer,
            composite=spec["composite"],
        )
    except (RuntimeError, ee.EEException) as exc:  # auth/project vs GEE compute
        raise HTTPException(503, f"GEE unavailable: {exc}") from exc

    return {
        "layer": layer,
        "season": payload["season"],
        "units": payload["units"],
        "years": {str(y): payload["years"][str(y)] for y in parsed if str(y) in payload["years"]},
    }
