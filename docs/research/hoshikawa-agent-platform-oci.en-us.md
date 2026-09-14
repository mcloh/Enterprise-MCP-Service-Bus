# Research: Agent Platform OCI (Christiano Hoshikawa) as a Python/LangGraph/Langfuse reference

> Source: https://github.com/hoshikawa2/agent_platform_oci (README + SPEC-001, 002, 003, 004, 007, 012, 018). Analyzed on 2026-09-11 to underpin the decisions recorded in [`ADR-022`](../adr/ADR-022-reference-hoshikawa-agent-platform-oci.en-us.md)/[`ADR-023`](../adr/ADR-023-authorization-never-comes-from-payload.en-us.md) (see also [`../../RI/docs/Assumptions.md`](../../RI/docs/Assumptions.md)). Referenced by ADR-022/ADR-023.
>
> **Scope of this research**: extract the *operational* LangGraph/Langfuse/MCP pattern from that project for our RI's Python implementation layer. The security core (PEP/PDP/Client-Bound Entitlement) of our architecture remains 100% defined by the `README.md` at the root of this repository — never by the project researched here.

---

## 1. LangGraph pattern

**StateGraph — nodes and state shape.** The per-backend graph is fixed and corporate:

```text
START → input_guardrails → routing_decision → [domain agent(s)] → output_supervisor
      → output_guardrails → judge → supervisor_review → persist → END
routing_decision → handoff → routing_decision   (conditional return edge)
```

`AgentState` is a `TypedDict(total=False)` with: `user_text, sanitized_input, response_text, tenant_id, agent_id, channel, session_id, conversation_key, message_id, route, intent, context, business_context, tool_arguments, mcp_tools, mcp_results, rag_context, rag_metadata, guardrails, judges, metadata, errors`, plus `active_transaction`/`last_transaction` in the transactional extension (a durable state contract that survives checkpoint/resume).

Registering a new agent is mechanical: import the class → instantiate it in the workflow's `__init__` (receiving shared dependencies: telemetry, tool_router, rag_service, cache, observer, memory) → async wrapper with a telemetry span → `builder.add_node(...)` → entry in `add_conditional_edges("routing_decision", ...)` → wiring to `output_supervisor`.

**Two routing layers, explicitly separated:**
- **Backend-local supervisor/router** — decides an agent's internal flow (`routing.yaml`, `ROUTING_MODE=router|supervisor`).
- **Global Supervisor / Agent Gateway** — a separate deployable service that decides **which whole backend** handles the conversation (`GLOBAL_ROUTING_MODE=router|supervisor|hybrid`, `backends.yaml`). HTTP routing between backends, not a second LangGraph.

**Checkpointing**: `memory` (tests), `sqlite` (local dev), `mongodb` (distributed), `autonomous` (OCI production) providers. Contract: `{conversation_key, checkpoint_id, state, pending_writes, created_at}`.

**Handoff**: intra-backend via the conditional edge `routing_decision → handoff → routing_decision`; inter-backend via `metadata.handover_backend` in the response, detected by the Agent Gateway, which keeps `global_session_id` separate from `backend_session_id`.

---

## 2. Langfuse pattern

