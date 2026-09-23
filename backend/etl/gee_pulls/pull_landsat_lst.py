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

CLI:
    python -m backend.etl.gee_pulls.pull_landsat_lst \
        --years 2020 2021 2022 2023 2024 --season pre-monsoon
    python -m backend.etl.gee_pulls.pull_landsat_lst --sanity-check
"""

from __future__ import annotations

import argparse
from typing import Any

from backend.config.settings import DATASETS, GEE_PROJECT_ID, SEASONS
from backend.etl import gee_common

LST_SCALE = 0.00341802
LST_OFFSET = 149.0

LST_BAND = "ST_B10"
QA_PIXEL_BAND = "QA_PIXEL"

# Collection 2 Level-2 QA_PIXEL bit meanings (single bits, 1-indexed):
#   bit 1 Dilated Cloud, bit 3 Cloud, bit 4 Cloud Shadow, bit 5 Snow.
CLOUD_QA_BITS = [1, 3, 4, 5]


def _season_dates(year: int, season: str) -> tuple[str, str]:
    """Return (start, end) ISO dates for one year + season window.

    'winter' wraps the calendar year boundary (Dec of `year` -> Feb of
    `year+1`), which is how a northern-hemisphere winter actually falls.
    """
    window = SEASONS[season]
    start = f"{year}-{window['start_mmdd']}"
    end = f"{year}-{window['end_mmdd']}"
    if season == "winter":
        # Dec 1 of `year` to Feb 28 of `year + 1`.
        start = f"{year}-{window['start_mmdd']}"
        end = f"{year + 1}-{window['end_mmdd']}"
    return start, end


def load_collection(years: list[int], season: str):
    """Merged, cloud-masked L8/L9 collection clipped to the Nagpur polygon.

    Every image passes through gee_common.scope_to_nagpur so filterBounds +
    clip are applied in exactly one place (project AOI policy).
    """
    ee = gee_common.get_ee()

    l8 = ee.ImageCollection(DATASETS["landsat8"])
    l9 = ee.ImageCollection(DATASETS["landsat9"])
    merged = l8.merge(l9)

    images: list[Any] = []
    for year in years:
        start, end = _season_dates(year, season)
        images.append(merged.filterDate(start, end))

    collection = images[0]
    for yearly in images[1:]:
        collection = collection.merge(yearly)

    collection = gee_common.scope_to_nagpur(collection)

    def _mask_clouds(image: Any) -> Any:
        qa = image.select(QA_PIXEL_BAND)
        cloud_mask = qa.bitwiseAnd(1 << 1).eq(0)
        for bit in CLOUD_QA_BITS[1:]:
            cloud_mask = cloud_mask.And(qa.bitwiseAnd(1 << bit).eq(0))
        masked = image.updateMask(cloud_mask)
        return gee_common.clip_to_nagpur(masked)

    return collection.map(_mask_clouds)


def to_lst_kelvin(image: Any) -> Any:
    """Apply ST_B10 scale/offset -> LST in Kelvin (server-side)."""
    lst = (
        image.select(LST_BAND)
        .multiply(LST_SCALE)
        .add(LST_OFFSET)
        .rename("LST_K")
    )
    return image.addBands(lst, overwrite=True)


def seasonal_composite(year: int, season: str) -> Any:
    """Median ST_B10 composite for one year + season over the Nagpur polygon."""
    collection = load_collection([year], season)

    def _scale(image: Any) -> Any:
        return to_lst_kelvin(image)

    scaled = collection.map(_scale)
    composite = scaled.median()
    return gee_common.clip_to_nagpur(composite.select("LST_K"))


def _lst_vis_params() -> dict:
    """Fixed visualization range (Kelvin) so year-to-year renders compare."""
    return {
        "bands": "LST_K",
        "min": 290.0,
        "max": 325.0,
        "palette": [
            "#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c",
        ],
    }


def sanity_check() -> dict:
    """Verify GEE auth + polygon scoping with tiny server-side queries."""
    ee = gee_common.get_ee()

    # 1. Auth/round-trip: echo a constant through GEE's compute engine.
    echo = ee.Number(42).getInfo()
    if echo != 42:
        raise RuntimeError(f"GEE echo returned unexpected value: {echo}")

    # 2. AOI loads and is a sane MultiPolygon-sized object.
    aoi = gee_common.aoi_geometry()
    area_m2 = aoi.area(maxError=1).getInfo()
    area_km2 = area_m2 / 1e6
    if not (50 < area_km2 < 1000):
        raise RuntimeError(
            f"AOI area implausible for Nagpur city extent: {area_km2:.1f} km2"
        )

    # 3. Tiny server-side reduce over a real Landsat scene footprint count.
    start, end = _season_dates(2024, "pre-monsoon")
    count = (
        ee.ImageCollection(DATASETS["landsat8"])
        .merge(ee.ImageCollection(DATASETS["landsat9"]))
        .filterBounds(gee_common.aoi_geometry())
        .filterDate(start, end)
        .size()
        .getInfo()
    )

    return {
        "gee_project_id": GEE_PROJECT_ID,
        "echo_ok": True,
        "aoi_area_km2": round(area_km2, 2),
        "landsat_scenes_2024_premonsoon": count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Landsat 8/9 LST pull (ST_B10)")
    parser.add_argument("--years", type=int, nargs="+", help="study years, e.g. 2020 2021 2022")
    parser.add_argument(
        "--season", default="pre-monsoon", choices=sorted(SEASONS)
    )
    parser.add_argument(
        "--sanity-check",
        action="store_true",
        help="verify GEE auth + polygon scoping with tiny server-side queries",
    )
    parser.add_argument(
        "--zonal-stats",
        action="store_true",
        help="per-ward zonal LST stats for --years, cached to data/processed "
             "(feeds /api/comparison)",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="recompute years already present in the zonal-stats cache",
    )
    args = parser.parse_args()

    if args.sanity_check:
        import json

        print(json.dumps(sanity_check(), indent=2))
        return

    if args.zonal_stats:
        if not args.years:
            parser.error("--zonal-stats needs --years")
        from backend.etl.analysis import lst_stats

        payload = lst_stats.compute_yearly_stats(
            args.years, args.season, refresh=args.refresh
        )
        import json

        print(json.dumps(
            {y: payload["years"][y]["city"] for y in sorted(payload["years"])},
            indent=2))
        return

    if not args.years:
        parser.error("provide --years, or run with --sanity-check")

    for year in args.years:
        composite = seasonal_composite(year, args.season)
        stats = gee_common.reduce_over_zones(composite, scale=1000)
        result = stats.getInfo()
        print(f"{year} {args.season}: {result}")


if __name__ == "__main__":
    main()
