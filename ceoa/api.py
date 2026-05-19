"""
CEOA API — Compute Energy Orchestration API

FastAPI application exposing carbon-aware workload scheduling.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ceoa.engine import (
    CEOAEngine,
    Workload,
    WorkloadType,
    OptimizationGoal,
    PlacementResult,
    OptimizationResult,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="CEOA — Compute Energy Orchestration API", version="1.0.0")

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: Optional[CEOAEngine] = None


def _get_engine() -> CEOAEngine:
    """Get or create the CEOA engine singleton."""
    global _engine
    if _engine is None:
        _engine = CEOAEngine()
        logger.info("CEOA Engine initialized")
    return _engine


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class WorkloadRequest(BaseModel):
    """Request to schedule a workload."""
    workload_id: str = Field(..., description="Unique workload identifier")
    workload_type: str = Field(
        ...,
        description="Workload type: batch, interactive, latency-sensitive, flexible"
    )
    compute_requirements: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Compute requirements (cpu_cores, memory_gb, gpu)"
    )
    regions: Optional[List[str]] = Field(
        default=None,
        description="Candidate regions (optional)"
    )
    max_cost_per_hour: Optional[float] = Field(
        default=None,
        description="Maximum cost per hour in USD"
    )
    optimization_goal: Optional[str] = Field(
        default="balanced",
        description="Optimization goal: min-carbon, min-cost, balanced, latency-priority"
    )


class WorkloadResponse(BaseModel):
    """Response from workload scheduling."""
    workload_id: str
    region_id: str
    region_name: str
    carbon_intensity: float
    cost_per_hour: float
    score: float
    explanation: str


class OptimizeRequest(BaseModel):
    """Request to optimize multiple workloads."""
    workloads: List[Dict[str, Any]] = Field(
        ...,
        description="List of workloads to optimize"
    )
    optimization_goal: str = Field(
        ...,
        description="Optimization goal: min-carbon, min-cost, balanced, latency-priority"
    )
    max_regions: Optional[int] = Field(
        default=None,
        description="Maximum number of regions to use"
    )


class OptimizeResponse(BaseModel):
    """Response from optimization."""
    placements: List[WorkloadResponse]
    total_carbon_score: float
    total_cost: float
    explanation: str


class CarbonIntensityResponse(BaseModel):
    """Response with carbon intensity data."""
    regions: Dict[str, Dict[str, Any]]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    engine: str
    regions_available: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/ceoa/v1/workloads", response_model=WorkloadResponse)
async def schedule_workload(request: WorkloadRequest) -> WorkloadResponse:
    """
    Schedule a compute workload to the best region.
    
    Selects optimal region based on carbon intensity, cost, and workload requirements.
    """
    engine = _get_engine()
    
    # Parse workload type
    try:
        workload_type = WorkloadType(request.workload_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid workload_type: {request.workload_type}. "
                   f"Valid values: {[wt.value for wt in WorkloadType]}"
        )
    
    # Parse optimization goal
    try:
        goal = OptimizationGoal(request.optimization_goal) if request.optimization_goal else OptimizationGoal.BALANCED
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid optimization_goal: {request.optimization_goal}"
        )
    
    # Build workload object
    compute_req = request.compute_requirements or {}
    workload = Workload(
        workload_id=request.workload_id,
        workload_type=workload_type,
        cpu_cores=compute_req.get("cpu_cores", 4),
        memory_gb=compute_req.get("memory_gb", 16.0),
        gpu_required=compute_req.get("gpu", False),
        max_cost_per_hour=request.max_cost_per_hour,
    )
    
    try:
        result = engine.schedule(
            workload=workload,
            candidate_regions=request.regions,
            goal=goal
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid workload request")
    
    logger.info(
        f"Scheduled workload {request.workload_id} to {result.region_id} "
        f"(carbon: {result.carbon_intensity:.0f} gCO2/kWh, score: {result.score:.3f})"
    )
    
    return WorkloadResponse(
        workload_id=result.workload_id,
        region_id=result.region_id,
        region_name=result.region_name,
        carbon_intensity=result.carbon_intensity,
        cost_per_hour=result.cost_per_hour,
        score=result.score,
        explanation=result.explanation
    )


@app.post("/ceoa/v1/placement/optimize", response_model=OptimizeResponse)
async def optimize_placement(request: OptimizeRequest) -> OptimizeResponse:
    """
    Optimize placement of multiple workloads across regions.
    
    Distributes workloads to minimize aggregate carbon/cost.
    """
    engine = _get_engine()
    
    # Parse optimization goal
    try:
        goal = OptimizationGoal(request.optimization_goal)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid optimization_goal: {request.optimization_goal}"
        )
    
    # Build workload objects
    workloads: List[Workload] = []
    for idx, w in enumerate(request.workloads):
        try:
            workload_type = WorkloadType(w.get("workload_type", "flexible"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid workload_type for workload {idx}: {w.get('workload_type')}"
            )
        
        compute_req = w.get("compute_requirements", {})
        workload = Workload(
            workload_id=w.get("workload_id", f"workload-{idx}"),
            workload_type=workload_type,
            cpu_cores=compute_req.get("cpu_cores", 4),
            memory_gb=compute_req.get("memory_gb", 16.0),
            gpu_required=compute_req.get("gpu", False),
            priority=w.get("priority", 1),
        )
        workloads.append(workload)
    
    result = engine.optimize(
        workloads=workloads,
        goal=goal,
        max_regions=request.max_regions
    )
    
    logger.info(
        f"Optimized {len(workloads)} workloads: "
        f"total carbon {result.total_carbon_score:.0f}, cost ${result.total_cost:.3f}/hr"
    )
    
    return OptimizeResponse(
        placements=[
            WorkloadResponse(
                workload_id=p.workload_id,
                region_id=p.region_id,
                region_name=p.region_name,
                carbon_intensity=p.carbon_intensity,
                cost_per_hour=p.cost_per_hour,
                score=p.score,
                explanation=p.explanation
            )
            for p in result.placements
        ],
        total_carbon_score=result.total_carbon_score,
        total_cost=result.total_cost,
        explanation=result.explanation
    )


@app.get("/ceoa/v1/carbon-intensity", response_model=CarbonIntensityResponse)
async def query_carbon_intensity(regions: Optional[List[str]] = None) -> CarbonIntensityResponse:
    """
    Get current carbon intensity for regions.
    
    Returns carbon data for all known regions or specified subset.
    """
    engine = _get_engine()
    region_data = engine.get_carbon_intensity(regions)
    
    return CarbonIntensityResponse(regions=region_data)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    engine = _get_engine()
    return HealthResponse(
        status="healthy",
        engine="CEOA",
        regions_available=len(engine.region_data)
    )


@app.exception_handler(Exception)
async def general_error(request, exc: Exception):
    """Global exception handler."""
    logger.exception("Unhandled exception in CEOA")
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7100")))
