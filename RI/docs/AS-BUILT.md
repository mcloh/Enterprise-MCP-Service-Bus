# AS-BUILT — Enterprise MCP Service Bus (RI)

Referência técnica do que existe hoje na Reference Implementation (RI): responsabilidade de
cada componente, onde o código vive, contratos de entrada/saída em nível alto (o detalhe fino
de cada contrato está em [`interfaces/`](interfaces/)), o que foi validado e contra qual
dependência real, e as limitações arquiteturais reais encontradas durante a implementação.

Público-alvo: quem vai **integrar com ou estender** a RI. Para quem vai **rodar** a RI, ver
[`How-To.md`](How-To.md). Para quem vai **avaliar/adaptar** a RI para um cenário real, ver
[`Assumptions.md`](Assumptions.md) e [`Production-Recommendations.md`](Production-Recommendations.md).

Decisões arquiteturais individuais estão registradas em [`../../docs/adr/`](../../docs/adr/)
(ADR-001 a ADR-025); as premissas e razões por trás delas estão sintetizadas em
[`Assumptions.md`](Assumptions.md).

## Status

Todo o backlog planejado (marcos M0 a M4) está implementado, testado e validado. **261 testes
automatizados** (contagem verificada via `pytest --collect-only` nesta revisão): 254 passam com
`pytest --forked` (unit + e2e + contract + adversarial), mais 7
testes de aceite de segurança (`tests/e2e/test_security_acceptance.py`) que exigem Docker real e
são rodados separadamente pelo custo de build+Keycloak por execução. Lógica de produção sem
mocks no núcleo de segurança e orquestração: OPA real (subprocess), Keycloak real (Docker),
LangGraph real com checkpointer SQLite, um LLM real (endpoint OpenAI-compatible), JWKS HTTP real
(stand-in leve para o resto da suíte e2e) com JWT RS256 reais, YAML reais de `config/`, SQLite
real para o Registry.

## Índice de épicos

Cada `EP-XX-TXX` que aparece em comentários/docstrings do código-fonte referencia um destes
épicos. Esta tabela é a referência autoritativa para essas siglas — consulte-a sempre que um
comentário/docstring citar um `EP-XX-TXX` sem contexto adicional.

