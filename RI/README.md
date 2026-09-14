# Enterprise MCP Service Bus — Reference Implementation

Implementação executável da arquitetura descrita em [`../README.md`](../README.md), planejada em [`../docs/RI-PLANNING.md`](../docs/RI-PLANNING.md).

> **Status: M0, M1, M2, M3 e M4 concluídos — backlog completo, nenhuma tarefa aberta** (M0-M2 implementados 2026-09-11 e revalidados 2026-09-14; M3 implementado 2026-09-14; M4 implementado e concluído 2026-09-14, incluindo as duas tarefas `could` EP-13-T05/T06). **260 testes automatizados** (253 passando com `--forked` — unit + e2e + contract + adversarial, sem flakiness — mais 7 testes de aceite de segurança contra o docker-compose real, EP-15-T02, rodados separadamente pelo custo de build+Keycloak por execução). M3 (Profile Intelligence, Offering Filter, Service Orchestrator com LangGraph real, Agent Runtime, agente de exemplo com LLM real + Langfuse self-hosted real) está descrito na seção "M3 — Personalização e orquestração"; M4 (testes de contrato, suíte de aceite de segurança, testes adversariais, testes de fail-closed, os dois modos multiagente do ADR-024, ADRs formalizados) na seção "M4 — Hardening e entrega", ambas abaixo. Detalhes completos e critérios de aceite verificados em `docs/RI-PLANNING.md` seção 8.7.

## Quickstart (sem Docker)

```bash
make install         # cria .venv e instala o pacote em modo editável (dev extras inclusos)
make lint             # ruff check + ruff format --check
make typecheck        # mypy --strict
make validate-schemas # valida todo YAML de config/ contra seu modelo Pydantic
make export-schemas   # regenera schemas/*.schema.json a partir dos modelos
make test             # pytest --forked (unit + e2e) -- ver nota abaixo
```

`make test` precisa do binário `opa` no PATH (ou `OPA_BINARY` apontando para ele) para os testes que exercitam o PDP de verdade — ver "Como instalar o OPA" abaixo. Sem ele, esses testes são pulados (`pytest.skip`), não falham. Os testes de `test_real_keycloak.py` precisam de `docker` no PATH pela mesma razão.

### Flakiness da suíte e2e: resolvida com `--forked`

Sessões anteriores documentaram falhas intermitentes (`mcp.shared.exceptions.MCPError: SSE stream ended without a response`) ao rodar `pytest tests/e2e/` sem isolamento de processo — a hipótese era limpeza assíncrona (anyio/httpx/uvicorn) compartilhada entre pares de servidor ASGI em processo, na mesma sessão pytest, e várias mitigações (mais retries, pausas, isolar por arquivo) não resolviam. O follow-up então recomendado — isolar cada teste em subprocesso próprio via `pytest-forked` — foi implementado e **confirma a hipótese**: com `--forked` (um processo `fork()` por função de teste), a suíte inteira passa de forma consistente. Verificado nesta sessão: **119/119 testes (97 unit + 22 e2e) passando em múltiplas execuções seguidas**, contra a mesma taxa de 1-9 falhas por execução sem `--forked`. `make test` e `.github/workflows/ci.yml` já usam `--forked` por padrão; o custo é só tempo de execução (~+1min nesta máquina).

### Como instalar o OPA (sem Docker)

OPA é um binário Go estático — não precisa de Docker nem de build:

```bash
curl -sL -o /tmp/opa "https://openpolicyagent.org/downloads/latest/opa_linux_amd64_static"
chmod +x /tmp/opa
cp /tmp/opa .venv/bin/opa   # coloca no PATH do venv
opa version                 # confirma
```

Versão usada durante o desenvolvimento desta RI: **OPA v1.20.2** (Rego v1 é o padrão — as policies em `config/policies/*.rego` usam `import rego.v1`).

### Subir a stack completa localmente (sem Docker)

```bash
source .venv/bin/activate
opa run --server --addr 127.0.0.1:8181 config/policies/ &
export SALES_DOMAIN_SERVICE_TOKEN=dev-sales-domain-service-token      # EP-07: credencial de saída, nunca o token do client
export FINANCE_DOMAIN_SERVICE_TOKEN=dev-finance-domain-service-token
python3 -m example_mcp_servers.sales_domain.server &
python3 -m example_mcp_servers.finance_domain.server &
# Sem OIDC_JWKS_URL/OIDC_ISSUER, o Gateway roda em modo "sem IdP configurado":
# nega tudo por padrão (ver "Dois modos de deployment" abaixo).
python3 -m emcp_bus.gateway.server
```

O Fabric router (EP-06-T01) resolve cada capability para o backend correto via `config/backends/*.yaml` + o Registry (seedado de `config/capabilities/` no startup do Gateway) — não há mais uma única `SALES_DOMAIN_URL` estática cobrindo tudo.

Para autenticação real, aponte `OIDC_JWKS_URL`/`OIDC_ISSUER` para um Keycloak real (EP-01-T01, ✅ implementado e validado — ver `deploy/keycloak/realm-export.json` e `tests/e2e/test_real_keycloak.py`) ou qualquer IdP OIDC compliant (`TokenValidator` é agnóstico de fornecedor). A maior parte da suíte (`tests/e2e/conftest.py`) continua usando um servidor JWKS local mais leve como stand-in — válido para a lógica de validação, mas `test_real_keycloak.py` é quem prova a integração com Keycloak de verdade (client_credentials grant, claims reais, `iss`/`aud` reais).

## Quickstart (Docker)

```bash
make up      # == docker compose --profile core up --build          (sem IdP)
make down    # == docker compose --profile core down
make logs    # == docker compose --profile core logs -f

# Com Keycloak real (EP-01-T01):
cp .env.example .env   # descomente as 3 linhas OIDC_*
docker compose --profile core --profile identity up --build
```

