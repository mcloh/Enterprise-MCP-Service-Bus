# ADR-012: Entitlement Manager como autoridade unica de MaximumEntitlement

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-012 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Autoridade do cardápio máximo.

## Decisão

Entitlement Manager é a única autoridade de `MaximumEntitlement`; não faz ranking nem confia em atributos autodeclarados do LLM.

## Alternativas consideradas

Fundir Entitlement Manager e Offering Filter num único componente.

## Consequências

Mantém EP-04 e EP-10 como serviços/módulos distintos com contratos próprios.
