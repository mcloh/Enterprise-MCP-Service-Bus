# ADR-011: Pipeline obrigatorio de publicacao de capabilities

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-011 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Ciclo de publicação de capabilities.

## Decisão

Pipeline obrigatório com gates de schema/risco/policy/health antes de entrar no Registry — sem cadastro manual em produção.

## Alternativas consideradas

Registro direto via API administrativa sem pipeline.

## Consequências

EP-02-T02 implementa o gate; nenhuma capability "nasce" já publicada.
