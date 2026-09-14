# Production Recommendations — o que muda para um ambiente produtivo real

Síntese do que um deployment de produção real precisaria mudar em relação a esta Reference
Implementation (RI), derivada das limitações reais encontradas e documentadas durante a
implementação (ver [`AS-BUILT.md`](AS-BUILT.md#limitações-e-achados-arquiteturais-reais)
para o detalhe de cada achado). Nada aqui é hipotético: cada item corresponde a uma lacuna real
verificada em teste, não a uma suposição sobre o que "poderia" faltar.

Público-alvo: quem vai **avaliar ou adaptar** esta RI para um cenário real.

## Identity Provider

Um IdP real em alta disponibilidade (cluster Keycloak, ou equivalente gerenciado), não a
instância única do `docker-compose.yml`. A extensão para mTLS/workload identity — cobrindo casos
em que `client_credentials` não é forte o suficiente (ex.: workloads em malha de serviço) — já
está documentada como ponto de extensão em `docs/adr/ADR-019-extensao-de-identidade.md`; produção
implementaria essa extensão, não reinventaria o middleware de autenticação do zero.

## PDP

Distribuição de política via bundle OPA real (um bundle server, não `push_client_profile`
ponto-a-ponto no boot do Gateway) — permite versionamento, rollback e distribuição consistente
para múltiplas réplicas do Gateway. `policy_version` deixaria de ser um hash de arquivos locais
(`pdp/client.py:compute_policy_version`, suficiente para provar que o campo flui ponta a ponta)
e passaria a ser a revisão real do bundle publicado.

## Registry

Um store durável (Postgres) em vez do SQLite atual (`registry/store.py`) — SQLite prova o
contrato/lifecycle corretamente, mas não é a escolha certa para concorrência de escrita entre
múltiplas réplicas do Gateway em produção. Um endpoint administrativo real para
revogação/lifecycle de capability também não existe hoje: as transições de estado
(`registry/lifecycle.py`) são exercitadas via chamada direta aos métodos internos em teste, não
via uma API HTTP protegida que um sistema de governança externo possa chamar.

## Audit

Um sink durável (Postgres, ou uma fila como Kafka/SQS) em vez do JSONL append-only atual
(`audit/sink.py`). Mais importante: um alerta real conectado à falha do sink. O comportamento
atual do Gateway — engolir qualquer exceção de `audit_sink.emit()` (`gateway/server.py:
_emit_audit`) para nunca transformar uma falha de auditoria numa operação de baixo risco em erro
500 — é **correto por design**, não um bug a remover; mas em produção, uma falha silenciosa do
sink que nunca é observada é, na prática, um blackout de auditoria sem alarme. Produção precisa
de observabilidade dedicada sobre o próprio sink (métrica de falha de `emit`, alerta), não de
mudar o comportamento fail-open do Gateway.

## Approval workflow

Um store persistente (não o `dict` em memória de `approval/service.py`, que perde todo o estado
de aprovações pendentes num restart do processo) e uma integração real de
notificação/UI para o aprovador — hoje `grant()`/`deny()` são chamados via CLI/teste, sem
interface real para um humano.

## Rate limiting e anti-replay

Nenhum dos dois existe nesta RI hoje — gaps reais, documentados e cobertos por teste adversarial
dedicado (`tests/adversarial/test_protocol_identity.py`), nunca escondidos. Um Gateway de
produção precisa de ambos: anti-replay (nonce, ou uma janela de deduplicação por
`mcp_request_id`) para fechar o vetor de replay de requisição byte-idêntica com um token ainda
válido; rate limiting para conter exfiltração em massa via chamadas de leitura legítimas
repetidas — hoje mitigado apenas por detectabilidade a posteriori via auditoria, nunca por
prevenção em tempo real.

## Observabilidade

O `otel-collector` + Jaeger do perfil `observability` tem a configuração validada
(`docker compose config`), mas não recebeu tráfego real de um teste automatizado — produção
precisa de um coletor/backend OTLP real de fato recebendo e retendo tráfego, com dashboards e
alertas sobre os `span attributes` de correlação já emitidos (`decision_id`,
`policy_decision_id`, `entitlement_version`). O Langfuse self-hosted (EP-13-T02) é o único
consumidor OTLP desta RI validado com tráfego real, e apenas manualmente — replicar essa
validação como parte de CI é um investimento real, não apenas ligar o profile.

## Segredos

Um gerenciador de segredos real (Vault, um KMS gerenciado, ou equivalente) em vez de variáveis
de ambiente com valores de desenvolvimento (`SALES_DOMAIN_SERVICE_TOKEN`,
`GATEWAY_TOKEN_EXCHANGE_CLIENT_SECRET`, etc., ver `.env.example`) — o *mecanismo* de indireção
(`BackendConfig.service_account_token_env_var` guarda o *nome* da variável, nunca um valor
literal, validado por `field_validator`) já está correto e se mantém: produção troca apenas de
onde a env var é populada, não a forma como o Gateway a consome.

## Escala e alta disponibilidade

O Gateway não mantém estado compartilhado entre requisições — cada `tools/call` abre uma sessão
própria a montante (`gateway/server.py:_with_downstream_session`), sem pool de conexão
persistente nem estado de sessão em memória entre chamadas. Isso é favorável a escalar
horizontalmente (múltiplas réplicas atrás de um load balancer, sem sticky sessions). PDP,
Registry e Approval, por outro lado, cada um precisa de sua própria estratégia de HA em
produção (ver seções acima) — nenhum dos três foi desenhado para múltiplas réplicas na RI.

## Multiagente (ADR-024)

- **Modo A**: o roteador do `GlobalSupervisor` (`agent_runtime/global_supervisor.py`) é um
  stand-in deliberadamente simples baseado em palavra-chave — não é, e nunca pretendeu ser, uma
  reivindicação de qualidade de roteamento. Produção substituiria `RouterFn` por uma
  classificação de intenção real (LLM ou motor de regras), sem qualquer mudança na fronteira de
  segurança (cada backend continua resolvendo seu próprio entitlement de forma independente,
  invariante que não depende da qualidade do roteador).
- **Modo B**: o `ModeBOrchestrator` invoca o journey graph uma vez por client e combina os
  resultados numa camada acima do grafo — não escala nativamente para muitos domínios sem uma
  extensão de `JourneyState`/`build_journey_graph` para múltiplos clients num único run (decisão
  de design documentada no próprio módulo, deliberadamente não tentada nesta RI para não
  arriscar um componente já testado numa demo `could`). A regra de combinação atual ("Finance
  sempre vence Sales") também é uma regra de referência, não um modelo de ranking real — produção
  substituiria `ModeBOrchestrator._combine` por um `NBADecisionModel` cross-domain de verdade.
