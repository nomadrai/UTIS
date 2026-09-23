"""Analysis: persistent UHI hotspot identification.

Design (agreed 2026-09-23 — see PLAN.md):
    - A pixel is a persistent hotspot if it stays in the TOP LST PERCENTILE
      (threshold decided at implementation; default candidate: 90th) across
      MOST of the study years (default candidate: >= 70% of years), computed
      within the Nagpur polygon only.
    - Thresholds will be configurable in backend/config/settings.py once the
      first composites exist.
"""

from __future__ import annotations


def identify_persistent_hotspots(yearly_lst: dict, pct: int = 90, min_year_frac: float = 0.7):
    """Cross-year persistent-top-percentile hotspot detection (server-side).

    Args:
        yearly_lst: {year: ee.Image of LST (Kelvin)} clipped to the polygon.
    Returns:
        ee.Image (1=hotspot) + small numeric summaries via reduceRegion.
    """
    raise NotImplementedError("Hotspot logic lands with PLAN.md task #5")
