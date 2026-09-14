# How-To — rodando a RI

Guia prático orientado a tarefas. Para entender *o que* cada componente faz e *por que*, ver
[`AS-BUILT.md`](AS-BUILT.md). Público-alvo: quem vai **rodar** esta RI.

## Pré-requisitos

- Python 3.12+ e `pip`/`uv`.
- Opcional: binário `opa` no PATH (ou `OPA_BINARY` apontando para ele) — sem ele, os testes que
  exercitam o PDP real são pulados (`pytest.skip`), não falham.
- Opcional: `docker` no PATH — sem ele, `tests/e2e/test_real_keycloak.py` e
  `tests/e2e/test_security_acceptance.py` são pulados pela mesma razão.
- Opcional: credenciais de um LLM OpenAI-compatible (`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`,
  ver `.env.example`) — sem elas, `tests/e2e/test_example_agent.py` e
  `tests/e2e/test_multi_agent_mode_a.py` são pulados.

## Instalação

```bash
make install         # cria .venv e instala o pacote em modo editável (dev extras inclusos)
```

### Instalar o OPA (sem Docker)

OPA é um binário Go estático — não precisa de Docker nem de build:

```bash
curl -sL -o /tmp/opa "https://openpolicyagent.org/downloads/latest/opa_linux_amd64_static"
chmod +x /tmp/opa
cp /tmp/opa .venv/bin/opa
opa version
```

Versão de referência usada nesta RI: OPA v1.20.2 (Rego v1 é o padrão — `config/policies/*.rego`
usa `import rego.v1`).

## Lint, typecheck e validação de schema

```bash
make lint             # ruff check + ruff format --check
make typecheck        # mypy --strict
make validate-schemas # valida todo YAML de config/ contra seu modelo Pydantic
make export-schemas   # regenera schemas/*.schema.json a partir dos modelos
```

## Rodando os testes

```bash
make test             # == pytest --forked
```

`--forked` (pytest-forked) isola cada função de teste em seu próprio processo — necessário
porque vários pares de servidor ASGI em processo, compartilhando um único event loop entre
muitos testes sequenciais na mesma sessão pytest, produziam falhas intermitentes de limpeza
assíncrona. Com `--forked`, a suíte é 100% determinística em execuções repetidas. O custo é só
tempo de execução (cerca de +1min nesta máquina de referência). `make test`/CI usam `--forked`
por padrão.

Por suíte, o que cada uma prova:

- `pytest tests/unit --forked` — comportamento isolado de cada componente (schemas, PDP,
  entitlement, authn, registry, downstream identity, approval, fabric router, audit, canonical
  request, rest adapter, bypass detection, gateway cache, shared client lint, profile
  intelligence, offering filter + invariantes de propriedade, orchestrator, agent runtime, PII
  redaction, prompt store).
- `pytest tests/e2e --forked` — fluxos ponta a ponta contra um Gateway real em processo
  (`test_walking_skeleton.py`, `test_governed_gateway.py`), Keycloak/Docker real
  (`test_real_keycloak.py`), LLM real (`test_example_agent.py`, `test_multi_agent_mode_a.py`),
  política de falha (`test_fail_closed.py`).
- `pytest tests/contract --forked` — o contrato input/output de cada tool, conectando direto a
  cada domain server (nunca pelo Gateway) — o contrato de uma tool é propriedade do domain
  server, independente de quem está ou não entitled a chamá-la.
- `pytest tests/adversarial --forked` — cenários adversariais de prompt/tool injection
  (`test_prompt_injection.py`, `test_tool_poisoning.py`, `test_payload_identity_spoofing.py`) e
  de protocolo/identidade (`test_protocol_identity.py`).
- `pytest tests/e2e/test_security_acceptance.py -v` — a suíte de aceite de segurança formal,
  contra o `docker-compose.yml` real (`--profile core --profile identity`, Keycloak incluído).
  **Não** roda com `--forked`/`make test` — exige Docker e paga o custo de build+Keycloak por
  execução, por isso é rodada separadamente:
  ```bash
  pytest tests/e2e/test_security_acceptance.py -v
  ```

## Subindo a stack local

### Sem Docker

```bash
source .venv/bin/activate
opa run --server --addr 127.0.0.1:8181 config/policies/ &
export SALES_DOMAIN_SERVICE_TOKEN=dev-sales-domain-service-token
export FINANCE_DOMAIN_SERVICE_TOKEN=dev-finance-domain-service-token
python3 -m example_mcp_servers.sales_domain.server &
python3 -m example_mcp_servers.finance_domain.server &
python3 -m emcp_bus.gateway.server
```

