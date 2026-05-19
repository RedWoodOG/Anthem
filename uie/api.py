"""
UIE API — Universal Intelligence Engine endpoint.

The meta-agent that orchestrates other Anthem agents.
Accepts user queries, decomposes them via LLM reasoning,
routes to specialist agents through the broker, and synthesizes results.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from anthem_common.harness import (
    AgentHarness,
    ToolDefinition,
    ToolRegistry,
    load_agent_identity,
    load_tool_definitions,
)
from anthem_common.schemas import Envelope, ErrorDetail, NormalizedResult
from anthem_common.tls import build_tls_client
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from uie.engine import LLMEngine, LLMResponse, ToolSpec

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="Anthem UIE", version="1.0.0")

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_harness: Optional[AgentHarness] = None
_llm: Optional[LLMEngine] = None
_broker_client: Optional[httpx.AsyncClient] = None
_identity = load_agent_identity("uie")


def _get_harness() -> AgentHarness:
    global _harness
    if _harness is None:
        tool_defs = load_tool_definitions("uie")
        registry = ToolRegistry()
        for td in tool_defs:
            registry.register(td, _handle_tool_call)

        _harness = AgentHarness(
            agent_name="uie",
            identity=_identity,
            tools=registry,
            max_turns=5,
            token_budget=32_000,
        )
    return _harness


def _get_llm() -> LLMEngine:
    global _llm
    if _llm is None:
        _llm = LLMEngine()
    return _llm


async def _get_broker() -> httpx.AsyncClient:
    global _broker_client
    if _broker_client is None:
        broker_url = os.getenv("BROKER_URL", "http://function-broker:8100")
        tls_client = build_tls_client(
            ca_bundle=os.getenv("CA_BUNDLE"),
            client_cert=os.getenv("CLIENT_CERT"),
            client_key=os.getenv("CLIENT_KEY"),
        )
        _broker_client = tls_client or httpx.AsyncClient(
            base_url=broker_url, timeout=httpx.Timeout(60.0)
        )
    return _broker_client


# ---------------------------------------------------------------------------
# Tool handlers — dispatched by the harness when LLM calls a tool
# ---------------------------------------------------------------------------

async def _handle_tool_call(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if tool_name == "call_agent":
        return await _handle_call_agent(params)
    if tool_name == "decompose_goal":
        return await _handle_decompose_goal(params)
    if tool_name == "synthesize_results":
        return await _handle_synthesize_results(params)
    return {"error": f"Unknown tool: {tool_name}"}


async def _handle_call_agent(params: Dict[str, Any]) -> Dict[str, Any]:
    """Route a sub-task to a specialist agent via the broker."""
    capability_id = params.get("capability_id", "")
    if not capability_id:
        return {"error": "capability_id is required"}

    task = params.get("task", "query")
    domains = params.get("domains", ["general"])

    envelope = Envelope(
        request_id=f"uie-{os.urandom(4).hex()}",
        tenant_id=params.get("tenant_id", "default"),
        actor="uie",
        capability_id=capability_id,
        intent={"task": task, "domains": domains},
        payload=params.get("payload", {}),
        governance_tier="T2",
    )

    try:
        broker = await _get_broker()
        response = await broker.post(
            "/v1/invoke",
            json={
                "capability_id": capability_id,
                "envelope": envelope.model_dump(),
            },
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.error("Broker call failed for %s: %s", capability_id, exc)
        return {"error": f"Agent '{capability_id}' unavailable: {exc}"}


async def _handle_decompose_goal(params: Dict[str, Any]) -> Dict[str, Any]:
    """Decompose a complex goal into sub-tasks."""
    goal = params.get("goal", "")
    llm = _get_llm()

    system_prompt = (
        "You are a task decomposition specialist. Given a user's goal, "
        "break it down into 2-5 sub-tasks. Return JSON array of objects "
        "with 'task', 'agent', 'capability_id', and 'domains' fields. "
        "Available agents: bue (underwriting), urpe (risk), ceoa (compute)."
    )

    response = await llm.complete(
        system_prompt=system_prompt,
        user_message=f"Decompose this goal: {goal}",
        max_tokens=1024,
        temperature=0.2,
    )

    try:
        content = response.content
        start = content.find("[")
        end = content.rfind("]") + 1
        if start >= 0 and end > start:
            sub_tasks = json.loads(content[start:end])
            return {"sub_tasks": sub_tasks}
    except (json.JSONDecodeError, ValueError):
        pass

    return {
        "sub_tasks": [
            {"task": "analyze", "agent": "bue", "capability_id": "bue.underwrite",
             "domains": ["finance"]}
        ],
        "note": "Simplified decomposition (LLM fallback)",
    }


async def _handle_synthesize_results(params: Dict[str, Any]) -> Dict[str, Any]:
    """Synthesize results from multiple agent calls."""
    results = params.get("results", [])
    if not results:
        return {"synthesis": "No results to synthesize."}

    summary = []
    for r in results:
        agent = r.get("agent", "unknown")
        result_data = r.get("result", {})
        summary.append({
            "agent": agent,
            "status": r.get("status", "unknown"),
            "key_metrics": _extract_key_metrics(result_data),
        })

    return {
        "synthesis": summary,
        "agent_count": len(results),
        "all_successful": all(r.get("status") == "success" for r in results),
    }


def _extract_key_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    dist = data.get("distribution", {})
    risk = data.get("risk_metrics", {})
    if dist:
        metrics["mean_revenue"] = dist.get("mean")
        metrics["p5_revenue"] = dist.get("p5")
        metrics["p95_revenue"] = dist.get("p95")
    if risk:
        metrics["default_probability"] = risk.get("probability_of_default")
        metrics["var_95"] = risk.get("var_95")
    if "overall_risk_score" in data:
        metrics["risk_score"] = data["overall_risk_score"]
        metrics["risk_tier"] = data.get("risk_tier")
    if not metrics:
        metrics = {k: v for k, v in data.items()
                    if isinstance(v, (int, float, str)) and not k.startswith("_")}
    return metrics


# ---------------------------------------------------------------------------
# LLM tool specs (for function calling)
# ---------------------------------------------------------------------------

def _build_llm_tools() -> List[ToolSpec]:
    return [
        ToolSpec(
            name="call_agent",
            description="Route a sub-task to a specialist agent (bue, urpe, ceoa, domain-cortex).",
            parameters={
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "enum": ["bue", "urpe", "ceoa", "domain-cortex"],
                    },
                    "capability_id": {
                        "type": "string",
                        "description": "e.g., bue.underwrite, urpe.evaluate",
                    },
                    "task": {
                        "type": "string",
                        "enum": ["underwriting", "evaluation", "analysis", "scheduling", "query"],
                    },
                    "domains": {
                        "type": "array", "items": {"type": "string"},
                    },
                },
                "required": ["capability_id", "task"],
            },
        ),
        ToolSpec(
            name="decompose_goal",
            description="Break a complex goal into sub-tasks.",
            parameters={
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                },
                "required": ["goal"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/v1/agent")
async def agent_endpoint(envelope: Envelope) -> NormalizedResult:
    """
    Main agent endpoint — runs the harness loop.

    1. Extract user query from envelope
    2. LLM decides what agent to call
    3. Execute tool calls via harness
    4. Synthesize and return
    """
    harness = _get_harness()
    llm = _get_llm()

    # Build user input from envelope payload
    user_input = envelope.payload.get("question") or envelope.payload.get("query") or ""
    if not user_input:
        parts = []
        for k, v in envelope.payload.items():
            if isinstance(v, (str, int, float)):
                parts.append(f"{k}: {v}")
        user_input = "; ".join(parts) if parts else str(envelope.payload)

    system_prompt = _identity.to_system_prompt()
    system_prompt += "\n\nAvailable specialist agents:\n"
    system_prompt += "- bue: Business underwriting (Monte Carlo simulation)\n"
    system_prompt += "- urpe: Risk assessment (sensitivity analysis)\n"

    try:
        llm_response = await llm.complete(
            system_prompt=system_prompt,
            user_message=user_input,
            tools=_build_llm_tools(),
            max_tokens=2048,
            temperature=0.3,
        )

        harness_results: List[Dict[str, Any]] = []
        for tc in llm_response.tool_calls:
            tool_result = await _handle_tool_call(tc["name"], tc["arguments"])
            harness_results.append({
                "agent": tc["arguments"].get("agent", ""),
                "capability_id": tc["arguments"].get("capability_id", ""),
                "status": "success" if "error" not in tool_result else "error",
                "result": tool_result,
            })

        if len(harness_results) > 1:
            synthesis = await _handle_synthesize_results({"results": harness_results})
        elif harness_results:
            synthesis = harness_results[0]["result"]
        else:
            synthesis = {"response": llm_response.content}

        from datetime import datetime, timezone
        all_ok = all(r["status"] == "success" for r in harness_results) if harness_results else True
        return NormalizedResult(
            result_id=envelope.request_id or f"uie-{os.urandom(4).hex()}",
            timestamp=datetime.now(timezone.utc),
            success=all_ok,
            data={
                "llm_analysis": llm_response.content,
                "executed_calls": harness_results,
                "final_result": synthesis,
                "model": llm_response.model,
                "provider": llm_response.provider,
            },
        )

    except Exception as exc:
        logger.exception("Agent endpoint failed")
        from datetime import datetime, timezone
        return NormalizedResult(
            result_id=envelope.request_id or f"uie-{os.urandom(4).hex()}",
            timestamp=datetime.now(timezone.utc),
            success=False,
            data={"error": "Agent processing failed"},
            error=ErrorDetail.from_exception(exc, include_traceback=False),
        )


@app.post("/v1/query")
async def query_endpoint(envelope: Envelope) -> NormalizedResult:
    """
    Simplified query endpoint — matches broker capability 'uie.query'.
    Accepts direct question payloads and routes through the simulation engine.
    """
    user_input = envelope.payload.get("question") or envelope.payload.get("query") or ""
    if not user_input:
        parts = [f"{k}: {v}" for k, v in envelope.payload.items()
                 if isinstance(v, (str, int, float))]
        user_input = "; ".join(parts) if parts else str(envelope.payload)

    llm = _get_llm()
    system_prompt = _identity.to_system_prompt()
    response = await llm.complete(
        system_prompt=system_prompt,
        user_message=user_input,
        max_tokens=2048,
    )

    from datetime import datetime, timezone
    return NormalizedResult(
        result_id=envelope.request_id or f"uie-{os.urandom(4).hex()}",
        timestamp=datetime.now(timezone.utc),
        success=True,
        data={"response": response.content, "model": response.model, "provider": response.provider},
        details={"capability_id": "uie.query"},
    )

@app.get("/health")
async def health():
    harness = _get_harness()
    return {
        "status": "healthy",
        "service": "uie",
        "version": "1.0.0",
        "agent": harness.identity.name,
        "llm_provider": _get_llm()._provider,
    }


@app.exception_handler(Exception)
async def general_error(request: Request, exc: Exception):
    logger.exception("Unhandled exception in UIE")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
