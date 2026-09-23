"""GEE data-pull: Sentinel-2 NDVI / NDBI seasonal composites.

Design (agreed 2026-09-23/24 — see PLAN.md):
    - Collection: COPERNICUS/S2_SR_HARMONIZED (Level-2A surface reflectance,
      10 m). Same AOI/season rules as the LST pull — scope_to_nagpur,
      settings.SEASONS windows via the shared season_dates helper.
    - Cloud masking: QA60 is unreliable on S2 SR; the SCL (Scene
      Classification Layer) is used instead — mask classes 3 (cloud
      shadow), 8 (cloud medium), 9 (cloud high), 10 (thin cirrus), and
      11 (snow) (bidirectional, symmetric).
    - Indices (computed per scene BEFORE compositing so the median is an
      index median, not a band median):
        NDVI = (B8 - B4) / (B8 + B4)          vegetation, ~[-1, 1]
        NDBI = (B11 - B8) / (B11 + B8)        built-up,    ~[-1, 1]
      Sentinel-2A/BE reflectance scaled 0..10000 -> divide by 10000 first.
    - Compositing: per-year seasonal MEDIAN over the same window as LST so
      the scenario fit (task #6) compares same-season dLST ~ dNDVI + dNDBI.
    - Water/urban caveat: NDBI also responds to water (bare-soil and water
      both raise SWIR); misreads land as urban mostly near waterbodies —
      acceptable at ward scale, documented in PROJECT.md.
    - Output policy: server-side only — reduceRegions summaries and
      getMapId tile URLs. No raw-imagery downloads.

CLI:
    python -m backend.etl.gee_pulls.pull_s2_indices --sanity-check
    python -m backend.etl.gee_pulls.pull_s2_indices --zonal-stats \
        --years 2020 2021 2022 2023 2024 --season pre-monsoon [--refresh]
"""

from __future__ import annotations

import argparse
from typing import Any

from backend.config.settings import DATASETS, GEE_PROJECT_ID, SEASONS
from backend.etl import gee_common
from backend.etl.gee_pulls.pull_landsat_lst import sanity_check as lst_sanity_check

S2_COLLECTION = DATASETS["sentinel2"]
SCL_BAND = "SCL"

# SCL classes to mask out (bidirectional — class 8/9 are clouds, not 'clear').
SCL_MASK_CLASSES = (3, 8, 9, 10, 11)  # shadow, cloud med, cloud high, cirrus, snow

# Reflectance scale factor: S2 L2A DN -> 0..1
REFLECTANCE_SCALE = 10000.0

BANDS = {
    "ndvi": ("B8", "B4"),   # (nir, red)
    "ndbi": ("B11", "B8"),  # (swir1, nir)
}

VIS_PARAMS = {
    "ndvi": {
        "bands": "NDVI",
        "min": 0.0,
        "max": 0.6,
        "palette": ["#d73027", "#fdae61", "#ffffbf", "#a6d96a", "#1a9850"],
    },
    "ndbi": {
        "bands": "NDBI",
        "min": -0.3,
        "max": 0.3,
        "palette": ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"],
    },
}


def ndvi_expression(image: Any) -> Any:
    """(B8 - B4) / (B8 + B4) on scaled reflectance -> band NDVI."""
    return image.normalizedDifference(["B8", "B4"]).rename("NDVI")


def ndbi_expression(image: Any) -> Any:
    """(B11 - B8) / (B11 + B8) on scaled reflectance -> band NDBI."""
    return image.normalizedDifference(["B11", "B8"]).rename("NDBI")


