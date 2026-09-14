# ADR-015: NBA como decisao de orquestracao, nao de autorizacao

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-015 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

NBA é decisão de autorização?

## Decisão

Não — é intenção de orquestração; Gateway/PDP reautorizam toda execução.

## Alternativas consideradas

Orchestrator despachar direto para o backend sem passar pelo Gateway.

## Consequências

EP-11-T04 implementa o branch de DENY/recálculo do §10.1.