> **✅ Validado com um daemon Docker real** (Docker 29.8.0 / Compose v5.5.1) — `gateway` + `sales-domain` + `opa` (+ `keycloak`, opcional) sobem, o Gateway sincroniza entitlements reais com o OPA real do compose, e um cliente MCP real do host completa `tools/list`/`tools/call` através do Gateway containerizado, com ou sem Keycloak. Ver "O que foi validado com Docker" abaixo para o que exatamente foi exercitado (incluindo três bugs reais encontrados e corrigidos ao longo dessas rodadas). Sem `.env`/perfil `identity`, o Gateway do compose roda em modo "sem IdP" (toda requisição não autenticada, deny-by-default) — os dois modos são deliberados, não um "modo incompleto" esperando o outro.

### O que foi validado com Docker

Build + up + smoke test end-to-end, mais dois testes adicionais montando um segundo container `gateway` manualmente (`docker run --network ri_default ...`) para exercitar caminhos que o compose padrão (sem Keycloak) não cobre, e (nesta rodada) uma segunda validação completa após o Fabric router multi-backend (EP-06-T01), o domínio Finance real (EP-06-T03), a segmentação de rede (EP-05-T07) e a stack de observabilidade (EP-08-T04):

1. **`docker compose --profile core up --build`** sobe os 4 serviços (`opa`, `sales-domain`, `finance-domain`, `gateway`); ambos os domain servers ficam `healthy`; `gateway` sincroniza com `opa` e seeda o Registry a partir de `config/capabilities/` no startup, permanecendo de pé.
2. **Modo sem OIDC** (compose padrão): `tools/list` vazio, `tools/call` negado com `UNAUTHENTICATED` — confirmado com um cliente MCP real do host contra `http://127.0.0.1:8000/mcp`.
3. **Sync real de entitlement**: `curl http://127.0.0.1:8181/v1/data/emcp/client_profiles` no OPA do compose mostra os profiles reais (`Sales.Read`, `Finance.Payments`, ...) que o Gateway empurrou no startup — não é um mock.
4. **Segmentação de rede real (EP-05-T07)**: `opa`, `sales-domain` e `finance-domain` não publicam porta de host no compose — confirmado com `curl http://127.0.0.1:8100/mcp` do host retornando `Connection refused`, algo que só um daemon Docker real prova (Docker só expõe uma porta de container para o host via `ports:`, então a ausência dela já é a segmentação, sem precisar de uma rede Docker customizada adicional).
5. **Caminho autenticado completo, cross-container, incluindo Finance**: com `--profile identity` (Keycloak real) e um token `client_credentials` real para `finance-payments-agent`, `tools/list` retorna exatamente os 3 tools de `Finance.Payments` (roteados pelo Fabric router para o container `finance-domain`, não `sales-domain`) e `tools/call finance.payment.create` executa de verdade contra o backend Finance real, retornando um `payment_id` genuíno.
6. **Correlação de trace entre containers de verdade** (não em-processo, como nos testes e2e): o mesmo `trace_id` aparece nos logs de `gateway` e do domain server correspondente para uma chamada bem-sucedida — a forma mais forte de validar o critério de aceite do Marco M0.
7. **Fail-closed real**: com o container `opa` parado, um novo container `gateway` falha ao subir (`Application startup failed. Exiting.`, `PDPUnavailableError` no traceback) — confirma README.md §38 sob Docker de verdade, não só em teste unitário.
8. **Keycloak real, via `docker compose --profile core --profile identity up`** (EP-01-T01): realm `emcp` importado de `deploy/keycloak/realm-export.json` (3 clients — `sales-read-agent`, `sales-write-agent`, `finance-payments-agent` — cada um com `client_credentials` grant habilitado e um mapper de audience para `emcp-gateway`); token obtido via `client_credentials` real, validado pelo Gateway contra o JWKS real do Keycloak, `tools/list`/`tools/call` corretos para `Sales.Read`, negação correta cross-domain (`Sales.Read` → `finance.payment.execute`) e `REQUIRE_APPROVAL` correto para `Finance.Payments` acima do threshold — tudo com identidades **realmente distintas** emitidas pelo mesmo IdP.
9. **`tests/e2e/test_real_keycloak.py`** automatiza o item 8 (sobe seu próprio container Keycloak via `docker run`, pula se `docker` não estiver no PATH) — 4 testes, agora estáveis com `--forked` (ver nota de flakiness acima).

O perfil `observability` (`otel-collector` + `jaeger`, EP-08-T04) não foi exercitado com tráfego real nesta rodada (apenas `docker compose config` validado) — os dois serviços usam imagens oficiais padrão (`otel/opentelemetry-collector-contrib`, `jaegertracing/all-in-one`) com uma config mínima (`deploy/otel/collector-config.yaml`), sem lógica própria da RI além da configuração em si.

**Três bugs reais encontrados e corrigidos ao longo da validação original** (nenhum seria pego sem um daemon Docker/Keycloak real):

