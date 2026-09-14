"""Finance backend for the Modo A multiagent demo (EP-13-T05, ADR-024).

Same shape as `backends.sales_agent` -- a thin factory around `ExampleAgent`
bound to the `finance-payments-agent` MCP Client identity (EP-01) instead.
See `sales_agent/__init__.py`'s module docstring for why the two backends
share everything except identity/prompt.
"""

from __future__ import annotations

from openai import AsyncOpenAI

from emcp_bus.audit.sink import AuditSink
from example_agent.agent import ExampleAgent

SYSTEM_PROMPT = (
    "You are a helpful assistant for a finance/billing team. Use only the "
    "tools you are given -- never claim to have capabilities outside them, "
    "and never invent a tool name that wasn't offered to you. Executing a "
    "payment above the approval threshold always requires a human approval "
    "before it can complete -- never tell the customer it is done until the "
    "tool result confirms it."
)


def build_finance_agent(
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
        agent_name="finance_agent",
        system_prompt=SYSTEM_PROMPT,
        audit_sink=audit_sink,
    )
