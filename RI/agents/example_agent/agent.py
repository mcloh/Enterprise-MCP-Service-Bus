"""Example conversational agent (EP-13-T01, README.md §6.1, §14, §29).

Real LLM tool-calling (an OpenAI-compatible API, EP-13's `llm_client.py`),
restricted exclusively to the catalog its own `tools/list` call returns --
the agent's tool schema is built *from* that response, so it structurally
cannot offer the model a tool outside its own MaximumEntitlement. Even if a
prompt manipulates the model into attempting an out-of-catalog or
over-limit call anyway, `session.call_tool` still goes through the real
Gateway/PDP (EP-05/EP-03), which reauthorizes independently and denies it
(README.md §29's scenario, Teste 3 of §45 -- reproduced in
tests/e2e/test_example_agent.py) -- the agent's own restraint is never the
security boundary, the Gateway is.

Instrumentation is hybrid per ADR-022: an automatic OTel span per MCP call
(already wired via `emcp_bus.common.otel`, on by default on the SDK's own
`ClientSession`) plus one manual span per LLM call carrying OTel GenAI
semantic-convention attributes (`gen_ai.request.model`,
`gen_ai.usage.{input,output}_token_count`, ...) -- the exact attribute set
Langfuse's own OTel integration recognizes as a "generation" observation
with model/tokens/latency (EP-13-T02, verified 2026-09-14 against a real
self-hosted Langfuse 4.35.0: both the MCP spans and the generation span for
one real agent turn landed in its ClickHouse `events_core` table via the
real OTLP endpoint) -- plus one manual, fail-open business event
(`emcp_bus.audit.events.agent_turn_completed`) -- an audit-sink failure
never aborts the conversation.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from typing import Any

import mcp_types as types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import (  # type: ignore[attr-defined]
    create_mcp_http_client,
    streamable_http_client,
)
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from opentelemetry import trace

from emcp_bus.audit.events import agent_turn_completed
from emcp_bus.audit.sink import AuditSink

_tracer = trace.get_tracer("example-agent")

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant for a sales team. Use only the tools you are "
    "given -- never claim to have capabilities outside them, and never invent "
    "a tool name that wasn't offered to you."
)


@dataclass
class AgentTurnResult:
    final_message: str
    tools_attempted: list[str] = field(default_factory=list)
    tools_denied: list[str] = field(default_factory=list)


def _tool_to_openai_schema(tool: types.Tool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema,
        },
    }


def _result_to_text(result: types.CallToolResult) -> str:
    if result.structured_content is not None:
        return json.dumps(result.structured_content)
    return " ".join(getattr(item, "text", "") for item in result.content) or "(empty result)"


class ExampleAgent:
    def __init__(
        self,
        *,
        gateway_url: str,
        bearer_token: str,
        llm_client: AsyncOpenAI,
        model: str,
        agent_name: str = "example-agent",
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self._gateway_url = gateway_url
        self._bearer_token = bearer_token
        self._llm = llm_client
        self._model = model
        self._agent_name = agent_name
        self._system_prompt = system_prompt
        self._audit_sink = audit_sink

    async def _call_llm(
        self, messages: list[dict[str, Any]], tools_schema: list[dict[str, Any]]
    ) -> ChatCompletion:
        """One LLM call, wrapped in a span carrying OTel GenAI
        semantic-convention attributes -- see the module docstring for why
        (EP-13-T02: this is the attribute set Langfuse's OTel integration
        recognizes as a "generation")."""
        with _tracer.start_as_current_span("llm_call") as span:
            span.set_attribute("gen_ai.system", "openai")
            span.set_attribute("gen_ai.request.model", self._model)
            span.set_attribute(
                "gen_ai.prompt", json.dumps([m for m in messages if m.get("role") != "tool"])
            )
            response = await self._llm.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                tools=tools_schema or None,  # type: ignore[arg-type]
            )
            span.set_attribute("gen_ai.response.model", response.model)
            choice = response.choices[0]
            span.set_attribute(
                "gen_ai.completion",
                choice.message.content
                or json.dumps([tc.model_dump() for tc in (choice.message.tool_calls or [])]),
            )
            if response.usage is not None:
                span.set_attribute("gen_ai.usage.input_token_count", response.usage.prompt_tokens)
                span.set_attribute(
                    "gen_ai.usage.output_token_count", response.usage.completion_tokens
                )
            return response

    async def run_turn(self, user_message: str, *, max_tool_iterations: int = 4) -> AgentTurnResult:
        async with (
            create_mcp_http_client(
                headers={"Authorization": f"Bearer {self._bearer_token}"}
            ) as http_client,
            streamable_http_client(self._gateway_url, http_client=http_client) as (
                read_stream,
                write_stream,
            ),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            catalog = await session.list_tools()
            tools_schema = [_tool_to_openai_schema(t) for t in catalog.tools]

            # User message first, system second: some tool-calling models
            # (verified 2026-09-14 against OCI's meta.llama-3.3-70b-instruct)
            # reject "Tool calling for this Llama model requires the first
            # message to be a user message" if a system message leads --
            # this ordering works for that model and remains valid for
            # standard OpenAI-compatible APIs, which don't require `system`
            # to be first.
            messages: list[dict[str, Any]] = [
                {"role": "user", "content": user_message},
                {"role": "system", "content": self._system_prompt},
            ]
            attempted: list[str] = []
            denied: list[str] = []

            for _ in range(max_tool_iterations):
                response = await self._call_llm(messages, tools_schema)
                choice = response.choices[0]

                if not choice.message.tool_calls:
                    result = AgentTurnResult(
                        final_message=choice.message.content or "",
                        tools_attempted=attempted,
                        tools_denied=denied,
                    )
                    self._emit_turn_completed(result)
                    return result

                messages.append(choice.message.model_dump(exclude_none=True))
                for tool_call in choice.message.tool_calls:
                    if tool_call.type != "function":
                        # This RI only ever offers function-style tools (see
                        # _tool_to_openai_schema) -- a custom tool call would
                        # mean the model invented a call shape we never
                        # advertised; skip it rather than guess at it.
                        continue
                    name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    attempted.append(name)
                    tool_result = await session.call_tool(name, arguments)
                    if tool_result.is_error:
                        denied.append(name)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": _result_to_text(tool_result),
                        }
                    )

            result = AgentTurnResult(
                final_message="(reached the tool-iteration limit without a final answer)",
                tools_attempted=attempted,
                tools_denied=denied,
            )
            self._emit_turn_completed(result)
            return result

    def _emit_turn_completed(self, result: AgentTurnResult) -> None:
        if self._audit_sink is None:
            return
        # ADR-022: telemetry is fail-open, never aborts the turn.
        with contextlib.suppress(Exception):
            self._audit_sink.emit(
                agent_turn_completed(
                    agent=self._agent_name,
                    tools_attempted=result.tools_attempted,
                    tools_denied=result.tools_denied,
                )
            )
