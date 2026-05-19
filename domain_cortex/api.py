"""
Domain Cortex API — Cross-Domain Synthesis Service.

FastAPI application that aggregates results from multiple agents
and produces unified synthesis reports.
"""

import logging
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from anthem_common.harness import (
    AgentHarness,
    load_agent_identity,
    load_tool_definitions,
    ToolRegistry,
    ToolDefinition,
)
from anthem_common.schemas import Envelope, NormalizedResult, ErrorDetail

from domain_cortex.engine import DomainCortexEngine, SynthesisReport

logger = logging.getLogger(__name__)

app = FastAPI(title="Anthem Domain Cortex", version="1.0.0")


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class AgentResult(BaseModel):
    """A single agent result for synthesis."""
    agent_id: str = Field(..., description="Source agent identifier")
    result: Dict[str, Any] = Field(..., description="NormalizedResult content")
    timestamp: str = Field(default=None, description="ISO timestamp of result")


class SynthesizeRequest(BaseModel):
    """Request to synthesize multiple agent results."""
    results: List[AgentResult] = Field(
        ...,
        description="List of agent results to synthesize",
        min_length=1,
        max_length=10
    )
    synthesis_mode: str = Field(
        default="weighted",
        description="Synthesis mode: consensus, weighted, or comparative"
    )


class SynthesizeResponse(BaseModel):
    """Response from synthesis endpoint."""
    contributing_agents: List[str] = Field(
        ...,
        description="List of agents that contributed to synthesis"
    )
    aggregated_metrics: Dict[str, Any] = Field(
        ...,
        description="Aggregated metrics from all agents"
    )
    contradictions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Detected contradictions between agents"
    )
    correlations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Cross-domain correlations found"
    )
    overall_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence score"
    )
    summary: str = Field(..., description="Human-readable synthesis summary")
    timestamp: str = Field(..., description="ISO timestamp of synthesis")


# ---------------------------------------------------------------------------
# Harness initialization
# ---------------------------------------------------------------------------


_harness: AgentHarness = None
_engine: DomainCortexEngine = None
_tool_registry: ToolRegistry = None


def _get_harness() -> AgentHarness:
    """Get or create the agent harness."""
    global _harness
    if _harness is None:
        identity = load_agent_identity("domain-cortex")
        _harness = AgentHarness(identity)
        logger.info("Domain Cortex harness initialized")
    return _harness


def _get_engine() -> DomainCortexEngine:
    """Get or create the synthesis engine."""
    global _engine
    if _engine is None:
        _engine = DomainCortexEngine(max_results=10)
        logger.info("Domain Cortex engine initialized")
    return _engine


def _get_tool_registry() -> ToolRegistry:
    """Get or create the tool registry."""
    global _tool_registry
    if _tool_registry is None:
        identity = load_agent_identity("domain-cortex")
        tool_defs = load_tool_definitions("domain-cortex")
        _tool_registry = ToolRegistry(identity, tool_defs)
        logger.info("Domain Cortex tool registry initialized")
    return _tool_registry


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/v1/synthesize", response_model=SynthesizeResponse)
async def synthesize(request: SynthesizeRequest) -> SynthesizeResponse:
    """
    Synthesize results from multiple specialist agents.
    
    Accepts an envelope with a list of agent results and produces
    a unified synthesis report with aggregated metrics, detected
    contradictions, and cross-domain correlations.
    
    Args:
        request: SynthesizeRequest with agent results
        
    Returns:
        SynthesizeResponse with unified synthesis
        
    Raises:
        HTTPException: If synthesis fails
    """
    try:
        engine = _get_engine()
        harness = _get_harness()
        
        # Convert request to engine format
        results = []
        for agent_result in request.results:
            result_dict = {
                "agent_id": agent_result.agent_id,
                **agent_result.result,
            }
            if agent_result.timestamp:
                result_dict["timestamp"] = agent_result.timestamp
            results.append(result_dict)
        
        # Run synthesis
        report = engine.aggregate(results)
        
        # Log to harness event stream
        harness.log_event(
            event_type="synthesis",
            details={
                "contributing_agents": report.contributing_agents,
                "contradictions_count": len(report.contradictions),
                "correlations_count": len(report.correlations),
                "confidence": report.overall_confidence
            }
        )
        
        # Convert contradictions to dicts
        contradictions = [
            {
                "agent_a": c.agent_a,
                "agent_b": c.agent_b,
                "claim_a": c.claim_a,
                "claim_b": c.claim_b,
                "domain": c.domain,
                "severity": c.severity,
                "confidence": c.confidence
            }
            for c in report.contradictions
        ]
        
        # Convert correlations to dicts
        correlations = [
            {
                "agents": corr.agents,
                "description": corr.description,
                "strength": corr.strength,
                "correlation_type": corr.correlation_type,
                "domains": corr.domains
            }
            for corr in report.correlations
        ]
        
        return SynthesizeResponse(
            contributing_agents=report.contributing_agents,
            aggregated_metrics=report.aggregated_metrics,
            contradictions=contradictions,
            correlations=correlations,
            overall_confidence=report.overall_confidence,
            summary=report.summary,
            timestamp=report.timestamp.isoformat()
        )
        
    except ValueError as e:
        logger.error(f"Synthesis validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid synthesis request")
    except Exception as e:
        logger.error(f"Synthesis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Synthesis failed")


