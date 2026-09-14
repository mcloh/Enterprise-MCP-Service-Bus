# ADR-002: MCP Gateway como PEP unico

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-002 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Onde aplicar enforcement.

## Decisão

MCP Gateway é o único PEP; nunca delega decisão ALLOW/DENY ao LLM.

## Alternativas consideradas

Enforcement distribuído em cada MCP Server.

## Consequências

Centraliza EP-05; servidores de domínio (EP-06) não reimplementam authz.
