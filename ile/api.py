"""
ILE API — Internal Learning Engine HTTP interface.

Exposes endpoints for recording feedback, querying drift metrics,
and generating learning signals.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ile.engine import ILEEngine, DriftMetrics, LearningSignal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="Anthem ILE", version="1.0.0")

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: Optional[ILEEngine] = None


def _get_engine() -> ILEEngine:
    global _engine
    if _engine is None:
        _engine = ILEEngine()
    return _engine


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class FeedbackEnvelope(BaseModel):
    """Envelope for feedback data."""
    agent_id: str = Field(..., description="The agent that produced this feedback")
    task: str = Field(..., description="The task or capability being evaluated")
    expected_outcome: Optional[Dict[str, Any]] = Field(None, description="Expected result structure")
    actual_outcome: Optional[Dict[str, Any]] = Field(None, description="Actual result produced")
    outcome: str = Field(..., description="High-level outcome classification")
    latency_ms: int = Field(..., description="Execution latency in milliseconds")
    timestamp: Optional[str] = Field(None, description="ISO 8601 timestamp")


class DriftQuery(BaseModel):
    """Query parameters for drift metrics."""
    agent_id: str = Field(..., description="The agent to analyze")
    window_size: int = Field(default=100, ge=1, description="Number of recent samples")
    metric: str = Field(default="combined", description="Which drift metric to compute")


class LearningSignalRequest(BaseModel):
    """Request for generating a learning signal."""
    agent_id: str = Field(..., description="The agent to generate signal for")
    confidence_threshold: float = Field(default=0.7, ge=0, le=1, description="Minimum confidence")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    engine: str
    version: str
    agents_tracked: int
    total_feedback_events: int


class DriftResponse(BaseModel):
    """Drift metrics response."""
    agent_id: str
    window_size: int
    samples_analyzed: int
    outcome_drift: float
    latency_drift: float
    combined_drift: float
    z_score: float
    is_anomaly: bool
    trend: str
    confidence: float


class LearningSignalResponse(BaseModel):
    """Learning signal response."""
    agent_id: str
    signal_type: str
    recommendation: str
    confidence: float
    supporting_evidence: Dict[str, Any]
    requires_governance: bool
    generated_at: str


class FeedbackRecordedResponse(BaseModel):
    """Response after recording feedback."""
    status: str
    agent_id: str
    task: str
    outcome: str
    timestamp: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/v1/learn")
async def learn_endpoint(envelope: FeedbackEnvelope) -> FeedbackRecordedResponse:
    """
    Record a feedback event for drift analysis.

    Accepts an envelope with feedback data including agent_id, task,
    expected vs actual outcome, and latency.
    """
    engine = _get_engine()

    # Parse timestamp
    timestamp = None
    if envelope.timestamp:
        try:
            timestamp = datetime.fromisoformat(envelope.timestamp.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Invalid timestamp format: %s", envelope.timestamp)

    try:
        event = engine.record_feedback(
            agent_id=envelope.agent_id,
            task=envelope.task,
            expected_outcome=envelope.expected_outcome,
            actual_outcome=envelope.actual_outcome,
            outcome=envelope.outcome,
            latency_ms=envelope.latency_ms,
            timestamp=timestamp,
        )

        logger.info(
            "Recorded feedback: agent=%s, task=%s, outcome=%s",
            envelope.agent_id, envelope.task, envelope.outcome
        )

        return FeedbackRecordedResponse(
            status="recorded",
            agent_id=event.agent_id,
            task=event.task,
            outcome=event.outcome,
            timestamp=event.timestamp.isoformat(),
        )

    except Exception as exc:
        logger.exception("Failed to record feedback")
        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {exc}")


@app.post("/v1/drift")
async def drift_endpoint(query: DriftQuery) -> DriftResponse:
    """
    Query drift metrics for a given agent over a time window.

    Returns computed drift metrics including outcome drift, latency drift,
    z-score, and anomaly detection.
    """
    engine = _get_engine()

    try:
        metrics = engine.compute_drift(
            agent_id=query.agent_id,
            window_size=query.window_size,
            metric=query.metric,
        )

        logger.info(
            "Computed drift for %s: combined=%.4f, z_score=%.4f, anomaly=%s",
            query.agent_id, metrics.combined_drift, metrics.z_score, metrics.is_anomaly
        )

        return DriftResponse(
            agent_id=metrics.agent_id,
            window_size=metrics.window_size,
            samples_analyzed=metrics.samples_analyzed,
            outcome_drift=metrics.outcome_drift,
            latency_drift=metrics.latency_drift,
            combined_drift=metrics.combined_drift,
            z_score=metrics.z_score,
            is_anomaly=metrics.is_anomaly,
            trend=metrics.trend,
            confidence=metrics.confidence,
        )

    except Exception as exc:
        logger.exception("Failed to compute drift")
        raise HTTPException(status_code=500, detail=f"Failed to compute drift: {exc}")


@app.post("/v1/signal")
async def signal_endpoint(request: LearningSignalRequest) -> Optional[LearningSignalResponse]:
    """
    Generate a learning signal with parameter adjustment recommendation.

    Produces actionable learning signals when confidence exceeds threshold.
    May return null if no significant signal detected.
    """
    engine = _get_engine()

    try:
        signal = engine.generate_signal(
            agent_id=request.agent_id,
            confidence_threshold=request.confidence_threshold,
        )

        if signal is None:
            logger.debug("No significant learning signal for %s", request.agent_id)
            return None

        logger.info(
            "Generated learning signal for %s: type=%s, governance=%s",
            request.agent_id, signal.signal_type, signal.requires_governance
        )

        return LearningSignalResponse(
            agent_id=signal.agent_id,
            signal_type=signal.signal_type,
            recommendation=signal.recommendation,
            confidence=signal.confidence,
            supporting_evidence=signal.supporting_evidence,
            requires_governance=signal.requires_governance,
            generated_at=signal.generated_at.isoformat(),
        )

    except Exception as exc:
        logger.exception("Failed to generate learning signal")
        raise HTTPException(status_code=500, detail=f"Failed to generate signal: {exc}")


@app.get("/health")
async def health() -> HealthResponse:
    """Health check endpoint."""
    engine = _get_engine()

    total_events = sum(len(events) for events in engine._feedback.values())

    return HealthResponse(
        status="healthy",
        engine="ILE",
        version="1.0.0",
        agents_tracked=len(engine._feedback),
        total_feedback_events=total_events,
    )


@app.exception_handler(Exception)
async def general_error(request, exc: Exception):
    logger.exception("Unhandled exception in ILE")
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "Internal error"}},
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7400")))
