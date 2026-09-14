# ADR-014: Profile never expands entitlement

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, when applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Can profile expand entitlement?

## Decision

Never — `FilteredOfferings ⊆ MaximumEntitlement`, profile only orders/reduces.

## Alternatives Considered

High-engagement profile unlocking new tools.

## Consequences

EP-10-T02 brings a property test validating the invariant for random inputs.
