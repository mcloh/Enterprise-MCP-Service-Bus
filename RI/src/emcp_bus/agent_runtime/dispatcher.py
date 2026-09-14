"""Dispatch service (EP-12-T01, README.md §6.13).

Consumes an `NBADecision` (EP-11-T03) and invokes the MCP Client already
registered for the target agent (EP-01) against the real Gateway -- the
Agent Runtime never generates or stores its own credential; the only
credential this module ever presents to the Gateway is the one the
already-registered MCP Client obtains for itself (`AgentTokenProvider`,
typically a `client_credentials` grant against the same IdP as any other
MCP Client, EP-01-T01). This is the exact same governed path any MCP Client
takes -- `tools/list`/`tools/call` are reauthorized by the Gateway/PDP
(EP-05/EP-03) precisely as if a human-operated client had called them; the
Agent Runtime has no elevated path of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx
import mcp_types as types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import (  # type: ignore[attr-defined]
    create_mcp_http_client,
    streamable_http_client,
)

from emcp_bus.orchestrator.nba_model import NBADecision


class UnknownAgentError(Exception):
    pass


class AgentCredentialError(Exception):
    """The IdP rejected the registered MCP Client's own credential request --
    callers must treat this as a failed dispatch, never fall back to any
    other credential (there is none to fall back to)."""


class AgentTokenProvider(Protocol):
    async def token_for(self, agent: str) -> str: ...


@dataclass(frozen=True)
class AgentClientCredentials:
    client_id: str
    client_secret: str
    token_endpoint: str


class OIDCAgentTokenProvider:
    """Reference `AgentTokenProvider`: a real `client_credentials` grant per
    agent, against whichever IdP that agent's MCP Client is registered with
    (EP-01-T01) -- structurally identical to how any other MCP Client
    authenticates, because it *is* one."""

    def __init__(
        self,
        credentials_by_agent: dict[str, AgentClientCredentials],
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._credentials_by_agent = credentials_by_agent
        self._http = http_client or httpx.AsyncClient()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def token_for(self, agent: str) -> str:
        credentials = self._credentials_by_agent.get(agent)
        if credentials is None:
            raise UnknownAgentError(agent)
        try:
            response = await self._http.post(
                credentials.token_endpoint,
                data={
                    "grant_type": "client_credentials",
                    "client_id": credentials.client_id,
                    "client_secret": credentials.client_secret,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AgentCredentialError(
                f"Failed to obtain a token for agent {agent!r}: {exc}"
            ) from exc
        token: str = response.json()["access_token"]
        return token


@dataclass(frozen=True)
class DispatchResult:
    decision_id: str
    action: str
    status: Literal["allowed", "denied"]
    structured_content: dict[str, Any] | None
    error_text: str | None = None


class AgentDispatcher:
    def __init__(self, *, gateway_url: str, token_provider: AgentTokenProvider) -> None:
        self._gateway_url = gateway_url
        self._token_provider = token_provider

    async def dispatch(self, nba: NBADecision, *, arguments: dict[str, Any]) -> DispatchResult:
        """Calls `nba.action` through the real Gateway, authenticated as the
        MCP Client registered for `nba.agent` -- never as a credential this
        module invented. Whatever the Gateway/PDP decides (allowed or
        denied) is exactly what `DispatchResult` reports; this method never
        second-guesses or retries around a denial (that is
        `emcp_bus.orchestrator.fallback.handle_denial`'s job, one layer up)."""
        token = await self._token_provider.token_for(nba.agent)
        async with (
            create_mcp_http_client(headers={"Authorization": f"Bearer {token}"}) as http_client,
            streamable_http_client(self._gateway_url, http_client=http_client) as (
                read_stream,
                write_stream,
            ),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            result = await session.call_tool(nba.action, arguments)

        if not isinstance(result, types.CallToolResult):
            raise TypeError(f"Unexpected dispatch result type: {type(result)!r}")

        if result.is_error:
            error_text = (
                " ".join(getattr(item, "text", "") for item in result.content).strip() or None
            )
            return DispatchResult(
                decision_id=nba.decision_id,
                action=nba.action,
                status="denied",
                structured_content=None,
                error_text=error_text,
            )
        return DispatchResult(
            decision_id=nba.decision_id,
            action=nba.action,
            status="allowed",
            structured_content=result.structured_content,
        )
