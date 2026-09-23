"""Analysis: persistent UHI hotspot wards (PLAN.md task #5).

Methodology (locked 2026-09-23/24 — see PLAN.md):
    - A ward is a PERSISTENT HOTSPOT if its within-year LST percentile rank
      is >= `pct` (default 90) in at least `min_year_frac` (default 0.7) of
      the study years with data.
    - Ranks are the within-year percentile ranks already computed by
      lst_stats.add_hotspot_ranks (city-internal, same-year) — a hotspot is
      "hot relative to the city that year", which controls for season but
      also for year-specific weather (a heatwave year shifts everyone).
    - Persistence across years is the signal: a ward hot in one anomalous
      year is noise; hot in 4 of 5 years is the urban fabric.
    - All stats come from the cached per-year summaries
      (data/processed/lst_ward_stats_lst_{season}.json) — no GEE calls.
    - Response is small: ward numbers + supporting stats (+ optional
      geometry). No pixel dumps, per the output policy.
"""

from __future__ import annotations

from typing import Any

from backend.etl.analysis.lst_stats import load_cached

DEFAULT_PCT = 90
DEFAULT_MIN_YEAR_FRAC = 0.7
SUPPORTED_LAYERS = ("lst",)


def detect_hotspots(
    season: str,
    pct: int = DEFAULT_PCT,
    min_year_frac: float = DEFAULT_MIN_YEAR_FRAC,
    layer: str = "lst",
) -> dict:
    """Detect persistent hotspot wards from the cached per-year ranks.

    Returns {season, pct, min_year_frac, years_used, hotspots: [...]} where
    each hotspot carries ward_no, years_hot, n_years, persistence (0..1),
    mean_percentile, mean_lst_k and per-year rank detail.
    """
    if layer not in SUPPORTED_LAYERS:
        raise ValueError(f"hotspots supported for {SUPPORTED_LAYERS} only, not {layer!r}")

    cache = load_cached(season, layer)
    if cache is None:
        raise FileNotFoundError(
            f"no cached {layer} stats for season {season!r} — run "
            "python -m backend.etl.gee_pulls.pull_landsat_lst --zonal-stats first"
        )

    years_data = cache.get("years", {})
    if not years_data:
        return {"season": season, "pct": pct, "min_year_frac": min_year_frac,
                "years_used": [], "hotspots": []}

    # ward_no -> {year: {mean, hotspot_pct}} (null wards join by order)
    per_ward: dict[Any, dict[str, dict]] = {}
    for year, bundle in sorted(years_data.items()):
        null_i = 0
        for s in bundle["wards"]:
            wn = s["ward_no"]
            if wn is None:
                wn = f"n{null_i}"  # stable: wards list is ordered, nulls last
                null_i += 1
            per_ward.setdefault(wn, {})[year] = s

    hotspots = []
    for wn, by_year in per_ward.items():
        valid = {y: s for y, s in by_year.items() if s.get("hotspot_pct") is not None}
        n_years = len(valid)
        if n_years == 0:
            continue
        years_hot = [y for y, s in valid.items() if s["hotspot_pct"] >= pct]
        persistence = len(years_hot) / n_years
        if persistence < min_year_frac:
            continue
        means = [s["mean"] for s in valid.values() if s["mean"] is not None]
        pcts = [s["hotspot_pct"] for s in valid.values()]
        hotspots.append({
            "ward_no": wn if isinstance(wn, int) else None,
            "years_hot": sorted(years_hot),
            "n_years": n_years,
            "persistence": round(persistence, 3),
            "mean_percentile": round(sum(pcts) / len(pcts), 1),
            "mean_lst_k": round(sum(means) / len(means), 2) if means else None,
            "yearly": {
                y: {"mean": s.get("mean"), "hotspot_pct": s.get("hotspot_pct")}
                for y, s in sorted(valid.items())
            },
        })

    hotspots.sort(key=lambda h: (-h["persistence"], -h["mean_percentile"]))
    return {
        "season": season,
        "layer": layer,
        "pct": pct,
        "min_year_frac": min_year_frac,
        "years_used": sorted(years_data.keys()),
        "n_wards_analyzed": len(per_ward),
        "hotspots": hotspots,
    }
