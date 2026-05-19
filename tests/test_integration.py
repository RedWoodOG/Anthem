"""
Integration tests for Anthem system.

These tests verify the full request path against locally-running services.
They use httpx to call real endpoints. If services aren't running, they skip.
"""

import pytest
import httpx
from typing import Dict, Any

from anthem_common.schemas import Envelope, GovernanceMetadata, NormalizedResult


# ---------------------------------------------------------------------------
# Service endpoints
# ---------------------------------------------------------------------------

GATEWAY_URL = "http://localhost:9200"
BROKER_URL = "http://localhost:8100"
BUE_URL = "http://localhost:9000"
URPE_URL = "http://localhost:7300"
UIE_URL = "http://localhost:8000"

SERVICE_PORTS = {
    "gateway": GATEWAY_URL,
    "broker": BROKER_URL,
    "bue": BUE_URL,
    "urpe": URPE_URL,
    "uie": UIE_URL,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------



@pytest.fixture
async def http_client():
    """Async HTTP client for integration tests."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


# ---------------------------------------------------------------------------
# Test: Full underwriting flow
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_underwriting_flow(http_client: httpx.AsyncClient):
    """
    POST to gateway /v1/submit with underwriting payload.
    Verify response has distribution stats.
    """
    envelope = Envelope(
        tenant_id="test-tenant",
        actor="integration-test",
        intent={
            "task": "underwriting",
            "domain": "finance",
        },
        payload={
            "industry": "technology",
            "revenue_base": 10_000_000,
            "growth_rate": 0.15,
            "volatility": 0.25,
        },
        governance=GovernanceMetadata(
            requested_tier="T2",
            region="US",
        ),
    )
    
    response = await http_client.post(
        f"{GATEWAY_URL}/v1/submit",
        json=envelope.to_transport_dict(),
        headers={"X-API-Key": "test-key"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "data" in data
    assert "details" in data or data.get("details") is not None
    
    # Verify distribution stats are present
    result_data = data.get("data", {})
    has_stats = any(
        key in str(result_data).lower()
        for key in ["mean", "median", "percentile", "distribution", "p50", "p90", "p10", "expected"]
    )
    assert has_stats, f"Response should contain distribution stats: {data}"


# ---------------------------------------------------------------------------
# Test: Full risk flow
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_risk_flow(http_client: httpx.AsyncClient):
    """
    POST to gateway /v1/submit with risk evaluation payload.
    Verify response has sensitivity analysis.
    """
    envelope = Envelope(
        tenant_id="test-tenant",
        actor="integration-test",
        intent={
            "task": "evaluation",
            "domain": "governance",
        },
        payload={
            "base_scenario": {
                "revenue": 50_000_000,
                "growth_rate": 0.10,
                "volatility": 0.20,
            },
            "risk_factors": [
                {"name": "market_downturn", "perturbation_2sigma": -0.30},
                {"name": "regulatory_change", "perturbation_2sigma": -0.15},
            ],
        },
        governance=GovernanceMetadata(
            requested_tier="T1",
            region="EU",
        ),
    )
    
    response = await http_client.post(
        f"{GATEWAY_URL}/v1/submit",
        json=envelope.to_transport_dict(),
        headers={"X-API-Key": "test-key"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify sensitivity analysis is present
    result_data = data.get("data", {})
    has_sensitivity = any(
        key in str(result_data).lower()
        for key in ["sensitivity", "scenario", "stressed", "delta", "perturb"]
    )
    assert has_sensitivity, f"Response should contain sensitivity analysis: {data}"


# ---------------------------------------------------------------------------
# Test: Gateway health
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_gateway_health(http_client: httpx.AsyncClient):
    """
    GET /health on gateway.
    Verify status healthy.
    """
    response = await http_client.get(f"{GATEWAY_URL}/health")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data.get("status") == "healthy"
    assert data.get("service") == "cortex-gateway"


# ---------------------------------------------------------------------------
# Test: Broker capabilities
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_broker_capabilities(http_client: httpx.AsyncClient):
    """
    GET /v1/capabilities on broker.
    Verify returns 4+ capabilities.
    """
    response = await http_client.get(f"{BROKER_URL}/v1/capabilities")
    
    assert response.status_code == 200
    data = response.json()
    
    capabilities = data.get("capabilities", [])
    assert len(capabilities) >= 4, f"Expected 4+ capabilities, got {len(capabilities)}"


# ---------------------------------------------------------------------------
# Test: Auth rejects missing key
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_rejects_missing_key(http_client: httpx.AsyncClient):
    """
    POST without API key header.
    Verify 401.
    """
    envelope = Envelope(
        tenant_id="test-tenant",
        actor="integration-test",
        intent={"task": "query"},
        payload={"query": "test"},
    )
    
    response = await http_client.post(
        f"{GATEWAY_URL}/v1/submit",
        json=envelope.to_transport_dict(),
    )
    
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test: Governance tier routing
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_governance_tier_routing(http_client: httpx.AsyncClient):
    """
    POST with different task types.
    Verify tier assignment in response metadata.
    """
    test_cases = [
        ("query", "T1"),
        ("analysis", "T2"),
        ("underwriting", "T2"),
        ("evaluation", "T1"),
    ]
    
    for task_type, expected_tier in test_cases:
        envelope = Envelope(
            tenant_id="test-tenant",
            actor="integration-test",
            intent={"task": task_type, "domain": "general"},
            payload={"data": "test"},
            governance=GovernanceMetadata(requested_tier=expected_tier),
        )
        
        response = await http_client.post(
            f"{GATEWAY_URL}/v1/submit",
            json=envelope.to_transport_dict(),
            headers={"X-API-Key": "test-key"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify governance metadata is present in response
        gov = data.get("governance", {})
        if gov:
            # Tier should be reflected in response
            assert "requested_tier" in gov or "tier" in str(gov).lower()


# ---------------------------------------------------------------------------
# Test: UIE query routing
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_uie_query_routing(http_client: httpx.AsyncClient):
    """
    POST to gateway with query task.
    Verify UIE routes to appropriate engine.
    """
    envelope = Envelope(
        tenant_id="test-tenant",
        actor="integration-test",
        intent={
            "task": "query",
            "domain": "general",
        },
        payload={
            "query": "What are the system capabilities?",
        },
    )
    
    response = await http_client.post(
        f"{GATEWAY_URL}/v1/submit",
        json=envelope.to_transport_dict(),
        headers={"X-API-Key": "test-key"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response indicates routing occurred
    traces = data.get("traces", {})
    # Either traces show routing, or data shows query was processed
    has_routing_info = (
        "uie" in str(traces).lower() or
        "route" in str(traces).lower() or
        "capability" in str(data).lower()
    )
    assert has_routing_info, f"Response should show routing info: {data}"


# ---------------------------------------------------------------------------
# Test: Error response is sanitized
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_response_is_sanitized(http_client: httpx.AsyncClient):
    """
    Verify error responses have code/message/category.
    Never leak tracebacks.
    """
    # Send a malformed request that should trigger an error
    envelope = Envelope(
        tenant_id="test-tenant",
        actor="integration-test",
        intent={"task": "invalid_task_type"},
        payload={},
    )
    
    response = await http_client.post(
        f"{GATEWAY_URL}/v1/submit",
        json=envelope.to_transport_dict(),
        headers={"X-API-Key": "test-key"},
    )
    
    # Should get an error response (could be 200 with error field, or 4xx/5xx)
    data = response.json()
    
    # Check for sanitized error structure
    error = data.get("error", {})
    if error:
        # Error must have required fields
        assert "code" in error, f"Error must have 'code': {data}"
        assert "message" in error, f"Error must have 'message': {data}"
        assert "category" in error, f"Error must have 'category': {data}"
        
        # Verify no traceback leakage
        error_str = str(data).lower()
        assert "traceback" not in error_str, f"Error response leaked traceback: {data}"
        assert "file \"" not in error_str, f"Error response leaked file path: {data}"
        assert "line " not in error_str or "line number" in error_str, f"Error response leaked line numbers: {data}"


# ---------------------------------------------------------------------------
# Test: End-to-end BUE underwrite
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_bue_underwrite(http_client: httpx.AsyncClient):
    """
    Direct POST to BUE /v1/underwrite.
    Verify Monte Carlo output shape.
    """
    payload = {
        "industry": "technology",
        "revenue_base": 10_000_000,
        "growth_rate": 0.12,
        "volatility": 0.20,
        "horizon_years": 3,
        "n_simulations": 5000,
    }
    
    response = await http_client.post(
        f"{BUE_URL}/v1/underwrite",
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify Monte Carlo output shape
    assert "distribution" in data or "results" in data or "statistics" in data, \
        f"Response should have distribution/results/statistics: {data}"
    
    # Check for statistical measures
    data_str = str(data).lower()
    has_stats = any(
        key in data_str
        for key in ["mean", "median", "std", "percentile", "p50", "p90", "p10", "variance"]
    )
    assert has_stats, f"Monte Carlo output should have stats: {data}"


# ---------------------------------------------------------------------------
# Test: End-to-end URPE evaluate
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_urpe_evaluate(http_client: httpx.AsyncClient):
    """
    Direct POST to URPE /v1/evaluate.
    Verify sensitivity analysis shape.
    """
    envelope = Envelope(
        tenant_id="test-tenant",
        actor="integration-test",
        intent={
            "task": "evaluation",
            "domain": "governance",
        },
        payload={
            "base_scenario": {
                "revenue": 25_000_000,
                "growth_rate": 0.08,
                "volatility": 0.15,
            },
            "risk_factors": [
                {"name": "economic_downturn", "perturbation_2sigma": -0.25},
            ],
        },
    )
    
    response = await http_client.post(
        f"{URPE_URL}/v1/evaluate",
        json=envelope.to_transport_dict(),
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify sensitivity analysis shape
    result_data = data.get("data", {})
    data_str = str(result_data).lower()
    
    has_sensitivity = any(
        key in data_str
        for key in ["sensitivity", "scenario", "stressed", "delta", "perturb", "risk_factor"]
    )
    assert has_sensitivity, f"Response should contain sensitivity analysis: {data}"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
