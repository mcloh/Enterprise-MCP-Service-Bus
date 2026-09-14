"""Sales backend for the Modo A multiagent demo (EP-13-T05, ADR-024).

A thin factory around the same `ExampleAgent` (EP-13-T01) every other
example-agent test already uses -- bound to a Sales MCP Client identity
(`sales-read-agent`/`sales-write-agent`, EP-01). Nothing about `ExampleAgent`
itself is Sales-specific; only the bearer token and system prompt differ
from `finance_agent`, which is the point (ADR-023: the security boundary is
identity/credential, never code path or prompt text).
"""

from __future__ import annotations

from openai import AsyncOpenAI

from emcp_bus.audit.sink import AuditSink
from example_agent.agent import ExampleAgent

SYSTEM_PROMPT = (
    "You are a helpful assistant for a sales team. Use only the tools you are "
    "given -- never claim to have capabilities outside them, and never invent "
    "a tool name that wasn't offered to you. If the customer wants to pay an "
    "invoice or discuss a payment, tell them you will connect them with "
    "billing -- you cannot process payments yourself."
)


def build_sales_agent(
    *,
    gateway_url: str,
    bearer_token: str,
    llm_client: AsyncOpenAI,
    model: str,
    audit_sink: AuditSink | None = None,
) -> ExampleAgent:
    return ExampleAgent(
        gateway_url=gateway_url,
        bearer_token=bearer_token,
        llm_client=llm_client,
        model=model,
        agent_name="sales_agent",
        system_prompt=SYSTEM_PROMPT,
        audit_sink=audit_sink,
    )
