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

Routing is resolved per capability through the Enterprise MCP Fabric router
(EP-06-T01, `emcp_bus.fabric.router.CapabilityRouter`) against the Global
Capability Registry (EP-02-T03), seeded at startup from `config/capabilities/`
-- not a hard-coded single downstream. A client's `tools/list` may therefore
span more than one backend (e.g. Sales + Finance); `tools/call` always
re-resolves the one backend that specific tool routes to.

Configuration is read from the environment lazily, inside `lifespan()`/
`build_auth()`, rather than into module-level constants at import time:
every RI service is one process per deployment in production, so this is
purely about correctness (env vars can differ across a Starlette app's
lifespan runs within one Python process, which the test suite relies on to
exercise multiple configurations without re-importing this module).

Tracing is automatic (see `common/otel.py`): the SDK's `OpenTelemetryMiddleware`
correlates every hop without any manual span code here; `emcp_bus.audit.correlation`
adds the business-level decision/entitlement/policy ids as span attributes on
top of that (EP-08-T03).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import mcp_types as types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import (  # type: ignore[attr-defined]
    create_mcp_http_client,
    streamable_http_client,
)
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from pydantic import AnyHttpUrl
from starlette.types import ASGIApp

from emcp_bus.approval.service import ApprovalService
from emcp_bus.audit import events
from emcp_bus.audit.correlation import (
    DecisionCorrelation,
    compute_policy_decision_id,
    new_decision_id,
)
from emcp_bus.audit.sink import AuditSink, JSONLFileAuditSink
from emcp_bus.common.config import load_yaml_models
from emcp_bus.common.otel import setup_tracing
from emcp_bus.downstream.identity import (
    BackendCredentialProvider,
    BackendCredentialUnavailableError,
    TokenExchangeClient,
    UnknownBackendError,
)
from emcp_bus.downstream.models import BackendConfig
from emcp_bus.entitlement.manager import EntitlementManager, UnknownClientError
from emcp_bus.entitlement.models import ClientProfile
from emcp_bus.fabric.router import CapabilityRouter, UnroutableCapabilityError
from emcp_bus.gateway.cache import tools_list_cache_hint
from emcp_bus.gateway.canonical_request import CanonicalRequestGate
from emcp_bus.identity.authn import TokenValidator
from emcp_bus.identity.models import ClientRegistration
from emcp_bus.identity.token_verifier import MCPTokenVerifier
from emcp_bus.pdp.client import PDPClient, PDPUnavailableError, compute_policy_version
from emcp_bus.pdp.models import PDPOutcome
from emcp_bus.registry.seed import seed_registry
from emcp_bus.registry.store import RegistryStore

setup_tracing("emcp-gateway")