- `deploy/docker/Dockerfile` não copiava `config/` para a imagem — o Gateway falhava ao subir (`ConfigError`: diretório `config/clients` não encontrado) porque `/app/config` simplesmente não existia no container. Corrigido com `COPY config ./config`.
- O healthcheck de `opa` no `docker-compose.yml` usava `wget`, que **não existe** na imagem oficial `openpolicyagent/opa` (é uma imagem estilo distroless, só o binário `opa`, sem shell). Isso deixava `gateway` (que dependia de `opa: condition: service_healthy`) preso para sempre em `Created`. Corrigido: sem healthcheck em `opa` (não há ferramenta na imagem para escrevê-lo), `gateway` depende de `opa: condition: service_started` e ganhou `restart: on-failure:5` — o próprio fail-closed do Gateway (item 6 acima) faz o papel de "esperar o OPA ficar pronto de verdade", com um pequeno número de retries do Compose cobrindo a janela entre o processo do OPA iniciar e aceitar conexões.
- Keycloak deriva o claim `iss` do `Host` header da requisição usada para *obter* o token, a menos que `KC_HOSTNAME` seja fixado — um token obtido via `127.0.0.1:8080` (do host, para teste manual) tinha `iss` diferente do que o Gateway (que valida via `keycloak:8080`, nome interno do compose) esperava, e era rejeitado por "wrong issuer" mesmo sendo um token 100% válido. Corrigido fixando `KC_HOSTNAME` (`keycloak` no compose; a URL completa `http://127.0.0.1:<porta>` no teste automatizado, já que `KC_HOSTNAME` não aceita `host:porta` sem esquema).

## Dois modos de deployment (importante)

O Gateway (`src/emcp_bus/gateway/server.py`) suporta dois modos, sempre *deny by default*:

1. **Com OIDC configurado** (`OIDC_JWKS_URL` + `OIDC_ISSUER` definidos): o próprio middleware de auth do SDK `mcp` (`RequireAuthMiddleware`) rejeita qualquer conexão sem bearer token válido **antes mesmo do handshake `initialize`** — mais estrito que qualquer checagem no nível do handler.
2. **Sem OIDC configurado** (padrão se as env vars não estiverem definidas): nenhum middleware de auth é instalado; toda requisição chega aos handlers com `get_access_token() is None`, e é a própria lógica do handler (`on_list_tools`/`on_call_tool`) que nega por padrão — `tools/list` vazio, `tools/call` sempre negado com `Access denied: UNAUTHENTICATED`.

Os dois modos são testados explicitamente em `tests/e2e/test_governed_gateway.py`.

## M3 — Personalização e orquestração

Implementado e validado em 2026-09-14 (mesma sessão). Perfil → entitlement → ofertas filtradas → NBA → dispatch, ponta a ponta:

1. **Profile Intelligence** (`src/emcp_bus/profile_intelligence/`): `ProfileView` versionado, provider rule-based determinístico (mesmo `subject_ref`+janela ISO → mesmo `profileVersion`), guardrails de governança (pseudonimização, lineage log, stub de drift).
2. **Offering Filter** (`src/emcp_bus/offering_filter/`): `FilteredOfferings = ActiveCatalog ∩ MaximumEntitlement ∩ ConsentContext` — invariante de subconjunto provada com Hypothesis (2000 casos gerados, `tests/unit/test_offering_filter_invariants.py`).
3. **Service Orchestrator** (`src/emcp_bus/orchestrator/`): `StateGraph` real do LangGraph 0.6 com checkpointer SQLite real — nós `resolve_profile → resolve_entitlement → filter_offerings → decide_nba → approval_gate`, mais um caminho de reentrada para recálculo após DENY (`handle_denial`, nunca chama o Fabric diretamente). O nó `approval_gate` usa `langgraph.types.interrupt`/`Command(resume=...)` — pausa de verdade, sem timeout que vire ALLOW implícito, integrado ao `ApprovalService` do EP-14.
4. **Agent Runtime** (`src/emcp_bus/agent_runtime/`): `AgentDispatcher` nunca gera/armazena credencial própria — usa exclusivamente o MCP Client já registrado, via `client_credentials` real contra o mesmo IdP de qualquer outro client. Channel adapter conversacional + Identity Resolver (`config/orchestrator/identity.yaml`, nunca consultado pelo PDP — checado via AST em teste).
5. **Agente de exemplo** (`agents/example_agent/`): tool-calling real contra um endpoint OpenAI-compatible (verificado com `meta.llama-3.3-70b-instruct` via OCI Generative AI), catálogo restrito ao `tools/list` do próprio client. O cenário de prompt injection do §29 (pedir `finance.payment.execute` fora do entitlement) é reproduzido de verdade em `tests/e2e/test_example_agent.py` — a chamada nunca é executada, seja porque o modelo nunca viu a tool no seu próprio catálogo, seja porque o Gateway/PDP nega.
6. **Langfuse self-hosted** (`deploy/langfuse/docker-compose.override.yml`, perfil `llm-observability`): adaptado do `docker-compose.yml` oficial do Langfuse (upstream, 2026-09-14) — 6 containers (web/worker/postgres/clickhouse/redis/minio). **Validado de verdade nesta sessão**: stack subida via `docker compose ... --profile llm-observability up`, um turno real do agente de exemplo (LLM real + Gateway real) com `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_EXPORTER_OTLP_HEADERS` apontando para o endpoint OTLP nativo do Langfuse (`/api/public/otel/v1/traces`, sem nenhuma mudança de código — só variáveis de ambiente padrão do OTel SDK), e os spans (incluindo um span de "generation" com `gen_ai.request.model`/`gen_ai.usage.{input,output}_token_count` reais, via `agents/example_agent/agent.py`) confirmados fisicamente na tabela `events_core` do ClickHouse. Essa validação foi manual (não virou teste e2e automatizado, dado o custo de subir 6 containers a cada execução da suíte) — os comandos exatos estão documentados no histórico desta sessão; reproduzir localmente: `docker compose -f docker-compose.yml -f deploy/langfuse/docker-compose.override.yml --profile llm-observability up -d`, aguardar `curl http://localhost:3000/api/public/health`, criar um projeto/API key (UI ou `LANGFUSE_INIT_*`), apontar as duas env vars OTel acima.
7. **Prompt versioning** (`agents/example_agent/prompts/store.py`, `could`): versionamento local (nunca sobrescreve, sempre cria versão nova) como núcleo testável — sync real para a API de Prompt Management do Langfuse é um adapter fino documentado, não implementado nesta sessão.

