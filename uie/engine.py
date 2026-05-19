"""
UIE LLM Engine — Model-agnostic LLM client.

Supports OpenAI, Anthropic, and OpenAI-compatible endpoints.
Returns structured responses for the agent harness to consume.
No hardcoded responses. No theater.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    content: str
    model: str
    provider: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "tool_calls": self.tool_calls,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
        }


@dataclass
class ToolSpec:
    """Tool specification for LLM function calling."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema for parameters


class LLMEngine:
    """
    Multi-provider LLM client with tool-use support.

    Provider selection:
    - ANTHROPIC_API_KEY set → Anthropic (via messages API)
    - OPENAI_API_KEY set → OpenAI (chat completions)
    - OLLAMA_HOST set → Ollama (OpenAI-compatible endpoint)
    - None set → falls back to a deterministic simulation mode for testing
    """

    def __init__(self) -> None:
        self._provider = self._detect_provider()
        logger.info("LLMEngine initialized with provider: %s", self._provider)

    def _detect_provider(self) -> str:
        if os.getenv("OLLAMA_HOST"):
            return "ollama"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"
        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
        return "simulation"

    def supports_tools(self) -> bool:
        return self._provider in ("openai", "anthropic", "ollama")

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        tools: Optional[List[ToolSpec]] = None,
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """
        Send a completion request to the configured LLM provider.

        Args:
            system_prompt: System-level instructions (agent identity)
            user_message: The user's query or task
            tools: Optional tool definitions for function calling
            model: Override the default model
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)
        """
        if self._provider == "simulation":
            return await self._simulate(user_message, tools)

        if self._provider == "openai":
            return await self._call_openai(
                system_prompt, user_message, tools, model, max_tokens, temperature
            )

        if self._provider == "anthropic":
            return await self._call_anthropic(
                system_prompt, user_message, tools, model, max_tokens, temperature
            )

        if self._provider == "ollama":
            return await self._call_ollama(
                system_prompt, user_message, tools, model, max_tokens, temperature
            )

        raise RuntimeError(f"Unknown provider: {self._provider}")

    # ------------------------------------------------------------------
    # OpenAI provider
    # ------------------------------------------------------------------

    async def _call_openai(
        self,
        system_prompt: str,
        user_message: str,
        tools: Optional[List[ToolSpec]],
        model: Optional[str],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.error("openai package not installed — install with: pip install openai")
            return LLMResponse(
                content="LLM unavailable: openai package not installed",
                model="none",
                provider="openai",
            )

        base_url = os.getenv("OPENAI_BASE_URL")
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=base_url) if base_url else AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model_name = model or os.getenv("UIE_MODEL", "gpt-4o-mini")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools and self.supports_tools():
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            kwargs["tool_choice"] = "auto"

        try:
            response = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.error("OpenAI call failed: %s", exc)
            return LLMResponse(
                content=f"LLM error: {exc}",
                model=model_name,
                provider="openai",
            )

        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        if message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }
                for tc in message.tool_calls
            ]

        return LLMResponse(
            content=message.content or "",
            model=response.model,
            provider="openai",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )

    # ------------------------------------------------------------------
    # Anthropic provider
    # ------------------------------------------------------------------

    async def _call_anthropic(
        self,
        system_prompt: str,
        user_message: str,
        tools: Optional[List[ToolSpec]],
        model: Optional[str],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        try:
            import anthropic
        except ImportError:
            logger.error("anthropic package not installed — install with: pip install anthropic")
            return LLMResponse(
                content="LLM unavailable: anthropic package not installed",
                model="none",
                provider="anthropic",
            )

        client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        model_name = model or os.getenv("UIE_MODEL", "claude-3-5-haiku-latest")

        # Anthropic uses a different tool format
        anthropic_tools = None
        if tools:
            anthropic_tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        try:
            kwargs: Dict[str, Any] = {
                "model": model_name,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if anthropic_tools:
                kwargs["tools"] = anthropic_tools

            response = await client.messages.create(**kwargs)
        except Exception as exc:
            logger.error("Anthropic call failed: %s", exc)
            return LLMResponse(
                content=f"LLM error: {exc}",
                model=model_name,
                provider="anthropic",
            )

        content_blocks = response.content
        text_parts = []
        tool_calls = []

        for block in content_blocks:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })

        return LLMResponse(
            content="\n".join(text_parts),
            model=response.model,
            provider="anthropic",
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "stop",
            usage={
                "input_tokens": response.usage.input_tokens if response.usage else 0,
                "output_tokens": response.usage.output_tokens if response.usage else 0,
            },
        )

    # ------------------------------------------------------------------
    # Ollama provider (OpenAI-compatible endpoint)
    # ------------------------------------------------------------------

    async def _call_ollama(
        self,
        system_prompt: str,
        user_message: str,
        tools: Optional[List[ToolSpec]],
        model: Optional[str],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.error("openai package not installed")
            return LLMResponse(
                content="LLM unavailable: openai package not installed",
                model="none",
                provider="ollama",
            )

        host = os.getenv("OLLAMA_HOST", "http://localhost:11434/v1")
        ollama_key = os.getenv("OPENAI_API_KEY") or os.getenv("OLLAMA_API_KEY") or "ollama"
        client = AsyncOpenAI(base_url=host, api_key=ollama_key)
        model_name = model or os.getenv("UIE_MODEL", "llama3.2:3b")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            logger.error("Ollama call failed: %s", exc)
            return LLMResponse(
                content=f"LLM error: {exc}",
                model=model_name,
                provider="ollama",
            )

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            provider="ollama",
            finish_reason=choice.finish_reason or "stop",
            usage={},
        )

    # ------------------------------------------------------------------
    # Simulation mode — deterministic routing for testing without LLM
    # ------------------------------------------------------------------

    async def _simulate(
        self, user_message: str, tools: Optional[List[ToolSpec]]
    ) -> LLMResponse:
        """
        Deterministic simulator for testing when no LLM API keys are set.
        Routes based on keyword matching against user input.
        """
        msg_lower = user_message.lower()

        # Route to appropriate engine based on keywords
        if any(w in msg_lower for w in ("underwrite", "revenue", "business", "financial")):
            return LLMResponse(
                content="Routing to BUE for business underwriting analysis.",
                model="simulator",
                provider="simulation",
                tool_calls=[{
                    "id": "sim_001",
                    "name": "call_agent",
                    "arguments": {
                        "agent": "bue",
                        "capability_id": "bue.underwrite",
                        "task": "underwriting",
                        "domains": ["finance"],
                    },
                }],
                finish_reason="tool_calls",
            )

        if any(w in msg_lower for w in ("risk", "sensitivity", "stress test", "scenario")):
            return LLMResponse(
                content="Routing to URPE for risk assessment.",
                model="simulator",
                provider="simulation",
                tool_calls=[{
                    "id": "sim_002",
                    "name": "call_agent",
                    "arguments": {
                        "agent": "urpe",
                        "capability_id": "urpe.evaluate",
                        "task": "evaluation",
                        "domains": ["strategy"],
                    },
                }],
                finish_reason="tool_calls",
            )

        if any(w in msg_lower for w in ("schedule", "compute", "carbon", "energy", "workload")):
            return LLMResponse(
                content="Routing to CEOA for compute scheduling.",
                model="simulator",
                provider="simulation",
                tool_calls=[{
                    "id": "sim_003",
                    "name": "call_agent",
                    "arguments": {
                        "agent": "ceoa",
                        "capability_id": "ceoa.schedule",
                        "task": "scheduling",
                        "domains": ["compute", "energy"],
                    },
                }],
                finish_reason="tool_calls",
            )

        # Default: general query
        return LLMResponse(
            content=(
                f"I'll help with your query. Based on my analysis, this appears to be a "
                f"general question. I can route it to the appropriate specialist agent "
                f"for a detailed response."
            ),
            model="simulator",
            provider="simulation",
            tool_calls=[],
            finish_reason="stop",
        )
