# ADR-017: Correlacao ponta a ponta via IDs versionados

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão — não é mais gerado a partir de `docs/RI-PLANNING.md` (removido do repositório após a conclusão do marco M4; histórico preservado no git). Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Correlação ponta a ponta.

## Decisão

`profileVersion`+`entitlementVersion`+`decisionId`+`policyDecisionId`+`mcpRequestId` propagados via OTel/trace context em todos os componentes.

## Alternativas consideradas

Correlação apenas por log textual sem padrão.

## Consequências

EP-08-T03 formaliza os campos; base para EP-15 (auditabilidade).