_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class GatewayConfig:
    opa_url: str
    config_dir: Path
    oidc_jwks_url: str
    oidc_issuer: str
    oidc_audience: str
    audit_log_path: str
    token_exchange_client_id: str
    token_exchange_client_secret: str

    @classmethod
    def from_env(cls) -> GatewayConfig:
        return cls(
            opa_url=os.environ.get("OPA_URL", "http://127.0.0.1:8181"),
            config_dir=Path(os.environ.get("EMCP_CONFIG_DIR", str(_REPO_ROOT / "config"))),
            oidc_jwks_url=os.environ.get("OIDC_JWKS_URL", ""),
            oidc_issuer=os.environ.get("OIDC_ISSUER", ""),
            oidc_audience=os.environ.get("OIDC_AUDIENCE", "emcp-gateway"),
            audit_log_path=os.environ.get("EMCP_AUDIT_LOG_PATH", "/tmp/emcp-audit.jsonl"),
            # EP-07 RFC 8693: the Gateway's own confidential IdP client, used
            # to obtain and exchange tokens for backends configured with
            # `credential_mode: token_exchange` (downstream/models.py). Empty
            # (default) unless set -- backends in `service_account` mode
            # (the RI's seed config) never need this.
            token_exchange_client_id=os.environ.get("GATEWAY_TOKEN_EXCHANGE_CLIENT_ID", ""),
            token_exchange_client_secret=os.environ.get("GATEWAY_TOKEN_EXCHANGE_CLIENT_SECRET", ""),
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

    @property
    def backends_dir(self) -> Path:
        return self.config_dir / "backends"

    @property
    def capabilities_dir(self) -> Path:
        return self.config_dir / "capabilities"


@dataclass
class GatewayState:
    entitlement_manager: EntitlementManager
    pdp: PDPClient
    router: CapabilityRouter
    backend_credentials: BackendCredentialProvider
    approval_service: ApprovalService
    audit_sink: AuditSink


_current_state: GatewayState | None = None
"""The live `GatewayState` of whichever app instance is currently running.

Every other per-request need is served by `ctx.lifespan_context`
(`on_list_tools`/`on_call_tool`); this module-level mirror exists solely so
an out-of-band approver -- a CLI, an HTTP endpoint, a future Orchestrator
node (EP-11-T05) -- can reach the *same* `ApprovalService` instance the
Gateway's own `on_call_tool` consults, since none of those call sites go
through an MCP request context at all. `get_current_state()` is the
supported way to read it.
"""


def get_current_state() -> GatewayState:
    if _current_state is None:
        raise RuntimeError("Gateway is not running (lifespan has not started)")
    return _current_state


@asynccontextmanager
async def lifespan(server: Server[GatewayState]) -> AsyncIterator[GatewayState]:
    global _current_state
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

    token_exchange_client: TokenExchangeClient | None = None
    if config.token_exchange_client_id and config.token_exchange_client_secret:
        token_exchange_client = TokenExchangeClient(
            config.token_exchange_client_id, config.token_exchange_client_secret
        )
    backend_credentials = BackendCredentialProvider(
        load_yaml_models(config.backends_dir, BackendConfig),
        token_exchange_client=token_exchange_client,
    )

    # Fresh Registry per lifespan run (mirrors `manager`/`backend_credentials`
    # above): a temp file rather than `config_dir`-relative, so repeated
    # lifespan runs within one test process (see module docstring) never see
    # another run's stale state. Also not try/excepted: a Registry the
    # Gateway cannot seed at startup must not come up looking healthy either.
    registry_fd, registry_db_path_str = tempfile.mkstemp(prefix="emcp-registry-", suffix=".db")
    os.close(registry_fd)
    registry_db_path = Path(registry_db_path_str)
    registry = RegistryStore(registry_db_path)
    seed_registry(registry, config.capabilities_dir)
    router = CapabilityRouter(registry, backend_credentials)

    audit_sink = JSONLFileAuditSink(config.audit_log_path)

    state = GatewayState(
        entitlement_manager=manager,
        pdp=pdp,
        router=router,
        backend_credentials=backend_credentials,
        approval_service=ApprovalService(audit_sink=audit_sink),
        audit_sink=audit_sink,
    )
    _current_state = state
    try:
        yield state
    finally:
        _current_state = None
        await pdp.aclose()
        if token_exchange_client is not None:
            await token_exchange_client.aclose()
        registry_db_path.unlink(missing_ok=True)


async def _with_downstream_session[ResultT](
    downstream_url: str,
    backend_token: str,
    coro_factory: Callable[[ClientSession], Awaitable[ResultT]],
) -> ResultT:
    """Open a fresh downstream connection for one request and run `coro_factory(session)`.

    `backend_token` is the *outbound* credential (EP-07-T01) -- never the
    inbound MCP Client's own bearer token (README.md §20, ADR-006: no blind
    token passthrough). A connection per call is simpler and safer than a
    shared long-lived session under concurrent requests; connection
    pooling/reuse per backend is a natural extension of the Fabric router
    (EP-06-T01), not implemented in this milestone.
    """
    async with (
        create_mcp_http_client(headers={"Authorization": f"Bearer {backend_token}"}) as http_client,
        streamable_http_client(downstream_url, http_client=http_client) as (
            read_stream,
            write_stream,
        ),
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


def _request_id_str(ctx: ServerRequestContext[GatewayState]) -> str | None:
    return str(ctx.request_id) if ctx.request_id is not None else None


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

    state.audit_sink.emit(
        events.client_authenticated(
            client_id=access_token.client_id, mcp_request_id=_request_id_str(ctx)
        )
    )

    # EP-06-T01: query only the backends that actually serve a tool this
    # client is entitled to, never every registered backend -- e.g. a
    # Sales.Read client never opens a connection to the Finance backend.
    all_tools: list[types.Tool] = []
    for backend_id in sorted(state.router.distinct_backends_for(resolved.allowed_tools)):
        try:
            credential = await state.backend_credentials.credential_for(backend_id)
        except (UnknownBackendError, BackendCredentialUnavailableError):
            continue
        downstream_result = await _with_downstream_session(
            credential.url, credential.token, lambda session: session.list_tools(params=params)
        )
        all_tools.extend(t for t in downstream_result.tools if t.name in resolved.allowed_tools)

    state.audit_sink.emit(
        events.tools_list_filtered(
            client_id=access_token.client_id,
            profile_name=resolved.profile_name,
            entitlement_version=resolved.entitlement_version,
            allowed=len(all_tools),
            total=len(resolved.allowed_tools),
        )
    )
    # EP-05-T03: see cache.py's module docstring -- `ttl_ms` will not
    # actually reach a client on this RI's classic-session transport (a
    # verified SDK/wire-mode constraint, not a bug here), but `cache_scope`
    # is always "private" regardless, and this is exactly correct if this
    # Gateway ever adds the stateless per-request (2026-07-28) transport.
    hint = tools_list_cache_hint()
    return types.ListToolsResult(tools=all_tools, ttl_ms=hint.ttl_ms, cache_scope=hint.scope)


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

    arguments = dict(params.arguments or {})
    correlation = DecisionCorrelation(
        decision_id=new_decision_id(),
        policy_decision_id=compute_policy_decision_id(
            policy_version=state.pdp.policy_version,
            client_profile=resolved.profile_name,
            tool=params.name,
            arguments=arguments,
        ),
        entitlement_version=resolved.entitlement_version,
        policy_version=state.pdp.policy_version,
        mcp_request_id=_request_id_str(ctx),
    )
    correlation.record_on_current_span()

    try:
        decision = await state.pdp.evaluate(
            client_profile=resolved.profile_name, tool=params.name, arguments=arguments
        )
    except PDPUnavailableError:
        state.audit_sink.emit(
            events.pdp_unavailable(client_id=access_token.client_id, tool=params.name)
        )
        return _denied("PDP_UNAVAILABLE")

    if decision.outcome is PDPOutcome.DENY:
        state.audit_sink.emit(
            events.tool_call_denied(
                client_id=access_token.client_id,
                profile_name=resolved.profile_name,
                tool=params.name,
                reason_code=decision.reason_code,
                correlation=correlation,
            )
        )
        return _denied(decision.reason_code)

    if decision.outcome is PDPOutcome.REQUIRE_APPROVAL:
        try:
            approved = state.approval_service.check_and_consume(
                client_profile=resolved.profile_name, tool=params.name, arguments=arguments
            )
        except Exception:  # noqa: BLE001 -- EP-14-T03: any approval-service failure is DENY, never ALLOW
            approved = False
        if not approved:
            # Out-of-band from here: an approver calls ApprovalService.grant()
            # with this approval_id (CLI/API today; EP-11-T05's Orchestrator
            # interrupt node later) before the caller retries the same call.
            request = state.approval_service.request(
                client_profile=resolved.profile_name,
                tool=params.name,
                arguments=arguments,
                reason_code=decision.reason_code,
            )
            state.audit_sink.emit(
                events.tool_call_require_approval(
                    client_id=access_token.client_id,
                    profile_name=resolved.profile_name,
                    tool=params.name,
                    approval_id=request.approval_id,
                    correlation=correlation,
                )
            )
            return _denied(f"REQUIRE_APPROVAL:{decision.reason_code}:{request.approval_id}")

    try:
        route = await state.router.route(params.name)
    except UnroutableCapabilityError:
        state.audit_sink.emit(
            events.tool_call_denied(
                client_id=access_token.client_id,
                profile_name=resolved.profile_name,
                tool=params.name,
                reason_code="UNROUTABLE_CAPABILITY",
                correlation=correlation,
            )
        )
        return _denied("UNROUTABLE_CAPABILITY")

    if route.backend_type != "mcp":
        # EP-06-T04: a "rest"/"grpc" backend.type has no seed capability yet
        # (see fabric/adapters/rest_adapter.py's module docstring) -- fail
        # closed rather than guess at a dispatch path with no test coverage.
        state.audit_sink.emit(
            events.backend_credential_unavailable(
                client_id=access_token.client_id, tool=params.name, backend=route.backend_id
            )
        )
        return _denied(f"UNSUPPORTED_BACKEND_TYPE:{route.backend_type}")

    result = await _with_downstream_session(
        route.url,
        route.credential_token,
        lambda session: session.call_tool(params.name, params.arguments or {}),
    )
    if isinstance(result, types.CallToolResult):
        state.audit_sink.emit(
            events.tool_call_allowed(
                client_id=access_token.client_id,
                profile_name=resolved.profile_name,
                tool=params.name,
                correlation=correlation,
            )
        )
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


def build_app(
    auth_settings: AuthSettings | None,
    token_verifier: TokenVerifier | None,
    *,
    host: str = "127.0.0.1",
) -> ASGIApp:
    """The Gateway's real ASGI app: the MCP Server wrapped with EP-05-T08's
    header/body consistency gate. Used by `main()` and by the test suite, so
    tests exercise the exact same wiring a deployment runs, not a stripped
    down variant of it."""
    app = server.streamable_http_app(host=host, auth=auth_settings, token_verifier=token_verifier)
    return CanonicalRequestGate(app)


def main() -> None:
    import uvicorn

    host = os.environ.get("GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("GATEWAY_PORT", "8000"))
    auth_settings, token_verifier = build_auth()
    app = build_app(auth_settings, token_verifier, host=host)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
