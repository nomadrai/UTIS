"""Analysis: scenario relationship fit dLST ~ dNDVI + dNDBI (task #6).

Methodology (locked 2026-09-23 — "explainable coefficients; no black box"):
    - Panel: ward x year DELTAS across the study period — for each ward and
      each consecutive year pair (same season, per the never-mix-seasons
      rule): dLST = LST_t - LST_{t-1}, likewise dNDVI/dNDBI, joined across
      the three per-layer caches by ward_no (null wards join by order).
    - Fit: ordinary least squares dLST ~ a + b_ndvi * dNDVI + b_ndbi * dNDBI
      with classical standard errors, t-stats, p-values, r², n. Pure numpy
      + scipy.stats — nothing fancier than an intro-stats regression, which
      is the point: the UI can print the actual equation.
    - Interpretation guard: b_ndvi is expected NEGATIVE (vegetation cools),
      b_ndbi POSITIVE (built-up heats). The fit result records whether the
      signs hold; the UI surfaces it rather than hiding it.
    - Prediction: a user slider delta (% vegetation / % built-up change) is
      converted to an index delta relative to that zone's BASELINE mean
      (dNDVI = veg_delta/100 * NDVI_base), then plugged into the fitted
      equation. Estimates far outside the observed dLST range are flagged
      (extrapolation: the linear fit is only trustworthy near observed data).
    - Everything comes from cached ward summaries — zero GEE calls.
"""

from __future__ import annotations

import threading
from typing import Any

import numpy as np

from backend.etl.analysis.lst_stats import load_cached

DEFAULT_SEASON = "pre-monsoon"
MAX_ABS_DLST_C = 5.0        # scenario estimates beyond this are flagged
EXTRAPOLATION_FRAC = 0.5    # |pred| > 0.5 * observed dLST range -> flag

_lock = threading.Lock()
_fit_cache: dict[str, dict] = {}  # season -> fit result


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------
def _series_by_ward(season: str, layer: str) -> dict[Any, dict[str, float]]:
    """{ward_key: {year: mean}} from one layer's cache (null wards: 'n0'..)."""
    cache = load_cached(season, layer)
    if cache is None:
        raise FileNotFoundError(
            f"no cached {layer} stats for {season!r} — run the corresponding "
            "--zonal-stats pull first"
        )
    out: dict[Any, dict[str, float]] = {}
    for year, bundle in sorted(cache.get("years", {}).items()):
        null_i = 0
        for s in bundle["wards"]:
            wn = s["ward_no"]
            if wn is None:
                wn = f"n{null_i}"
                null_i += 1
            if s.get("mean") is not None:
                out.setdefault(wn, {})[year] = s["mean"]
    return out


def build_panel(season: str = DEFAULT_SEASON) -> list[dict]:
    """Ward x year-pair delta rows where all three layers have both years."""
    lst = _series_by_ward(season, "lst")
    ndvi = _series_by_ward(season, "ndvi")
    ndbi = _series_by_ward(season, "ndbi")

    rows: list[dict] = []
    for wn, lst_ts in lst.items():
        nd_ts, nb_ts = ndvi.get(wn, {}), ndbi.get(wn, {})
        years = sorted(set(lst_ts) & set(nd_ts) & set(nb_ts))
        for prev, cur in zip(years, years[1:]):
            rows.append({
                "ward_no": wn if isinstance(wn, int) else None,
                "year_pair": f"{prev}-{cur}",
                "d_lst": lst_ts[cur] - lst_ts[prev],
                "d_ndvi": nd_ts[cur] - nd_ts[prev],
                "d_ndbi": nb_ts[cur] - nb_ts[prev],
            })
    return rows


