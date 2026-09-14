# ADR-015: NBA como decisao de orquestracao, nao de autorizacao

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão. Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

NBA é decisão de autorização?

## Decisão

Não — é intenção de orquestração; Gateway/PDP reautorizam toda execução.

## Alternativas consideradas

Orchestrator despachar direto para o backend sem passar pelo Gateway.

## Consequências

EP-11-T04 implementa o branch de DENY/recálculo do §10.1.
