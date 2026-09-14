# Enterprise MCP Service Bus — Reference Implementation

Implementação executável da arquitetura descrita em [`../README.md`](../README.md), planejada em [`../docs/RI-PLANNING.md`](../docs/RI-PLANNING.md).

> **Status: Marco M1 concluído** (fechamento retroativo pós-M2, 2026-09-11) — todos os gaps de M0/M1 identificados após o M2 foram implementados nesta rodada: Fabric router multi-backend (EP-06-T01), domínio Finance com backend real (EP-06-T03), auditoria IC/NOC/GRL + correlação ponta a ponta (EP-08-T02/T03), stack local de observabilidade (EP-08-T04), cache hint (EP-05-T03), anti-bypass (EP-05-T07), consistência header/body (EP-05-T08), adapter REST genérico (EP-06-T04), lint de shared client (EP-01-T05), spike de mTLS (EP-01-T04), pipeline de CI (EP-00-T03). Ver "O que existe hoje" abaixo. A flakiness da suíte e2e documentada em sessões anteriores está **resolvida** (`--forked`, ver abaixo). Os demais marcos (M3/M4) estão descritos em `docs/RI-PLANNING.md`, seção 8.7.

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
| EP-07 (completo) | Outbound/downstream identity: credencial de backend distinta da do client | ✅ `src/emcp_bus/downstream/{models,identity}.py`, ligado ao Gateway, testado |
| EP-08-T01 | Tracing OTel | ✅ (M0) |
| EP-08-T02 | Eventos de auditoria (taxonomia IC/NOC/GRL) | ✅ `src/emcp_bus/audit/{models,events,sink}.py` — nunca registra valor de token/secret (hash apenas), sink JSONL append-only |
| EP-08-T03 | Correlação ponta a ponta (decisionId/policyDecisionId/entitlementVersion/mcpRequestId) | ✅ `src/emcp_bus/audit/correlation.py` — exposto no trace (span attributes) e em todo evento de auditoria |
| EP-08-T04 | Stack local de observabilidade (OTel Collector + Jaeger) | ✅ `docker-compose.yml` perfil `observability` + `deploy/otel/collector-config.yaml` — config validada (`docker compose config`), não exercitada com tráfego real nesta rodada |
| EP-14 (completo) | Approval workflow: contrato, serviço, fail-closed, ligado ao Gateway | ✅ `src/emcp_bus/approval/{models,service}.py`, testado (ciclo completo e2e para Sales **e** Finance: nega → aprova externamente → executa → replay nega) |

**119 testes automatizados** (97 unit + 22 e2e, incluindo 4 contra Keycloak real em `test_real_keycloak.py`), a lógica de produção sem mocks do núcleo de segurança: OPA real (subprocess), Keycloak real (Docker) + JWKS HTTP real (stand-in leve para o resto da suíte) + JWT RS256 reais, YAML reais de `config/`, SQLite real para o Registry. **100% determinísticos com `--forked`** (verificado em múltiplas execuções seguidas) — a flakiness antes documentada para a suíte e2e está resolvida, ver seção dedicada acima.

## Limitações conhecidas

- **SEP-2549 (`ttlMs` do cache hint de `tools/list`, EP-05-T03)**: implementado corretamente (`src/emcp_bus/gateway/cache.py`), mas o campo é vocabulário exclusivo do protocolo 2026-07-28, que só existe no modo *stateless per-request* do SDK (sem handshake `initialize`) — esta RI usa o handshake de sessão clássico em toda parte (Gateway↔Client e Gateway↔backends), então `ttl_ms` nunca chega ao wire nesta arquitetura, não importa o que o Gateway compute (o SDK descarta o campo na serialização para versões de protocolo anteriores a 2026-07-28 — verificado empiricamente). `cache_scope` não sofre essa limitação de wire, mas por não ter dependência de wire-mode também não é algo que um teste e2e consiga verificar de forma discriminante (o cliente sempre usa o default do próprio campo). A propriedade de segurança real (Teste 5, §45 — nunca vazar catálogo entre clientes) é garantida de forma independente pelo Gateway nunca cachear o catálogo filtrado no servidor.
- **EP-05-T08 (consistência header/body)**: implementado como um gate próprio (`canonical_request.py`) reaproveitando as constantes/nomes de campo do SDK, e não como o ladder de validação nativo do SDK (`mcp.shared.inbound.classify_inbound_request`), que só se aplica ao mesmo modo *stateless per-request* de 2026-07-28 mencionado acima — pela mesma razão, este RI não o alcança pelo caminho nativo.
- **EP-06-T04 (adapter REST)**: implementado e testado de forma standalone; nenhum backend de exemplo desta RI é REST (ambos são MCP-nativos), então o roteamento ao vivo através do Gateway para um backend `type: "rest"` não foi exercitado end-to-end.
- **Token exchange RFC 8693** (EP-07, modo `token_exchange` de `BackendConfig`): implementado como contrato/config validado, mas a chamada real ao endpoint de token exchange é um `NotImplementedError` documentado — o modo `service_account` (credencial estática por env var) é o caminho testado ponta a ponta.
- **Stack de observabilidade** (EP-08-T04): config validada, não exercitada com tráfego real (ver "O que foi validado com Docker").

## Versões fixadas

Ver `pyproject.toml`. Confirmadas via `pip index versions`/download direto em 2026-09-11 (não citadas de memória — ver `docs/RI-PLANNING.md`, EP-16-T04):

- `mcp` 2.2.0 (SDK v2 — API mudou significativamente da v1; ver comentários em `src/emcp_bus/gateway/server.py`)
- `pydantic` 2.13.x, `opentelemetry-sdk` 1.44.x, `uvicorn` 0.52.x, `pyjwt[crypto]` 2.14.x, `ruff` 0.16.x, `mypy` 2.3.x, `pytest` 9.1.x
- `OPA` 1.20.2 (binário estático, Rego v1 padrão)
- `pytest-forked` 1.7.x (resolve a flakiness da suíte e2e, ver acima)

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
│   └── gateway/{server,cache,canonical_request}.py  # EP-05, integra tudo acima
├── services/example_mcp_servers/
│   ├── sales_domain/server.py    # EP-06-T02 (6 tools: R1 + R2)
│   └── finance_domain/server.py  # EP-06-T03 (invoice.get R1, payment.create R2, payment.execute R3)
└── tests/
    ├── unit/       # schemas, PDP, entitlement, authn, registry, downstream identity, approval,
    │                # fabric router, audit, canonical request, rest adapter, bypass detection,
    │                # gateway cache, shared client lint
    └── e2e/        # conftest.py (fixtures compartilhados), walking skeleton, governed gateway,
                     # test_real_keycloak.py (EP-01-T01, Docker real)
```