# ---------------------------------------------------------------------------
# OLS
# ---------------------------------------------------------------------------
def fit_model(panel: list[dict]) -> dict:
    """OLS dLST ~ 1 + dNDVI + dNDBI with classical diagnostics."""
    if len(panel) < 10:
        raise RuntimeError(
            f"scenario panel too small to fit (n={len(panel)}) — run the "
            "zonal-stats pulls for lst+ndvi+ndbi over >= 2 consecutive years"
        )

    y = np.array([r["d_lst"] for r in panel])
    x_ndvi = np.array([r["d_ndvi"] for r in panel])
    x_ndbi = np.array([r["d_ndbi"] for r in panel])
    X = np.column_stack([np.ones_like(x_ndvi), x_ndvi, x_ndbi])

    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    dof = n - k
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    sigma2 = ss_res / dof

    cov = sigma2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    from scipy.stats import t as tdist

    t_stats = beta / se
    p_vals = 2 * tdist.sf(np.abs(t_stats), dof)

    return {
        "coef": {"intercept": float(beta[0]), "ndvi": float(beta[1]), "ndbi": float(beta[2])},
        "se": {"intercept": float(se[0]), "ndvi": float(se[1]), "ndbi": float(se[2])},
        "t": {"intercept": float(t_stats[0]), "ndvi": float(t_stats[1]), "ndbi": float(t_stats[2])},
        "p": {"intercept": float(p_vals[0]), "ndvi": float(p_vals[1]), "ndbi": float(p_vals[2])},
        "r2": float(r2),
        "n": int(n),
        "dof": int(dof),
        "resid_std_k": float(np.sqrt(sigma2)),
        "d_lst_observed_range_k": [float(y.min()), float(y.max())],
        "signs_as_expected": bool(beta[1] < 0 and beta[2] > 0),
    }


def get_fit(season: str = DEFAULT_SEASON, refresh: bool = False) -> dict:
    """Fit result for a season (memoized; refresh recomputes)."""
    with _lock:
        if not refresh and season in _fit_cache:
            return _fit_cache[season]
        panel = build_panel(season)
        fit = fit_model(panel)
        fit["season"] = season
        _fit_cache[season] = fit
        return fit


