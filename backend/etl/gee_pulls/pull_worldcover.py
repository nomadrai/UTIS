"""GEE data-pull: ESA WorldCover v200 land-cover reference (task #4 completion).

Design (2026-09-24):
    - Collection: ESA/WorldCover/v200 — a SINGLE-YEAR (2021) 10 m
      classification snapshot, NOT annual imagery. It therefore sits
      OUTSIDE the year-selector model: /api/layers pins year=2021 (other
      years are rejected with a clear 400) and the frontend disables the
      year control for this layer.
    - Classes (band "Map", values -> label, legend color):
        10 Tree cover #1a9850, 20 Shrubland #a6d96a, 30 Grassland #ffffbf,
        40 Cropland #d9ef8b, 50 Built-up #d73027, 60 Bare/sparse #fdae61,
        80 Water #2c7bb6, 90 Herbaceous wetland #3288bd, 95 Mangroves
        #5e4fa2, 100 Moss/lichen #bcbddc. Nagpur will realistically show
        cropland/built-up/tree/grass/water only — the full table is kept
        for correctness.
    - Compositing: the dataset is a global mosaic already (one image,
      band "Map"). We clip to the Nagpur polygon (gee_common, AOI policy)
      and provide a class-palette visualization.
    - Zonal stats: per-ward CLASS SHARE (% of ward pixels per class) via a
      pixelArea-weighted grouped reduction — the natural summary for a
      categorical layer (a mean would be meaningless). Cached to
      data/processed/worldcover_ward_stats.json. Server-side only.
"""

from __future__ import annotations

import argparse

from backend.config.settings import DATASETS, GEE_PROJECT_ID
from backend.etl import gee_common

WORLDCOVER_YEAR = 2021  # v200 snapshot year — the only valid year
WC_COLLECTION = DATASETS["worldcover"]

# class value -> (label, legend hex)
CLASSES: dict[int, tuple[str, str]] = {
    10: ("Tree cover", "#1a9850"),
    20: ("Shrubland", "#a6d96a"),
    30: ("Grassland", "#ffffbf"),
    40: ("Cropland", "#d9ef8b"),
    50: ("Built-up", "#d73027"),
    60: ("Bare / sparse", "#fdae61"),
    80: ("Water", "#2c7bb6"),
    90: ("Herbaceous wetland", "#3288bd"),
    95: ("Mangroves", "#5e4fa2"),
    100: ("Moss / lichen", "#bcbddc"),
}

# ordered palette for the tile render (vis params form)
VIS_PARAMS = {
    "bands": "Map",
    "min": 10,
    "max": 100,
    "palette": [c[1] for c in CLASSES.values()],
    # GEE renders categorical data correctly only with an explicit
    # class->color mapping when values are non-contiguous; WorldCover values
    # are 10..100 step 10 (contiguous-ish), so palette order matches.
}


def worldcover_image():
    """The 2021 WorldCover mosaic clipped to the Nagpur polygon."""
    ee = gee_common.get_ee()
    img = ee.ImageCollection(WC_COLLECTION).first().select("Map")
    return gee_common.clip_to_nagpur(img)


def ward_class_shares(scale: int = 30) -> list[dict]:
    """Per-ward class shares (% of ward area) via pixelArea-weighted grouping.

    One server-side grouped reduction over the ward FeatureCollection.
    Returns [{ward_no, shares: {class_value: pct}, dominant: {value, label,
    pct}}] sorted by ward_no (nulls last, ward_no=None).
    """
    ee = gee_common.get_ee()
    from backend.etl.analysis.lst_stats import ward_feature_collection

    img = worldcover_image()
    wards = ward_feature_collection()

    # km² per pixel keyed by class value; the grouped reducer consumes
    # (data=area, group=class) bands and sums area per class.
    area_band = img.select("Map").multiply(
        ee.Image.pixelArea().divide(1e6)
    )
    grouped = area_band.addBands(img.select("Map")).reduceRegions(
        collection=wards,  # ward_no property survives reduceRegions
        reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
        scale=scale,
    )

    raw = grouped.getInfo()["features"]
    out = []
    for feat in raw:
        props = feat["properties"]
        wn = props.get("ward_no")
        wn = None if wn in (None, -1) else wn
        groups = props.get("groups", [])
        total = sum(g["sum"] for g in groups) or 1.0
        shares = {
            int(g["class"]): round(100.0 * g["sum"] / total, 2)
            for g in groups
            if int(g["class"]) in CLASSES
        }
        dom_val = max(shares, key=shares.get) if shares else None
        out.append({
            "ward_no": wn,
            "shares": shares,
            "dominant": (
                {"value": dom_val, "label": CLASSES[dom_val][0], "pct": shares[dom_val]}
                if dom_val is not None else None
            ),
        })
    out.sort(key=lambda r: (r["ward_no"] is None, r["ward_no"] or 0))
    return out


def sanity_check() -> dict:
    """Live probes: image loads, class values present, built-up share sane."""
    ee = gee_common.get_ee()
    img = worldcover_image()
    aoi = gee_common.aoi_geometry()

    hist = (
        img.select("Map")
        .reduceRegion(reducer=ee.Reducer.frequencyHistogram(), geometry=aoi,
                      scale=100, maxPixels=1e9, bestEffort=True)
        .getInfo()
    )["Map"]
    total = sum(hist.values()) or 1.0
    top = sorted(((int(k), 100.0 * v / total) for k, v in hist.items()),
                 key=lambda t: -t[1])[:5]

    return {
        "gee_project_id": GEE_PROJECT_ID,
        "classes_present": {CLASSES[int(k)][0]: round(pct, 1) for k, pct in top},
        "note": "top-5 classes by AOI share (sanity: expect cropland+built-up+tree dominant around Nagpur)",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ESA WorldCover 2021 land cover over Nagpur (task #4)"
    )
    parser.add_argument("--sanity-check", action="store_true",
                        help="print top AOI classes")
    parser.add_argument("--zonal-stats", action="store_true",
                        help="per-ward class shares, cached to data/processed")
    args = parser.parse_args()

    import json

    if args.sanity_check:
        print(json.dumps(sanity_check(), indent=2))
        return

    if args.zonal_stats:
        from backend.config.settings import DATA_PROCESSED_DIR

        rows = ward_class_shares()
        payload = {
            "layer": "landcover",
            "source": "ESA WorldCover v200 (2021 snapshot, 10 m)",
            "year": WORLDCOVER_YEAR,
            "classes": {str(k): v[0] for k, v in CLASSES.items()},
            "wards": rows,
        }
        out = DATA_PROCESSED_DIR / "worldcover_ward_stats.json"
        out.write_text(json.dumps(payload))
        dom = [(r["ward_no"], r["dominant"]["label"], r["dominant"]["pct"]) for r in rows[:6]]
        print(f"wrote {out} ({len(rows)} wards); first few dominant classes: {dom}")
        return

    parser.error("provide --sanity-check or --zonal-stats")


if __name__ == "__main__":
    main()
