"""
Anthem Harness — Bridge between Luna's cognitive field and Anthem agents.

Each engine is a Luna-hosted agent. The harness loads identity, goals, and tools
from YAML configs and drives the LLM through Luna's planner, not directly.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

CONFIGS_DIR = Path(__file__).resolve().parents[2] / "configs"


# ---------------------------------------------------------------------------
# Agent identity (loaded from YAML)
# ---------------------------------------------------------------------------

@dataclass
class AgentIdentity:
    """Stable identity that persists across all invocations."""
    name: str
    role: str
    axioms: List[str] = field(default_factory=list)        # Never change
    constraints: List[str] = field(default_factory=list)    # Hard limits
    heuristics: List[str] = field(default_factory=list)     # Soft preferences
    tool_permissions: List[str] = field(default_factory=list)

    def to_system_prompt(self) -> str:
        """Render identity as a system prompt for the verbalizer (LLM)."""
        lines = [
            f"You are {self.name}, an Anthem platform agent.",
            f"Role: {self.role}",
            "",
            "## Axioms (absolute, never override):",
        ]
        for axiom in self.axioms:
            lines.append(f"- {axiom}")

        lines.append("")
        lines.append("## Constraints (hard limits):")
        for constraint in self.constraints:
            lines.append(f"- {constraint}")

        lines.append("")
        lines.append("## Heuristics (preferences, not absolute):")
        for heuristic in self.heuristics:
            lines.append(f"- {heuristic}")

        return "\n".join(lines)


@dataclass
class ToolDefinition:
    """Typed tool definition for an agent."""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    returns: Dict[str, Any] = field(default_factory=dict)
    permissions: List[str] = field(default_factory=list)
    estimated_cost: Optional[str] = None
    expected_latency_ms: Optional[int] = None


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

# Tool handler type: async function that takes params and returns result
ToolHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]]


class ToolRegistry:
    """Registry of tool definitions and their handlers."""

    def __init__(self) -> None:
        self._definitions: Dict[str, ToolDefinition] = {}
        self._handlers: Dict[str, ToolHandler] = {}

    def register(
        self, definition: ToolDefinition, handler: ToolHandler
    ) -> None:
        self._definitions[definition.name] = definition
        self._handlers[definition.name] = handler

    async def execute(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        handler = self._handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return await handler(params)
        except Exception as e:
            logger.exception("Tool %s failed", tool_name)
            return {"error": f"Tool execution failed: {type(e).__name__}"}

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return tool definitions in LLM function-calling format."""
        tools = []
        for defn in self._definitions.values():
            tools.append({
                "type": "function",
                "function": {
                    "name": defn.name,
                    "description": defn.description,
                    "parameters": defn.parameters,
                },
            })
        return tools

    def is_permitted(self, tool_name: str, agent_permissions: List[str]) -> bool:
        defn = self._definitions.get(tool_name)
        if not defn:
            return False
        if not defn.permissions:
            return True
        return any(p in agent_permissions for p in defn.permissions)


# ---------------------------------------------------------------------------
# Reflection loop
# ---------------------------------------------------------------------------

@dataclass
class ReflectionResult:
    """Result of a reflection check after a tool call."""
    drift_detected: bool = False
    contradiction_detected: bool = False
    identity_violation: bool = False
    messages: List[str] = field(default_factory=list)

    @property
    def should_self_correct(self) -> bool:
        return self.drift_detected or self.contradiction_detected or self.identity_violation


