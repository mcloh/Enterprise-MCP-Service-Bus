# Pesquisa: Agent Platform OCI (Christiano Hoshikawa) como referência Python/LangGraph/Langfuse

> Fonte: https://github.com/hoshikawa2/agent_platform_oci (README + SPEC-001, 002, 003, 004, 007, 012, 018). Analisado em 2026-09-11 para fechar as lacunas G2/G8 do [`../RI-PLANNING.md`](../RI-PLANNING.md). Referenciado por ADR-022/ADR-023.
>
> **Escopo desta pesquisa**: extrair o padrão *operacional* de LangGraph/Langfuse/MCP daquele projeto para a camada de implementação Python da nossa RI. O núcleo de segurança (PEP/PDP/Client-Bound Entitlement) da nossa arquitetura permanece 100% definido pelo `README.md` na raiz deste repositório — nunca pelo projeto pesquisado aqui.

---

## 1. Padrão LangGraph

**StateGraph — nós e shape do state.** O grafo por backend é fixo e corporativo:

```text
START → input_guardrails → routing_decision → [agente(s) de domínio] → output_supervisor
      → output_guardrails → judge → supervisor_review → persist → END
routing_decision → handoff → routing_decision   (aresta condicional de retorno)
```

`AgentState` é um `TypedDict(total=False)` com: `user_text, sanitized_input, response_text, tenant_id, agent_id, channel, session_id, conversation_key, message_id, route, intent, context, business_context, tool_arguments, mcp_tools, mcp_results, rag_context, rag_metadata, guardrails, judges, metadata, errors`, mais `active_transaction`/`last_transaction` na extensão transacional (contrato durável de estado, sobrevive a checkpoint/resume).

Registrar um novo agente é mecânico: import da classe → instanciar no `__init__` do workflow (recebendo dependências compartilhadas: telemetry, tool_router, rag_service, cache, observer, memory) → wrapper assíncrono com span de telemetria → `builder.add_node(...)` → entrada em `add_conditional_edges("routing_decision", ...)` → ligação ao `output_supervisor`.

**Duas camadas de roteamento, explicitamente separadas:**
- **Supervisor/router local do backend** — decide o fluxo interno de um agente (`routing.yaml`, `ROUTING_MODE=router|supervisor`).
- **Global Supervisor / Agent Gateway** — serviço deployável separado que decide **qual backend inteiro** trata a conversa (`GLOBAL_ROUTING_MODE=router|supervisor|hybrid`, `backends.yaml`). Roteamento HTTP entre backends, não é um segundo LangGraph.

**Checkpointing**: providers `memory` (testes), `sqlite` (dev local), `mongodb` (distribuído), `autonomous` (produção OCI). Contrato: `{conversation_key, checkpoint_id, state, pending_writes, created_at}`.

**Handoff**: intra-backend via aresta condicional `routing_decision → handoff → routing_decision`; inter-backend via `metadata.handover_backend` na resposta, detectado pelo Agent Gateway, que mantém `global_session_id` separado de `backend_session_id`.

---

## 2. Padrão Langfuse

**Taxonomia IC / NOC / GRL** (não é "Informational Context" — é evento de **negócio/jornada**, **operacional** e **guardrail**, respectivamente):

| Família | Significado | Exemplos |
|---|---|---|
| IC | evento de negócio/jornada do agente | `IC.GATEWAY_RECEIVED`, `IC.AGENT_STARTED/COMPLETED`, `IC.MCP_CACHE_HIT/MISS/SET/BYPASS/NOT_STORED`, `IC.MCP_TOOL_DEDUPED`, `IC.GLOBAL_BACKEND_SELECTED` |
| NOC | erro/indisponibilidade/timeout/degradação | `NOC.RUNTIME_FAILED`, `NOC.MCP_TIMEOUT`, `NOC.LLM_FAILED` |
| GRL | governança/guardrail/bloqueio/sanitização | `GRL.INPUT_BLOCKED`, `GRL.OUTPUT_BLOCKED`, `GRL.MASK_APPLIED` |

Regra prática: não criar evento por linha de código — só para decisões relevantes.