Dependências novas: `langgraph`, `langgraph-checkpoint-sqlite`, `hypothesis` (dev), `openai`, `python-dotenv` (dev). Nenhuma delas é necessária para M0-M2 (Gateway/PDP/Registry continuam funcionando sem elas).

## M4 — Hardening e entrega

Implementado e concluído em 2026-09-14 (mesma sessão do M3). Cobre EP-15 (testes de segurança/adversariais) completo, EP-16 (deploy final/documentação) completo, e os dois modos de integração multiagente do ADR-024 (EP-13-T05/T06, ambos `should`/`could` mas implementados):

1. **EP-15-T01 (testes de contrato)** (`tests/contract/`): conectam direto a cada domain server, nunca pelo Gateway — o contrato input/output de uma tool é propriedade do domain server (ADR-023), independente de quem está ou não entitled a chamá-la. **Achado durante a implementação**: `CapabilityManifest` (EP-02-T01) não carrega `input_schema`/`output_schema` — nunca fez parte do desenho do EP-02 (o manifesto é metadado de entitlement/risco, não formato). Resolvido sem reinterpretar silenciosamente o critério de aceite: (a) o `input_schema` **real**, auto-gerado pelo MCP SDK a partir da assinatura Python de cada tool, já é validado pelo próprio servidor (campo obrigatório ausente/tipo errado → `is_error: True` via Pydantic, antes de qualquer código da RI rodar) — exercitado diretamente, não reimplementado; (b) o `output_schema` auto-gerado é genérico demais (`additionalProperties: true`, já que toda tool retorna `dict[str, object]`) — resolvido com JSON Schema escrito à mão por tool (`jsonschema`, já dependência transitiva), validado contra a resposta real das 9 tools (6 Sales + 3 Finance). 20 testes.
2. **EP-15-T02 (suíte de aceite de segurança, §45)** (`tests/e2e/test_security_acceptance.py`): roda contra o `docker-compose.yml` real (`--profile core --profile identity`, Keycloak incluído), não os fixtures in-process do resto da suíte e2e. 7 dos 10 testes formais automatizados diretamente: Teste 1 (unauthorized discovery), Teste 2 (direct unauthorized call), Teste 4 (role spoofing via payload forjado), Teste 5 (cache isolation, incluindo `cache_scope="private"`), Teste 7 (gateway bypass — `sales-domain`/`finance-domain`/`opa` não publicam porta de host), Teste 9 (backend/transaction-policy isolation, `TRANSACTION_POLICY_DENIED` real), Teste 10 (client compromise containment). Os outros 3 já têm cobertura real documentada no docstring do arquivo em vez de duplicada: Teste 3 (prompt injection, LLM real) em `test_example_agent.py`; Teste 6 (policy revocation, sem endpoint HTTP de revogação nesta RI) em `test_entitlement_manager.py`; Teste 8 (token audience) em `test_real_keycloak.py`, mesmo realm Keycloak real.
3. **EP-15-T03 (testes adversariais de prompt/tool injection)** (`tests/adversarial/{test_prompt_injection,test_tool_poisoning,test_payload_identity_spoofing}.py`, 12 testes): contra o Gateway real. Injeção direta/indireta de conteúdo em argumentos nunca altera autorização nem o catálogo; hidden tool invocation e spoofing de nome (case/whitespace/typo) sempre negados por comparação exata; **tool description poisoning** provado com um `MCPServer` malicioso real montado em runtime (descrição hostil pedindo "acesso admin") — a Gateway repassa a descrição verbatim (nunca sanitiza) mas ela não tem efeito algum na decisão PDP; variação explícita do achado ADR-023 (`agent_id`/`tenant_id`/`business_context` forjados nos argumentos) provada por negação de entitlement e por auditoria (`tool_call_allowed` sempre registra o `client_id` real, nunca o forjado).
4. **EP-15-T04 (testes adversariais de protocolo/identidade)** (`tests/adversarial/test_protocol_identity.py`, 6 testes + referências cruzadas para o que já era coberto alhures): header/body mismatch rejeitado pré-autenticação; replay de requisição idêntica (gap real e documentado — sem nonce nesta RI, mitigado por token de vida curta) mas sempre auditado com `decision_id` distinto; **revogação de política ao vivo** contra um Gateway rodando (fecha a lacuna do Teste 6 que EP-15-T02 havia documentado); condição de corrida de entitlement sob concorrência real sem crash; **approval replay sob concorrência real** (`ThreadPoolExecutor`) — achado real: `ApprovalService.check_and_consume` não era thread-safe, corrigido com `threading.Lock`; bulk exfiltration (gap real e documentado — sem rate limiting) sempre com trilha de auditoria completa.
5. **EP-15-T05 (testes de política de falha, §38)** (`tests/e2e/test_fail_closed.py`, 7 testes, um por linha da tabela): IdP inalcançável nega novas autenticações; PDP morrendo em runtime (não só no boot) falha fechado na próxima chamada; Registry sem `capabilities/` falha o boot do Gateway; **achado real corrigido**: nenhuma das 8 chamadas `audit_sink.emit` do Gateway estava protegida — uma falha no sink teria virado erro 500 numa operação já ALLOWed, corrigido com o helper `_emit_audit`; approval service falho nega (nunca crasha) uma operação de alto risco; backend morto falha só aquela requisição, sem derrubar o Gateway.
6. **EP-13-T05 (Modo A — multiagente governado, ADR-024)** (`src/emcp_bus/agent_runtime/global_supervisor.py` + `agents/example_agent/backends/{sales_agent,finance_agent}/`): `GlobalSupervisor` com roteamento por palavra-chave simples (deliberadamente não é a fronteira de segurança — documentado), nunca importa `emcp_bus.orchestrator` (checado via AST). Validado com **LLM real + Gateway real** (`tests/e2e/test_multi_agent_mode_a.py`, 2 testes): handoff de `sales_agent` para `finance_agent` resolve entitlement do zero com token completamente distinto; injeção de prompt via handoff tentando `finance.payment.execute` continua negada pelo Gateway/PDP reais.
7. **EP-13-T06 (Modo B — Orchestrator como único cérebro de NBA/NBO, `could`)** (`agents/example_agent/mode_b_orchestrator_driven/`): `ModeBOrchestrator` invoca o journey `StateGraph` real do EP-11-T02 (não modificado) uma vez por client relevante para o mesmo subject, combina os `NBADecision`s (Finance sempre vence Sales na regra de referência) e despacha via `AgentDispatcher` real — nunca cria autorização própria. Validado **contra Keycloak real, OPA real, Sales+Finance reais** (`tests/e2e/test_real_keycloak.py::test_mode_b_orchestrator_combines_offerings_and_dispatches_through_the_real_chain`): candidatos de ambos os domínios realmente combinados, decisão final do nosso Orchestrator, dispatch `ALLOW` de ponta a ponta.
8. **EP-16 (deploy final e documentação)**: `docker-compose.yml` validado com `--profile core --profile identity --profile observability up -d --build` real (7 serviços saudáveis); 25 ADRs formalizados em `docs/adr/` (ADR-001 a ADR-025, gerados a partir da tabela §8.4 do planning); versões confirmadas consolidadas em `docs/adr/ADR-018-stack-de-implementacao.md`.

