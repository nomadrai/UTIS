"""GET /api/hotspots — persistent UHI hotspot wards for the study period."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.etl.analysis import hotspots
from backend.etl.analysis.lst_stats import load_wards_geojson

router = APIRouter()


@router.get("/api/hotspots")
def get_hotspots(
    pct: int = hotspots.DEFAULT_PCT,
    min_year_frac: float = hotspots.DEFAULT_MIN_YEAR_FRAC,
    season: str = "pre-monsoon",
    with_geometry: bool = False,
) -> dict:
    """Return persistent hotspot wards as a GeoJSON FeatureCollection.

    Detection contract (agreed 2026-09-23, methodology in
    backend/etl/analysis/hotspots.py):
        - a ward is a persistent hotspot if its within-year percentile rank
          is >= `pct` in >= `min_year_frac` of the study years with data
        - default pct=90, min_year_frac=0.7 → "top-10% in at least 4 of 5
          years" — persistence is the signal, single-year heat is noise
        - response is small (ward numbers + stats) — never raw pixel dumps
        - geometry: null by default (the client joins ward_no to /api/wards);
          with_geometry=true embeds the ward polygons for standalone use
    """
    if not (50 <= pct <= 99):
        raise HTTPException(400, "pct must be an integer in 50..99")
    if not (0 < min_year_frac <= 1.0):
        raise HTTPException(400, "min_year_frac must be in (0, 1]")

    try:
        result = hotspots.detect_hotspots(season, pct, min_year_frac)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    geom_by_ward: dict | None = None
    if with_geometry:
        fc = load_wards_geojson()
        geom_by_ward = {
            f["properties"]["ward_no"]: f["geometry"]
            for f in fc["features"]
            if f["properties"]["ward_no"] is not None
        }

    features = []
    for h in result["hotspots"]:
        wn = h["ward_no"]
        features.append({
            "type": "Feature",
            "properties": {
                "ward_no": wn,
                "years_hot": h["years_hot"],
                "n_years": h["n_years"],
                "persistence": h["persistence"],
                "mean_percentile": h["mean_percentile"],
                "mean_lst_k": h["mean_lst_k"],
                "yearly": h["yearly"],
            },
            "geometry": geom_by_ward.get(wn) if geom_by_ward else None,
        })

    return {
        "type": "FeatureCollection",
        "name": "persistent_hotspot_wards",
        "detection": {
            k: result[k]
            for k in ("season", "layer", "pct", "min_year_frac", "years_used", "n_wards_analyzed")
        },
        "features": features,
        "note": "percentile ranks are within-year, city-internal; persistence "
                "across years is the signal (methodology in "
                "backend/etl/analysis/hotspots.py)",
    }
