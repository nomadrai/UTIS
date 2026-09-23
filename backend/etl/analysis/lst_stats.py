"""Analysis: per-ward zonal LST statistics (PLAN.md task #3).

Design (agreed 2026-09-23/24, see PLAN.md):
    - Zones: the 114 georeferenced CIS-2005 wards in
      backend/config/aoi/nagpur_wards.geojson (ward_no=null for the 13
      wards whose numbers were never printed on the source map).
    - Imagery: seasonal median composites from pull_landsat_lst — the SAME
      composite function the map layer uses, so stats and render agree.
    - Compute: server-side only. One reduceRegions (mean + p95, shared
      inputs) over the ward FeatureCollection per (year, season). No pixel
      dumps ever leave GEE.
    - Scale: 100 m sampling — the ST_B10 grid is 30 m, but ward MEANS at
      0.5–2 km² ward size are stable at 100 m and the reduction is ~10x
      cheaper. bestEffort lets GEE coarsen further for tiny wards.
    - Hotspot semantics: hotspot rank is a PERCENTILE rank of the ward mean
      within the year (city-internal), never a fixed °C cutoff — seasonal
      composites control for season, not year-specific weather.
    - Cache: data/processed/lst_ward_stats_{season}.json, keyed by year.
      Endpoints read the cache; the ETL CLI recomputes it.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config.settings import AOI_DIR, DATA_PROCESSED_DIR, SEASONS
from backend.etl import gee_common
from backend.etl.gee_pulls import pull_landsat_lst

WARDS_PATH = AOI_DIR / "nagpur_wards.geojson"

# Sampling resolution (meters) for per-ward reductions — see module docstring.
ZONAL_SCALE = 100

DEFAULT_SEASON = "pre-monsoon"  # UHI-peak window, per settings.SEASONS comment


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------
def load_wards_geojson() -> dict:
    """Load + validate the ward FeatureCollection (cached at module level)."""
    global _wards_cache
    if _wards_cache is None:
        with open(WARDS_PATH) as f:
            fc = json.load(f)
        feats = fc.get("features", [])
        if not feats:
            raise RuntimeError(
                f"{WARDS_PATH} has no features — run "
                "python -m backend.etl.wards_from_pdf first"
            )
        _wards_cache = fc
    return _wards_cache


_wards_cache: dict | None = None


def ward_feature_collection() -> Any:
    """The 114 wards as an ee.FeatureCollection (property: ward_no).

    Unlabeled wards (ward_no=None in the file) get sentinel -1 server-side —
    ee.Feature properties can't be null — and are mapped back to None on the
    returned summaries.
    """
    ee = gee_common.get_ee()
    fc = load_wards_geojson()
    feats = [
        ee.Feature(
            f["geometry"],
            {"ward_no": f["properties"].get("ward_no") if
             f["properties"].get("ward_no") is not None else -1},
        )
        for f in fc["features"]
    ]
    return ee.FeatureCollection(feats)


# ---------------------------------------------------------------------------
# Zonal reduction
# ---------------------------------------------------------------------------
def ward_year_stats(year: int, season: str = DEFAULT_SEASON) -> list[dict]:
    """Per-ward {ward_no, mean, p95} for one year's seasonal composite.

    One server-side reduceRegions call for all wards (mean + 95th pct,
    shared inputs). Unlabeled wards come back with ward_no=None.
    """
    ee = gee_common.get_ee()
    composite = pull_landsat_lst.seasonal_composite(year, season)
    wards = ward_feature_collection()

    reducer = ee.Reducer.mean().combine(
        ee.Reducer.percentile([95]), sharedInputs=True
    )
    reduced = composite.reduceRegions(
        collection=wards, reducer=reducer, scale=ZONAL_SCALE
    )

    raw = reduced.getInfo()["features"]
    stats = []
    for feat in raw:
        props = feat["properties"]
        wn = props.get("ward_no")
        stats.append({
            "ward_no": None if wn in (None, -1) else wn,
            "mean": props.get("mean"),
            "p95": props.get("p95"),
        })
    stats.sort(key=lambda s: (s["ward_no"] is None, s["ward_no"] or 0))
    return stats


def add_hotspot_ranks(stats: list[dict]) -> list[dict]:
    """Annotate each ward with its within-year percentile rank (0-100).

    Computed in Python from the small per-ward summaries — hotspot status
    is relative to the city in the SAME year/season, per the percentile-
    rank methodology (never fixed °C cutoffs).
    """
    valid = [s for s in stats if s["mean"] is not None]
    ranked = sorted(valid, key=lambda s: s["mean"])
    n = len(ranked)
    for i, s in enumerate(ranked):
        s["hotspot_pct"] = round(i / (n - 1) * 100, 1) if n > 1 else 100.0
    for s in stats:
        s.setdefault("hotspot_pct", None)
    return stats


def city_wide_stats(stats: list[dict]) -> dict:
    """Area-weighted-ish city summary from the ward means (unweighted mean
    of ward means + city max)."""
    means = [s["mean"] for s in stats if s["mean"] is not None]
    if not means:
        return {"mean": None, "max": None, "n_wards": len(stats)}
    return {
        "mean": round(sum(means) / len(means), 2),
        "max": round(max(s["p95"] for s in stats if s["p95"] is not None), 2),
        "n_wards": len(stats),
    }


# ---------------------------------------------------------------------------
# Cache + yearly aggregation
# ---------------------------------------------------------------------------
def _cache_path(season: str) -> Path:
    return DATA_PROCESSED_DIR / f"lst_ward_stats_{season}.json"


def load_cached(season: str = DEFAULT_SEASON) -> dict | None:
    """Return the cached stats file for a season, or None."""
    path = _cache_path(season)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def compute_yearly_stats(
    years: list[int], season: str = DEFAULT_SEASON, refresh: bool = False
) -> dict:
    """{year: {wards: [...], city: {...}}} for the requested years.

    Uses/extends the on-disk cache; only missing (or refresh=True) years
    hit GEE. Same-season rule enforced: every year uses the same `season`
    window (settings.SEASONS).
    """
    if season not in SEASONS:
        raise ValueError(f"unknown season {season!r}; use {list(SEASONS)}")

    cached = load_cached(season) or {"season": season, "years": {}}
    years_out: dict = dict(cached.get("years", {}))

    for year in years:
        if not refresh and str(year) in years_out:
            continue
        stats = add_hotspot_ranks(ward_year_stats(year, season))
        years_out[str(year)] = {
            "wards": stats,
            "city": city_wide_stats(stats),
        }

    payload = {
        "layer": "lst",
        "season": season,
        "units": "Kelvin",
        "zonal_scale_m": ZONAL_SCALE,
        "source": "Landsat 8/9 C2 L2 ST_B10 seasonal median composite",
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "years": years_out,
    }
    _cache_path(season).parent.mkdir(parents=True, exist_ok=True)
    with open(_cache_path(season), "w") as f:
        json.dump(payload, f)
    return payload


def yearly_stats(yearly_images: dict, zones=None) -> dict:
    """Back-compat signature from the original stub: {layer: {year: stats}}.

    `yearly_images` maps year -> ee.Image (or int years; composites are
    built internally either way). Real entry point for the API is
    compute_yearly_stats().
    """
    season = DEFAULT_SEASON
    years = sorted(int(y) for y in yearly_images)
    payload = compute_yearly_stats(years, season)
    return {"lst": payload["years"]}
