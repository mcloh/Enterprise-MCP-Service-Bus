# ADR-023: Autorizacao de tools nunca vem de campo declarado no payload

**Status:** Aceito.
**Fonte:** `docs/RI-PLANNING.md` §8.4 (tabela de ADRs), linha ADR-023 — gerado a partir dela por EP-16-T03. Onde a RI tem um componente/teste concreto implementando a decisão, este documento aponta para ele; a tabela em si continua a referência primária e mais atualizada.

## Contexto

Autorização de tools NUNCA vem de um campo declarado no payload/conversa (achado crítico da análise do Hoshikawa, reforça ADR-001/002/003).

## Decisão

O MCP Gateway do Agent Platform OCI autoriza tools por um allowlist estático (`tools.yaml`/`authorization.agents.<agent_id>.allowed_tools`) avaliado sobre `agent_id`, campo que chega como **dado do payload de entrada da conversa**, não como claim de uma identidade autenticada verificada independentemente — a própria SPEC-004 deles admite que isso não substitui autenticação/autorização real. Nossa RI reaproveita a *forma* de proxy desse MCP Gateway (contratos `ToolInvocation`/`ToolResult`, cache por tool idempotente, catálogo `/v1/tools`) **exclusivamente na camada de Fabric (EP-06)/UX conversacional**, mas a decisão ALLOW/DENY continua 100% no nosso PEP (EP-05) consultando o PDP (EP-03) com a identidade autenticada do MCP Client (EP-01) — nunca com `agent_id`/`tenant_id` autodeclarado no payload.

## Alternativas consideradas

Reaproveitar também o bloco `authorization` deles como atalho de implementação.

## Consequências

EP-15-T03 ganha um cenário adversarial explícito de "payload-declared agent_id spoofing" (variação do Teste 4, §45) para provar que esse vetor específico está fechado na nossa RI.