def load_collection(years: list[int], season: str):
    """SCL-masked S2 collection clipped to the Nagpur polygon.

    Every image passes through gee_common.scope_to_nagpur (filterBounds +
    clip in exactly one place — AOI policy).
    """
    ee = gee_common.get_ee()
    yearly = [
        ee.ImageCollection(S2_COLLECTION).filterDate(*gee_common.season_dates(y, season))
        for y in years
    ]
    merged = yearly[0]
    for col in yearly[1:]:
        merged = merged.merge(col)

    merged = gee_common.scope_to_nagpur(merged)

    def _mask(image: Any) -> Any:
        scl = image.select(SCL_BAND)
        mask = scl.neq(SCL_MASK_CLASSES[0])
        for cls in SCL_MASK_CLASSES[1:]:
            mask = mask.And(scl.neq(cls))
        return gee_common.clip_to_nagpur(image.updateMask(mask))

    return merged.map(_mask)


def seasonal_composite(year: int, season: str, index: str) -> Any:
    """Median NDVI or NDBI composite for one year + season over the polygon.

    Reflectance scaling + index math happen per scene, before the median.
    """
    if index not in BANDS:
        raise ValueError(f"index must be one of {sorted(BANDS)}")

    expr = ndvi_expression if index == "ndvi" else ndbi_expression

    def _to_index(image: Any) -> Any:
        scaled = image.select("B4", "B8", "B11").divide(REFLECTANCE_SCALE)
        return expr(scaled)  # clip happens once, below, on the composite

    scaled = load_collection([year], season).map(_to_index)
    return gee_common.clip_to_nagpur(scaled.median())


def sanity_check() -> dict:
    """Live GEE probes for the S2 pull + the shared LST checks."""
    ee = gee_common.get_ee()
    lst_result = lst_sanity_check()  # auth + AOI sanity (echo, area, scenes)

    start, end = gee_common.season_dates(2024, "pre-monsoon")
    aoi = gee_common.aoi_geometry()
    col = (
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(aoi)
        .filterDate(start, end)
    )
    count = col.size().getInfo()

    # mean NDVI/NDBI over the AOI for pre-monsoon 2024 — plausibility probe
    ndvi_mean = (
        gee_common.reduce_over_zones(seasonal_composite(2024, "pre-monsoon", "ndvi"), scale=100)
        .getInfo()
    )
    ndbi_mean = (
        gee_common.reduce_over_zones(seasonal_composite(2024, "pre-monsoon", "ndbi"), scale=100)
        .getInfo()
    )

    return {
        **lst_result,
        "s2_scenes_2024_premonsoon": count,
        "ndvi_2024_premonsoon_mean": ndvi_mean,
        "ndbi_2024_premonsoon_mean": ndbi_mean,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sentinel-2 NDVI/NDBI seasonal composites (SCL-masked)"
    )
    parser.add_argument("--years", type=int, nargs="+", help="study years")
    parser.add_argument(
        "--season", default="pre-monsoon", choices=sorted(SEASONS)
    )
    parser.add_argument(
        "--sanity-check", action="store_true",
        help="verify auth/scoping and print AOI index means",
    )
    parser.add_argument(
        "--zonal-stats", action="store_true",
        help="per-ward zonal NDVI/NDBI stats, cached to data/processed "
             "(feeds /api/comparison for these layers)",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="recompute years already present in the cache",
    )
    args = parser.parse_args()

    import json

    if args.sanity_check:
        print(json.dumps(sanity_check(), indent=2))
        return

    if args.zonal_stats:
        if not args.years:
            parser.error("--zonal-stats needs --years")
        from backend.etl.analysis import lst_stats

        for index in ("ndvi", "ndbi"):
            payload = lst_stats.compute_yearly_stats(
                args.years, args.season, refresh=args.refresh, layer=index,
                composite=lambda y, s, _idx=index: seasonal_composite(y, s, _idx),
            )
            print(f"{index}: " + json.dumps(
                {y: payload["years"][y]["city"] for y in sorted(payload["years"])}
            ))
        return

    if not args.years:
        parser.error("provide --years, or run with --sanity-check")

    for year in args.years:
        for index in ("ndvi", "ndbi"):
            composite = seasonal_composite(year, args.season, index)
            stats = gee_common.reduce_over_zones(composite, scale=100).getInfo()
            print(f"{year} {args.season} {index}: {stats}")


if __name__ == "__main__":
    main()
