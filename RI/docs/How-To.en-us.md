# How-To — Running the RI

Practical, task-oriented guide. To understand *what* each component does and *why*, see
[`AS-BUILT.md`](AS-BUILT.md). Target audience: whoever is going to **run** this RI.

## Prerequisites

- Python 3.12+ and `pip`/`uv`.
- Optional: `opa` binary on the PATH (or `OPA_BINARY` pointing to it) — without it, the tests that
  exercise the real PDP are skipped (`pytest.skip`), not failed.
- Optional: `docker` on the PATH — without it, `tests/e2e/test_real_keycloak.py` and
  `tests/e2e/test_security_acceptance.py` are skipped for the same reason.
- Optional: credentials for an OpenAI-compatible LLM (`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`,
  see `.env.example`) — without them, `tests/e2e/test_example_agent.py` and
  `tests/e2e/test_multi_agent_mode_a.py` are skipped.

## Installation

```bash
make install         # creates .venv and installs the package in editable mode (dev extras included)
```

### Installing OPA (without Docker)

OPA is a static Go binary — it doesn't need Docker or a build step:

```bash
curl -sL -o /tmp/opa "https://openpolicyagent.org/downloads/latest/opa_linux_amd64_static"
chmod +x /tmp/opa
cp /tmp/opa .venv/bin/opa
opa version
```

Reference version used in this RI: OPA v1.20.2 (Rego v1 is the default — `config/policies/*.rego`
uses `import rego.v1`).

## Lint, Typecheck, and Schema Validation

```bash
make lint             # ruff check + ruff format --check
make typecheck        # mypy --strict
make validate-schemas # validates all YAML under config/ against its Pydantic model
make export-schemas   # regenerates schemas/*.schema.json from the models
```

## Running the Tests

```bash
make test             # == pytest --forked
```

`--forked` (pytest-forked) isolates each test function in its own process — necessary because
several in-process ASGI server pairs, sharing a single event loop across many sequential tests
within the same pytest session, produced intermittent async cleanup failures. With `--forked`,
the suite is 100% deterministic across repeated runs. The cost is only execution time (about
+1min on this reference machine). `make test`/CI use `--forked` by default.

Per suite, what each one proves:

- `pytest tests/unit --forked` — isolated behavior of each component (schemas, PDP,
  entitlement, authn, registry, downstream identity, approval, fabric router, audit, canonical
  request, rest adapter, bypass detection, gateway cache, shared client lint, profile
  intelligence, offering filter + property invariants, orchestrator, agent runtime, PII
  redaction, prompt store).
- `pytest tests/e2e --forked` — end-to-end flows against a real in-process Gateway
  (`test_walking_skeleton.py`, `test_governed_gateway.py`), a real Keycloak/Docker
  (`test_real_keycloak.py`), a real LLM (`test_example_agent.py`, `test_multi_agent_mode_a.py`),
  fail policy (`test_fail_closed.py`).
- `pytest tests/contract --forked` — the input/output contract of each tool, connecting directly
  to each domain server (never through the Gateway) — a tool's contract belongs to the domain
  server, regardless of who is or isn't entitled to call it.
- `pytest tests/adversarial --forked` — adversarial prompt/tool injection scenarios
  (`test_prompt_injection.py`, `test_tool_poisoning.py`, `test_payload_identity_spoofing.py`) and
  protocol/identity scenarios (`test_protocol_identity.py`).
- `pytest tests/e2e/test_security_acceptance.py -v` — the formal security acceptance suite,
  against the real `docker-compose.yml` (`--profile core --profile identity`, Keycloak included).
  It **does not** run with `--forked`/`make test` — it requires Docker and pays the
  build+Keycloak cost per run, which is why it's run separately:
  ```bash
  pytest tests/e2e/test_security_acceptance.py -v
  ```

## Bringing Up the Local Stack

### Without Docker

```bash
source .venv/bin/activate
opa run --server --addr 127.0.0.1:8181 config/policies/ &
export SALES_DOMAIN_SERVICE_TOKEN=dev-sales-domain-service-token
export FINANCE_DOMAIN_SERVICE_TOKEN=dev-finance-domain-service-token
python3 -m example_mcp_servers.sales_domain.server &
python3 -m example_mcp_servers.finance_domain.server &
python3 -m emcp_bus.gateway.server
```

