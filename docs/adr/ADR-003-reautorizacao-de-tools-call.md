# ADR-003: Reautorizacao independente em tools/call

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão. Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

`tools/list` filtrado é suficiente?

## Decisão

Não — `tools/call` deve ser reautorizado independentemente do discovery.

## Alternativas consideradas

Confiar apenas em filtered discovery.

## Consequências

EP-05 implementa dois pontos de enforcement, não um.
