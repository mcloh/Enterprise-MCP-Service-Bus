# ADR-017: Correlacao ponta a ponta via IDs versionados

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-017 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Correlação ponta a ponta.

## Decisão

`profileVersion`+`entitlementVersion`+`decisionId`+`policyDecisionId`+`mcpRequestId` propagados via OTel/trace context em todos os componentes.

## Alternativas consideradas

Correlação apenas por log textual sem padrão.

## Consequências

EP-08-T03 formaliza os campos; base para EP-15 (auditabilidade).
