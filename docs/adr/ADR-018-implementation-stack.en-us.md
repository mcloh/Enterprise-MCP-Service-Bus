# ADR-018: RI implementation stack

**Status:** Accepted.
**Source:** this ADR is the canonical record of this decision. For implementation and validation context, see `RI/docs/AS-BUILT.md` and, when applicable, the relevant contract in `RI/docs/interfaces/`.

## Context

RI implementation stack (closes G2).

## Decision

Python 3.12+, `uv`, Pydantic v2, declarative YAML with JSON Schema, official `mcp` SDK.

## Alternatives Considered

Node/TypeScript (the MCP SDK is also official there); Go.

## Consequences

Defines the entire repository structure (8.5).

## Confirmed Versions (EP-16-T04)

Dependency-free spike, runnable at any time (EP-16-T04): confirm,
immediately before pinning in `pyproject.toml`/
`docker-compose.yml`, the exact stable version numbers of each piece of the
stack — no version cited in code/config without real confirmation
(`pip index versions`/direct download/actual install), never from memory.
Consolidated record, with the date each group was verified (see
`RI/README.md`, "Versões fixadas", for the same list maintained alongside
`pyproject.toml`):

Confirmed on 2026-09-11:

- `mcp` 2.2.0 (Python SDK v2 — the API changed significantly from v1; see
  comments in `src/emcp_bus/gateway/server.py`)
- `pydantic` 2.13.x, `opentelemetry-sdk` 1.44.x, `uvicorn` 0.52.x,
  `pyjwt[crypto]` 2.14.x, `ruff` 0.16.x, `mypy` 2.3.x, `pytest` 9.1.x
- `OPA` 1.20.2 (static binary, Rego v1 syntax as default)
- `pytest-forked` 1.7.x

Confirmed on 2026-09-14 (M3/M4, via actual install/`docker pull`):

- `langgraph` 0.6.x + `langgraph-checkpoint-sqlite` 2.x (EP-11)
- `hypothesis` 6.1xx.x (dev, EP-10-T02)
- `openai` 1.109.x (EP-13-T01)
- `python-dotenv` 1.2.x (dev)
- `types-jsonschema` 4.26.x (dev, stubs for `mypy --strict`; `jsonschema`
  itself was already a transitive dependency of `mcp[cli]`, EP-15-T01)
- Langfuse self-hosted 4.35.0 (`docker.langfuse.com/langfuse/langfuse:4`,
  official image, EP-13-T02)
- Keycloak 26.7.3 (`quay.io/keycloak/keycloak:26.7.3`, Quarkus; Standard
  Token Exchange GA since 26.2 — EP-01-T01/EP-07)
- `opentelemetry-collector-contrib` 0.114.0 and `jaeger` (all-in-one) 1.62.0
  (`observability` profile of `docker-compose.yml`, EP-08-T04)

None of the versions above have changed since the original confirmation — this
record is the single source of truth that `RI/README.md` links back to.
