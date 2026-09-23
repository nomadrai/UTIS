"""GET /api/gee-status — GEE auth/polyon-scope diagnostics."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/gee-status")
def gee_status() -> dict:
    """Report GEE init status + AOI polygon path/info (stub)."""
    raise NotImplementedError("GEE status endpoint lands with PLAN.md task #7")