**Duas correções de código reais** (não apenas testes) surgiram escrevendo os testes adversariais/fail-closed: `ApprovalService` ganhou um `threading.Lock` (race condition real de double-spend sob concorrência), e o Gateway ganhou `_emit_audit` (falha de audit sink podia virar erro 500 numa operação já decidida, violando §38).

## O que existe hoje

| Tarefa | Componente | Status |
|---|---|---|
| EP-00 (completo) | Scaffold, config loader, docker-compose base, **CI** | ✅ `.github/workflows/ci.yml` (EP-00-T03) |
| EP-01 (completo) | Registro de MCP Client, middleware OIDC/JWT, Keycloak, lint de shared client, spike mTLS | ✅ validado com JWKS real + tokens RS256 reais + Keycloak real (26.7.3, `tests/e2e/test_real_keycloak.py`); lint em `src/emcp_bus/identity/shared_client_lint.py` (ligado a `make validate-schemas`); spike em `docs/adr/ADR-019-identity-extension.md` |
| EP-02-T01..T05 (completo) | Registry: schema, pipeline, storage, lifecycle, manifests de exemplo | ✅ `src/emcp_bus/registry/*`, testado (inclui `seed.py`, usado pelo Gateway em runtime desde EP-06-T01) |
| EP-03 (completo) | PDP/OPA: entitlement.rego, transaction.rego, cliente, contrato de decisão | ✅ validado com **OPA real** — 9 testes Rego + 6 Python |
| EP-04 (completo) | Entitlement Manager: resolve, revoke, versionamento | ✅ validado com OPA real + YAML reais |
| EP-05 (completo) | Gateway: discovery filtrado, execution enforcement, fail-closed, **cache hint**, **anti-bypass**, **consistência header/body** | ✅ `src/emcp_bus/gateway/{server,cache,canonical_request}.py` — ver limitação de wire-mode do cache hint abaixo |
| EP-06-T01 | Fabric core (roteador por capability via Registry) | ✅ `src/emcp_bus/fabric/router.py` — multi-backend real, testado (Sales→sales-domain, Finance→finance-domain, nunca cruzado) |
| EP-06-T02 | MCP Server de exemplo — Sales | ✅ 6 tools (R1 + R2), agora com `BackendCredentialGate` (EP-05-T07) |
| EP-06-T03 | MCP Server de exemplo — Finance | ✅ `services/example_mcp_servers/finance_domain/server.py` — invoice.get (R1), payment.create (R2), payment.execute (R3, ciclo de aprovação completo testado e2e) |
| EP-06-T04 | Adapter REST genérico | ✅ `src/emcp_bus/fabric/adapters/rest_adapter.py` — implementado e testado standalone (`httpx.MockTransport`); nenhum manifest seed usa `backend.type: "rest"` ainda (os dois domínios de exemplo são MCP-nativos), então não há caminho ao vivo através do Gateway exercitando-o — ver módulo docstring |
| EP-07 (completo) | Outbound/downstream identity: credencial de backend distinta da do client, **token exchange RFC 8693** | ✅ `src/emcp_bus/downstream/{models,identity}.py` — `service_account` (padrão dos backends seed) **e** `token_exchange` (Keycloak Standard Token Exchange, validado contra Keycloak real 2026-09-14) |
| EP-08-T01 | Tracing OTel | ✅ (M0) |
| EP-08-T02 | Eventos de auditoria (taxonomia IC/NOC/GRL) | ✅ `src/emcp_bus/audit/{models,events,sink}.py` — nunca registra valor de token/secret (hash apenas), sink JSONL append-only |
| EP-08-T03 | Correlação ponta a ponta (decisionId/policyDecisionId/entitlementVersion/mcpRequestId) | ✅ `src/emcp_bus/audit/correlation.py` — exposto no trace (span attributes) e em todo evento de auditoria |
| EP-08-T04 | Stack local de observabilidade (OTel Collector + Jaeger) | ✅ `docker-compose.yml` perfil `observability` + `deploy/otel/collector-config.yaml` — config validada (`docker compose config`), não exercitada com tráfego real nesta rodada |
| EP-14 (completo) | Approval workflow: contrato, serviço, fail-closed, ligado ao Gateway | ✅ `src/emcp_bus/approval/{models,service}.py`, testado (ciclo completo e2e para Sales **e** Finance: nega → aprova externamente → executa → replay nega) |
| EP-09 (completo) | Profile Intelligence: contrato, provider rule-based, governança | ✅ `src/emcp_bus/profile_intelligence/*.py` |
| EP-10 (completo) | Offering Filter: serviço + invariante de subconjunto | ✅ `src/emcp_bus/offering_filter/service.py` — invariante provada com Hypothesis (2000 casos) |
| EP-11 (completo) | Service Orchestrator: DecisionContext, StateGraph LangGraph, decisioning pluggable, recálculo, HITL | ✅ `src/emcp_bus/orchestrator/*.py` — LangGraph + checkpointer SQLite reais, checkpoint-resume e pausa/retomada de aprovação validados |
| EP-12 (completo) | Agent Runtime: dispatch, channel adapter, handoff, identity resolver | ✅ `src/emcp_bus/agent_runtime/*.py` — validado contra Gateway + Keycloak reais |
| EP-13-T01/T03/T04 | Agente de exemplo (LLM real), redação de PII, versionamento de prompt | ✅ `agents/example_agent/*.py` — tool-calling real, cenário de prompt injection do §29 reproduzido |
| EP-13-T02 | Langfuse self-hosted | ✅ `deploy/langfuse/docker-compose.override.yml` — subido e validado de verdade (ver seção M3 acima); validação manual, não automatizada em CI |
| EP-15-T01 | Testes de contrato dos MCP Servers | ✅ `tests/contract/*.py` — input schema real do SDK exercitado + output schema escrito à mão, validado contra os 2 domain servers reais (ver seção M4 acima) |
| EP-15-T02 | Suíte de aceite de segurança (§45) | ✅ `tests/e2e/test_security_acceptance.py` — 7/10 testes formais automatizados contra o docker-compose real; os outros 3 já cobertos em outros arquivos (ver seção M4 acima) |
| EP-15-T03 | Testes adversariais de prompt/tool injection | ✅ `tests/adversarial/{test_prompt_injection,test_tool_poisoning,test_payload_identity_spoofing}.py` — 12 testes, incluindo um MCP server malicioso real (ver seção M4 acima) |
| EP-15-T04 | Testes adversariais de protocolo/identidade | ✅ `tests/adversarial/test_protocol_identity.py` — 6 testes novos + `threading.Lock` real corrigido em `ApprovalService` (ver seção M4 acima) |
| EP-15-T05 | Testes de política de falha (§38) | ✅ `tests/e2e/test_fail_closed.py` — 7 testes, um por linha da tabela + `_emit_audit` real corrigido no Gateway (ver seção M4 acima) |
| EP-13-T05 (`should`) | Modo A — multiagente governado (ADR-024) | ✅ `src/emcp_bus/agent_runtime/global_supervisor.py` + `agents/example_agent/backends/*` — validado com LLM real + Gateway real (ver seção M4 acima) |
| EP-13-T06 (`could`) | Modo B — Orchestrator como único cérebro de NBA/NBO | ✅ `agents/example_agent/mode_b_orchestrator_driven/*` — validado com Keycloak real + OPA real + Sales/Finance reais (ver seção M4 acima) |
| EP-16 (completo) | Deploy final, ADRs formalizados, README | ✅ `docker-compose.yml` validado com todos os perfis; 25 ADRs em `docs/adr/`; versões confirmadas em `docs/adr/ADR-018-stack-de-implementacao.md` |