Without `OIDC_JWKS_URL`/`OIDC_ISSUER` set, the Gateway runs in "no IdP configured" mode: it
denies everything by default (`tools/list` empty, `tools/call` always `UNAUTHENTICATED`) — see
[`interfaces/mcp-gateway.md`](interfaces/mcp-gateway.md#dois-modos-de-deployment) for the two
modes.

### With Docker Compose

```bash
make up      # == docker compose --profile core up --build          (without IdP)
make down
make logs
```

Available profiles (`docker-compose.yml`):

| Profile | Services | What it adds |
|---|---|---|
| `core` | `opa`, `sales-domain`, `finance-domain`, `gateway` | PEP/PDP + the two example domains — minimal functional setup |
| `identity` | + `keycloak` | real OIDC authentication |
| `observability` | + `otel-collector`, `jaeger` | OTLP tracing (Jaeger UI at `http://localhost:16686`) |

With a real Keycloak:

```bash
cp .env.example .env   # uncomment the 3 OIDC_* lines
docker compose --profile core --profile identity up --build
```

All profiles simultaneously:

```bash
docker compose --profile core --profile identity --profile observability up -d --build
```

## Running the Example Agent and the Multi-Agent Modes

Requires `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` in `.env` (any OpenAI-compatible endpoint;
validated against `meta.llama-3.3-70b-instruct` via OCI Generative AI).

```bash
pytest tests/e2e/test_example_agent.py -v          # single agent, real tool-calling
pytest tests/e2e/test_multi_agent_mode_a.py -v     # Mode A (external Global Supervisor, ADR-024)
pytest tests/e2e/test_real_keycloak.py -k mode_b -v  # Mode B (Orchestrator as sole brain)
```

Mode B requires Docker (it brings up its own real Keycloak).

## Publishing a New Capability

1. Write the YAML manifest at `config/capabilities/<domain>/<capability>.yaml`, following the
   `CapabilityManifest` schema (see [`interfaces/registry-capability-manifest.md`](interfaces/registry-capability-manifest.md)
   for the full schema, and any file under `config/capabilities/*/` as a real example —
   canonical name `<domain>.<capability>`, `risk_tier`, `owner`, `entitlements`, `backend.service`
   pointing to a backend already registered under `config/backends/`).
2. If the capability needs a new backend, register it at `config/backends/<backend>.yaml`
   (see [`interfaces/downstream-identity.md`](interfaces/downstream-identity.md)).
3. Associate the capability with an existing or new `ClientProfile` at
   `config/clients/profiles/<profile>.yaml`, adding the canonical name to `allowed_tools`.
4. Run `make validate-schemas` — it validates the new YAML against its Pydantic model before
   anything else.
5. Run `make export-schemas` if the Pydantic model itself changed (not necessary just to add an
   example YAML to an already-existing schema).
6. Restart the Gateway (or the Docker stack) — the Registry is seeded from
   `config/capabilities/` at boot (`registry/seed.py`); there is no hot-reload in this RI.

## Registering a New MCP Client

1. Register the client in the Keycloak realm (or OIDC equivalent) with the `client_credentials`
   grant enabled and an audience mapper for the Gateway's `OIDC_AUDIENCE` (`emcp-gateway` by
   default) — see `deploy/keycloak/realm-export.json` for the 3 example clients already
   configured this way.
2. Create `config/clients/<client-id>.yaml` (`ClientRegistration`: `client_id`, `profile`,
   `environment`) pointing to an existing or new `ClientProfile` under
   `config/clients/profiles/`.
3. Run `make validate-schemas`.
4. Restart the Gateway — client registrations are also loaded at boot
   (`load_yaml_models(config.clients_dir, ClientRegistration)`).

## Observability

### Jaeger (Tracing)

```bash
docker compose --profile core --profile observability up -d --build
# UI: http://localhost:16686
```

### Self-Hosted Langfuse (LLM Observability)

```bash
docker compose -f docker-compose.yml -f deploy/langfuse/docker-compose.override.yml \
  --profile llm-observability up -d
# Wait for it:
curl http://localhost:3000/api/public/health
# Create a project/API key in the UI (http://localhost:3000) or pre-seed via
# LANGFUSE_INIT_PROJECT_PUBLIC_KEY/LANGFUSE_INIT_PROJECT_SECRET_KEY
# (see deploy/langfuse/docker-compose.override.yml).
```

Then, point the standard OTel SDK variables to Langfuse's native OTLP endpoint (no code changes
needed):

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://langfuse-web:3000/api/public/otel
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64(public_key:secret_key)>"
```

This profile is heavy (6 containers: web/worker/postgres/clickhouse/redis/minio) and opt-in,
decoupled from the `core`/`identity`/`observability` profiles.
