"""
UIE Tests — verify the meta-agent routes correctly.

Run with: pytest tests/test_uie.py -v

Tests run in simulation mode (no LLM API keys needed).
The simulator routes based on keyword matching in user input.
"""

import os
import sys
from pathlib import Path

import pytest

# Force simulation mode for deterministic tests — no API keys
for _key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OLLAMA_HOST"):
    os.environ.pop(_key, None)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uie.engine import LLMEngine, LLMResponse, ToolSpec


class TestLLMEngineSimulation:
    """Simulation mode routes queries to the correct agent."""

    @pytest.mark.asyncio
    async def test_routes_underwriting_to_bue(self):
        engine = LLMEngine()
        assert engine._provider == "simulation"

        response = await engine.complete(
            system_prompt="You are a meta-agent.",
            user_message="Please underwrite Acme Corp with $5M revenue in software",
        )

        assert response.provider == "simulation"
        assert len(response.tool_calls) == 1
        tc = response.tool_calls[0]
        assert tc["name"] == "call_agent"
        assert tc["arguments"]["agent"] == "bue"
        assert tc["arguments"]["capability_id"] == "bue.underwrite"

    @pytest.mark.asyncio
    async def test_routes_risk_to_urpe(self):
        engine = LLMEngine()
        response = await engine.complete(
            system_prompt="You are a meta-agent.",
            user_message="Run a sensitivity analysis on our stress test scenario",
        )

        assert len(response.tool_calls) == 1
        tc = response.tool_calls[0]
        assert tc["arguments"]["agent"] == "urpe"
        assert tc["arguments"]["capability_id"] == "urpe.evaluate"

    @pytest.mark.asyncio
    async def test_routes_scheduling_to_ceoa(self):
        engine = LLMEngine()
        response = await engine.complete(
            system_prompt="You are a meta-agent.",
            user_message="Schedule this compute workload with carbon awareness",
        )

        assert len(response.tool_calls) == 1
        tc = response.tool_calls[0]
        assert tc["arguments"]["agent"] == "ceoa"
        assert tc["arguments"]["capability_id"] == "ceoa.schedule"

    @pytest.mark.asyncio
    async def test_general_query_no_tool_calls(self):
        engine = LLMEngine()
        response = await engine.complete(
            system_prompt="You are a meta-agent.",
            user_message="What is the weather today?",
        )

        assert response.provider == "simulation"
        assert response.tool_calls == []
        assert len(response.content) > 0
        assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_response_is_structured(self):
        engine = LLMEngine()
        response = await engine.complete(
            system_prompt="test",
            user_message="underwrite something",
        )

        d = response.to_dict()
        assert "content" in d
        assert "model" in d
        assert "provider" in d
        assert "tool_calls" in d
        assert "finish_reason" in d
        assert "usage" in d


class TestToolSpec:
    """ToolSpec creates valid JSON Schema for LLM function calling."""

    def test_valid_openai_tool_format(self):
        spec = ToolSpec(
            name="call_agent",
            description="Call a specialist agent",
            parameters={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "enum": ["bue", "urpe"]},
                },
                "required": ["agent"],
            },
        )

        import json
        schema = json.dumps({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        })
        parsed = json.loads(schema)
        assert parsed["function"]["name"] == "call_agent"
        assert "agent" in parsed["function"]["parameters"]["properties"]


class TestUIEHarnessIntegration:
    """Verify the UIE API module imports and the harness loads."""

    def test_uie_identity_loads(self):
        from anthem_common.harness import load_agent_identity
        identity = load_agent_identity("uie")
        assert identity.name is not None
        assert "UIE" in identity.name
        assert len(identity.axioms) > 0
        assert len(identity.constraints) > 0
        assert "call_agent" in identity.tool_permissions

    def test_uie_tool_definitions_load(self):
        from anthem_common.harness import load_tool_definitions
        tools = load_tool_definitions("uie")
        tool_names = [t.name for t in tools]
        assert "call_agent" in tool_names
        assert "decompose_goal" in tool_names
        assert "synthesize_results" in tool_names

    def test_uie_api_module_imports(self):
        """Verify the UIE API module imports cleanly."""
        from uie.api import app, _get_harness, _get_llm

        harness = _get_harness()
        assert harness.identity.name is not None

        llm = _get_llm()
        assert llm._provider == "simulation"

        routes = [r.path for r in app.routes]
        assert "/v1/agent" in routes
        assert "/health" in routes

    def test_uie_api_health_endpoint(self):
        """Health endpoint returns expected shape."""
        from uie.api import health
        import asyncio
        result = asyncio.run(health())
        assert result["status"] == "healthy"
        assert result["service"] == "uie"
        assert "agent" in result
        assert "llm_provider" in result