**260 testes automatizados no total**: 253 passam com `--forked` (unit + e2e + contract + adversarial — todo `tests/` exceto `test_security_acceptance.py`, confirmado em execução completa 2026-09-14), mais 7 testes de aceite de segurança (EP-15-T02) contra o `docker-compose.yml` real (build + Keycloak, ~72s, rodados separadamente do `--forked` padrão pelo custo por execução). Lógica de produção sem mocks no núcleo de segurança e orquestração: OPA real (subprocess), Keycloak real (Docker), LangGraph real com checkpointer SQLite real, LLM real (endpoint OpenAI-compatible), JWKS HTTP real (stand-in leve para o resto da suíte) + JWT RS256 reais, YAML reais de `config/`, SQLite real para o Registry. **100% determinísticos com `--forked`** (verificado em múltiplas execuções seguidas) — a flakiness antes documentada para a suíte e2e está resolvida, ver seção dedicada acima.

## Limitações conhecidas

- **SEP-2549 (`ttlMs` do cache hint de `tools/list`, EP-05-T03)**: implementado corretamente (`src/emcp_bus/gateway/cache.py`), mas o campo é vocabulário exclusivo do protocolo 2026-07-28, que só existe no modo *stateless per-request* do SDK (sem handshake `initialize`) — esta RI usa o handshake de sessão clássico em toda parte (Gateway↔Client e Gateway↔backends), então `ttl_ms` nunca chega ao wire nesta arquitetura, não importa o que o Gateway compute (o SDK descarta o campo na serialização para versões de protocolo anteriores a 2026-07-28 — verificado empiricamente). `cache_scope` não sofre essa limitação de wire, mas por não ter dependência de wire-mode também não é algo que um teste e2e consiga verificar de forma discriminante (o cliente sempre usa o default do próprio campo). A propriedade de segurança real (Teste 5, §45 — nunca vazar catálogo entre clientes) é garantida de forma independente pelo Gateway nunca cachear o catálogo filtrado no servidor.
- **EP-05-T08 (consistência header/body)**: implementado como um gate próprio (`canonical_request.py`) reaproveitando as constantes/nomes de campo do SDK, e não como o ladder de validação nativo do SDK (`mcp.shared.inbound.classify_inbound_request`), que só se aplica ao mesmo modo *stateless per-request* de 2026-07-28 mencionado acima — pela mesma razão, este RI não o alcança pelo caminho nativo.
- **EP-06-T04 (adapter REST)**: implementado e testado de forma standalone; nenhum backend de exemplo desta RI é REST (ambos são MCP-nativos), então o roteamento ao vivo através do Gateway para um backend `type: "rest"` não foi exercitado end-to-end.
- **Stack de observabilidade** (EP-08-T04): config validada, não exercitada com tráfego real (ver "O que foi validado com Docker").

