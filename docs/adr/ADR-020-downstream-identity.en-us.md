# ADR-020: Downstream identity: token exchange or isolated service account

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, when applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Downstream identity in the RI (closes G5/P5).

## Decision

Token exchange (RFC 8693) when the backend supports OIDC; otherwise a service account isolated per adapter.

## Alternatives Considered

Always reusing the client's token (forbidden by ADR-006).

## Consequences

EP-07; documented per backend in the manifest.
