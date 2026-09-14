# ADR-007: Backend nunca exposto diretamente ao client

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão — não é mais gerado a partir de `docs/RI-PLANNING.md` (removido do repositório após a conclusão do marco M4; histórico preservado no git). Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Backend acessível diretamente pelo client?

## Decisão

Não — rede/identidade restringem acesso só ao Gateway/Fabric.

## Alternativas consideradas

Expor Fabric publicamente com authz "best effort".

## Consequências

EP-05-T07, EP-15 (teste de bypass).
