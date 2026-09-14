# ADR-008: Segmentacao de clients por dominio e risk tier

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão — não é mais gerado a partir de `docs/RI-PLANNING.md` (removido do repositório após a conclusão do marco M4; histórico preservado no git). Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Como segmentar clients.

## Decisão

Por domínio + risk tier (R0–R4), não um client global.

## Alternativas consideradas

Um client "enterprise admin" único.

## Consequências

Define P6 (granularidade) e EP-04.
