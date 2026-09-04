# Rodada: piloto do Monarch, modo criar + executar

Plano `pilot-monarch-create-run` · produto `simulated-apps` · preparada em 4 set 2026 ·
hash de configuração `df58417a1d17288a` (muda se qualquer arquivo de entrada mudar).
Situação: **configurada, não executada.** Só roda depois que o Carlos confirmar
com a faixa de custo abaixo. Todos os números aqui vêm dos arquivos de
configuração, não foram digitados à mão.

## O que está sendo comparado

O Monarch, produto da TestBox, constrói um workflow a partir de um pedido em
linguagem natural e depois o executa (modo "criar + executar"). É comparado com
cinco modelos de linguagem "crus", que recebem o mesmo pedido e três ferramentas
genéricas sobre as mesmas apps simuladas, e com o gabarito, um competidor
programado que sempre faz a tarefa certa e ancora o pareamento. Ninguém se
avalia: após cada tentativa o bench tira um snapshot dos dados simulados e um
checador separado decide.

Aprovação significa: o resultado esperado está presente, nada mais mudou e o
competidor terminou normalmente.

## Produto sob teste

47 apps de negócio simuladas do AutomationBench (Salesforce, Gmail, HubSpot,
Slack, Jira e outras 42), cada tentativa em uma cópia fresca dos dados. Os
modelos crus as alcançam por um mundo em processo; o Monarch as alcança pelo
front door HTTP do bench, exposto aos servidores do Monarch por um túnel. As 10
tarefas do piloto tocam só Salesforce e Gmail.

## Competidores

| Competidor | Harness | Provedor e id do modelo | Preço, US$ por milhão de tokens (entrada / cache / saída) | Esforço |
|---|---|---|---|---|
| `oracle` (gabarito) | programado | nenhum | 0 | |
| `kimi-k3-fireworks/api` | loop de ferramentas via API | Fireworks, `accounts/fireworks/models/kimi-k3` | 3,00 / 0,30 / 15,00 | xhigh |
| `glm-5.3-fireworks/api` | loop de ferramentas via API | Fireworks, `accounts/fireworks/models/glm-5p3` | 1,40 / 0,26 / 4,40 (tabela da Z.ai; preço da Fireworks a confirmar) | xhigh |
| `claude-opus-5/api` (baseline) | loop de ferramentas via API | Anthropic, `claude-opus-5` | 5,00 / 0,50 / 25,00 | xhigh |
| `gpt-5.6-terra/api` | loop de ferramentas via API | OpenAI Responses, `gpt-5.6-terra` | 2,00 / 0,20 / 12,00 | xhigh |
| `gpt-5.6-sol/api` | loop de ferramentas via API | OpenAI Responses, `gpt-5.6-sol` | 4,00 / 0,40 / 20,00 | xhigh |
| `monarch@e21dc0044+feat/railway-dev-deploy` | Monarch | Monarch no Railway, commit `e21dc0044` do branch `feat/railway-dev-deploy`; sua equipe de modelos pela API da Anthropic (Opus 4.8 no planejamento, Sonnet 5 e Haiku 4.5 nos auxiliares), precificada pela tabela `monarch-team-bedrock` (2026-09-03) | Opus 4.8: 5,00 / 0,50 / 25,00; Sonnet 5: 2,00 / 0,20 / 10,00; Haiku 4.5: 1,00 / 0,10 / 5,00 | |

O loop de ferramentas via API dá a cada modelo três ferramentas: buscar no
catálogo de APIs, chamar uma API, base64. Sem acesso a arquivos nem à máquina.
Kimi K3 e GLM 5.3 são servidos pela Fireworks porque não há chave da Moonshot
nem da Z.ai; as versões são as pedidas, não versões mais antigas.

## Como o Monarch está configurado

- Deploy: projeto Railway `monarch-dev`, de pé só enquanto uma rodada corre
  (`railway-ops.sh unlock` antes, `lock` depois).
- Base de conhecimento: 47 produtos Monarch `bench-<app>`, um por app simulada,
  gerados a partir dos documentos OpenAPI das apps (686 ações, sem credencial),
  importados uma vez; os 47 hashes da base fazem parte do hash de configuração
  desta rodada. Base diferente é rodada diferente.
- Organização: usuário Monarch `bench@testbox.com`, dono de uma organização que
  só enxerga os 47 produtos `bench-*`, para que o Monarch tenha o mesmo catálogo
  dos outros competidores e nada além.
- Front door: o bench serve as apps simuladas na porta 9105, alcançável do
  Railway por `https://imputable-tracklessly-kellan.ngrok-free.dev`.
- Por tentativa: login, envio do pedido como objetivo do workflow, resposta a
  qualquer pergunta com a frase fixa "No further information is available.
  Proceed with your best judgment.", execução ao vivo do workflow, snapshot,
  exclusão do workflow. Uma tentativa do Monarch por vez.