~~Token exchange RFC 8693 (`NotImplementedError`)~~ — **resolvido em 2026-09-14** (início do M3): `TokenExchangeClient` implementa o Standard Token Exchange do Keycloak (GA desde 26.2) de ponta a ponta, validado contra Keycloak real, incluindo um `tools/call` completo pelo Gateway usando uma credencial obtida por exchange. Ver `docs/RI-PLANNING.md` §8.7 para os detalhes verificados (exigências reais do IdP: `audience` precisa ser um client id registrado; `scope` precisa acompanhar `audience` ou o exchange falha).

**M3, ressalvas (2026-09-14):**

- **EP-13-T02 (Langfuse)**: validado manualmente de verdade (ver seção M3 acima — spans reais confirmados no ClickHouse), mas não é um teste e2e automatizado por causa do custo de subir 6 containers a cada execução da suíte.
- **EP-13-T04 (prompt versioning, `could`)**: o núcleo de versionamento é real e testado; o sync com a API de Prompt Management do Langfuse (`langfuse.api.prompts.create`) é um adapter fino documentado, não implementado.
- **Credencial de LLM**: `LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL` (ver `.env.example`) são necessárias para `tests/e2e/test_example_agent.py` e `tests/e2e/test_multi_agent_mode_a.py` — sem elas, esses testes são pulados (`pytest.skip`), não falham, igual ao padrão já usado para `opa`/`docker`.

**M4, ressalvas (2026-09-14):**

- **EP-12-T03 (`execute_handoff`/`build_handoff_payload`, `could`)**: continua implementado e testado (`tests/unit/test_agent_runtime_handoff.py`), mas **achado real durante o M4**: nem o Modo A (EP-13-T05) nem o Modo B (EP-13-T06) acabaram usando esse primitivo. Modo A precisa de roteamento conversacional (qual backend responde à próxima mensagem), não de despacho de uma `NBADecision` específica — `GlobalSupervisor` chama `run_turn()` diretamente nos backends. Modo B já combina `NBADecision`s de múltiplos clients num único passo (`ModeBOrchestrator._combine`) e despacha o vencedor via `AgentDispatcher.dispatch` puro — não há um agente "de origem" cedendo controle a outro para `execute_handoff` interceptar. `execute_handoff` continua correto e reutilizável para um cenário futuro que precise especificamente de handoff *dentro* de uma jornada Orchestrator-driven (ex.: EP-11 decidindo, no meio de uma jornada, redirecionar para outro agente mantendo o mesmo `NBADecision`), mas essa forma específica de uso não existe nesta RI.
- **Replay de requisição** (`tests/adversarial/test_protocol_identity.py`): sem nonce/anti-replay nesta RI — uma requisição capturada com um token ainda válido pode ser reenviada com sucesso. Mitigado por tokens de vida curta (`credential_policy.short_lived` em todo `ClientProfile` seed) e por auditoria completa (cada tentativa, mesmo idêntica, gera `decision_id` próprio).
- **Rate limiting / bulk exfiltration** (`tests/adversarial/test_protocol_identity.py`): sem limitação de taxa de requisições no Gateway — N leituras legítimas consecutivas são todas permitidas. Mitigado apenas por detectabilidade a posteriori via auditoria (cada chamada gera evento correlacionado), nunca por prevenção em tempo real.
- **`GlobalSupervisor` (Modo A, EP-13-T05)**: roteamento por palavra-chave simples, deliberadamente não é a fronteira de segurança (documentado no módulo) — não é uma reivindicação de qualidade de roteamento, apenas um stand-in honesto para o que uma plataforma externa real faria.
- **`ModeBOrchestrator` (Modo B, EP-13-T06)**: a regra de combinação entre domínios (Finance sempre vence Sales) é uma regra de referência simples, não uma reivindicação de otimalidade — mesma postura já adotada por `RuleBasedNBADecisionModel` (EP-11-T03). Não estende `JourneyState`/`build_journey_graph` para múltiplos `client_id`s nativamente; a combinação vive numa camada acima do grafo (decisão de design documentada no módulo).
- **EP-06-T04 (adapter REST)**, **stack de observabilidade** (EP-08-T04, tráfego real ainda não exercitado por um teste automatizado — mas a subida completa com o perfil `observability` foi validada manualmente no M4) e o restante das ressalvas de M0-M3 acima continuam válidas sem mudança.

## Versões fixadas

Ver `pyproject.toml`. Confirmadas via `pip index versions`/download direto em 2026-09-11 (não citadas de memória — ver `docs/RI-PLANNING.md`, EP-16-T04):

