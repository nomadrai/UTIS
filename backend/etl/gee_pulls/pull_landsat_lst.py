"""GEE data-pull: Landsat 8/9 Land Surface Temperature.

Design (agreed 2026-09-23 — see PLAN.md):
    - Collections: LANDSAT/LC08/C02/T1_L2 + LANDSAT/LC09/C02/T1_L2, merged.
    - LST band: ST_B10 — already atmospherically corrected surface
      temperature; NO derivation from raw thermal radiance. Scale to Kelvin
      with the C2 L2 scale factor (DN * 0.00341802 + 149.0).
    - AOI: static Nagpur city polygon via gee_common (filterBounds + clip) —
      never a bbox.
    - Compositing: per-year seasonal MEDIAN over the same season window for
      every year in the study period, so no year is compared against a
      different season.
    - Output policy: server-side only — reduceRegion summaries and getMapId
      tile URLs. No raw-imagery downloads.

Planned CLI (not implemented yet):
    python -m backend.etl.gee_pulls.pull_landsat_lst \
        --years 2020 2021 2022 2023 2024 --season pre-monsoon
"""

from __future__ import annotations

import argparse

from backend.config.settings import DATASETS, SEASONS
from backend.etl.gee_common import scope_to_nagpur  # noqa: F401  (policy wiring lands task #1)

LST_SCALE = 0.00341802
LST_OFFSET = 149.0


def load_collection(years: list[int], season: str):
    """Merged, cloud-masked L8/L9 collection clipped to the Nagpur polygon.

    TODO (task #1): ee.ImageCollection merge of the two dataset IDs,
    date filter per season window, QA_PIXEL cloud mask, scope_to_nagpur().
    """
    raise NotImplementedError("Landsat collection loading lands with PLAN.md task #1")


def to_lst_kelvin(image):
    """Apply ST_B10 scale/offset -> LST in Kelvin (server-side)."""
    raise NotImplementedError("LST scaling lands with PLAN.md task #1")


def seasonal_composite(year: int, season: str):
    """Median ST_B10 composite for one year + season over the Nagpur polygon."""
    raise NotImplementedError("Seasonal composite lands with PLAN.md task #1")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", help="study years, e.g. 2020 2021 2022")
    parser.add_argument(
        "--season", default="pre-monsoon", choices=sorted(SEASONS)
    )
    parser.add_argument(
        "--sanity-check",
        action="store_true",
        help="verify GEE auth + polygon scoping with a tiny server-side query",
    )
    args = parser.parse_args()

    if args.sanity_check:
        raise NotImplementedError("GEE sanity check lands with PLAN.md task #1")
    raise NotImplementedError("LST pull pipeline lands with PLAN.md tasks #1–#3")


if __name__ == "__main__":
    main()
