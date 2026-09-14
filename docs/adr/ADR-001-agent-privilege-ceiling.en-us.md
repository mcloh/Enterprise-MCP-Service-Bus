# ADR-001: MaximumEntitlement Boundary at the MCP Client

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, where applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Who defines the agent's privilege ceiling.

## Decision

MCP Client (authenticated identity) is the `MaximumEntitlement` boundary, never the agent/prompt.

## Alternatives Considered

Authorization by self-declared role of the agent.

## Consequences

All EP-01/EP-04 design revolves around the client's identity, not the agent's.