- `mcp` 2.2.0 (SDK v2 — API mudou significativamente da v1; ver comentários em `src/emcp_bus/gateway/server.py`)
- `pydantic` 2.13.x, `opentelemetry-sdk` 1.44.x, `uvicorn` 0.52.x, `pyjwt[crypto]` 2.14.x, `ruff` 0.16.x, `mypy` 2.3.x, `pytest` 9.1.x
- `OPA` 1.20.2 (binário estático, Rego v1 padrão)
- `pytest-forked` 1.7.x (resolve a flakiness da suíte e2e, ver acima)
- `langgraph` 0.6.x + `langgraph-checkpoint-sqlite` 2.x (M3, EP-11), `hypothesis` 6.1xx.x (dev, EP-10-T02), `openai` 1.109.x (M3, EP-13-T01), `python-dotenv` 1.2.x (dev) — confirmadas via instalação direta em 2026-09-14
- Langfuse self-hosted 4.35.0 (`docker.langfuse.com/langfuse/langfuse:4`, imagem oficial, EP-13-T02)
- `types-jsonschema` 4.26.x (dev, stubs para `mypy --strict`; `jsonschema` em si já era dependência transitiva do `mcp[cli]`, EP-15-T01) — confirmada via instalação direta em 2026-09-14
- Keycloak 26.7.3 (`quay.io/keycloak/keycloak:26.7.3`, Quarkus), `opentelemetry-collector-contrib` 0.114.0, `jaeger` (all-in-one) 1.62.0 — imagens fixadas em `docker-compose.yml`; registro completo em `docs/adr/ADR-018-stack-de-implementacao.md` (EP-16-T04)

## Estrutura

Ver `../docs/RI-PLANNING.md`, seção 8.5, para a árvore completa planejada. O que existe até agora:

```text
RI/
├── pyproject.toml
├── Makefile
├── docker-compose.yml          # perfil "core": gateway+sales-domain+finance-domain+opa;
│                                # "identity": +keycloak; "observability": +otel-collector+jaeger
├── .env.example
├── deploy/docker/Dockerfile
├── deploy/keycloak/realm-export.json  # EP-01-T01: realm "emcp", 3 clients
├── deploy/otel/collector-config.yaml  # EP-08-T04
├── scripts/{export_schemas,validate_config}.py
├── schemas/*.schema.json        # gerados por export_schemas.py
├── config/
│   ├── policies/                          # EP-03: entitlement.rego, transaction.rego (+ opa test)
│   ├── clients/{*.yaml,profiles/*.yaml}   # EP-01/EP-04: registrations + profiles
│   ├── backends/*.yaml                    # EP-06-T01/EP-07: endpoint + outbound identity por backend
│   └── capabilities/{sales,finance}/*.yaml # EP-02-T05: manifests de exemplo
├── src/emcp_bus/
│   ├── common/{config,otel,models}.py     # EP-00-T02, EP-08-T01, risk tier compartilhado
│   ├── identity/{models,authn,token_verifier,shared_client_lint}.py  # EP-01
│   ├── entitlement/{models,manager}.py    # EP-04
│   ├── registry/{models,store,pipeline,lifecycle,seed}.py  # EP-02
│   ├── pdp/{client,models}.py             # EP-03
│   ├── fabric/router.py                   # EP-06-T01
│   ├── fabric/adapters/rest_adapter.py    # EP-06-T04 (standalone, ver limitações)
│   ├── downstream/{models,identity}.py    # EP-07
│   ├── audit/{models,events,sink,correlation,bypass_detection}.py  # EP-08-T02/T03, EP-05-T07
│   ├── approval/{models,service}.py       # EP-14
│   ├── gateway/{server,cache,canonical_request}.py  # EP-05, integra tudo acima
│   ├── profile_intelligence/{models,rule_based_provider,governance}.py  # EP-09
│   ├── offering_filter/service.py         # EP-10
│   ├── orchestrator/{decision_context,state,graph,nba_model,decisioning,fallback,hitl_node}.py  # EP-11
│   └── agent_runtime/{dispatcher,identity_resolver,handoff_graph,global_supervisor,channels/*}.py  # EP-12, EP-13-T05
├── services/example_mcp_servers/
│   ├── sales_domain/server.py    # EP-06-T02 (6 tools: R1 + R2)
│   └── finance_domain/server.py  # EP-06-T03 (invoice.get R1, payment.create R2, payment.execute R3)
├── agents/example_agent/
│   ├── agent.py, llm_client.py   # EP-13-T01
│   ├── prompts/{store.py,v1.txt} # EP-13-T04
│   ├── backends/{sales_agent,finance_agent}/  # EP-13-T05, Modo A (ADR-024)
│   └── mode_b_orchestrator_driven/{decision_model,orchestrator}.py  # EP-13-T06, Modo B (ADR-024)
├── deploy/langfuse/docker-compose.override.yml  # EP-13-T02
├── docs/adr/                     # ADR-001..025 formalizados (EP-16-T03), um arquivo por decisão
└── tests/
    ├── unit/       # schemas, PDP, entitlement, authn, registry, downstream identity, approval,
    │                # fabric router, audit, canonical request, rest adapter, bypass detection,
    │                # gateway cache, shared client lint, profile intelligence, offering filter
    │                # (+ invariants), orchestrator (decision_context/decisioning/fallback/hitl/graph),
    │                # agent_runtime (channels/identity_resolver/handoff/global_supervisor),
    │                # pii_redaction, prompt store
    ├── e2e/        # conftest.py (fixtures compartilhados), walking skeleton, governed gateway,
    │                # test_real_keycloak.py (EP-01-T01/T12, token exchange, Modo B, Docker real),
    │                # test_example_agent.py (EP-13-T01, LLM real),
    │                # test_security_acceptance.py (EP-15-T02, docker-compose real),
    │                # test_multi_agent_mode_a.py (EP-13-T05, LLM real),
    │                # test_fail_closed.py (EP-15-T05)
    ├── contract/   # conftest.py + test_sales_domain.py + test_finance_domain.py (EP-15-T01)
    └── adversarial/  # test_prompt_injection.py, test_tool_poisoning.py,
                       # test_payload_identity_spoofing.py (EP-15-T03),
                       # test_protocol_identity.py (EP-15-T04)
```