| Épico | Título | Módulo/teste principal |
|---|---|---|
| EP-00 | Bootstrap e tooling da RI | `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `src/emcp_bus/common/config.py` |
| EP-01 | Identidade do MCP Client e autenticação | `src/emcp_bus/identity/*.py`, `deploy/keycloak/realm-export.json` |
| EP-02 | Global Capability Registry e publishing pipeline | `src/emcp_bus/registry/*.py` |
| EP-03 | PDP / Policy Engine (OPA) | `src/emcp_bus/pdp/*.py`, `config/policies/*.rego` |
| EP-04 | Entitlement Manager | `src/emcp_bus/entitlement/*.py` |
| EP-05 | MCP Gateway / PEP | `src/emcp_bus/gateway/*.py` |
| EP-06 | Enterprise MCP Fabric e servidores de domínio de exemplo | `src/emcp_bus/fabric/*.py`, `services/example_mcp_servers/*` |
| EP-07 | Downstream identity (inbound vs outbound) | `src/emcp_bus/downstream/*.py` |
| EP-08 | Auditoria, correlação e observabilidade | `src/emcp_bus/audit/*.py`, `src/emcp_bus/common/otel.py` |
| EP-09 | Profile Intelligence (contrato genérico) | `src/emcp_bus/profile_intelligence/*.py` |
| EP-10 | Offering Filter | `src/emcp_bus/offering_filter/service.py` |
| EP-11 | Service Orchestrator (NBA/NBO) | `src/emcp_bus/orchestrator/*.py` |
| EP-12 | Agent Runtime e channel adapters | `src/emcp_bus/agent_runtime/*.py` |
| EP-13 | Agente de exemplo e instrumentação Langfuse | `agents/example_agent/*` |
| EP-14 | Human-in-the-loop / Approval workflow | `src/emcp_bus/approval/*.py` |
| EP-15 | Testes de segurança e adversariais | `tests/contract/`, `tests/e2e/test_security_acceptance.py`, `tests/adversarial/`, `tests/e2e/test_fail_closed.py` |
| EP-16 | Deploy final e documentação | `docker-compose.yml`, `docs/adr/` |

Dentro de cada épico, `TXX` numera as tarefas (ex.: `EP-05-T03` = terceira tarefa do épico
EP-05/Gateway — o cache hint de `tools/list`). Os ADRs referenciados por número (`ADR-XXX`) são
arquivos individuais em [`../../docs/adr/`](../../docs/adr/).

## Componentes

### Identidade do MCP Client (EP-01)

**Responsabilidade:** autenticar a identidade de workload que faz a chamada, nunca a identidade
autodeclarada em `clientInfo` ou em qualquer campo do payload. `src/emcp_bus/identity/authn.py`
(`TokenValidator`) valida um bearer token OAuth2/OIDC contra o JWKS do IdP (assinatura RS256,
`exp`, `iss`, `aud`); o `client_id` confiável vem exclusivamente da claim `azp`/`client_id` do
token verificado. `src/emcp_bus/identity/models.py` (`ClientRegistration`) mapeia esse
`client_id` a exatamente um `ClientProfile` (EP-04) via YAML em `config/clients/*.yaml`.
`shared_client_lint.py` (EP-01-T05) valida em CI que dois agentes distintos nunca compartilham
o mesmo `client_id` sob profiles diferentes.

**Validado contra:** Keycloak 26.7.3 real via Docker (`tests/e2e/test_real_keycloak.py`) — realm
`emcp` importado de `deploy/keycloak/realm-export.json`, 3 clients (`sales-read-agent`,
`sales-write-agent`, `finance-payments-agent`) com grant `client_credentials`; e um servidor JWKS
HTTP local mais leve como stand-in para o resto da suíte e2e (válido para a lógica de validação,
não para a integração de protocolo real com o IdP).

**Extensão de produção documentada, não implementada:** mTLS/workload identity —
`docs/adr/ADR-019-extensao-de-identidade.md`.

### PDP / Policy Engine (EP-03)

**Responsabilidade:** decidir ALLOW/DENY/REQUIRE_APPROVAL de forma determinística e auditável.
Modelo em dois passos (`src/emcp_bus/pdp/client.py`, `PDPClient.evaluate`): (1) `entitlement.rego`
decide se a tool está no `ClientProfile.allowed_tools` — DENY aqui é definitivo, nenhum argumento
é avaliado; (2) `transaction.rego` restringe por argumento/recurso (limite de valor, região,
classificação do cliente) e pode rebaixar um ALLOW para REQUIRE_APPROVAL acima de
`approval_threshold`. Toda resposta é um `PDPDecision` (`outcome`, `policy_version`,
`reason_code`) — nunca um booleano. `policy_version` é um hash SHA-256 (12 chars) do conteúdo
dos arquivos `.rego` em disco, computado uma vez no boot do Gateway.

**Validado contra:** OPA real via subprocess (binário `opa run --server`), 9 testes Rego
(`opa test`) + 6 testes Python de integração.

### Global Capability Registry (EP-02)

**Responsabilidade:** control-plane asset com autoridade e ciclo de vida próprios sobre o
catálogo de capabilities, separado da visão de execução que o Gateway expõe a cada client.
`registry/models.py` define `CapabilityManifest` (nome canônico `<domínio>.<capability>`,
`risk_tier` R0–R4, `data_classification`, `side_effects`, `idempotent`, `entitlements`,
`backend`, `approval`, `observability`, `lifecycle`). `registry/pipeline.py`
(`PublishingPipeline`) é o único caminho de entrada: valida gates de negócio (owner obrigatório,
backend declarado, tiers R3/R4 exigem `approval.required=true`) e avança
`NOMINATE → REVIEW → REGISTER`; um `publish()` separado avança `REGISTER → ACTIVE`, quando a
capability se torna resolvível pelo Fabric. `registry/lifecycle.py` garante mecanicamente que
nada alcança `ACTIVE` sem passar por `REVIEW`. `registry/store.py` persiste em SQLite;
`registry/seed.py` popula o Registry a partir de `config/capabilities/*.yaml` no boot do Gateway
(um arquivo temporário por processo, não compartilhado entre execuções).

**Validado contra:** SQLite real, 9 manifestos de exemplo (6 Sales + 3 Finance) passando pelo
pipeline completo sem intervenção manual.

### PEP / MCP Gateway (EP-05)

**Responsabilidade:** único Policy Enforcement Point. `src/emcp_bus/gateway/server.py`
implementa dois invariantes: `tools/list` retorna a interseção do catálogo dos backends
entitled com o `MaximumEntitlement` do client autenticado (discovery filtrado); `tools/call` é
reautorizado de forma totalmente independente do que `tools/list` retornou — o PDP é consultado
em toda chamada. Sem token válido: `tools/list` vazio, `tools/call` sempre `Access denied:
UNAUTHENTICATED`. PDP inalcançável é DENY (`PDP_UNAVAILABLE`), nunca ALLOW implícito. Falha do
`AuditSink` nunca vira erro 500 numa operação já decidida (`_emit_audit`, engole exceção em
todos os 8 pontos de emissão). Roteamento por capability é resolvido a cada chamada via
`CapabilityRouter` (EP-06) contra o Registry — um client pode ver tools de mais de um backend
(ex.: Sales + Finance). Ver [`interfaces/mcp-gateway.md`](interfaces/mcp-gateway.md) para o
contrato completo (headers, códigos de negação, cache hint).

**Validado contra:** OPA real, Keycloak real (Docker), JWT RS256 reais, e um cliente MCP real do
host contra o Gateway containerizado (`docker compose --profile core [--profile identity] up`).

### Enterprise MCP Fabric e servidores de domínio de exemplo (EP-06)

**Responsabilidade:** `src/emcp_bus/fabric/router.py` (`CapabilityRouter`) resolve um nome de
tool `<domínio>.<capability>` para o backend que a serve, usando apenas manifestos `ACTIVE` do
Registry — nunca um mapeamento estático no Gateway. `services/example_mcp_servers/sales_domain/`
(6 tools, R1+R2) e `finance_domain/` (3 tools: `invoice.get` R1, `payment.create` R2,
`payment.execute` R3 com ciclo de aprovação completo) são os dois domínios de exemplo,
protegidos por `BackendCredentialGate` (EP-05-T07) — uma requisição sem a credencial de saída do
Gateway nunca alcança um handler de tool. `fabric/adapters/rest_adapter.py` (EP-06-T04)
implementa um adapter REST genérico, testado de forma standalone (`httpx.MockTransport`); nenhum
manifesto seed usa `backend.type: "rest"`, então não há caminho ao vivo através do Gateway
exercitando-o.

**Validado contra:** roteamento real Sales→sales-domain / Finance→finance-domain nunca cruzado,
inclusive cross-container via Docker Compose real (segmentação de rede confirmada: nenhum dos
domain servers ou o OPA publica porta de host).

### Downstream / outbound identity (EP-07)

**Responsabilidade:** a credencial que o Fabric apresenta ao backend nunca é o token inbound do
MCP Client (`src/emcp_bus/downstream/identity.py`, `BackendCredentialProvider`). Dois modos
declarados por backend em `config/backends/*.yaml` (`BackendConfig.credential_mode`):
`service_account` (credencial estática lida de uma env var no momento da chamada — o modo
padrão dos backends seed) e `token_exchange` (RFC 8693 via Keycloak Standard Token Exchange,
`TokenExchangeClient` — dois round-trips HTTP por troca nova, com cache por backend até pouco
antes do `expires_in`). Ver [`interfaces/downstream-identity.md`](interfaces/downstream-identity.md).

**Validado contra:** Keycloak 26.7.3 real — `audience` do exchange precisa ser um client id
realmente registrado (uma string livre falha com "Audience not found"); pedir `audience` sem um
`scope` que efetivamente adiciona essa audience falha com "Requested audience not available".
Realm ganhou o client `gateway-token-exchange` e client scopes com `oidc-audience-mapper` por
backend. 7 testes (4 unit com `httpx.MockTransport`, 3 e2e contra Keycloak real, incluindo um
`tools/call` completo pelo Gateway usando uma credencial obtida por token exchange).

### Auditoria, correlação e observabilidade (EP-08)

**Responsabilidade:** `audit/models.py` define `EventEnvelope` com uma taxonomia de 3 categorias
adotada da referência Agent Platform OCI (ADR-022): **IC** (Indicador de Controle/negócio-jornada,
ex. `client_authenticated`, `tool_call_allowed`), **NOC** (operacional/erro de disponibilidade,
ex. `pdp_unavailable`), **GRL** (guardrail/governança, ex. `tool_call_denied`,
`tools_list_filtered`, `bypass_attempt_detected`). Todo evento sanitiza recursivamente qualquer
chave cujo nome contenha `token`/`secret`/`password`/`authorization`/`credential`, substituindo o
valor por `sha256:<hex>` — nunca um valor de segredo chega a um sink. `audit/correlation.py`
propaga `decision_id`/`policy_decision_id`/`entitlement_version`/`policy_version`/
`mcp_request_id` como campos de primeira classe em todo evento e como atributos de span OTel
(ADR-017). `audit/sink.py` (`JSONLFileAuditSink`) grava em arquivo JSONL append-only.
`common/otel.py` instala tracing automático (`OpenTelemetryMiddleware`) sem código manual de
span no Gateway. Ver [`interfaces/audit-events.md`](interfaces/audit-events.md).

**Validado contra:** correlação de `trace_id` real entre containers Docker distintos (Gateway ↔
domain server) para uma chamada bem-sucedida. Stack local `otel-collector` + Jaeger
(EP-08-T04, perfil `observability`): configuração validada (`docker compose config`), não
exercitada com tráfego OTLP real por um teste automatizado — Langfuse (EP-13-T02) é quem recebeu
tráfego OTLP real de fato, validado manualmente (ver componente "Agente de exemplo" abaixo).

### Entitlement Manager (EP-04)

**Responsabilidade:** `entitlement/manager.py` (`EntitlementManager`) resolve o
`MaximumEntitlement` combinando o `ClientProfile` (YAML validado, `entitlement/models.py`) com a
decisão de entitlement do PDP, produzindo um `ResolvedEntitlement` versionado
(`entitlement_version`) com `allowed_tools`/`risk_ceiling`/`profile_name`. `sync_profiles_to_pdp`
empurra os profiles validados para o data document do OPA no boot — falha aqui impede o Gateway
de subir "saudável" (fail-closed, README.md §38). Revogação invalida o cache de entitlement e
reavalia a partir da próxima chamada.

**Validado contra:** OPA real + YAML reais; revogação de política ao vivo contra um Gateway
rodando (`tests/adversarial/test_protocol_identity.py`).

### Approval workflow (EP-14)

**Responsabilidade:** `approval/service.py` (`ApprovalService`) gate para decisões
`REQUIRE_APPROVAL`: `check_and_consume` (chamado pelo Gateway a cada tentativa) só retorna
verdadeiro para uma aprovação concedida, não expirada e ainda não consumida — single-use, nunca
"enfileira e libera". Um `ApprovalRequest` é vinculado a um hash SHA-256 do triplo exato
`(client_profile, tool, arguments)` (`compute_operation_hash`), não apenas ao nome da tool: uma
aprovação para uma chamada nunca satisfaz uma chamada diferente com os mesmos tool/profile.
`check_and_consume` é protegido por `threading.Lock` (achado real de concorrência, ver
"Limitações" abaixo). Ver [`interfaces/approval-workflow.md`](interfaces/approval-workflow.md).

**Validado contra:** ciclo completo e2e para Sales e Finance (nega → aprova externamente →
executa → replay nega); replay sob concorrência real (`ThreadPoolExecutor`, 20 threads).

### Profile Intelligence (EP-09)

**Responsabilidade:** `profile_intelligence/models.py` define `ProfileView` (`subject_ref`
pseudonimizado, `profile_version`, `segments`, `attributes`, `reason_codes`, `expires_at`) como
um contrato genérico e substituível — qualquer `ProfileIntelligenceProvider` (o stub
determinístico rule-based em `rule_based_provider.py`, ou um modelo de clustering real numa
implantação de produção) produz o mesmo contrato. Um `ProfileView` nunca é consultado pelo PDP e
nunca pode conceder uma capability fora do `MaximumEntitlement` — nada aqui está conectado ao
caminho de autorização. `governance.py` implementa os guardrails de governança: pseudonimização,
log de linhagem, stub de monitor de drift.

**Validado contra:** determinismo (mesmo `subject_ref` + janela ISO → mesmo `profileVersion`).

### Offering Filter (EP-10)

**Responsabilidade:** `offering_filter/service.py` implementa
`FilteredOfferings = ActiveCatalog ∩ MaximumEntitlement ∩ ConsentContext`. A ordem da interseção
é deliberada: `allowed_tools` (MaximumEntitlement, já resolvido pelo EP-04) é o único termo
tratado como relevante para segurança e é aplicado primeiro; um `ConsentContext` (aqui, apenas
`allow_restricted_data` sobre `CapabilityManifest.data_classification`) só pode reduzir o que já
sobreviveu a essa interseção, nunca reintroduzir uma capability fora do entitlement.

**Validado contra:** invariante de subconjunto provada com Hypothesis, 2000 casos gerados
(`tests/unit/test_offering_filter_invariants.py`).

### Service Orchestrator (EP-11)

**Responsabilidade:** `orchestrator/graph.py` (`build_journey_graph`) é um `StateGraph` real do
LangGraph com nós fixos `resolve_profile → resolve_entitlement → filter_offerings → decide_nba
→ approval_gate`, mais uma reentrada dedicada para o loop de recálculo após DENY
(`handle_denial_node`, que nunca chama o Fabric diretamente — apenas recalcula a NBA sobre as
offerings restantes). `orchestrator/nba_model.py` define `NBADecision`
(`decision_id`, `action`, `capability_version`, `subject_ref`, `channel`, `agent`,
`reason_codes`, `policy_context`, `expires_at`) e o protocolo `NBADecisionModel` — trocar a
implementação de referência (`decisioning.RuleBasedNBADecisionModel`) por um modelo de
ranking/IA não muda nada no contrato de entrada/saída nem no que EP-03/04/05 autorizam, porque o
modelo só ordena/seleciona entre `DecisionContext.filtered_offerings`, já intersectado pelo
EP-10 antes de chegar aqui. `orchestrator/hitl_node.py` usa `langgraph.types.interrupt`/
`Command(resume=...)` para pausar de verdade o grafo em aprovação — sem timeout que vire ALLOW
implícito.

**Validado contra:** OPA real + LangGraph real + checkpointer SQLite real, incluindo prova de
que retomar de um checkpoint pausado não reprocessa nós já executados.

### Agent Runtime (EP-12)

**Responsabilidade:** `agent_runtime/dispatcher.py` (`AgentDispatcher`) consome uma `NBADecision`
e a despacha contra o Gateway real, autenticado como o MCP Client já registrado para o agente
alvo — nunca gera ou armazena credencial própria (`AgentTokenProvider`, tipicamente um
`client_credentials` real contra o mesmo IdP de qualquer outro MCP Client). `handoff_graph.py`
(EP-12-T03, `execute_handoff`/`build_handoff_payload`) implementa handoff entre agentes com
minimização de contexto e resolução de entitlement sempre independente por agente — ver
"Limitações" abaixo para o achado de que nem o Modo A nem o Modo B (EP-13-T05/T06) acabaram
usando esse primitivo. `identity_resolver.py` (EP-12-T04, `IdentityResolver`) normaliza nomes de
campo entre canais (`config/orchestrator/identity.yaml`) e nunca é consultado pelo PDP — checado
mecanicamente via análise de AST no teste unitário correspondente, a mesma disciplina que
`global_supervisor.py` usa para provar que nunca importa `emcp_bus.orchestrator`.

**Validado contra:** Gateway + Keycloak reais — `AgentDispatcher` alcançando o backend Sales
real e sendo negado no cross-domain; dois agentes reais obtendo tokens `client_credentials`
independentes.

### Agente de exemplo (EP-13)

**Responsabilidade:** `agents/example_agent/agent.py` é um agente conversacional com
tool-calling real contra um endpoint OpenAI-compatible, cujo catálogo é restrito ao próprio
`tools/list` do client. `common/pii_redaction.py` redige PII/segredos antes de qualquer export.
`prompts/store.py` implementa versionamento local de prompt (nunca sobrescreve uma versão
anterior) como núcleo testável — sincronização com a API de Prompt Management do Langfuse é um
adapter fino documentado, não implementado.

**Validado contra:** um LLM real (`meta.llama-3.3-70b-instruct` via endpoint OpenAI-compatible da
OCI Generative AI), com tool-calling confirmado empiricamente; o cenário de prompt injection do
README.md §29 (pedir uma tool fora do entitlement) reproduzido de verdade — a chamada nunca
executa, seja porque o modelo nunca viu a tool no próprio catálogo, seja porque o Gateway/PDP
nega. Langfuse self-hosted real (6 containers: web/worker/postgres/clickhouse/redis/minio,
`deploy/langfuse/docker-compose.override.yml`) recebendo tráfego OTLP real do agente —
spans de MCP e de "generation" (com `gen_ai.request.model`/tokens reais) confirmados fisicamente
na tabela `events_core` do ClickHouse. Essa validação é manual, não um teste e2e automatizado
(custo de subir 6 containers a cada execução da suíte).

### Modo A — Global Supervisor externo (EP-13-T05, ADR-024)

**Responsabilidade:** `agent_runtime/global_supervisor.py` (`GlobalSupervisor`) é o stand-in
deliberadamente simples (roteamento por palavra-chave) para uma plataforma de orquestração
externa que decide qual agente de backend atende uma conversa — nunca é, ou pretende ser, a
fronteira de segurança; nunca importa `emcp_bus.orchestrator` (checado via AST). A propriedade de
segurança real não está neste módulo: está no fato de que cada `BackendAgent`
(`agents/example_agent/backends/{sales_agent,finance_agent}/`) resolve seu próprio MCP
Client/entitlement de forma completamente independente — token, `tools/list` e reautorização
próprios — e o `GlobalSupervisor` nunca lê, guarda ou repassa a credencial de um backend para
outro.

**Validado contra:** LLM real + Gateway real (`tests/e2e/test_multi_agent_mode_a.py`, 2 testes):
handoff de `sales_agent` para `finance_agent` com token completamente distinto; injeção de
prompt via handoff tentando `finance.payment.execute` continua negada pelo Gateway/PDP reais.

### Modo B — Orchestrator como único cérebro de NBA/NBO (EP-13-T06, `could`, ADR-024)

**Responsabilidade:** `agents/example_agent/mode_b_orchestrator_driven/orchestrator.py`
(`ModeBOrchestrator`) invoca o journey `StateGraph` real do EP-11-T02 (não modificado) uma vez
por `client_id` relevante para o mesmo subject, combina os `NBADecision`s resultantes (regra de
referência: pendência de Finance sempre vence oferta discricionária de Sales) e despacha o
vencedor via `AgentDispatcher` real — nunca cria um caminho de autorização próprio. Deliberadamente
não estende `JourneyState`/`build_journey_graph` para múltiplos `client_id`s nativamente; a
combinação vive uma camada acima do grafo (decisão de design registrada no próprio módulo).

**Validado contra:** Keycloak real + OPA real + Sales/Finance reais
(`tests/e2e/test_real_keycloak.py::test_mode_b_orchestrator_combines_offerings_and_dispatches_through_the_real_chain`):
candidatos de ambos os domínios realmente combinados, decisão final do nosso Orchestrator,
dispatch `ALLOW` de ponta a ponta.

## O que foi validado, por dependência real

| Dependência real | O que exercita | Onde |
|---|---|---|
| OPA (subprocess) | `entitlement.rego`/`transaction.rego`, `PDPClient` | `tests/unit/policies/`, toda a suíte e2e |
| Keycloak (Docker, 26.7.3) | client_credentials, JWKS real, token exchange RFC 8693, Modo B | `tests/e2e/test_real_keycloak.py` |
| LangGraph 0.6 + checkpointer SQLite | journey graph, pausa/retomada de aprovação | `tests/unit/test_orchestrator_graph.py`, e2e do M3 |
| LLM real (OpenAI-compatible) | tool-calling do agente de exemplo, prompt injection | `tests/e2e/test_example_agent.py`, `test_multi_agent_mode_a.py` |
| Docker Compose completo | build+up+fail-closed+trace cross-container+segmentação de rede | `tests/e2e/test_security_acceptance.py`, validação manual documentada |
| Langfuse self-hosted (6 containers) | export OTLP real, spans de generation | Validação manual (não automatizada) |

## Limitações e achados arquiteturais reais

- **`ttl_ms` do cache hint de `tools/list` (SEP-2549, EP-05-T03)**: implementado corretamente em
  `gateway/cache.py`, mas o campo pertence ao protocolo 2026-07-28, que só existe no modo
  *stateless per-request* do SDK `mcp` (sem handshake `initialize`). Esta RI usa o handshake de
  sessão clássico em toda parte (Gateway↔Client e Gateway↔backends), então `ttl_ms` nunca chega
  ao wire nesta arquitetura — o SDK descarta o campo na serialização para versões de protocolo
  anteriores a 2026-07-28 (verificado empiricamente). `cache_scope="private"` é sempre definido,
  mas por não depender do wire-mode também não é algo que um teste e2e consiga verificar de
  forma discriminante. A propriedade de segurança real (nunca vazar catálogo entre clientes) é
  garantida de forma independente: o Gateway nunca cacheia o catálogo filtrado no servidor.
- **Consistência header/body (EP-05-T08)**: implementada como um gate próprio
  (`gateway/canonical_request.py`) reaproveitando as constantes de campo do SDK, não como o
  ladder de validação nativo do SDK (que só se aplica ao mesmo modo *stateless per-request* de
  2026-07-28 acima) — pela mesma razão, esta RI não o alcança pelo caminho nativo.
  Cabeçalhos ausentes (um client que não implementa esse SEP) não são um erro.
- **Adapter REST (EP-06-T04)**: implementado e testado de forma standalone
  (`fabric/adapters/rest_adapter.py`); nenhum backend de exemplo desta RI é REST (ambos são
  MCP-nativos), então o roteamento ao vivo através do Gateway para um backend `type: "rest"`
  nunca foi exercitado end-to-end.
- **Handoff entre agentes (EP-12-T03, `execute_handoff`/`build_handoff_payload`)**: continua
  implementado e testado (`tests/unit/test_agent_runtime_handoff.py`), mas nem o Modo A
  (EP-13-T05) nem o Modo B (EP-13-T06) acabaram usando esse primitivo. O Modo A precisa de
  roteamento conversacional (qual backend responde à próxima mensagem), não de despacho de uma
  `NBADecision` específica — `GlobalSupervisor` chama `run_turn()` diretamente nos backends. O
  Modo B já combina `NBADecision`s de múltiplos clients num único passo e despacha o vencedor via
  `AgentDispatcher.dispatch` puro — não há um agente "de origem" cedendo controle a outro para
  `execute_handoff` interceptar. O primitivo permanece correto e reutilizável para um cenário
  futuro de handoff *dentro* de uma jornada Orchestrator-driven, mas essa forma específica de uso
  não existe nesta RI.
- **Replay de requisição**: sem nonce/anti-replay nesta RI — uma requisição capturada com um
  token ainda válido pode ser reenviada com sucesso. Mitigado por tokens de vida curta
  (`credential_policy.short_lived` em todo `ClientProfile` seed) e por auditoria completa (cada
  tentativa, mesmo idêntica, gera `decision_id` próprio). Ver
  `tests/adversarial/test_protocol_identity.py`.
- **Rate limiting / bulk exfiltration**: sem limitação de taxa de requisições no Gateway — N
  leituras legítimas consecutivas são todas permitidas. Mitigado apenas por detectabilidade a
  posteriori via auditoria (cada chamada gera evento correlacionado), nunca por prevenção em
  tempo real.
- **Race condition real corrigida em `ApprovalService`**: `check_and_consume` fazia check-then-set
  em duas operações não atômicas — sob concorrência real de threads, duas tentativas podiam
  ambas observar "granted" antes de qualquer uma escrever "consumed" (double-spend de um grant
  single-use). Corrigido com `threading.Lock` dedicado, provado com `ThreadPoolExecutor` (20
  threads) em `tests/adversarial/test_protocol_identity.py`.
- **Falha de audit sink podia virar erro 500 real, corrigida**: nenhuma das 8 chamadas
  `audit_sink.emit(...)` no Gateway estava protegida — uma falha no sink (disco cheio, fila
  indisponível) podia transformar uma operação já `ALLOW`ed num erro 500 para o caller, violando
  a política de não bloquear operações de baixo risco. Corrigido com o helper `_emit_audit`
  (`gateway/server.py`), que engole qualquer exceção do sink nos 8 pontos de emissão, para ALLOW
  e para DENY. Uma falha do sink em produção precisa de observabilidade própria (ver
  `Production-Recommendations.md`) — este comportamento é correto por design, mas silencioso.
- **Roteamento do `GlobalSupervisor` (Modo A)**: por palavra-chave simples, deliberadamente não é
  a fronteira de segurança nem uma reivindicação de qualidade de roteamento — apenas um stand-in
  honesto para o que uma plataforma externa real faria.
- **Regra de combinação do `ModeBOrchestrator` (Modo B)**: "Finance sempre vence Sales" é uma
  regra de referência simples, não uma reivindicação de otimalidade — mesma postura de
  `RuleBasedNBADecisionModel` (EP-11-T03).
- **Stack de observabilidade (EP-08-T04)**: configuração validada (`docker compose config`), não
  exercitada com tráfego real por um teste automatizado (a subida completa com o perfil
  `observability` foi validada manualmente).
