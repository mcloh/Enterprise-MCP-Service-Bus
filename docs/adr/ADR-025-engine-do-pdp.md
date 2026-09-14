# ADR-025: OPA/Rego como engine do PDP

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão. Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Engine do PDP (fecha G3 — **decisão confirmada pelo autor em 2026-09-11**; renumerado de ADR-010 para ADR-025 em 2026-09-11 para não colidir com o ADR-010 do README, "Global Capability Registry Governance").

## Decisão

OPA/Rego, self-hosted, OSS (Apache-2.0). Decisão definitiva, não sujeita a revisão. **Verificado em 2026-09-11 via busca web**: OPA está em v1.0+, com sintaxe Rego v1 como padrão (breaking change vs. v0) — EP-03 deve escrever policies em sintaxe Rego v1 desde o início.

## Alternativas consideradas

Cedar (AWS, cita-se em §43.2); engine própria em Python.

## Consequências

EP-03 inteiro fica acoplado à API REST do OPA; policies versionadas como código em Rego v1.
