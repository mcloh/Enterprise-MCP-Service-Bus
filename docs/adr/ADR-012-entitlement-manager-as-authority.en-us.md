# ADR-012: Entitlement Manager as the sole authority for MaximumEntitlement

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, where applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Authority over the maximum menu.

## Decision

Entitlement Manager is the sole authority for `MaximumEntitlement`; it does not rank nor trust self-declared attributes from the LLM.

## Alternatives Considered

Merging Entitlement Manager and Offering Filter into a single component.

## Consequences

Keeps EP-04 and EP-10 as distinct services/modules with their own contracts.
