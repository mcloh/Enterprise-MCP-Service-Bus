# ADR-013: Contrato plugavel de Profile Intelligence

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão — não é mais gerado a partir de `docs/RI-PLANNING.md` (removido do repositório após a conclusão do marco M4; histórico preservado no git). Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Contrato de Profile Intelligence.

## Decisão

Interface genérica e substituível (`ProfileView` versionado, com `reasonCodes`), implementação plugável.

## Alternativas consideradas

Acoplar a um vendor/taxonomia específica de segmentação.

## Consequências

EP-09 define apenas o contrato + stub de referência (ver P7).
