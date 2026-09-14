# ADR-002: MCP Gateway as the sole PEP

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, where applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Where to apply enforcement.

## Decision

MCP Gateway is the sole PEP; it never delegates the ALLOW/DENY decision to the LLM.

## Alternatives Considered

Distributed enforcement in each MCP Server.

## Consequences

Centralizes EP-05; domain servers (EP-06) do not reimplement authz.
