"""
Klein — Route Intelligence Layer API

FastAPI application exposing route scoring and recommendation endpoints.
"""

import logging
import os
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import pydantic
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from klein.engine import KleinEngine, RouteCandidate, RouteRecommendation, ScoredRoute

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="Klein — Route Intelligence Layer", version="1.0.0")

_engine: Optional[KleinEngine] = None


def _get_engine() -> KleinEngine:
    """Get or create the Klein engine singleton."""
    global _engine
    if _engine is None:
        _engine = KleinEngine()
    return _engine


class ScoreRequest(pydantic.BaseModel):
    """Request body for /v1/score endpoint."""
    candidates: List[Dict[str, Any]]
    weights: Optional[Dict[str, float]] = None
    top_n: int = 10


class ScoreResponse(pydantic.BaseModel):
    """Response body for /v1/score endpoint."""
    scored: List[Dict[str, Any]]
    ranked: List[Dict[str, Any]]


class RecommendRequest(pydantic.BaseModel):
    """Request body for /v1/advisory/recommend endpoint."""
    candidates: List[Dict[str, Any]]
    weights: Optional[Dict[str, float]] = None
    workload_type: str = "batch"


class RecommendResponse(pydantic.BaseModel):
    """Response body for /v1/advisory/recommend endpoint."""
    recommendation: Dict[str, Any]


@app.post("/v1/score")
async def score_routes(request: ScoreRequest) -> ScoreResponse:
    """
    Score and rank route candidates.

    Accepts route candidates with latency, cost, carbon, and optional
    reliability metrics. Returns scored and ranked candidates.
    """
    engine = _get_engine()

    if len(request.candidates) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 candidates allowed per request"
        )

    try:
        candidates = [
            RouteCandidate(
                route_id=c["route_id"],
                latency_ms=c["latency_ms"],
                cost_usd=c["cost_usd"],
                carbon_gco2=c["carbon_gco2"],
                reliability_score=c.get("reliability_score"),
                metadata=c.get("metadata", {}),
            )
            for c in request.candidates
        ]
    except KeyError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required field: {e.args[0]}"
        )

    scored = engine.score(candidates, request.weights)
    ranked = engine.rank(scored, top_n=request.top_n)

    return ScoreResponse(
        scored=[asdict(s) for s in scored],
        ranked=[asdict(r) for r in ranked],
    )


@app.post("/v1/advisory/recommend")
async def recommend_route(request: RecommendRequest) -> RecommendResponse:
    """
    Produce a single route recommendation with explanation.

    Advisory only — does not execute routes. Returns top recommendation
    with scoring breakdown and rationale.
    """
    engine = _get_engine()

    if len(request.candidates) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 candidates allowed per request"
        )

    try:
        candidates = [
            RouteCandidate(
                route_id=c["route_id"],
                latency_ms=c["latency_ms"],
                cost_usd=c["cost_usd"],
                carbon_gco2=c["carbon_gco2"],
                reliability_score=c.get("reliability_score"),
                metadata=c.get("metadata", {}),
            )
            for c in request.candidates
        ]
    except KeyError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required field: {e.args[0]}"
        )

    recommendation: RouteRecommendation = engine.recommend(
        candidates,
        request.weights,
        request.workload_type,
    )

    return RecommendResponse(
        recommendation=asdict(recommendation)
    )


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint."""
    engine = _get_engine()
    return {
        "status": "healthy",
        "service": "klein",
        "weights": engine.weights,
    }


@app.exception_handler(Exception)
async def general_error(request: Any, exc: Exception) -> JSONResponse:
    """Global exception handler."""
    logger.exception("Unhandled exception in Klein")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7200")))
