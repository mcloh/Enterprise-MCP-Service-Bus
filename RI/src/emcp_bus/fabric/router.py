"""Enterprise MCP Fabric core: capability router (EP-06-T01, README.md §6.7).

Resolves a `<domain>.<capability>` tool name to the backend that actually
serves it, using the Global Capability Registry (EP-02-T03) as the single
source of truth -- not a Gateway-local static mapping (the pre-M3 state this
replaces: `GatewayConfig.downstream_url`/`downstream_backend` hard-coded to
one backend, see git history of gateway/server.py). Only `ACTIVE` manifests
are routable (README.md §6.6): anything still in nominate/review/register,
or already deprecated/retired, is a control-plane-only concern the Fabric
must never dispatch a live call to.

The Registry says *which* backend id serves a capability
(`CapabilityManifest.backend.service`); `BackendCredentialProvider` (EP-07)
resolves that id to a connection URL and an outbound credential -- the
router itself never touches a socket.
"""

from __future__ import annotations

from dataclasses import dataclass

from emcp_bus.downstream.identity import BackendCredentialProvider, UnknownBackendError
from emcp_bus.registry.models import CapabilityManifest
from emcp_bus.registry.store import RegistryStore


class UnroutableCapabilityError(Exception):
    """`tool` has no ACTIVE capability manifest, or its backend is unresolvable.

    Callers (the Gateway) must treat this identically to DENY (README.md
    §38) -- never as "fall back to some default backend".
    """


@dataclass(frozen=True)
class BackendRoute:
    tool: str
    backend_id: str
    backend_type: str
    """`CapabilityManifest.backend.type`: "mcp" | "rest" | "grpc" (EP-06-T04
    dispatches "rest" through `fabric.adapters.rest_adapter`; "mcp" is
    handled directly by the Gateway via a downstream MCP session)."""
    url: str
    credential_token: str
    credential_audience: str


class CapabilityRouter:
    def __init__(
        self, registry: RegistryStore, backend_credentials: BackendCredentialProvider
    ) -> None:
        self._registry = registry
        self._backend_credentials = backend_credentials

    def route(self, tool: str) -> BackendRoute:
        manifest = self._active_manifest(tool)
        backend_ref = manifest.backend
        try:
            credential = self._backend_credentials.credential_for(backend_ref.service)
        except UnknownBackendError as exc:
            raise UnroutableCapabilityError(
                f"Capability {tool!r} references unknown backend {backend_ref.service!r}"
            ) from exc

        return BackendRoute(
            tool=tool,
            backend_id=backend_ref.service,
            backend_type=backend_ref.type,
            url=credential.url,
            credential_token=credential.token,
            credential_audience=credential.audience,
        )

    def active_capabilities_for(self, tool_names: frozenset[str]) -> list[CapabilityManifest]:
        """Every ACTIVE manifest whose name is in `tool_names` -- lets
        `on_list_tools` know which distinct backends it must actually query
        for a given client's entitlement, instead of always querying every
        registered backend (README.md §6.7)."""
        return [m for m in self._registry.list_active() if m.name in tool_names]

    def distinct_backends_for(self, tool_names: frozenset[str]) -> set[str]:
        return {m.backend.service for m in self.active_capabilities_for(tool_names)}

    def _active_manifest(self, tool: str) -> CapabilityManifest:
        for manifest in self._registry.list_active():
            if manifest.name == tool:
                return manifest
        raise UnroutableCapabilityError(f"No ACTIVE capability named {tool!r}")
