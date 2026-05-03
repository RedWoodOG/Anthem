"""
BUE API — Business Underwriting Engine service.
FastAPI app that runs BUE as a Luna-hosted agent with real Monte Carlo tools.
"""

import logging
import os

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from anthem_common.schemas import Envelope, NormalizedResult
from anthem_common.harness import (
    AgentHarness, ToolRegistry, ToolDefinition,
    load_agent_identity,
)
from bue.simulation.monte_carlo import (
    MonteCarloSimulator, SimulationInputs,
    handle_monte_carlo_simulate,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Anthem BUE", version="1.0.0")


# ---------------------------------------------------------------------------
# Direct tool endpoint (for broker adapter calls without full agent loop)
# ---------------------------------------------------------------------------

class UnderwriteRequest(BaseModel):
    """Direct underwriting request."""
    business_name: str
    current_revenue: float = Field(gt=0)
    industry: str = "general"
    growth_rate: Optional[float] = None
    volatility: Optional[float] = None
    operating_margin: Optional[float] = None
    revenue_history: Optional[List[float]] = None
    horizon_years: int = Field(default=5, ge=1, le=30)
    n_simulations: int = Field(default=10_000, ge=1_000, le=100_000)


@app.post("/v1/underwrite")
async def underwrite(request: UnderwriteRequest) -> Dict[str, Any]:
    """
    Run Monte Carlo underwriting on a business.
    Returns real distribution statistics and risk metrics.
    """
    # Use industry taxonomy defaults as priors if not provided
    from bue.simulation.taxonomy import get_industry_defaults
    defaults = get_industry_defaults(request.industry)

    inputs = SimulationInputs(
        current_revenue=request.current_revenue,
        growth_rate=request.growth_rate or defaults.get("growth_rate", 0.04),
        volatility=request.volatility or defaults.get("volatility", 0.18),
        operating_margin=request.operating_margin or defaults.get("operating_margin", 0.18),
        revenue_history=request.revenue_history,
        n_simulations=request.n_simulations,
        horizon_years=request.horizon_years,
    )

    simulator = MonteCarloSimulator()
    result = simulator.simulate(inputs)

    using_defaults = []
    if request.growth_rate is None:
        using_defaults.append("growth_rate")
    if request.volatility is None:
        using_defaults.append("volatility")
    if request.operating_margin is None:
        using_defaults.append("operating_margin")

    return {
        "business_name": request.business_name,
        "industry": request.industry,
        "underwriting": result.to_dict(),
        "data_quality": {
            "using_industry_defaults_for": using_defaults,
            "calibrated_from_history": bool(
                request.revenue_history and len(request.revenue_history) >= 3
            ),
            "warning": (
                "Some parameters use industry-average priors, not company-specific data"
                if using_defaults else None
            ),
        },
    }


@app.post("/v1/analyze")
async def analyze(envelope: Envelope) -> NormalizedResult:
    """
    Broker-compatible endpoint. Accepts Envelope, returns NormalizedResult.
    """
    payload = envelope.payload
    if "current_revenue" not in payload:
        return NormalizedResult(
            data=None,
            success=False,
            error={"code": "MISSING_FIELD", "message": "current_revenue required", "category": "client"},
        )

    result = await handle_monte_carlo_simulate(payload)

    return NormalizedResult(
        data=result,
        traces={
            "capability_id": "bue.underwrite",
            "request_id": envelope.request_id,
        },
        governance=envelope.governance,
    )


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "bue", "version": "1.0.0"}