class ReflectionLoop:
    """
    Checks agent state after every tool call.
    Surfaces drift, contradiction, and identity violations.
    """

    def __init__(self, identity: AgentIdentity) -> None:
        self.identity = identity
        self._decisions: List[Dict[str, Any]] = []
        self._goal_stack: List[str] = []

    def set_goal(self, goal: str) -> None:
        self._goal_stack.append(goal)

    def record_decision(self, decision: Dict[str, Any]) -> None:
        self._decisions.append(decision)

    def check(self, proposed_action: Dict[str, Any]) -> ReflectionResult:
        result = ReflectionResult()

        # Drift: is the proposed action relevant to the current goal?
        if self._goal_stack:
            current_goal = self._goal_stack[-1]
            action_desc = proposed_action.get("description", "")
            # Simple heuristic: if neither the tool name nor description mentions
            # any word from the goal, flag as potential drift
            goal_words = set(current_goal.lower().split())
            action_words = set(action_desc.lower().split())
            tool_name = proposed_action.get("tool", "").lower().replace("_", " ")
            action_words.update(tool_name.split())
            if not goal_words & action_words and len(goal_words) > 2:
                result.drift_detected = True
                result.messages.append(
                    f"Potential drift: action '{action_desc}' may not relate to goal '{current_goal}'"
                )

        # Contradiction: does this action contradict a prior decision?
        for prior in self._decisions:
            if (
                prior.get("tool") == proposed_action.get("tool")
                and prior.get("conclusion")
                and proposed_action.get("conclusion")
                and prior["conclusion"] != proposed_action["conclusion"]
            ):
                result.contradiction_detected = True
                result.messages.append(
                    f"Contradiction: prior decision '{prior['conclusion']}' "
                    f"conflicts with proposed '{proposed_action['conclusion']}'"
                )

        # Identity: check constraints
        for constraint in self.identity.constraints:
            constraint_lower = constraint.lower()
            action_desc_lower = proposed_action.get("description", "").lower()
            # Very basic check — in production, Luna's field handles this geometrically
            if "never" in constraint_lower:
                forbidden = constraint_lower.split("never")[-1].strip()
                if forbidden and forbidden in action_desc_lower:
                    result.identity_violation = True
                    result.messages.append(
                        f"Identity violation: constraint '{constraint}' may be breached"
                    )

        return result


# ---------------------------------------------------------------------------
# Agent harness (the main class)
# ---------------------------------------------------------------------------

