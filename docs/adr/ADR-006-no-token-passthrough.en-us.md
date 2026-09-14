# ADR-006: Prohibition of token passthrough

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, where applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Can the agent's token be forwarded to the backend?

## Decision

No — blind token passthrough is prohibited; inbound ≠ outbound identity.

## Alternatives Considered

Direct passthrough of the client's token.

## Consequences

EP-07 implements exchange/service account per backend.
