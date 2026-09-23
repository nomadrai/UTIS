"""GEE data-pull script: Landsat 8/9 surface temperature + optical bands.

Planned usage (not implemented yet):
    python -m backend.etl.gee_pulls.pull_landsat_lst \
        --year 2024 --season pre-monsoon --sanity-check
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, help="target year, e.g. 2024")
    parser.add_argument(
        "--season", default="pre-monsoon", choices=["pre-monsoon", "monsoon", "post-monsoon", "winter"]
    )
    parser.add_argument(
        "--sanity-check",
        action="store_true",
        help="only verify GEE auth by counting images in a tiny collection query",
    )
    args = parser.parse_args()

    if args.sanity_check:
        # TODO (PLAN.md task #1): ee.Authenticate()/ee.Initialize(project=...),
        # then ImageCollection count over NAGPUR_BBOX.
        raise NotImplementedError("GEE sanity check lands with PLAN.md task #1")

    raise NotImplementedError("Real Landsat pull lands with PLAN.md tasks #1–#2")


if __name__ == "__main__":
    main()
