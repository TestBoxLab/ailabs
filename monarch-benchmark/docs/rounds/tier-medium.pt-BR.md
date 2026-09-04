# Rodada: Nível médio (`tier-medium`)

Plano `config/plans/tier-medium.yaml` · produto `simulated-apps` · feature 005 ·
preparada em 4 set 2026. Situação: **plano e mecanismo de sorteio prontos;
conjunto de tarefas ainda não sorteado.** Esta rodada não pode rodar até os três
bloqueios abaixo serem resolvidos. Todos os números vêm do arquivo do plano; a
lista de tarefas virá do sorteio congelado.

## O que é esta rodada

A mesma comparação do piloto criar + executar (o Monarch constrói e executa cada
workflow ao lado de cinco modelos crus e do gabarito), sobre **os dez prompts cuja pontuação cai no terço do meio**. Os
quatro conjuntos (simples, médio, complexo, aleatório) rodam como rodadas
separadas contra os mesmos competidores; o relatório por conjunto responde se a
diferença entre o Monarch e os modelos muda com a dificuldade, e o conjunto
aleatório confere a média combinada.

## Como o conjunto de tarefas é escolhido

- Corpus: o domínio `simple` do AutomationBench (200 tarefas) mais os seis
  domínios pontuados (finance, hr, marketing, operations, sales, support; 600
  tarefas), importados com `wb corpus import-ab --domains all` e com regras de
  aprovação derivadas por `wb corpus declare`.
- Pontuação de dificuldade, calculada só do arquivo da tarefa: número de
  serviços que a tarefa usa + número de mudanças esperadas + número de
  ferramentas necessárias. Os níveis são os tercis do corpus utilizável (hoje 9 e
  12); tarefa exatamente no corte cai no nível de baixo.
- Sorteio: `wb corpus tiers --seed <N>` escolhe dez por nível, estratificado
  entre os sete domínios (rodízio), e mais dez ao acaso do corpus utilizável
  excluindo os trinta dos níveis. Mesma semente, mesmos conjuntos, byte a byte.
  Cada tarefa sorteada é cópia exata da original mais dois rótulos (`tier`,
  `domain`) que não entram no hash da tarefa. O manifesto
  `tasks/tiers-manifest.yaml` registra a medida, os cortes, a semente e, para
  cada tarefa, pontuação, nível, domínio e hash.
- Tarefa sem regra de aprovação, ou com hash diferente do conteúdo, sai do pool
  antes do sorteio.

## Competidores (idênticos nas quatro rodadas)

| Competidor | Harness | Provedor e id do modelo | Preço, US$ por milhão de tokens (entrada / cache / saída) |
|---|---|---|---|
| `oracle` (gabarito) | programado | nenhum | 0 |
| `kimi-k3-fireworks/api` | loop de ferramentas via API | Fireworks, `accounts/fireworks/models/kimi-k3` | 3.00 / 0.30 / 15.00 |
| `glm-5.3-fireworks/api` | loop de ferramentas via API | Fireworks, `accounts/fireworks/models/glm-5p3` | 1.40 / 0.26 / 4.40 (tabela da Z.ai; preço da Fireworks a confirmar) |
| `claude-opus-5/api` (baseline) | loop de ferramentas via API | Anthropic, `claude-opus-5` | 5.00 / 0.50 / 25.00 |
| `gpt-5.6-terra/api` | loop de ferramentas via API | OpenAI Responses, `gpt-5.6-terra` | 2.00 / 0.20 / 12.00 |
| `gpt-5.6-sol/api` | loop de ferramentas via API | OpenAI Responses, `gpt-5.6-sol` | 4.00 / 0.40 / 20.00 |
| `monarch@<version>` | Monarch | Monarch no Railway, equipe de modelos pela API da Anthropic, precificada por `monarch-team-bedrock` | Opus 4.8 5.00 / 0.50 / 25.00; Sonnet 5 2.00 / 0.20 / 10.00; Haiku 4.5 1.00 / 0.10 / 5.00 |

## Tamanho, tempo e dinheiro (por rodada)

| Item | Valor |
|---|---|
| Prompts (tarefas) | 10 |
| Tentativas por prompt, para cada competidor | 2 |
| Tentativas por competidor | 20 = 10 prompts × 2 tentativas |
| Tentativas no total | 140 = 7 competidores × 20, das quais 120 pagas |
| Timeout por tentativa | 900 s |
| Teto de custo no plano | US$ 40 |
| Faixa de custo | modelos cerca de US$ 5 a 7; Monarch US$ 18 a 30 em tarefas simples, provavelmente mais nas complexas (authoring mais longo); total US$ 25 a 45 |
| Aprovação | `approved_by` vazio; o Carlos aprova cada rodada separadamente |

## Bloqueios antes do sorteio

1. Confirmar a medida de dificuldade com o Lucas. Medido em 4 set: o terço mais
   baixo é quase todo do domínio `simple` e o mais alto quase todo dos domínios
   pontuados, então nível e domínio se sobrepõem; uma variável limpa de
   dificuldade exigiria que o nível simples também sorteasse da ponta fácil dos
   domínios pontuados (outra regra de corte, mesma medida).
2. Estender a derivação de regras de aprovação aos tipos de asserção dos domínios
   pontuados: todas as 600 tarefas têm ao menos um tipo não mapeado e 218 não
   geram regra nenhuma (tipos mais comuns: envios de Gmail, "não existe" em Slack
   e Sheets). Sem isso o pool fica enviesado e as regras, parciais.
3. Os patches do Lucas no AutomationBench, que podem mudar tarefas dos domínios
   pontuados; aplicados depois do sorteio, forçam novo sorteio.

## Conjunto de tarefas e pedidos

Ainda não sorteado. Quando o sorteio estiver congelado, esta seção lista os dez
ids e o texto dos pedidos, e a rodada pode ser aprovada.