class AgentHarness:
    """
    The main harness that wraps a Luna-hosted agent.

    Loads identity from YAML, manages tools, drives the LLM through
    the tool-use loop, and runs reflection after each step.
    """

    def __init__(
        self,
        agent_name: str,
        identity: AgentIdentity,
        tools: ToolRegistry,
        verbalizer: Optional[Any] = None,  # LLM client (OpenAI/Anthropic)
        max_turns: int = 10,
        token_budget: int = 50_000,
    ) -> None:
        self.agent_name = agent_name
        self.identity = identity
        self.tools = tools
        self.verbalizer = verbalizer
        self.max_turns = max_turns
        self.token_budget = token_budget
        self.reflection = ReflectionLoop(identity)
        self._event_log: List[Dict[str, Any]] = []
        self._tokens_used = 0

    async def run(self, goal: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent loop: plan → act → observe → reflect → repeat.

        Returns the final result or an error.
        """
        self.reflection.set_goal(goal)
        self._log_event("goal_set", {"goal": goal})

        messages = [
            {"role": "system", "content": self.identity.to_system_prompt()},
            {"role": "user", "content": self._format_task(goal, context)},
        ]

        for turn in range(self.max_turns):
            if self._tokens_used >= self.token_budget:
                self._log_event("budget_exhausted", {"tokens_used": self._tokens_used})
                return {"error": "Token budget exhausted", "partial": self._last_text(messages)}

            # Call verbalizer (LLM)
            response = await self._call_verbalizer(messages)
            if not response:
                return {"error": "Verbalizer call failed"}

            # Check if LLM wants to call a tool
            tool_calls = response.get("tool_calls", [])
            if not tool_calls:
                # LLM is done — return final text
                final = response.get("content", "")
                self._log_event("completed", {"turns": turn + 1, "tokens": self._tokens_used})
                return {"result": final, "turns": turn + 1, "tokens_used": self._tokens_used}

            # Execute tool calls
            for tc in tool_calls:
                tool_name = tc.get("function", {}).get("name", "")
                tool_args = tc.get("function", {}).get("arguments", {})
                if isinstance(tool_args, str):
                    import json
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError:
                        tool_args = {}

                # Permission check
                if not self.tools.is_permitted(tool_name, self.identity.tool_permissions):
                    self._log_event("permission_denied", {"tool": tool_name})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": f"Permission denied for tool: {tool_name}",
                    })
                    continue

                # Reflection check before execution
                proposed = {"tool": tool_name, "description": str(tool_args)}
                check = self.reflection.check(proposed)
                if check.should_self_correct:
                    self._log_event("reflection_triggered", {
                        "drift": check.drift_detected,
                        "contradiction": check.contradiction_detected,
                        "identity": check.identity_violation,
                        "messages": check.messages,
                    })
                    # Inject correction into context
                    messages.append({
                        "role": "system",
                        "content": (
                            "REFLECTION WARNING: " + "; ".join(check.messages)
                            + "\nPlease reconsider your approach."
                        ),
                    })
                    break  # Re-enter LLM loop for self-correction

                # Execute tool
                self._log_event("tool_call", {"tool": tool_name, "args": tool_args})
                tool_result = await self.tools.execute(tool_name, tool_args)
                self._log_event("tool_result", {"tool": tool_name, "result_keys": list(tool_result.keys())})

                self.reflection.record_decision({
                    "tool": tool_name,
                    "args": tool_args,
                    "conclusion": tool_result.get("conclusion"),
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": str(tool_result),
                })

        self._log_event("max_turns_reached", {"turns": self.max_turns})
        return {"error": "Max turns reached", "partial": self._last_text(messages)}

    async def _call_verbalizer(self, messages: List[Dict]) -> Optional[Dict]:
        """Call the LLM with the current message history + available tools."""
        if not self.verbalizer:
            # Stub for testing without a real LLM
            return {"content": "No verbalizer configured", "tool_calls": []}

        try:
            tools = self.tools.list_tools()
            response = await self.verbalizer.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
            )
            choice = response.choices[0]
            self._tokens_used += response.usage.total_tokens if response.usage else 0

            result: Dict[str, Any] = {"content": choice.message.content or ""}
            if choice.message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ]
            return result

        except Exception:
            logger.exception("Verbalizer call failed")
            return None

    def _format_task(self, goal: str, context: Dict[str, Any]) -> str:
        parts = [f"## Task\n{goal}"]
        if context:
            parts.append(f"\n## Context\n```json\n{context}\n```")
        return "\n".join(parts)

    def _last_text(self, messages: List[Dict]) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                return msg["content"]
        return ""

    def _log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        from datetime import datetime, timezone
        self._event_log.append({
            "agent": self.agent_name,
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    @property
    def event_log(self) -> List[Dict[str, Any]]:
        return list(self._event_log)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_agent_identity(agent_name: str) -> AgentIdentity:
    """Load agent identity from YAML config."""
    config_path = CONFIGS_DIR / "agents" / f"{agent_name}.yaml"
    if not config_path.exists():
        logger.warning("No identity config for %s, using defaults", agent_name)
        return AgentIdentity(name=agent_name, role=f"{agent_name} agent")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return AgentIdentity(
        name=data.get("name", agent_name),
        role=data.get("role", ""),
        axioms=data.get("axioms", []),
        constraints=data.get("constraints", []),
        heuristics=data.get("heuristics", []),
        tool_permissions=data.get("tool_permissions", []),
    )


def load_tool_definitions(agent_name: str) -> List[ToolDefinition]:
    """Load tool definitions for an agent from YAML config."""
    config_path = CONFIGS_DIR / "tools" / f"{agent_name}.yaml"
    if not config_path.exists():
        return []

    with open(config_path) as f:
        data = yaml.safe_load(f)

    tools = []
    for tool_data in data.get("tools", []):
        tools.append(ToolDefinition(
            name=tool_data["name"],
            description=tool_data.get("description", ""),
            parameters=tool_data.get("parameters", {}),
            returns=tool_data.get("returns", {}),
            permissions=tool_data.get("permissions", []),
            estimated_cost=tool_data.get("estimated_cost"),
            expected_latency_ms=tool_data.get("expected_latency_ms"),
        ))

    return tools
