"""FastAPI entry point — serves analysis results to the Leaflet frontend.

Endpoints (agreed 2026-09-23, stubs only — see PLAN.md task board):
    GET  /api/gee-status   — GEE auth/polygon-scope diagnostics
    GET  /api/layers       — per-year LST/NDVI/NDBI tile URLs + metadata
    GET  /api/comparison   — multi-year per-year composite stats
    GET  /api/hotspots     — persistent hotspot zones (GeoJSON)
    POST /api/scenario     — what-if estimation for a zone + slider deltas
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.app.api.layers import router as layers_router
from backend.app.api.comparison import router as comparison_router
from backend.app.api.hotspots import router as hotspots_router
from backend.app.api.scenario import router as scenario_router
from backend.app.api.gee_status import router as gee_status_router

app = FastAPI(
    title="UHI Nagpur API",
    description="Backend for the Urban Heat Island intelligence platform (see PROJECT.md).",
    version="0.2.0",
)

app.include_router(layers_router)
app.include_router(comparison_router)
app.include_router(hotspots_router)
app.include_router(scenario_router)
app.include_router(gee_status_router)


@app.get("/api/health")
def health() -> dict:
    """Liveness probe. GEE status check lands with PLAN.md task #7."""
    return {"status": "ok", "gee_authenticated": None}
