"""POST /api/scenario — what-if estimation for a zone + land-cover deltas."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.etl.analysis import scenario

router = APIRouter()


class ScenarioRequest(BaseModel):
    zone_id: str = Field(
        ...,
        description="Ward number as a string (e.g. \"15\") or \"city\" for the "
        "city-wide mean-baseline estimate",
    )
    veg_delta: float = Field(
        ..., ge=-100, le=100, description="% change in vegetation (baseline NDVI)"
    )
    builtup_delta: float = Field(
        ..., ge=-100, le=100, description="% change in built-up (baseline NDBI)"
    )


class ScenarioResponse(BaseModel):
    zone_id: str
    est_lst_change_c: float
    explanation: dict = Field(
        ...,
        description="Fitted model terms (coefficients, se/t/p, r2, n, equation, "
        "warnings) so the UI can explain WHY the estimate is what it is — "
        "no black-box model.",
    )


@router.post("/api/scenario", response_model=ScenarioResponse)
def estimate_scenario(req: ScenarioRequest, season: str = scenario.DEFAULT_SEASON) -> dict:
    """Estimate dLST (°C) for a zone under vegetation/built-up % deltas.

    The estimate comes from the fitted panel regression
    dLST ~ dNDVI + dNDBI (ward x year deltas, cached stats only — see
    backend/etl/analysis/scenario.py). Slider %s are applied to the zone's
    baseline mean NDVI/NDBI; estimates far outside observed year-to-year
    changes carry explicit warnings in explanation.warnings.
    """
    try:
        return scenario.predict(req.zone_id, req.veg_delta, req.builtup_delta, season)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:  # unknown zone / bad id
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:  # panel too small to fit
        raise HTTPException(503, str(exc)) from exc
