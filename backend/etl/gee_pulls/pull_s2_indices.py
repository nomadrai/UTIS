"""GEE data-pull: Sentinel-2 NDVI / NDBI and ESA WorldCover reference.

Design (agreed 2026-09-23 — see PLAN.md):
    - Collection: COPERNICUS/S2_SR_HARMONIZED (10 m) — same AOI polygon and
      seasonal-median compositing rule as the Landsat LST pipeline, so
      NDVI/NDBI and LST describe the same season each year.
    - NDVI = (NIR - Red) / (NIR + Red)          -> B8, B4
    - NDBI = (SWIR - NIR) / (SWIR + NIR)        -> B11, B8
    - Cloud mask: SCL (Scene Classification Layer) filtering, server-side.
    - ESA WorldCover v200 (ESA/WorldCover/v200) clipped to the same polygon
      as the land-cover reference for zone classification
      (vegetation/built-up/water/...).
    - Output policy: server-side only — reduceRegion summaries and getMapId
      tile URLs. No raw-imagery downloads.

Planned CLI (not implemented yet):
    python -m backend.etl.gee_pulls.pull_s2_indices \
        --years 2020 2021 2022 2023 2024 --season pre-monsoon
"""

from __future__ import annotations

import argparse

from backend.config.settings import DATASETS, SEASONS
from backend.etl.gee_common import scope_to_nagpur  # noqa: F401  (policy wiring lands task #1)


def load_collection(years: list[int], season: str):
    """Cloud-masked S2 SR collection clipped to the Nagpur polygon."""
    raise NotImplementedError("S2 collection loading lands with PLAN.md task #4")


def add_indices(image):
    """Add NDVI (B8/B4) and NDBI (B11/B8) bands, server-side."""
    raise NotImplementedError("Index computation lands with PLAN.md task #4")


def seasonal_composite(year: int, season: str):
    """Median NDVI/NDBI composite for one year + season over the polygon."""
    raise NotImplementedError("Seasonal composite lands with PLAN.md task #4")


def load_worldcover():
    """ESA WorldCover v200 clipped to the Nagpur polygon."""
    raise NotImplementedError("WorldCover pull lands with PLAN.md task #4")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", help="study years, e.g. 2020 2021 2022")
    parser.add_argument("--season", default="pre-monsoon", choices=sorted(SEASONS))
    args = parser.parse_args()

    raise NotImplementedError("S2 indices + WorldCover pipeline lands with PLAN.md task #4")


if __name__ == "__main__":
    main()
