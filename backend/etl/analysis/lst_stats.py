"""Analysis: LST / NDVI / NDBI multi-year statistics.

Responsibilities (see PLAN.md task #5):
    - per-year, per-zone (and city-wide) summary stats for each layer
      (mean/percentiles), computed server-side via reduceRegion and cached
      to data/processed as small JSON — this is what the comparison endpoint
      returns for the change-over-time view
    - multi-year delta rasters/summaries between selected year pairs
"""

from __future__ import annotations


def yearly_stats(yearly_images: dict, zones=None) -> dict:
    """{layer: {year: {zone: stats}}} small JSON summaries (server-side)."""
    raise NotImplementedError("Yearly stats lands with PLAN.md task #5")
