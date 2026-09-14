# ADR-016: Agent Runtime dispatch/handoff contract

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, when applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Agent Runtime dispatch/handoff contract.

## Decision

Versioned dispatch object (`decisionId`, `expiresAt`, `reasonCodes`) that does not replace the MCP Client's token.

## Alternatives Considered

Runtime injecting its own credentials into the agent.

## Consequences

EP-12-T01 consumes exclusively the dispatch object + the already-existing MCP Client.
