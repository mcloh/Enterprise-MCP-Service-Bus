# Enterprise MCP Service Bus — Reference Implementation

Implementação executável da arquitetura descrita em [`../README.md`](../README.md) (arquitetura
de referência). Para a referência técnica completa do que existe e como funciona, ver
[`docs/AS-BUILT.md`](docs/AS-BUILT.md).

## Status

Todo o backlog planejado (marcos M0 a M4) está implementado, testado e validado. **261 testes
automatizados**: 254 passam com `pytest --forked` (unit + e2e + contract + adversarial), mais 7
testes de aceite de segurança (`tests/e2e/test_security_acceptance.py`) que exigem Docker real e
são rodados separadamente pelo custo de build+Keycloak por execução. Lógica de produção sem
mocks no núcleo de segurança e orquestração: OPA real (subprocess), Keycloak real (Docker),
LangGraph real com checkpointer SQLite, um LLM real (endpoint OpenAI-compatible), JWKS HTTP real
com JWT RS256 reais, YAML reais de `config/`, SQLite real para o Registry.

## Navegação

| Documento | Para quem |
|---|---|
| [`docs/AS-BUILT.md`](docs/AS-BUILT.md) | Integrar com ou estender a RI — o que existe, como funciona, o que foi validado. |
| [`docs/How-To.md`](docs/How-To.md) | Rodar a RI — instalação, testes, stack local, publicar uma capability, registrar um client. |
| [`docs/interfaces/`](docs/interfaces/) | Contratos exatos por interface (Gateway, identidade, PDP, Registry, downstream identity, auditoria, aprovação, agent runtime). |
| [`docs/Assumptions.md`](docs/Assumptions.md) | Avaliar/adaptar a RI — o que foi assumido e por quê. |
| [`docs/Production-Recommendations.md`](docs/Production-Recommendations.md) | Avaliar/adaptar a RI — o que muda para produção real. |
| [`../docs/adr/`](../docs/adr/) | Decisões arquiteturais individuais (ADR-001 a ADR-025). |

## Quickstart (sem Docker)

```bash
make install         # cria .venv e instala o pacote em modo editável (dev extras inclusos)
make lint             # ruff check + ruff format --check
make typecheck        # mypy --strict
make validate-schemas # valida todo YAML de config/ contra seu modelo Pydantic
make test             # pytest --forked (unit + e2e + contract + adversarial)
```

`make test` precisa do binário `opa` no PATH (ou `OPA_BINARY`) para os testes que exercitam o
PDP real — sem ele, esses testes são pulados (`pytest.skip`), não falham. `docker` no PATH é
necessário pela mesma razão para `tests/e2e/test_real_keycloak.py`. Ver
[`docs/How-To.md`](docs/How-To.md) para o passo a passo completo, incluindo como instalar o OPA
sem Docker e subir os serviços diretamente no host.

## Quickstart (Docker)

```bash
make up      # == docker compose --profile core up --build   (sem IdP)
make down
make logs

# Com Keycloak real:
cp .env.example .env   # descomente as 3 linhas OIDC_*
docker compose --profile core --profile identity up --build
```

Ver [`docs/How-To.md`](docs/How-To.md#subindo-a-stack-local) para os perfis disponíveis
(`core`, `identity`, `observability`) e o que cada um adiciona.

## Estrutura

```text
RI/
├── pyproject.toml
├── Makefile
├── docker-compose.yml          # perfis: core (gateway+sales-domain+finance-domain+opa),
│                                # identity (+keycloak), observability (+otel-collector+jaeger)
├── .env.example
├── deploy/
│   ├── docker/Dockerfile
│   ├── keycloak/realm-export.json   # realm "emcp", 3 clients
│   ├── opa/
│   ├── otel/collector-config.yaml
│   └── langfuse/docker-compose.override.yml   # perfil llm-observability, opt-in
├── scripts/{export_schemas,validate_config}.py
├── schemas/*.schema.json        # gerados por export_schemas.py
├── config/
│   ├── env/{dev,ci}.yaml
│   ├── policies/                          # entitlement.rego, transaction.rego
│   ├── clients/{*.yaml,profiles/*.yaml}   # registrations + client profiles
│   ├── backends/*.yaml                    # endpoint + outbound identity por backend
│   ├── capabilities/{sales,finance}/*.yaml
│   └── orchestrator/identity.yaml
├── src/emcp_bus/
│   ├── common/{config,otel,models,pii_redaction}.py
│   ├── identity/{models,authn,token_verifier,shared_client_lint}.py
│   ├── entitlement/{models,manager}.py
│   ├── registry/{models,store,pipeline,lifecycle,seed}.py
│   ├── pdp/{client,models}.py
│   ├── fabric/{router,adapters/rest_adapter}.py
│   ├── downstream/{models,identity}.py
│   ├── audit/{models,events,sink,correlation,bypass_detection}.py
│   ├── approval/{models,service}.py
│   ├── gateway/{server,cache,canonical_request}.py
│   ├── profile_intelligence/{models,rule_based_provider,governance}.py
│   ├── offering_filter/service.py
│   ├── orchestrator/{decision_context,state,graph,nba_model,decisioning,fallback,hitl_node}.py
│   └── agent_runtime/{dispatcher,identity_resolver,handoff_graph,global_supervisor,channels/*}.py
├── services/example_mcp_servers/
│   ├── sales_domain/server.py    # 6 tools: R1 + R2
│   └── finance_domain/server.py  # invoice.get R1, payment.create R2, payment.execute R3
├── agents/example_agent/
│   ├── agent.py, llm_client.py
│   ├── prompts/{store.py,v1.txt}
│   ├── backends/{sales_agent,finance_agent}/          # Modo A (ADR-024)
│   └── mode_b_orchestrator_driven/{decision_model,orchestrator}.py   # Modo B (ADR-024)
├── docs/
│   ├── AS-BUILT.md
│   ├── How-To.md
│   ├── Assumptions.md
│   ├── Production-Recommendations.md
│   └── interfaces/*.md
└── tests/
    ├── unit/
    ├── e2e/          # walking skeleton, governed gateway, real Keycloak, example agent,
    │                  # security acceptance, multi-agent Modo A, fail-closed
    ├── contract/     # contrato input/output de cada domain server
    └── adversarial/  # prompt/tool injection, protocolo/identidade
```

## Versões fixadas

Ver `pyproject.toml`. Principais: `mcp` 2.2.0, `pydantic` 2.13.x, `opentelemetry-sdk` 1.44.x,
`uvicorn` 0.52.x, `pyjwt[crypto]` 2.14.x, `ruff` 0.16.x, `mypy` 2.3.x, `pytest` 9.1.x,
`pytest-forked` 1.7.x, `langgraph` 0.6.x + `langgraph-checkpoint-sqlite` 2.x, `hypothesis`
6.1xx.x (dev), `openai` 1.109.x, `python-dotenv` 1.2.x (dev), OPA v1.20.2 (binário estático, Rego
v1 padrão), Keycloak 26.7.3, Langfuse self-hosted 4.35.0, `opentelemetry-collector-contrib`
0.114.0, `jaeger` (all-in-one) 1.62.0. Registro completo com procedência de cada versão em
`docs/adr/ADR-018-stack-de-implementacao.md`.
