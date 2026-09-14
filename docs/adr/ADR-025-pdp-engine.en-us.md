# ADR-025: OPA/Rego as the PDP engine

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, when applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

PDP engine (closes G3 — **decision confirmed by the author on 2026-09-11**; renumbered from ADR-010 to ADR-025 on 2026-09-11 to avoid colliding with the README's ADR-010, "Global Capability Registry Governance").

## Decision

OPA/Rego, self-hosted, OSS (Apache-2.0). Final decision, not subject to review. **Verified on 2026-09-11 via web search**: OPA is at v1.0+, with Rego v1 syntax as the default (a breaking change vs. v0) — EP-03 must write policies in Rego v1 syntax from the start.

## Alternatives Considered

Cedar (AWS, cited in §43.2); a custom engine in Python.

## Consequences

The entire EP-03 becomes coupled to OPA's REST API; policies versioned as code in Rego v1.
