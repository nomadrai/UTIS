"""GET /api/comparison — multi-year per-year composite stats for change-over-time."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/comparison")
def get_comparison(years: str, layer: str = "lst") -> dict:
    """Return {layer: {year: stats}} small JSON summaries (no pixel dumps).

    `years` = comma-separated, e.g. ?years=2020,2022,2024 — must all have
    composites computed for the SAME season (see settings.SEASONS rule).
    """
    raise NotImplementedError("Comparison endpoint lands with PLAN.md task #7")