@app.post("/v1/agent")
async def agent_endpoint(envelope: Envelope) -> NormalizedResult:
    """
    Standard agent endpoint powered by the harness.
    
    Processes synthesis tasks through the Domain Cortex engine.
    """
    try:
        harness = _get_harness()
        engine = _get_engine()
        
        # Execute through harness
        result = harness.execute(
            task="synthesis",
            params={"envelope": envelope.model_dump()}
        )
        
        # If result contains agent results, synthesize them
        if result and isinstance(result, dict):
            agent_results = result.get("agent_results", [])
            if agent_results:
                synthesis = engine.aggregate(agent_results)
                return NormalizedResult(
                    data={
                        "synthesis": {
                            "contributing_agents": synthesis.contributing_agents,
                            "aggregated_metrics": synthesis.aggregated_metrics,
                            "contradictions": [
                                {
                                    "agent_a": c.agent_a,
                                    "agent_b": c.agent_b,
                                    "claim_a": c.claim_a,
                                    "claim_b": c.claim_b,
                                    "domain": c.domain,
                                    "severity": c.severity
                                }
                                for c in synthesis.contradictions
                            ],
                            "correlations": [
                                {
                                    "agents": corr.agents,
                                    "description": corr.description,
                                    "strength": corr.strength,
                                    "correlation_type": corr.correlation_type
                                }
                                for corr in synthesis.correlations
                            ]
                        },
                        "confidence": synthesis.overall_confidence,
                        "summary": synthesis.summary
                    },
                    traces={"agent_id": "domain-cortex", "task": "synthesis"},
                    success=True,
                )
        
        return NormalizedResult(
            data=result or {},
            traces={"agent_id": "domain-cortex", "task": "synthesis"},
            success=True,
        )
        
    except Exception as e:
        logger.error(f"Agent endpoint failed: {e}", exc_info=True)
        return NormalizedResult(
            data={},
            success=False,
            error=ErrorDetail(
                code="SYNTHESIS_FAILED",
                message="Synthesis failed",
                category="server",
            ),
            traces={"agent_id": "domain-cortex", "task": "synthesis"},
        )


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "domain-cortex",
        "version": "1.0.0"
    }


# ---------------------------------------------------------------------------
# Tool handlers (for direct tool calls via broker)
# ---------------------------------------------------------------------------


async def _handle_aggregate_results(params: Dict[str, Any]) -> Dict[str, Any]:
    """Tool handler for aggregate_results."""
    engine = _get_engine()
    results = params.get("results", [])
    
    report = engine.aggregate(results)
    
    return {
        "contributing_agents": report.contributing_agents,
        "aggregated_metrics": report.aggregated_metrics,
        "contradictions_count": len(report.contradictions),
        "correlations_count": len(report.correlations),
        "overall_confidence": report.overall_confidence,
        "summary": report.summary
    }


async def _handle_find_correlations(params: Dict[str, Any]) -> Dict[str, Any]:
    """Tool handler for find_correlations."""
    engine = _get_engine()
    results = params.get("results", [])
    
    correlations = engine.find_correlations(results)
    
    return {
        "correlations": [
            {
                "agents": corr.agents,
                "description": corr.description,
                "strength": corr.strength,
                "correlation_type": corr.correlation_type,
                "domains": corr.domains
            }
            for corr in correlations
        ]
    }


async def _handle_flag_contradictions(params: Dict[str, Any]) -> Dict[str, Any]:
    """Tool handler for flag_contradictions."""
    engine = _get_engine()
    results = params.get("results", [])
    
    contradictions = engine.detect_contradictions(results)
    
    return {
        "contradictions": [
            {
                "agent_a": c.agent_a,
                "agent_b": c.agent_b,
                "claim_a": c.claim_a,
                "claim_b": c.claim_b,
                "domain": c.domain,
                "severity": c.severity,
                "confidence": c.confidence
            }
            for c in contradictions
        ],
        "contradictions_count": len(contradictions)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7500)
