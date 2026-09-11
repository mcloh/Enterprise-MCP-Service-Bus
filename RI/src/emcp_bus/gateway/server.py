"""MCP Gateway / PEP (EP-05-T01/T02/T04).

Enforces the two invariants of README.md §9/§10:
- `tools/list` returns the intersection of the downstream catalog and the
  authenticated client's MaximumEntitlement (filtered discovery, RF-03).
- `tools/call` is re-authorized independently of whatever `tools/list`
  returned -- the PDP is consulted on every call, never skipped because a
  tool was (or wasn't) visible in a prior discovery response (RF-04, Axiom 5).

No identity, no discovery, no execution (README.md §5): a request with no
valid access token gets an empty tool list and every `tools/call` denied --
this is the correct behavior when EP-01-T01 (Keycloak or any OIDC IdP) is
not configured for a given deployment, not a bug to work around.

Fail-closed (README.md §38, EP-05-T06): a PDP that cannot be reached is a
DENY, not an ALLOW -- see the `PDPUnavailableError` branch in `on_call_tool`.

Configuration is read from the environment lazily, inside `lifespan()`/
`build_auth()`, rather than into module-level constants at import time:
every RI service is one process per deployment in production, so this is
purely about correctness (env vars can differ across a Starlette app's
lifespan runs within one Python process, which the test suite relies on to
exercise multiple configurations without re-importing this module).

Tracing is automatic (see `common/otel.py`): the SDK's `OpenTelemetryMiddleware`
correlates every hop without any manual span code here.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import mcp_types as types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from pydantic import AnyHttpUrl

from emcp_bus.common.config import load_yaml_models
from emcp_bus.common.otel import setup_tracing
from emcp_bus.entitlement.manager import EntitlementManager, UnknownClientError
from emcp_bus.entitlement.models import ClientProfile
from emcp_bus.identity.authn import TokenValidator
from emcp_bus.identity.models import ClientRegistration
from emcp_bus.identity.token_verifier import MCPTokenVerifier
from emcp_bus.pdp.client import PDPClient, PDPUnavailableError, compute_policy_version
from emcp_bus.pdp.models import PDPOutcome

setup_tracing("emcp-gateway")

_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class GatewayConfig:
    downstream_url: str
    opa_url: str
    config_dir: Path
    oidc_jwks_url: str
    oidc_issuer: str
    oidc_audience: str

    @classmethod
    def from_env(cls) -> GatewayConfig:
        return cls(
            downstream_url=os.environ.get("SALES_DOMAIN_URL", "http://127.0.0.1:8100/mcp"),
            opa_url=os.environ.get("OPA_URL", "http://127.0.0.1:8181"),
            config_dir=Path(os.environ.get("EMCP_CONFIG_DIR", str(_REPO_ROOT / "config"))),
            oidc_jwks_url=os.environ.get("OIDC_JWKS_URL", ""),
            oidc_issuer=os.environ.get("OIDC_ISSUER", ""),
            oidc_audience=os.environ.get("OIDC_AUDIENCE", "emcp-gateway"),
        )

    @property
    def clients_dir(self) -> Path:
        return self.config_dir / "clients"

    @property
    def profiles_dir(self) -> Path:
        return self.clients_dir / "profiles"

    @property
    def policies_dir(self) -> Path:
        return self.config_dir / "policies"


@dataclass
class GatewayState:
    entitlement_manager: EntitlementManager
    pdp: PDPClient
    downstream_url: str


@asynccontextmanager
async def lifespan(server: Server[GatewayState]) -> AsyncIterator[GatewayState]:
    config = GatewayConfig.from_env()
    pdp = PDPClient(
        base_url=config.opa_url, policy_version=compute_policy_version(config.policies_dir)
    )
    manager = EntitlementManager(pdp)
    manager.load_registrations(load_yaml_models(config.clients_dir, ClientRegistration))
    manager.load_profiles(load_yaml_models(config.profiles_dir, ClientProfile))
    # Deliberately not try/excepted: a PDP the Gateway cannot sync entitlements
    # to at startup must not come up looking healthy (README.md §38).
    await manager.sync_profiles_to_pdp()
    try:
        yield GatewayState(
            entitlement_manager=manager, pdp=pdp, downstream_url=config.downstream_url
        )
    finally:
        await pdp.aclose()


async def _with_downstream_session[ResultT](
    downstream_url: str,
    coro_factory: Callable[[ClientSession], Awaitable[ResultT]],
) -> ResultT:
    """Open a fresh downstream connection for one request and run `coro_factory(session)`.

    A connection per call is simpler and safer than a shared long-lived
    session under concurrent requests; the Enterprise MCP Fabric (EP-06) is
    where connection pooling/reuse per backend would be introduced later.
    """
    async with (
        streamable_http_client(downstream_url) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        return await coro_factory(session)


def _denied(reason_code: str) -> types.CallToolResult:
    """A deterministic denial the calling agent can observe and react to
    (README.md §10/§14: "Operação bloqueada") -- a structured tool-result,
    not a raised protocol-level error, matching real MCP tool-failure shape.
    """
    return types.CallToolResult(
        is_error=True,
        content=[types.TextContent(type="text", text=f"Access denied: {reason_code}")],
    )


async def on_list_tools(
    ctx: ServerRequestContext[GatewayState],
    params: types.PaginatedRequestParams | None,
) -> types.ListToolsResult:
    access_token = get_access_token()
    if access_token is None:
        return types.ListToolsResult(tools=[])

    state = ctx.lifespan_context
    try:
        resolved = state.entitlement_manager.resolve(access_token.client_id)
    except UnknownClientError:
        return types.ListToolsResult(tools=[])

    downstream_result = await _with_downstream_session(
        state.downstream_url, lambda session: session.list_tools(params=params)
    )
    filtered_tools = [
        tool for tool in downstream_result.tools if tool.name in resolved.allowed_tools
    ]
    return downstream_result.model_copy(update={"tools": filtered_tools})


async def on_call_tool(
    ctx: ServerRequestContext[GatewayState],
    params: types.CallToolRequestParams,
) -> types.CallToolResult:
    access_token = get_access_token()
    if access_token is None:
        return _denied("UNAUTHENTICATED")

    state = ctx.lifespan_context
    try:
        resolved = state.entitlement_manager.resolve(access_token.client_id)
    except UnknownClientError:
        return _denied("UNKNOWN_CLIENT")

    try:
        decision = await state.pdp.evaluate(
            client_profile=resolved.profile_name,
            tool=params.name,
            arguments=dict(params.arguments or {}),
        )
    except PDPUnavailableError:
        return _denied("PDP_UNAVAILABLE")

    if decision.outcome is PDPOutcome.DENY:
        return _denied(decision.reason_code)
    if decision.outcome is PDPOutcome.REQUIRE_APPROVAL:
        # EP-14 (human approval workflow) does not exist yet in this milestone
        # -- fail closed rather than silently upgrading to ALLOW.
        return _denied(f"REQUIRE_APPROVAL:{decision.reason_code}")

    result = await _with_downstream_session(
        state.downstream_url, lambda session: session.call_tool(params.name, params.arguments or {})
    )
    if isinstance(result, types.CallToolResult):
        return result
    raise TypeError(f"Unexpected downstream result type for tools/call: {type(result)!r}")


server = Server(
    "emcp-gateway",
    version="0.1.0",
    instructions="Enterprise MCP Service Bus Gateway / PEP.",
    lifespan=lifespan,
    on_list_tools=on_list_tools,
    on_call_tool=on_call_tool,
)


def build_auth(
    config: GatewayConfig | None = None,
) -> tuple[AuthSettings | None, TokenVerifier | None]:
    """Wires up OIDC bearer-token auth when EP-01-T01 (Keycloak or any OIDC
    IdP) is configured; otherwise both are `None` and every request is
    treated as unauthenticated (deny by default, see module docstring) -- a
    deliberate, safe default, not a placeholder to silence.
    """
    config = config or GatewayConfig.from_env()
    if not (config.oidc_jwks_url and config.oidc_issuer):
        return None, None

    token_validator = TokenValidator(
        jwks_url=config.oidc_jwks_url, issuer=config.oidc_issuer, audience=config.oidc_audience
    )
    token_verifier: TokenVerifier = MCPTokenVerifier(token_validator, resource=config.oidc_audience)
    # `TokenValidator` already checks `aud` against `oidc_audience` itself
    # (README.md §45 Teste 8), so the SDK's own RFC 8707 resource check is
    # left off here rather than requiring `oidc_audience` to also be a URL.
    auth_settings = AuthSettings(
        issuer_url=AnyHttpUrl(config.oidc_issuer),
        resource_server_url=AnyHttpUrl(f"https://emcp-bus.internal/{config.oidc_audience}"),
        validate_token_resource=False,
    )
    return auth_settings, token_verifier


def main() -> None:
    import uvicorn

    host = os.environ.get("GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("GATEWAY_PORT", "8000"))
    auth_settings, token_verifier = build_auth()
    app = server.streamable_http_app(host=host, auth=auth_settings, token_verifier=token_verifier)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
