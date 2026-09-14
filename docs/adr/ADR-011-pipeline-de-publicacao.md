# ADR-011: Pipeline obrigatorio de publicacao de capabilities

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão. Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Ciclo de publicação de capabilities.

## Decisão

Pipeline obrigatório com gates de schema/risco/policy/health antes de entrar no Registry — sem cadastro manual em produção.

## Alternativas consideradas

Registro direto via API administrativa sem pipeline.

## Consequências

EP-02-T02 implementa o gate; nenhuma capability "nasce" já publicada.
