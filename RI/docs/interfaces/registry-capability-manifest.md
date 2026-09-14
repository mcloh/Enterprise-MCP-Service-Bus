# Interface: manifesto de capability e ciclo de vida do Registry

Schema do manifesto de capability e o pipeline de publicação, para quem vai publicar uma nova
capability no Global Capability Registry. Implementação:
[`src/emcp_bus/registry/models.py`](../../src/emcp_bus/registry/models.py),
[`registry/pipeline.py`](../../src/emcp_bus/registry/pipeline.py),
[`registry/lifecycle.py`](../../src/emcp_bus/registry/lifecycle.py),
[`registry/store.py`](../../src/emcp_bus/registry/store.py). Ver
[`AS-BUILT.md`](../AS-BUILT.md#global-capability-registry-ep-02).

## Schema do manifesto (`CapabilityManifest`)

```yaml
# config/capabilities/finance/payment-execute.yaml
name: finance.payment.execute      # <domínio>.<capability>, validado (domain deve prefixar name)
version: 1.0.0                     # SemVer
domain: finance
owner: finance-platform
risk_tier: R3                      # R0-R4
side_effects: true
idempotent: false
data_classification: [confidential, restricted]   # public | internal | confidential | restricted
entitlements: [Finance.Payments]   # nomes de ClientProfile que podem ver/chamar esta capability
backend:
  type: mcp                        # mcp | rest | grpc (só "mcp" tem dispatch ao vivo nesta RI)
  service: finance-domain          # id resolvido por config/backends/<service>.yaml
approval:
  required: true                   # obrigatório se risk_tier em {R3, R4} — gate do pipeline
```

(exemplo real: `config/capabilities/finance/payment-execute.yaml`)

Campos com default: `observability.audit_level` (`"full"`), `lifecycle.status`
(`"nominate"` — nunca se declara `active` diretamente num manifesto novo).

## Ciclo de vida (`LifecycleStatus`)

```
NOMINATE → REVIEW → REGISTER → ACTIVE ⇄ ACTIVE → DEPRECATED → RETIRED
              ↑________________|
           (review rejeitado volta a NOMINATE)
```

Só uma capability `ACTIVE` é resolvível pelo Fabric (`CapabilityRouter`) — qualquer outro status
é um assunto exclusivo do control plane. Nada alcança `ACTIVE` sem passar por `REVIEW`
(`registry/lifecycle.py:validate_transition`, verificado mecanicamente).

## Pipeline de publicação

```python
pipeline = PublishingPipeline(store)
registered = pipeline.submit(manifest)  # roda os gates -> NOMINATE -> REVIEW -> REGISTER
pipeline.publish(registered.name)  # REGISTER -> ACTIVE
```

`submit()` roda gates de negócio antes de qualquer transição de estado (schema/naming já é
responsabilidade do próprio `CapabilityManifest` na construção):

| Gate | Regra |
|---|---|
| Owner | `owner` não pode ser vazio. |
| Backend | `backend.service` não pode ser vazio. |
| Aprovação por risco | `risk_tier` em `{R3, R4}` exige `approval.required: true`. |

Qualquer gate reprovado levanta `PublishingRejectedError(reasons)` — nada entra parcialmente no
Registry (fail-closed, sem cadastro manual ad hoc).

## Como o Fabric resolve uma capability

`CapabilityRouter.route(tool)` busca o manifesto `ACTIVE` de `tool`, resolve
`backend.service` para uma URL+credencial via `BackendCredentialProvider` (ver
[`downstream-identity.md`](downstream-identity.md)), e retorna um `BackendRoute`. Sem manifesto
`ACTIVE` correspondente, ou backend não resolvível: `UnroutableCapabilityError` — o Gateway trata
isso como `UNROUTABLE_CAPABILITY` (DENY).

## Erros

| Situação | Exceção |
|---|---|
| `name` sem `.` (não é `<domínio>.<capability>`) | `pydantic.ValidationError` na construção do manifesto. |
| `domain` não é o prefixo de `name` | `pydantic.ValidationError` na construção do manifesto. |
| Gate de negócio reprovado em `submit()` | `PublishingRejectedError` |
| Transição de lifecycle inválida (ex.: `NOMINATE` → `ACTIVE` direto) | `InvalidLifecycleTransitionError` |
| `tool` sem manifesto `ACTIVE`, ou backend inexistente | `UnroutableCapabilityError` |

## Não implementado nesta RI

Um endpoint HTTP administrativo para publicar/revogar via API (hoje `PublishingPipeline` e as
transições de lifecycle são chamadas Python diretas, exercitadas em teste, não expostas via
rede) — ver `../Production-Recommendations.md`. Health check de `backend.service` como gate
de publicação também não existe (seria um `TODO` disfarçado sem um registro real de endpoints de
saúde de backend nesta RI).
