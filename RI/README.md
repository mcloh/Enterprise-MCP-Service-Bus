# Enterprise MCP Service Bus — Reference Implementation

Implementação executável da arquitetura descrita em [`../README.md`](../README.md), planejada em [`../docs/RI-PLANNING.md`](../docs/RI-PLANNING.md).

> **Status: núcleo de enforcement do Marco M1 concluído e testado ponta a ponta** (auth real → entitlement → PDP → decisão no Gateway, com OPA e um servidor JWKS reais — não mocks). Ver "O que existe hoje" abaixo. Os demais marcos estão descritos em `docs/RI-PLANNING.md`, seção 8.7.

## Quickstart (sem Docker)

```bash
make install   # cria .venv e instala o pacote em modo editável (dev extras inclusos)
make lint      # ruff check + ruff format --check
make typecheck # mypy --strict
make test      # pytest (38 testes: unit + e2e)
```

`make test` precisa do binário `opa` no PATH (ou `OPA_BINARY` apontando para ele) para os testes que exercitam o PDP de verdade — ver "Como instalar o OPA" abaixo. Sem ele, esses testes são pulados (`pytest.skip`), não falham.

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
python3 -m example_mcp_servers.sales_domain.server &
# Sem OIDC_JWKS_URL/OIDC_ISSUER, o Gateway roda em modo "sem IdP configurado":
# nega tudo por padrão (ver "Dois modos de deployment" abaixo).
python3 -m emcp_bus.gateway.server
```

Para autenticação real, seria necessário apontar `OIDC_JWKS_URL`/`OIDC_ISSUER` para um IdP OIDC de verdade (Keycloak, EP-01-T01 — não validado nesta sessão, ver abaixo). Os testes automatizados (`tests/e2e/conftest.py`) substituem isso por um servidor JWKS local real + tokens RS256 reais assinados na hora — válido para provar a lógica de validação de token, não para provar o Keycloak em si.

## Quickstart (Docker)

```bash
docker compose --profile core up --build
```

> **Nota**: `docker-compose.yml` e os Dockerfiles em `deploy/docker/` **não foram validados com um daemon Docker real** nesta sessão (ambiente sem `docker` disponível) — foram escritos e revisados manualmente, e a stack equivalente foi validada rodando os processos diretamente no host. Rode `docker compose --profile core up --build` na primeira vez em um ambiente com Docker e reporte qualquer ajuste necessário. **O `docker-compose.yml` atual ainda não inclui OPA/Keycloak como serviços** — apenas gateway + sales-domain (perfil `core`, herdado do M0); isso é trabalho pendente do M1 (ver tabela abaixo).

## Dois modos de deployment (importante)

O Gateway (`src/emcp_bus/gateway/server.py`) suporta dois modos, sempre *deny by default*:

1. **Com OIDC configurado** (`OIDC_JWKS_URL` + `OIDC_ISSUER` definidos): o próprio middleware de auth do SDK `mcp` (`RequireAuthMiddleware`) rejeita qualquer conexão sem bearer token válido **antes mesmo do handshake `initialize`** — mais estrito que qualquer checagem no nível do handler.
2. **Sem OIDC configurado** (padrão se as env vars não estiverem definidas): nenhum middleware de auth é instalado; toda requisição chega aos handlers com `get_access_token() is None`, e é a própria lógica do handler (`on_list_tools`/`on_call_tool`) que nega por padrão — `tools/list` vazio, `tools/call` sempre negado com `Access denied: UNAUTHENTICATED`.

Os dois modos são testados explicitamente em `tests/e2e/test_governed_gateway.py`.

## O que existe hoje

| Tarefa | Componente | Status |
|---|---|---|
| EP-00 (completo) | Scaffold, config loader, docker-compose base | ✅ (ver README anterior/git history) |
| EP-01-T02 | Schema de registro de MCP Client | ✅ `src/emcp_bus/identity/models.py` |
| EP-01-T03 | Middleware de autenticação OIDC/JWT | ✅ validado com JWKS real + tokens RS256 reais (assinatura, expiração, issuer, audience) |
| EP-01-T01 | Keycloak (realm export, serviço no compose) | ❌ não implementado — sem Java neste ambiente para validar; ver "Limitações desta sessão" |
| EP-01-T05 | Lint de shared client | ❌ não implementado (prioridade `could`) |
| EP-02 (Registry) | Schema de capability manifest | ✅ `src/emcp_bus/registry/models.py` (schema apenas — pipeline/storage/API ainda não) |
| EP-02-T02/T03/T05 | Publishing pipeline, storage, manifests de exemplo | ❌ não implementado |
| EP-03 (completo) | PDP/OPA: entitlement.rego, transaction.rego, cliente Python, contrato de decisão | ✅ validado com **OPA real** (binário, não mock) — 9 testes Rego nativos + 6 testes Python de integração |
| EP-04 (completo) | Entitlement Manager: resolve, revoke, versionamento | ✅ validado com OPA real + YAML reais de `config/clients/` |
| EP-05-T01 | Gateway skeleton | ✅ (M0) |
| EP-05-T02 | `tools/list` filtrado por entitlement | ✅ testado (README.md §45 Teste 1) |
| EP-05-T04 | `tools/call` reautorizado via PDP | ✅ testado (Teste 2, Teste 4 — agent role spoofing sem efeito) |
| EP-05-T06 | Fail-closed (PDP indisponível) | ✅ testado — `lifespan()` recusa subir se o OPA sync falhar |
| EP-05-T03 | Cache privado de `tools/list` | ❌ não implementado |
| EP-05-T07 | Anti-bypass (isolamento de rede) | ❌ não implementado (depende de docker-compose real) |
| EP-05-T08 | Consistência header/body (Mcp-Method/Mcp-Name) | ❌ não implementado explicitamente (o SDK já expõe os headers nativamente — ver §22 do README de arquitetura; falta o passo de validação cruzada) |
| EP-06-T01 | Fabric core (roteador por capability) | ❌ ainda roteamento estático (uma única URL fixa), não por Registry |
| EP-06-T02 | MCP Server de exemplo — Sales | ✅ (M0) |
| EP-06-T03 | MCP Server de exemplo — Finance | ❌ não implementado — os testes de negação para tools `finance.*` passam porque o PDP nega *antes* de qualquer tentativa de roteamento ao backend, então a ausência do servidor Finance real não invalida esses testes, mas nenhum cenário de **sucesso** em Finance foi exercitado |
| EP-06-T04 | Adapter REST genérico | ❌ não implementado |
| EP-08-T01 | Tracing OTel | ✅ (M0) |
| EP-08-T02/T03/T04 | Eventos de auditoria (IC/NOC/GRL), correlação, stack de observabilidade | ❌ não implementado — hoje só existe o trace OTel, sem taxonomia de eventos nem sink de auditoria |

**39 testes automatizados**, todos reais (sem mocks do núcleo de segurança): OPA de verdade (subprocess), JWKS HTTP real + JWT RS256 reais, YAML reais de `config/`.

## Limitações desta sessão

Nenhum `docker` nem `java` disponíveis no ambiente onde esta RI foi escrita:

- **Docker**: não validado (ver nota acima). Risco considerado baixo — o Dockerfile usa a mesma instalação (`pip install -e .`) já validada localmente.
- **Keycloak**: não implementado nem validado — precisa de JVM. A lógica de validação de OAuth2/OIDC (`TokenValidator`, EP-01-T03) é padrão-agnóstica de IdP (qualquer provedor OIDC compliant funciona) e foi validada com um servidor JWKS real + tokens RS256 reais, o que prova a lógica de validação mas **não prova a integração específica com Keycloak** (realm config, client credentials grant, claims exatas que o Keycloak emite). EP-01-T01 continua pendente.

## Versões fixadas

Ver `pyproject.toml`. Confirmadas via `pip index versions`/download direto em 2026-09-11 (não citadas de memória — ver `docs/RI-PLANNING.md`, EP-16-T04):

- `mcp` 2.2.0 (SDK v2 — API mudou significativamente da v1; ver comentários em `src/emcp_bus/gateway/server.py`)
- `pydantic` 2.13.x, `opentelemetry-sdk` 1.44.x, `uvicorn` 0.52.x, `pyjwt[crypto]` 2.14.x, `ruff` 0.16.x, `mypy` 2.3.x, `pytest` 9.1.x
- `OPA` 1.20.2 (binário estático, Rego v1 padrão)

## Estrutura

Ver `../docs/RI-PLANNING.md`, seção 8.5, para a árvore completa planejada. O que existe até agora:

```text
RI/
├── pyproject.toml
├── Makefile
├── docker-compose.yml          # perfil "core": gateway + sales-domain (OPA/Keycloak pendentes)
├── .env.example
├── deploy/docker/Dockerfile
├── config/
│   ├── policies/                          # EP-03: entitlement.rego, transaction.rego (+ testes opa test)
│   └── clients/                           # EP-01/EP-04: registrations + profiles/*.yaml
├── src/emcp_bus/
│   ├── common/{config,otel,models}.py     # EP-00-T02, EP-08-T01, risk tier compartilhado
│   ├── identity/{models,authn,token_verifier}.py  # EP-01-T02/T03
│   ├── entitlement/{models,manager}.py    # EP-04
│   ├── registry/models.py                 # EP-02-T01 (schema apenas)
│   ├── pdp/{client,models}.py             # EP-03
│   └── gateway/server.py                  # EP-05-T01/T02/T04/T06
├── services/example_mcp_servers/sales_domain/server.py  # EP-06-T02
└── tests/
    ├── unit/       # schemas, PDP client, entitlement manager, authn — todos contra dependências reais
    └── e2e/        # conftest.py (fixtures compartilhados), walking skeleton, governed gateway
```
