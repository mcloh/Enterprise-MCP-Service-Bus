"""Private `tools/list` cache hint (EP-05-T03, README.md §13, Threat: Cache
leakage §28).

SEP-2549 (`ttlMs`/`cacheScope`) is a field pair the `mcp` SDK itself defines
(`mcp.server.caching.CacheHint`, `types.ListToolsResult.ttl_ms`/`.cache_scope`)
-- there is deliberately no hand-rolled HTTP cache here, only this thin
wrapper around the SDK's own primitive.

**Important, verified-empirically limitation of this RI's deployment
shape** (not a bug in this module): SEP-2549 belongs to protocol revision
2026-07-28, which the SDK implements as an entirely different wire mode --
a stateless, session-less per-request envelope (`mcp/server/_streamable_http_modern.py`:
"no `initialize` handshake, no `Mcp-Session-Id`") reached via `server/discover`,
never via the classic `initialize` handshake. `mcp_types.version.HANDSHAKE_PROTOCOL_VERSIONS`
(everything reachable via `ClientSession.initialize()`) and
`MODERN_PROTOCOL_VERSIONS` (`("2026-07-28",)`, the stateless mode) are
disjoint sets. This RI's entire transport -- the Gateway's inbound side *and*
every downstream connection it opens (`_with_downstream_session`) -- uses the
classic session handshake exclusively, so a connection here can never
negotiate 2026-07-28, and the SDK's own per-version wire sieve
(`ServerRunner._serialize`) deliberately strips `ttlMs`/`cacheScope` for
every version outside `MODERN_PROTOCOL_VERSIONS` ("2026-era vocabulary
cannot be delivered on a legacy wire"). Concretely: `tools_list_cache_hint()`
below is computed correctly and set on every `ListToolsResult` `on_list_tools`
returns, but on today's wire the client only ever sees the field's own
default (`ttl_ms=0`, `cache_scope="private"`) -- which happens to be the
maximally conservative fallback (`ttl_ms=0` means "never treat this as
fresh," i.e. no caching benefit, but also no risk), not an unsafe one. This
code is kept anyway: it costs nothing, is exactly correct if this Gateway
ever adds the stateless per-request transport mode, and documents the
intended behavior precisely. See
`tests/e2e/test_governed_gateway.py::test_tools_list_cache_scope_is_always_private`
for what is actually verifiable given this constraint.

The Gateway's own `on_list_tools` already recomputes `MaximumEntitlement`
fresh on every call (no server-side caching of the filtered catalog across
clients), so cross-client leakage (Teste 5, §45) cannot happen regardless of
what any hint does or doesn't tell a *client* to do locally, and regardless
of whether `ttl_ms` reaches the wire: this module's job is telling a
well-behaved client on a future/modern transport the two things it would
need to cache safely -- how long, and, per SEP-2549's contract, "private"
scope, so a cached tools/list result is scoped to a client's own
authorization context and never shared with a different one.

Revocation (EP-04-T03) is honored independently of `ttl_ms`: a revoked
client's *next* `tools/list`/`tools/call` is re-evaluated server-side
regardless of whether its own local cache still thinks a prior response is
fresh -- this hint is an optimization for a well-behaved client, never the
Gateway's own source of truth.
"""

from __future__ import annotations

import os

from mcp.server.caching import CacheHint

_DEFAULT_TTL_MS = 5_000


def tools_list_cache_hint() -> CacheHint:
    ttl_ms = int(os.environ.get("EMCP_TOOLS_LIST_CACHE_TTL_MS", str(_DEFAULT_TTL_MS)))
    # `scope` is never "public": a discovery result depends on the caller's
    # own MaximumEntitlement, so it must never be treated as reusable across
    # a different authorization context.
    return CacheHint(ttl_ms=ttl_ms, scope="private")
