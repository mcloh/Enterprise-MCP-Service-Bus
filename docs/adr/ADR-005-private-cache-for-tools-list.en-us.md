# ADR-005: Private cache for tools/list

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, where applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

`tools/list` cache shared across clients.

## Decision

`cacheScope=private`, key = identity+context+policy_version.

## Alternatives Considered

Shared cache for performance.

## Consequences

EP-05-T03; dedicated isolation test (EP-15).
