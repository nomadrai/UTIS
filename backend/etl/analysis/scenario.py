"""Analysis: what-if scenario estimation.

Planned responsibilities (see PLAN.md task #7):
    - fit empirical NDVI/NDBI ↔ LST relationship on Nagpur's historical data
    - apply per-zone land-cover deltas (slider inputs) to estimate relative
      LST shifts
    - IMPORTANT: relative scenario estimation only — never absolute future
      temperature prediction (see PROJECT.md scope)
"""

from __future__ import annotations


def estimate_scenario(*args, **kwargs):
    raise NotImplementedError("Scenario engine lands with PLAN.md task #7")
