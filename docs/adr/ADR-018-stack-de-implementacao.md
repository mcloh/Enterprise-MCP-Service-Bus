# ADR-018: Stack de implementacao da RI

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-018 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Stack de implementação da RI (fecha G2).

## Decisão

Python 3.12+, `uv`, Pydantic v2, YAML declarativo com JSON Schema, SDK oficial `mcp`.

## Alternativas consideradas

Node/TypeScript (SDK MCP também oficial); Go.

## Consequências

Define toda a estrutura de repositório (8.5).

## Versões confirmadas (EP-16-T04)

Spike sem dependências, executável a qualquer momento (`docs/RI-PLANNING.md`
EP-16-T04): confirmar, imediatamente antes de fixar em `pyproject.toml`/
`docker-compose.yml`, os números exatos de versão estável de cada peça da
stack — nenhuma versão citada em código/config sem confirmação real
(`pip index versions`/download direto/instalação real), nunca de memória.
Registro consolidado, com a data em que cada grupo foi verificado (ver
`RI/README.md`, "Versões fixadas", para a mesma lista mantida junto ao
`pyproject.toml`):

Confirmadas em 2026-09-11:

- `mcp` 2.2.0 (SDK Python v2 — API mudou significativamente da v1; ver
  comentários em `src/emcp_bus/gateway/server.py`)
- `pydantic` 2.13.x, `opentelemetry-sdk` 1.44.x, `uvicorn` 0.52.x,
  `pyjwt[crypto]` 2.14.x, `ruff` 0.16.x, `mypy` 2.3.x, `pytest` 9.1.x
- `OPA` 1.20.2 (binário estático, sintaxe Rego v1 como padrão)
- `pytest-forked` 1.7.x

Confirmadas em 2026-09-14 (M3/M4, via instalação/`docker pull` reais):

- `langgraph` 0.6.x + `langgraph-checkpoint-sqlite` 2.x (EP-11)
- `hypothesis` 6.1xx.x (dev, EP-10-T02)
- `openai` 1.109.x (EP-13-T01)
- `python-dotenv` 1.2.x (dev)
- `types-jsonschema` 4.26.x (dev, stubs para `mypy --strict`; `jsonschema`
  em si já era dependência transitiva de `mcp[cli]`, EP-15-T01)
- Langfuse self-hosted 4.35.0 (`docker.langfuse.com/langfuse/langfuse:4`,
  imagem oficial, EP-13-T02)
- Keycloak 26.7.3 (`quay.io/keycloak/keycloak:26.7.3`, Quarkus; Standard
  Token Exchange GA desde 26.2 — EP-01-T01/EP-07)
- `opentelemetry-collector-contrib` 0.114.0 e `jaeger` (all-in-one) 1.62.0
  (perfil `observability` do `docker-compose.yml`, EP-08-T04)

Nenhuma versão acima foi alterada desde a confirmação original — este
registro é o ponto único de verdade que `RI/README.md` linka de volta para
cá.