- Custo e fases: lidos dos traces do Monarch no Langfuse (Langfuse Cloud),
  precificados pela tabela do próprio bench; tempo por fase pelos relógios do
  bench.

## Conjunto de tarefas e pedidos

10 tarefas, pasta `tasks/`, congeladas por hash. Todo competidor recebe
exatamente este texto (o Monarch como objetivo do workflow; os modelos como
mensagem do usuário sob um prompt de sistema fixo que manda usar as
ferramentas, não fazer perguntas e ficar em cerca de 50 turnos).

| Tarefa | Pedido |
|---|---|
| `simple.email_sf_contact_city_update` | Lisa Park emailed us about her company's office relocation. Find the email and update her mailing city in Salesforce. |
| `simple.email_sf_contact_department_update` | Amir Hassan emailed to say he transferred departments. Find the email and update his department in Salesforce. |
| `simple.email_sf_contact_email_update` | Maria Santos sent us an email saying she has a new email address. Find her email and update her contact in Salesforce with the new address. |
| `simple.email_sf_contact_mobile_update` | Marcus Rivera emailed with his new direct mobile number. Find the email and update his mobile phone in Salesforce. |
| `simple.email_sf_contact_phone_update` | Jordan Lee just emailed us with a new phone number. Can you find that email and update her phone number in Salesforce? |
| `simple.email_sf_contact_title_update` | Tyler Chen emailed to let us know he got promoted. Find the email and update his title in Salesforce. |
| `simple.sf_opp_amount_update` | Update the amount on opportunity 006003 (DataStream Analytics License) to $45,000 in Salesforce. |
| `simple.sf_opp_closed_won` | Great news - the NexGen Platform Deal (opportunity 006001) just closed! Please mark it as Closed Won in Salesforce. |
| `simple.sf_opp_next_step_update` | Update the next_step field on opportunity 006009 (Orion Fleet Management) to 'Schedule technical demo with engineering team' in Salesforce. |
| `simple.sf_opp_stage_proposal` | Update opportunity 006002 (CloudBridge Migration) to stage 'Proposal/Price Quote' in Salesforce. |

## Tamanho, tempo e dinheiro

| Item | Valor |
|---|---|
| Repetições por tarefa e competidor | 2 |
| Tentativas por competidor | 20 (escala de smoke) |
| Tentativas no total | 140, das quais 120 pagas |
| Timeout por tentativa | 900 s |
| Concorrência | 4 (Monarch serializado em 1) |
| Teto de custo no plano | US$ 40 (a rodada para se atingir) |
| Faixa de custo | modelos cerca de US$ 6 (as mesmas tarefas custaram US$ 3,15 com três modelos em 4 set); Monarch US$ 18 a 30 (um authoring ao vivo custou US$ 0,91) |
| Aprovação | `approved_by` vazio; o Carlos confirma a rodada antes de começar |

## O que o relatório mostra

Por competidor: taxa de aprovação estrita com barras de erro, taxa de
aprovação, taxa de falha de infraestrutura (retentada e excluída do
denominador), taxa de acerto de cache, custo. Comparações pareadas contra o
baseline em conjuntos idênticos de tentativas com o teste de McNemar. Para o
Monarch: tempo e custo por fase (authoring, execução), custo por modelo da
equipe, perguntas feitas e o motivo quando desiste de construir o workflow.
Toda figura carrega sua linha de origem (conjunto de tarefas, contagem,
competidor, id da rodada, versão da tabela de preços, parcela de tentativas
sem custo). Público: interno.

## Limitações conhecidas desta rodada

- `simple.sf_opp_closed_won`: a regra de aprovação não permite `is_closed`,
  `is_won` e `probability`, que os modelos definem como o Salesforce real faria.
  Os três modelos reprovaram nela em 4 set por esse motivo. Corrigir a regra
  exige aprovação do Lucas e muda o hash da tarefa.
- Os documentos OpenAPI das apps simuladas não trazem schemas de request nem de
  response, então a base de conhecimento do Monarch declara ações de update sem
  campos de body. Na primeira tentativa ao vivo o Monarch desistiu de construir
  o workflow por isso. Os seeds estão sendo regenerados com declaração de body
  aberto; a rodada espera por isso.
- 29 das 686 ações, em sete apps, não foram importadas pelo Monarch (colisão de
  ids após normalização); Salesforce e Gmail, as duas apps das tarefas, estão
  completas.
- Os preços do GLM 5.3 são a tabela da Z.ai até confirmar a da Fireworks.

## Como rodar

```
/monarch-benchmark --product simulated-apps --plan pilot-monarch-create-run
```

A skill mostra esta configuração para confirmação, roda os checks do doctor e
só inicia a rodada depois de um "sim" explícito. Depois, `wb grade` e
`wb report`. Próxima rodada depois desta: modo só executar (feature 004), em
que o Monarch executa um workflow conhecido e correto por tarefa e só o motor
é medido.
