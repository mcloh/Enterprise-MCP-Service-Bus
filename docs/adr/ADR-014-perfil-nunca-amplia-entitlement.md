# ADR-014: Perfil nunca amplia entitlement

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão. Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Perfil pode ampliar entitlement?

## Decisão

Nunca — `FilteredOfferings ⊆ MaximumEntitlement`, perfil só ordena/reduz.

## Alternativas consideradas

Perfil de alto engajamento desbloqueando novas tools.

## Consequências

EP-10-T02 traz teste de propriedade validando a invariante para entradas aleatórias.
