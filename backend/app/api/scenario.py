"""POST /api/scenario — what-if estimation for a zone + land-cover deltas."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class ScenarioRequest(BaseModel):
    zone_id: str = Field(..., description="Zone/ward inside the Nagpur polygon")
    veg_delta: float = Field(..., ge=-100, le=100, description="% change in vegetation")
    builtup_delta: float = Field(..., ge=-100, le=100, description="% change in built-up")


class ScenarioResponse(BaseModel):
    zone_id: str
    est_lst_change_c: float
    explanation: dict = Field(
        ...,
        description="Fitted model terms (coefficients, r2, n) so the UI can "
        "explain WHY the estimate is what it is — no black-box model.",
    )


@router.post("/api/scenario", response_model=ScenarioResponse)
def estimate_scenario(req: ScenarioRequest) -> ScenarioResponse:
    raise NotImplementedError("Scenario endpoint lands with PLAN.md task #7")
