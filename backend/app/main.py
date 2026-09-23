"""FastAPI entry point — serves analysis results to the Leaflet frontend.

v1 endpoints planned (see PLAN.md task board):
    GET  /api/health     — liveness + GEE auth status
    GET  /api/layers     — available LST/NDVI/NDBI layers and years
    GET  /api/hotspots   — hotspot zones for a year/season
    POST /api/scenario   — what-if estimation for a zone + slider deltas
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="UHI Nagpur API",
    description="Backend for the Urban Heat Island intelligence platform (see PROJECT.md).",
    version="0.1.0",
)


@app.get("/api/health")
def health() -> dict:
    """Liveness probe. GEE status check lands with PLAN.md task #1."""
    return {"status": "ok", "gee_authenticated": None}
