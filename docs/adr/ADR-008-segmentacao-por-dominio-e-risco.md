# ADR-008: Segmentacao de clients por dominio e risk tier

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-008 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Como segmentar clients.

## Decisão

Por domínio + risk tier (R0–R4), não um client global.

## Alternativas consideradas

Um client "enterprise admin" único.

## Consequências

Define P6 (granularidade) e EP-04.
