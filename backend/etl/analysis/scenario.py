"""Analysis: what-if scenario estimation.

Design (agreed 2026-09-23 — see PLAN.md):
    - Fit a simple, EXPLAINABLE statistical relationship between historical
      NDVI/NDBI change and LST change WITHIN the Nagpur polygon (e.g. OLS on
      zonal values: dLST ~ a*dNDVI + b*dNDBI + c), using year-pairs.
    - The scenario endpoint applies this fitted relationship to a hypothetical
      land-cover delta (e.g. -10% vegetation in zone X) and returns an
      estimated LST change PLUS the model terms, so the response can explain
      WHY the estimate is what it is.
    - Explicitly a black-box-free approach: linear, inspectable coefficients.
    - Hard scope rule: relative scenario estimation only — never absolute
      future temperature prediction (see PROJECT.md).
"""

from __future__ import annotations


def fit_lst_relationship(yearly_lst: dict, yearly_indices: dict) -> dict:
    """Fit dLST ~ a*dNDVI + b*dNDBI + c on historical year-pairs.

    Returns dict with coefficients a/b/c, r2, n, and diagnostics — the
    payload the API uses to explain estimates to the user.
    """
    raise NotImplementedError("Relationship fit lands with PLAN.md task #6")


def estimate_scenario(zone_id: str, veg_delta: float, builtup_delta: float) -> dict:
    """Apply the fitted relationship to a hypothetical zone-level delta.

    Returns the estimated LST change for the zone and the explanation terms.
    """
    raise NotImplementedError("Scenario estimation lands with PLAN.md task #6")