Sem `OIDC_JWKS_URL`/`OIDC_ISSUER` definidos, o Gateway roda em modo "sem IdP configurado": nega
tudo por padrão (`tools/list` vazio, `tools/call` sempre `UNAUTHENTICATED`) — ver
[`interfaces/mcp-gateway.md`](interfaces/mcp-gateway.md#dois-modos-de-deployment) para os dois
modos.

### Com Docker Compose

```bash
make up      # == docker compose --profile core up --build          (sem IdP)
make down
make logs
```

Perfis disponíveis (`docker-compose.yml`):

| Perfil | Serviços | O que adiciona |
|---|---|---|
| `core` | `opa`, `sales-domain`, `finance-domain`, `gateway` | PEP/PDP + os dois domínios de exemplo — mínimo funcional |
| `identity` | + `keycloak` | autenticação OIDC real |
| `observability` | + `otel-collector`, `jaeger` | tracing OTLP (UI Jaeger em `http://localhost:16686`) |

Com Keycloak real:

```bash
cp .env.example .env   # descomente as 3 linhas OIDC_*
docker compose --profile core --profile identity up --build
```

Todos os perfis simultaneamente:

```bash
docker compose --profile core --profile identity --profile observability up -d --build
```

## Rodando o agente de exemplo e os modos multiagente

Requer `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` em `.env` (qualquer endpoint OpenAI-compatible;
validado contra `meta.llama-3.3-70b-instruct` via OCI Generative AI).

```bash
pytest tests/e2e/test_example_agent.py -v          # agente único, tool-calling real
pytest tests/e2e/test_multi_agent_mode_a.py -v     # Modo A (Global Supervisor externo, ADR-024)
pytest tests/e2e/test_real_keycloak.py -k mode_b -v  # Modo B (Orchestrator como único cérebro)
```

Modo B exige Docker (sobe seu próprio Keycloak real).

## Publicando uma nova capability

1. Escreva o manifesto YAML em `config/capabilities/<domain>/<capability>.yaml`, seguindo o
   schema `CapabilityManifest` (ver [`interfaces/registry-capability-manifest.md`](interfaces/registry-capability-manifest.md)
   para o schema completo, e qualquer arquivo em `config/capabilities/*/` como exemplo real —
   nome canônico `<domain>.<capability>`, `risk_tier`, `owner`, `entitlements`, `backend.service`
   apontando para um backend já registrado em `config/backends/`).
2. Se a capability precisar de um backend novo, registre-o em `config/backends/<backend>.yaml`
   (ver [`interfaces/downstream-identity.md`](interfaces/downstream-identity.md)).
3. Associe a capability a um `ClientProfile` existente ou novo em
   `config/clients/profiles/<profile>.yaml`, adicionando o nome canônico a `allowed_tools`.
4. Rode `make validate-schemas` — valida o novo YAML contra seu modelo Pydantic antes de
   qualquer coisa.
5. Rode `make export-schemas` se o modelo Pydantic em si mudou (não necessário para apenas
   adicionar um YAML de exemplo a um schema já existente).
6. Reinicie o Gateway (ou a stack Docker) — o Registry é semeado a partir de
   `config/capabilities/` no boot (`registry/seed.py`); não há hot-reload nesta RI.

## Registrando um novo MCP Client

1. Registre o client no realm Keycloak (ou equivalente OIDC) com grant `client_credentials`
   habilitado e um mapper de audience para o `OIDC_AUDIENCE` do Gateway (`emcp-gateway` por
   padrão) — ver `deploy/keycloak/realm-export.json` para os 3 clients de exemplo já
   configurados dessa forma.
2. Crie `config/clients/<client-id>.yaml` (`ClientRegistration`: `client_id`, `profile`,
   `environment`) apontando para um `ClientProfile` existente ou novo em
   `config/clients/profiles/`.
3. Rode `make validate-schemas`.
4. Reinicie o Gateway — registros de client também são carregados no boot
   (`load_yaml_models(config.clients_dir, ClientRegistration)`).

## Observabilidade

### Jaeger (tracing)

```bash
docker compose --profile core --profile observability up -d --build
# UI: http://localhost:16686
```

### Langfuse self-hosted (observabilidade de LLM)

```bash
docker compose -f docker-compose.yml -f deploy/langfuse/docker-compose.override.yml \
  --profile llm-observability up -d
# Aguardar:
curl http://localhost:3000/api/public/health
# Criar um projeto/API key na UI (http://localhost:3000) ou pré-semear via
# LANGFUSE_INIT_PROJECT_PUBLIC_KEY/LANGFUSE_INIT_PROJECT_SECRET_KEY
# (ver deploy/langfuse/docker-compose.override.yml).
```

Depois, aponte as variáveis padrão do OTel SDK para o endpoint OTLP nativo do Langfuse (nenhuma
mudança de código):

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://langfuse-web:3000/api/public/otel
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64(public_key:secret_key)>"
```

Este perfil é pesado (6 containers: web/worker/postgres/clickhouse/redis/minio) e opt-in,
desacoplado dos perfis `core`/`identity`/`observability`.
