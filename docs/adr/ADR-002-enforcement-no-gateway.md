# ADR-002: MCP Gateway como PEP unico

**Status:** Aceito.
**Fonte:** este ADR é o registro canônico desta decisão. Para contexto de implementação e validação, ver `RI/docs/AS-BUILT.md` e, quando aplicável, o contrato relevante em `RI/docs/interfaces/`.

## Contexto

Onde aplicar enforcement.

## Decisão

MCP Gateway é o único PEP; nunca delega decisão ALLOW/DENY ao LLM.

## Alternativas consideradas

Enforcement distribuído em cada MCP Server.

## Consequências

Centraliza EP-05; servidores de domínio (EP-06) não reimplementam authz.
