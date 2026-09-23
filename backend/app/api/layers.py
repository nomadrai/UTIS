"""GET /api/layers — per-year LST/NDVI/NDBI layer metadata + GEE tile URLs."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/layers")
def get_layers(year: int, layer: str) -> dict:
    """Return {tile_url, vis_params, valid_min, valid_max} for one layer/year.

    Contract (agreed 2026-09-23):
        - layers: "lst" | "ndvi" | "ndbi" | "landcover"
        - tile URLs come from GEE getMapId; imagery stays server-side.
        - every tile render is clipped to the Nagpur polygon (gee_common).
    """
    raise NotImplementedError("Layers endpoint lands with PLAN.md task #7")
