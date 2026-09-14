# ADR-021: Scope of LangGraph and Langfuse in the RI

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, when applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

Scope of LangGraph/Langfuse (closes G8/P8).

## Decision

LangGraph only in the Service Orchestrator (EP-11) and the Agent Runtime handoff (EP-12); Langfuse only where there is an actual LLM call (EP-13). Checkpointer: SQLite in dev.

## Alternatives Considered

Also using LangGraph in the Gateway/Fabric for "stack consistency."

## Consequences

Avoids the over-engineering vetoed by section 6 of the superprompt; Gateway/Fabric remain plain Python.
