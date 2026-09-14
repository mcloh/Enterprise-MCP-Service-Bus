# ADR-007: Backend never exposed directly to the client

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, where applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Is the backend directly accessible by the client?

## Decision

No — network/identity restrict access to the Gateway/Fabric only.

## Alternatives Considered

Exposing the Fabric publicly with "best effort" authz.

## Consequences

EP-05-T07, EP-15 (bypass test).