**Instrumentação híbrida**: spans técnicos automáticos por nó do grafo; chamadas LLM capturadas automaticamente via `ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION=true` (providers compatíveis com OpenAI); eventos de negócio (IC/NOC/GRL) sempre manuais via `_emit_ic/_emit_noc/_emit_grl`, **fail-open** (observer ausente/com erro nunca quebra a jornada). Modo de trace `LANGFUSE_TRACE_MODE=verbose|compact`.

**Prompt management**: **não usa** o CMS de prompts do Langfuse — versiona prompt localmente em YAML (`prompt_policy.yaml`, campos `id`/`version`). Langfuse entra como fonte de dados para avaliação em lote (`EvaluationRun.source=langfuse`, apps `evals/offline`/`evals/certification`), não como o motor de julgamento síncrono (esse é um nó do próprio grafo, usando profile LLM `judge`).

**Setup local (docker-compose)**: `langfuse-web`, `langfuse-worker`, PostgreSQL, ClickHouse, Redis, MinIO, mais MongoDB (memória do framework, não do Langfuse). Portas: Web/API 3005, MinIO S3 9090/Console 9091, MongoDB 27017, Postgres 5433, Redis 6379, ClickHouse 8124/9002. Fluxo: `docker compose up -d` → criar org/projeto → gerar par de chaves `pk-lf-.../sk-lf-...` em Settings > API Keys → configurar `.env` do backend.

---

## 3. Padrão de integração MCP

**MCP Gateway**: app deployável único — `/v1/tools`, `/v1/tools/{name}`, `/v1/tools/{name}/invoke`, `/v1/servers`, `/health`, `/ready`. Contratos `ToolInvocation`/`ToolResult` carregando `tenant_id`, `agent_id`, `business_context`, `metadata.request_id/trace_id`.

**MCP Parameter Mapping** (`mcp_parameter_mapping.yaml`): traduz chaves canônicas de negócio (`customer_key`, `contract_key`, `session_key`) para o nome de parâmetro esperado por cada tool.

**Cache MCP com eventos Langfuse**: chave `tenant_id:agent_id:tool_name:hash(arguments)`, só tools idempotentes, TTL por tool. Fluxo de eventos: miss → `IC.MCP_CACHE_MISS → IC.MCP_TOOL_EXECUTING → IC.MCP_TOOL_EXECUTED → IC.MCP_CACHE_SET`; hit → só `IC.MCP_CACHE_HIT`.

**FastMCP** como padrão de servidor MCP oficial:
```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("telecom_mcp_server")

@mcp.tool()
def consultar_fatura(msisdn: str | None = None) -> dict: ...

mcp.run(transport="streamable-http")
```

### ⚠️ Achado crítico: autorização rasa e potencialmente insegura

O bloco `authorization` do MCP Gateway deles é um **allowlist estático por `agent_id`**:

```yaml
authorization:
  default_policy: deny
  agents:
    telecom_contas:
      allowed_tools: [consultar_fatura, consultar_pagamentos]
```

O campo `agent_id` que governa essa allowlist **chega como dado do payload de entrada da conversa** (`GatewayRequest`/`ToolInvocation`), não como claim de uma identidade de MCP Client autenticada e verificada independentemente. A própria SPEC-004 deles admite: *"a política conversacional não substitui autenticação, autorização, idempotência nem atomicidade no MCP Server."* Não há PDP/OPA/Cedar, não há `policy_decision_id`/`entitlement_version`, não há separação discovery/execution como dois enforcement points deliberadamente independentes.

**Isto é estruturalmente o anti-padrão que o ADR-001 da nossa RI proíbe** ("autorização por role autodeclarado do agente"). Ver ADR-023 para a decisão de como reaproveitar a engenharia de proxy sem herdar esse problema.

---

## 4. Convenções de configuração YAML

