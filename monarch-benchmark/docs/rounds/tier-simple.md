# Round: Simple tier (`tier-simple`)

Plan `config/plans/tier-simple.yaml` · product `simulated-apps` · feature 005 ·
prepared 4 Sep 2026. Status: **plan and draw machinery ready; task set not
drawn yet.** This round cannot run until the three blockers below are cleared.
Every number here comes from the plan file; the task list will come from the
frozen draw.

## What this round is

The same comparison as the create + run pilot (Monarch builds and runs each
workflow beside five raw models and the answer key), on **the ten prompts whose difficulty score falls in the lowest third of the corpus**. The four
sets (simple, medium, complex, random-10) are run as separate rounds against
the same competitors; the report per set answers whether the gap between
Monarch and the models changes with difficulty, and the random set checks the
blended average.

## How the task set is chosen

- Corpus: the AutomationBench `simple` domain (200 tasks) plus the six scored
  domains (finance, hr, marketing, operations, sales, support; 600 tasks),
  imported with `wb corpus import-ab --domains all` and given approval rules by
  `wb corpus declare`.
- Difficulty score, computed from the task file alone: number of services the
  task seeds + number of expected changes + number of tools it needs. Tiers are
  the terciles of the whole usable corpus (today 9 and 12); a task on a cut
  point falls in the lower tier.
- Draw: `wb corpus tiers --seed <N>` picks ten per tier, stratified across the
  seven domains (round-robin), and ten more at random from the usable corpus
  except the thirty tier tasks. Same seed, same sets, byte for byte. Each drawn
  task is an exact copy of its corpus original plus two labels (`tier`,
  `domain`) that do not enter the task hash. The manifest
  `tasks/tiers-manifest.yaml` records the measure, the cut points, the seed and
  every drawn task's score, tier, domain and hash.
- A task with no approval rule, or whose hash does not match its content, is
  excluded from the pool before the draw.

## Competitors (identical in all four rounds)

| Competitor | Harness | Provider and model id | Price, US$ per million tokens (input / cached / output) |
|---|---|---|---|
| `oracle` (answer key) | scripted | none | 0 |
| `kimi-k3-fireworks/api` | API tool loop | Fireworks, `accounts/fireworks/models/kimi-k3` | 3.00 / 0.30 / 15.00 |
| `glm-5.3-fireworks/api` | API tool loop | Fireworks, `accounts/fireworks/models/glm-5p3` | 1.40 / 0.26 / 4.40 (Z.ai list rates; Fireworks rate to confirm) |
| `claude-opus-5/api` (baseline) | API tool loop | Anthropic, `claude-opus-5` | 5.00 / 0.50 / 25.00 |
| `gpt-5.6-terra/api` | API tool loop | OpenAI Responses, `gpt-5.6-terra` | 2.00 / 0.20 / 12.00 |
| `gpt-5.6-sol/api` | API tool loop | OpenAI Responses, `gpt-5.6-sol` | 4.00 / 0.40 / 20.00 |
| `monarch@<version>` | Monarch | Monarch on Railway, model team through the Anthropic API, priced by `monarch-team-bedrock` | Opus 4.8 5.00 / 0.50 / 25.00; Sonnet 5 2.00 / 0.20 / 10.00; Haiku 4.5 1.00 / 0.10 / 5.00 |

## Size, time and money (per round)

| Item | Value |
|---|---|
| Prompts (tasks) | 10 |
| Attempts per prompt, for each competitor | 2 |
| Attempts per competitor | 20 = 10 prompts × 2 attempts |
| Attempts in total | 140 = 7 competitors × 20, of which 120 paid |
| Timeout per attempt | 900 s |
| Cost ceiling in the plan | US$ 40 |
| Cost band | models about US$ 5 to 7; Monarch US$ 18 to 30 on simple tasks, likely more on complex ones (longer authoring); total US$ 25 to 45 |
| Approval | `approved_by` empty; Carlos approves each round separately |

## Blockers before the draw

1. Confirm the difficulty measure with Lucas. Measured on 4 Sep: the lowest
   tercile is almost entirely `simple`-domain tasks and the top tercile almost
   entirely scored-domain tasks, so tier and domain overlap; a clean difficulty
   variable would need the simple tier to draw from the scored domains' easy
   end too (a different cut rule, same measure).
2. Extend the approval-rule derivation to the scored domains' assertion types:
   every one of the 600 scored tasks has at least one type the derivation does
   not map, and 218 derive no rule at all (top types: Gmail send assertions,
   Slack and Sheets "not exists"). Without it the pool is skewed and the rules
   partial.
3. Lucas's AutomationBench patches, which may change scored-domain tasks;
   applied after a draw they force a redraw.

## Task set and requests

Not drawn yet. Once the draw is frozen, this section lists the ten task ids
and their request texts, and the round can be approved.