def model_payload(season: str = DEFAULT_SEASON) -> dict:
    """Everything the WHAT-IF MAP (task #10) needs, in one payload.

    The client computes per-ward predicted dLST locally (no 114 server
    round-trips while sliders move) — so the BACKEND must publish the exact
    inputs, and this endpoint is their single source of truth.

    SEMANTICS (decided 2026-09-24, supersedes the original PLAN sketch):
    the map shows the INTERVENTION EFFECT — the difference vs no-action —
      effect_ward = b_ndvi * (veg_pct/100 * ndvi_base)
                  + b_ndbi * (built_pct/100 * ndbi_base)
    The intercept is EXCLUDED: it captures the study period's average
    year-pair drift (~−0.49 K), so including it would show "do nothing →
    city cools 0.5°" at zero sliders. (predict() keeps the intercept:
    there the question is anchored to the historical panel; on the map the
    anchor is *today*.) Includes the extrapolation thresholds so the map
    can flag extreme wards exactly like the endpoint does.
    """
    fit = get_fit(season)

    def _baselines(series):
        return {
            (wn if isinstance(wn, int) else None):
            (sum(ts.values()) / len(ts) if ts else None)
            for wn, ts in series.items()
        }

    baselines = {
        "ndvi": _baselines(_series_by_ward(season, "ndvi")),
        "ndbi": _baselines(_series_by_ward(season, "ndbi")),
    }
    lo, hi = fit["d_lst_observed_range_k"]
    return {
        "season": season,
        "coef": fit["coef"],
        "effect_semantics": (
            "map shows intervention effect vs no-action: "
            "b_ndvi*dNDVI + b_ndbi*dNDBI (intercept excluded)"
        ),
        "r2": fit["r2"],
        "n": fit["n"],
        "signs_as_expected": fit["signs_as_expected"],
        "d_lst_observed_range_k": [lo, hi],
        "thresholds": {
            "max_abs_dlst_c": MAX_ABS_DLST_C,
            "extrapolation_frac": EXTRAPOLATION_FRAC,
        },
        "ward_baselines": baselines,
        "equation": (
            f"dLST = {fit['coef']['intercept']:+.3f} "
            f"{fit['coef']['ndvi']:+.3f}*dNDVI {fit['coef']['ndbi']:+.3f}*dNDBI (K)"
        ),
    }


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------
def predict(
    zone_id: str,
    veg_delta: float,
    builtup_delta: float,
    season: str = DEFAULT_SEASON,
) -> dict:
    """Estimate LST change (°C) for a zone under slider deltas.

    veg_delta/builtup_delta are PERCENT changes applied to the zone's
    baseline mean NDVI/NDBI (e.g. veg_delta=+20 with baseline NDVI 0.30 ->
    dNDVI = +0.06). Returns the payload for /api/scenario.
    """
    fit = get_fit(season)

    # resolve zone -> baselines (city-wide fallback is NOT offered silently:
    # an unknown id is an error, "city" uses the mean of ward baselines)
    lst_s = _series_by_ward(season, "lst")
    ndvi_s = _series_by_ward(season, "ndvi")
    ndbi_s = _series_by_ward(season, "ndbi")

    if zone_id == "city":
        def _mean_base(series):
            vals = [sum(ts.values()) / len(ts) for ts in series.values() if ts]
            return sum(vals) / len(vals)

        ndvi_base, ndbi_base = _mean_base(ndvi_s), _mean_base(ndbi_s)
        resolved = "city (mean of ward baselines)"
    else:
        try:
            wn: Any = int(zone_id)
        except ValueError:
            raise ValueError(f"zone_id must be a ward number or 'city', got {zone_id!r}")
        if wn not in lst_s or wn not in ndvi_s or wn not in ndbi_s:
            raise ValueError(f"ward {wn} has no complete LST+NDVI+NDBI series for {season!r}")
        ndvi_base = sum(ndvi_s[wn].values()) / len(ndvi_s[wn])
        ndbi_base = sum(ndbi_s[wn].values()) / len(ndbi_s[wn])
        resolved = f"ward {wn}"

    d_ndvi = (veg_delta / 100.0) * ndvi_base
    d_ndbi = (builtup_delta / 100.0) * ndbi_base

    c = fit["coef"]
    d_lst_k = c["intercept"] + c["ndvi"] * d_ndvi + c["ndbi"] * d_ndbi
    d_lst_c = d_lst_k  # a temperature DELTA is identical in K and °C

    lo, hi = fit["d_lst_observed_range_k"]
    observed_span = max(abs(hi), abs(lo))
    warnings = []
    if abs(d_lst_c) > MAX_ABS_DLST_C:
        warnings.append(
            f"estimate |{d_lst_c:.2f}| °C exceeds ±{MAX_ABS_DLST_C} °C — "
            "outside anything observed in the study period; treat as rough"
        )
    if abs(d_lst_c) > EXTRAPOLATION_FRAC * observed_span:
        warnings.append(
            "delta is far from observed year-to-year changes "
            f"(observed range {lo:+.2f}..{hi:+.2f} K) — linear extrapolation"
        )

    return {
        "zone_id": resolved,
        "season": season,
        "baseline": {"ndvi": round(ndvi_base, 4), "ndbi": round(ndbi_base, 4)},
        "deltas": {"d_ndvi": round(d_ndvi, 4), "d_ndbi": round(d_ndbi, 4)},
        "est_lst_change_c": round(d_lst_c, 2),
        "explanation": {
            "equation": "dLST = {intercept:+.3f} {ndvi_sign} {ndvi:.2f}·dNDVI "
                        "{ndbi_sign} {ndbi:.2f}·dNDBI  (K)".format(
                            intercept=c["intercept"],
                            ndvi_sign="+" if c["ndvi"] >= 0 else "-",
                            ndvi=abs(c["ndvi"]),
                            ndbi_sign="+" if c["ndbi"] >= 0 else "-",
                            ndbi=abs(c["ndbi"])),
            "coef": c,
            "se": fit["se"],
            "t": fit["t"],
            "p": fit["p"],
            "r2": fit["r2"],
            "n": fit["n"],
            "signs_as_expected": fit["signs_as_expected"],
            "interpretation": {
                "ndvi": "coefficient < 0 means vegetation gain cools the ward",
                "ndbi": "coefficient > 0 means built-up gain warms the ward",
            },
            "warnings": warnings,
        },
    }
