# ADR-013: Contrato plugavel de Profile Intelligence

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-013 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Contrato de Profile Intelligence.

## Decisão

Interface genérica e substituível (`ProfileView` versionado, com `reasonCodes`), implementação plugável.

## Alternativas consideradas

Acoplar a um vendor/taxonomia específica de segmentação.

## Consequências

EP-09 define apenas o contrato + stub de referência (ver P7).
