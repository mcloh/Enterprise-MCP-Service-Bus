# ADR-022: Referencia operacional: Agent Platform OCI (Hoshikawa)

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-022 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Referência concreta de implementação Python/LangGraph/Langfuse (fecha G2 — **decisão confirmada pelo autor em 2026-09-11**).

## Decisão

Adotar como referência operacional o "Agent Platform OCI" de Christiano Hoshikawa (`github.com/hoshikawa2/agent_platform_oci`): StateGraph com router/supervisor por backend + camada superior de roteamento entre backends (nosso EP-11/EP-12); checkpointing plugável (memory/sqlite/mongodb/produção — nós adotamos SQLite em dev, ver ADR-021); taxonomia de observabilidade **IC/NOC/GRL** via Langfuse (evento de negócio/operacional/guardrail), com instrumentação híbrida (span automático por nó + emissão manual fail-open); `identity.yaml`/`BusinessContext` para normalizar identidade de negócio entre canais; FastMCP como padrão de servidor MCP. Análise completa registrada em `docs/research/hoshikawa-agent-platform-oci.md`.

## Alternativas consideradas

Continuar com o padrão genérico da seção 6 do superprompt sem referência concreta de terceiros (mais lento, mais decisões ad hoc); adotar um framework de agentes de mercado (CrewAI, AutoGen) em vez de LangGraph puro.

## Consequências

Muda a forma (não a segurança) de EP-08, EP-11, EP-12, EP-13 — ver ADR-023 para o limite explícito do que NÃO é adotado.
