# ADR-012: Entitlement Manager como autoridade unica de MaximumEntitlement

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão — não é mais gerado a partir de `docs/RI-PLANNING.md` (removido do repositório após a conclusão do marco M4; histórico preservado no git). Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Autoridade do cardápio máximo.

## Decisão

Entitlement Manager é a única autoridade de `MaximumEntitlement`; não faz ranking nem confia em atributos autodeclarados do LLM.

## Alternativas consideradas

Fundir Entitlement Manager e Offering Filter num único componente.

## Consequências

Mantém EP-04 e EP-10 como serviços/módulos distintos com contratos próprios.
