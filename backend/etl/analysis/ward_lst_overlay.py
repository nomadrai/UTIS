"""Visual QA overlay: ward boundaries over the LST composite (PNG).

Purpose: catch registration errors between the ward polygons and the LST
raster — the N-S mirror bug (2026-09-24) was invisible in numeric checks
but obvious as soon as polygons were drawn over satellite heat. Run after
any change to the ward extraction or the LST composite:

    .venv/bin/python -m backend.etl.analysis.ward_lst_overlay

Reads: nagpur_wards.geojson + the GEE composite for one year (median
reduced to a 30 m grid over the AOI bbox — small, city-wide download used
ONLY for QA rendering, never for analysis; the server-side-only rule
applies to the analysis path).
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import Polygon, shape
from shapely.ops import transform as shp_transform

from backend.config.settings import AOI_DIR, DATA_PROCESSED_DIR
from backend.etl import gee_common
from backend.etl.gee_pulls import pull_landsat_lst
from backend.etl.analysis.lst_stats import ZONAL_SCALE, load_wards_geojson

OUT_PNG = DATA_PROCESSED_DIR / "ward_lst_overlay.png"


def _raster(year: int, season: str, step_px: int = 2):
    """LST composite on a coarse pixel grid over the AOI bbox (QA render)."""
    ee = gee_common.get_ee()
    composite = pull_landsat_lst.seasonal_composite(year, season)
    w, s, e, n = gee_common.aoi_bbox_wsen()
    region = ee.Geometry.Rectangle([w, s, e, n])
    # sampleScale in meters per pixel; step_px coarsens the 30 m grid for speed
    url = composite.getThumbURL({
        "bands": "LST_K",
        "min": 295.0,
        "max": 320.0,
        "palette": ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"],
        "region": region,
        "dimensions": 1024,
        "format": "png",
    })
    import urllib.request

    png_path = DATA_PROCESSED_DIR / "_lst_thumb.png"
    urllib.request.urlretrieve(url, png_path)

    import matplotlib.image as mpimg

    return mpimg.imread(png_path), (w, s, e, n)


def main(year: int = 2024, season: str = "pre-monsoon") -> None:
    fc = load_wards_geojson()
    img, (w, s, e, n) = _raster(year, season)

    fig, ax = plt.subplots(figsize=(11, 10))
    ax.imshow(img, extent=[w, e, s, n], origin="upper")

    # ward fill = per-ward mean LST percentile (same semantics as the app)
    stats = None
    cache = DATA_PROCESSED_DIR / f"lst_ward_stats_{season}.json"
    if cache.exists():
        payload = json.loads(cache.read_text())
        stats = payload["years"].get(str(year), {}).get("wards")

    def pct_color(pct):
        if pct is None:
            return (0.5, 0.5, 0.5, 0.15)
        ramp = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"]
        i = min(len(ramp) - 1, int(pct / 100 * len(ramp)))
        r = matplotlib.colors.to_rgb(ramp[i])
        return (*r, 0.28)

    for f in fc["features"]:
        geom = shape(f["geometry"])
        if isinstance(geom, Polygon):
            geoms = [geom]
        else:
            geoms = list(geom.geoms)
        s_prop = next(
            (s for s in (stats or []) if s["ward_no"] == f["properties"]["ward_no"]),
            None,
        ) if stats else None
        facecolor = pct_color(s_prop["hotspot_pct"] if s_prop else None)
        for g in geoms:
            xs, ys = g.exterior.xy
            ax.fill(xs, ys, facecolor=facecolor, edgecolor="black", linewidth=0.4)
            for hole in g.interiors:
                hx, hy = hole.xy
                ax.fill(hx, hy, color="white", alpha=0.9, linewidth=0)

    wn_label = next(
        (f for f in fc["features"] if f["properties"]["ward_no"] == 15), None
    )
    ax.set_title(
        f"QA overlay: ward boundaries vs LST composite — {year} {season}\n"
        f"(basemap: GEE LST median composite; fills: ward hotspot percentile)"
    )
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150)
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