**IC / NOC / GRL taxonomy** (not "Informational Context" — it's a **business/journey**, **operational**, and **guardrail** event, respectively):

| Family | Meaning | Examples |
|---|---|---|
| IC | agent business/journey event | `IC.GATEWAY_RECEIVED`, `IC.AGENT_STARTED/COMPLETED`, `IC.MCP_CACHE_HIT/MISS/SET/BYPASS/NOT_STORED`, `IC.MCP_TOOL_DEDUPED`, `IC.GLOBAL_BACKEND_SELECTED` |
| NOC | error/unavailability/timeout/degradation | `NOC.RUNTIME_FAILED`, `NOC.MCP_TIMEOUT`, `NOC.LLM_FAILED` |
| GRL | governance/guardrail/block/sanitization | `GRL.INPUT_BLOCKED`, `GRL.OUTPUT_BLOCKED`, `GRL.MASK_APPLIED` |

Practical rule: don't create an event per line of code — only for decisions that matter.

**Hybrid instrumentation**: automatic technical spans per graph node; LLM calls captured automatically via `ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION=true` (OpenAI-compatible providers); business events (IC/NOC/GRL) always manual via `_emit_ic/_emit_noc/_emit_grl`, **fail-open** (a missing or erroring observer never breaks the journey). Trace mode `LANGFUSE_TRACE_MODE=verbose|compact`.

**Prompt management**: **does not use** Langfuse's prompt CMS — versions the prompt locally in YAML (`prompt_policy.yaml`, `id`/`version` fields). Langfuse comes in as a data source for batch evaluation (`EvaluationRun.source=langfuse`, `evals/offline`/`evals/certification` apps), not as the synchronous judging engine (that is a node of the graph itself, using the `judge` LLM profile).

**Local setup (docker-compose)**: `langfuse-web`, `langfuse-worker`, PostgreSQL, ClickHouse, Redis, MinIO, plus MongoDB (the framework's own memory, not Langfuse's). Ports: Web/API 3005, MinIO S3 9090/Console 9091, MongoDB 27017, Postgres 5433, Redis 6379, ClickHouse 8124/9002. Flow: `docker compose up -d` → create org/project → generate a `pk-lf-.../sk-lf-...` key pair under Settings > API Keys → configure the backend's `.env`.

---

## 3. MCP integration pattern

**MCP Gateway**: a single deployable app — `/v1/tools`, `/v1/tools/{name}`, `/v1/tools/{name}/invoke`, `/v1/servers`, `/health`, `/ready`. `ToolInvocation`/`ToolResult` contracts carrying `tenant_id`, `agent_id`, `business_context`, `metadata.request_id/trace_id`.

**MCP Parameter Mapping** (`mcp_parameter_mapping.yaml`): translates canonical business keys (`customer_key`, `contract_key`, `session_key`) into the parameter name each tool expects.

**MCP cache with Langfuse events**: key `tenant_id:agent_id:tool_name:hash(arguments)`, idempotent tools only, per-tool TTL. Event flow: miss → `IC.MCP_CACHE_MISS → IC.MCP_TOOL_EXECUTING → IC.MCP_TOOL_EXECUTED → IC.MCP_CACHE_SET`; hit → just `IC.MCP_CACHE_HIT`.

**FastMCP** as the official MCP server default:
```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("telecom_mcp_server")

@mcp.tool()
def consultar_fatura(msisdn: str | None = None) -> dict: ...

mcp.run(transport="streamable-http")
```

### ⚠️ Critical finding: shallow and potentially insecure authorization

Their MCP Gateway's `authorization` block is a **static allowlist keyed by `agent_id`**:

```yaml
authorization:
  default_policy: deny
  agents:
    telecom_contas:
      allowed_tools: [consultar_fatura, consultar_pagamentos]
```

The `agent_id` field that governs this allowlist **arrives as data from the conversation's input payload** (`GatewayRequest`/`ToolInvocation`), not as a claim of an authenticated, independently verified MCP Client identity. Their own SPEC-004 admits it: *"conversational policy does not replace authentication, authorization, idempotency, or atomicity in the MCP Server."* There is no PDP/OPA/Cedar, no `policy_decision_id`/`entitlement_version`, no discovery/execution separation as two deliberately independent enforcement points.

**This is structurally the anti-pattern our RI's ADR-001 forbids** ("authorization by the agent's self-declared role"). See ADR-023 for the decision on how to reuse the proxy engineering without inheriting this problem.

---

## 4. YAML configuration conventions

| File | Purpose |
|---|---|
| `agents.yaml` | Agent registry (agent_id, isolated config paths, domain metadata) |
| `routing.yaml` | Intents, keywords/examples/priority, `mcp_tools` per intent, `state_policies` |
| `tools.yaml` | Tool catalog: target server, args schema, cache, `allowed_agents` |
| `guardrails.yaml` | Input/output guardrails, enable/disable by code |
| `judges.yaml` | Post-response evaluation criteria (deterministic/llm), threshold, sample_rate |
| `llm_profiles.yaml` | Model/temperature profiles per component (router, judge, supervisor, RAG) |
| `identity.yaml` | Channel field name aliases → canonical business keys (Identity Resolver) |
| `mcp_parameter_mapping.yaml` | Canonical key → parameter name expected by each tool |
| `mcp_servers.yaml` (+ `.docker.yaml`) | MCP server addresses/transport (local vs. Docker) |
| `backends.yaml` | Agent backend registry + Agent Gateway's global routing rules |
| `prompt_policy.yaml` | Base/persistent agent prompt, versioned (`id`, `version`) |
| `tool_policies.yaml` | Classifies a tool as `read_only`/`transactional`, requires confirmation |
| `authorization` (block in the MCP Gateway's config) | Tool allowlist by `agent_id` — **do not reuse as an authorization source** (see section 3) |

---

## 5. Security/identity model (SPEC-018) — compatibility

- **Workload authentication** (5 modes: config_file/instance_principal/workload_identity/resource_principal/api_key) — addresses how the *framework* itself authenticates against OCI resources (Vault, GenAI, ADB). **Orthogonal** to our tool-entitlement problem.
- **Authorization** — listed as 5 questions to answer, with no formal PDP; in practice resolved by the shallow allowlist described in section 3.
- **Secrets, data protection, channel security** — compatible/complementary, do not touch entitlement.
- **Auditing** — a good audit-trail model (user/channel, agent_id, tenant_id, tool, model, guardrail, judge score, trace_id), but with no equivalent to `decisionId`/`policyDecisionId`/`entitlementVersion` (our ADR-017), because there is no separate PDP generating those decisions.

**Where it is clearly compatible/orthogonal**: `identity.yaml`/`BusinessContext` — normalization of **business** identity (end customer, contract), never a tool-authorization decision. Adoptable without tension with the security core.

**Verdict**: SPEC-018 should not be used as a normative security spec for our RI — it mixes workload authentication with tool authorization without separating the two problems or proposing a PDP.

---

## 6. Deployment

Not tied to OCI at the application layer — runs 100% locally via Docker Compose with generic, self-hostable services (Redis, MongoDB, PostgreSQL, ClickHouse, MinIO, Langfuse). OCI integrations (GenAI, ADB, Vault, workload identity) are pluggable options among several, not a development requirement.

---

## Reuse recommendations (applied in the RI via ADR-022/ADR-023)

**Adopt as-is** (do not touch the security core): `identity.yaml`/BusinessContext · IC/NOC/GRL taxonomy + EventEnvelope · local Langfuse setup via docker-compose · `ConversationSummaryMemory` · RAG-vs-MCP heuristic (Hoshikawa §30.3-30.4: systems → MCP, documents → RAG) · `mcp_parameter_mapping.yaml` · FastMCP as the default MCP server.

**Adopt with adaptation**: the *shape* of the MCP Gateway's proxying (catalog, `ToolInvocation`/`ToolResult`, cache with events, retry/timeout/circuit breaker) — but the ALLOW/DENY decision is always delegated to our own PEP/PDP, never to their `authorization` block. The Agent Gateway/Global Supervisor layer (two session levels, handoff) informs the design of EP-11/EP-12, keeping it strictly as UX/business routing, never as an authorization authority. `tool_policies.yaml` (read_only/transactional + confirmation) is conversational convenience, not a security control.

**Do not copy as a source of security truth**: the `authorization` block keyed by a self-declared `agent_id` in the payload; SPEC-018 as authorization doctrine.