| Arquivo | Propósito |
|---|---|
| `agents.yaml` | Registro de agentes (agent_id, paths de config isolada, metadados de domínio) |
| `routing.yaml` | Intents, keywords/examples/priority, `mcp_tools` por intent, `state_policies` |
| `tools.yaml` | Catálogo de tools: server destino, schema de args, cache, `allowed_agents` |
| `guardrails.yaml` | Guardrails de entrada/saída habilitáveis por código |
| `judges.yaml` | Critérios de avaliação pós-resposta (deterministic/llm), threshold, sample_rate |
| `llm_profiles.yaml` | Perfis de modelo/temperatura por componente (router, judge, supervisor, RAG) |
| `identity.yaml` | Aliases de nomes de canal → chaves canônicas de negócio (Identity Resolver) |
| `mcp_parameter_mapping.yaml` | Tradução de chave canônica → nome de parâmetro esperado por tool |
| `mcp_servers.yaml` (+ `.docker.yaml`) | Endereços/transporte dos MCP servers (local vs. Docker) |
| `backends.yaml` | Cadastro de backends de agente + regras de roteamento global do Agent Gateway |
| `prompt_policy.yaml` | Prompt base/persistente do agente, versionado (`id`, `version`) |
| `tool_policies.yaml` | Classifica tool como `read_only`/`transactional`, exige confirmação |
| `authorization` (bloco em config do MCP Gateway) | Allowlist de tools por `agent_id` — **não reaproveitar como fonte de autorização** (ver seção 3) |

---

## 5. Modelo de segurança/identidade (SPEC-018) — compatibilidade

- **Autenticação de workload** (5 modos: config_file/instance_principal/workload_identity/resource_principal/api_key) — trata de como o *framework* se autentica perante recursos OCI (Vault, GenAI, ADB). **Ortogonal** ao nosso problema de entitlement de tools.
- **Autorização** — listada como 5 perguntas a responder, sem PDP formal; na prática resolvida pelo allowlist raso descrito na seção 3.
- **Secrets, proteção de dados, segurança de canal** — compatíveis/complementares, não tocam em entitlement.
- **Auditoria** — bom modelo de trilha (usuário/canal, agent_id, tenant_id, tool, modelo, guardrail, judge score, trace_id), mas sem equivalente a `decisionId`/`policyDecisionId`/`entitlementVersion` (nossos ADR-017), porque não existe PDP separado gerando essas decisões.

**Onde é claramente compatível/ortogonal**: `identity.yaml`/`BusinessContext` — normalização de identidade de **negócio** (cliente final, contrato), nunca decide autorização de tool. Adotável sem tensão com o núcleo de segurança.

**Veredito**: SPEC-018 não deve ser usada como spec de segurança normativa para a nossa RI — mistura autenticação de workload com autorização de tool sem separar os dois problemas nem propor um PDP.

---

## 6. Deployment

Não é amarrado a OCI na camada de aplicação — roda 100% local via Docker Compose com serviços genéricos self-hostáveis (Redis, MongoDB, PostgreSQL, ClickHouse, MinIO, Langfuse). Integrações OCI (GenAI, ADB, Vault, workload identity) são opções plugáveis entre várias, não requisito de desenvolvimento.

---

## Recomendações de reuso (aplicadas na RI via ADR-022/ADR-023)

**Adotar como estão** (não tocam no núcleo de segurança): `identity.yaml`/BusinessContext · taxonomia IC/NOC/GRL + EventEnvelope · setup local do Langfuse via docker-compose · `ConversationSummaryMemory` · heurística RAG-vs-MCP (§30.3-30.4 do Hoshikawa: sistemas → MCP, documentos → RAG) · `mcp_parameter_mapping.yaml` · FastMCP como padrão de servidor MCP.

**Adotar com adaptação**: a *forma* de proxy do MCP Gateway (catálogo, `ToolInvocation`/`ToolResult`, cache com eventos, retry/timeout/circuit breaker) — mas a decisão ALLOW/DENY é sempre delegada ao nosso PEP/PDP, nunca ao bloco `authorization` deles. A camada Agent Gateway/Global Supervisor (dois níveis de sessão, handoff) informa o desenho de EP-11/EP-12, mantendo-a estritamente como roteamento de UX/negócio, nunca como autoridade de autorização. `tool_policies.yaml` (read_only/transactional + confirmação) é conveniência conversacional, não controle de segurança.

**Não copiar como fonte de verdade de segurança**: o bloco `authorization` por `agent_id` autodeclarado no payload; SPEC-018 como normativa de autorização.
