# Round: Monarch pilot, create + run mode

Plan `pilot-monarch-create-run` · product `simulated-apps` · prepared 4 Sep 2026 ·
configuration hash `df58417a1d17288a` (changes if any input file changes).
Status: **configured, not run.** It runs only after Carlos confirms it with the
cost band below. Every number here is read from the configuration files, not
typed by hand.

## What is being compared

Monarch, TestBox's product, builds a workflow from a plain-language request and
then executes it (mode "create + run"). It is compared with five raw language
models given the same request and three generic tools over the same simulated
apps, and with the answer key, a scripted competitor that always does the task
right and anchors the pairing. Nothing grades itself: after every attempt the
bench takes a snapshot of the simulated data and a separate checker decides.

Pass means: the expected result is present, nothing else changed, and the
competitor finished normally.

## Product under test

47 simulated business apps from AutomationBench (Salesforce, Gmail, HubSpot,
Slack, Jira, and 42 others), each attempt on a fresh copy of the data. The raw
models reach them through an in-process world; Monarch reaches them through the
bench's HTTP front door, exposed to Monarch's servers through a tunnel. The
10 pilot tasks touch Salesforce and Gmail only.

## Competitors

| Competitor | Harness | Provider and model id | Price, US$ per million tokens (input / cached / output) | Effort |
|---|---|---|---|---|
| `oracle` (answer key) | scripted | none | 0 | |
| `kimi-k3-fireworks/api` | API tool loop | Fireworks, `accounts/fireworks/models/kimi-k3` | 3.00 / 0.30 / 15.00 | xhigh |
| `glm-5.3-fireworks/api` | API tool loop | Fireworks, `accounts/fireworks/models/glm-5p3` | 1.40 / 0.26 / 4.40 (Z.ai list rates; Fireworks rate to confirm) | xhigh |
| `claude-opus-5/api` (baseline) | API tool loop | Anthropic, `claude-opus-5` | 5.00 / 0.50 / 25.00 | xhigh |
| `gpt-5.6-terra/api` | API tool loop | OpenAI Responses, `gpt-5.6-terra` | 2.00 / 0.20 / 12.00 | xhigh |
| `gpt-5.6-sol/api` | API tool loop | OpenAI Responses, `gpt-5.6-sol` | 4.00 / 0.40 / 20.00 | xhigh |
| `monarch@e21dc0044+feat/railway-dev-deploy` | Monarch | Monarch on Railway, commit `e21dc0044` of branch `feat/railway-dev-deploy`; its model team through the Anthropic API (Opus 4.8 for planning, Sonnet 5 and Haiku 4.5 for helpers), priced by the table `monarch-team-bedrock` (2026-09-03) | Opus 4.8: 5.00 / 0.50 / 25.00; Sonnet 5: 2.00 / 0.20 / 10.00; Haiku 4.5: 1.00 / 0.10 / 5.00 | |

The API tool loop gives each model three tools: search the API catalogue, call
an API, base64. No file or machine access. Kimi K3 and GLM 5.3 are served by
Fireworks because no Moonshot or Z.ai key is available; the model versions are
the ones requested, not older ones.

## How Monarch is set up

- Deployment: Railway project `monarch-dev`, kept up only while a round runs
  (`railway-ops.sh unlock` before, `lock` after).
- Knowledge base: 47 Monarch products `bench-<app>`, one per simulated app,
  generated from the apps' OpenAPI documents (686 actions, no credential),
  imported once; the 47 knowledge-base hashes are part of this round's
  configuration hash. A different knowledge base is a different round.
- Organisation: Monarch user `bench@testbox.com`, owner of an organisation that
  can see only the 47 `bench-*` products, so Monarch has the same catalogue as
  the other competitors and nothing else.
- Front door: the bench serves the simulated apps on port 9105, reachable from
  Railway through `https://imputable-tracklessly-kellan.ngrok-free.dev`.
- Per attempt: log in, send the request as the workflow goal, answer any
  question with the fixed sentence "No further information is available.
  Proceed with your best judgment.", run the workflow live, take the snapshot,
  delete the workflow. One Monarch attempt at a time.
- Cost and phases: read from Monarch's Langfuse traces (Langfuse Cloud), priced
  by the bench's own table; wall-clock per phase from the bench's clocks.

## Task set and requests

10 tasks, folder `tasks/`, frozen by hash. Every competitor receives exactly
this text (Monarch as the workflow goal, the models as the user message under a
fixed system prompt that says to use the tools, not to ask clarifying questions,
and to stay within about 50 tool turns).

| Task | Request |
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

## Size, time and money

| Item | Value |
|---|---|
| Prompts (tasks) | 10 |
| Attempts per prompt, for each competitor | 2 (the same prompt is tried twice, on a fresh copy of the data each time) |
| Attempts per competitor | 20 = 10 prompts × 2 attempts (smoke scale) |
| Attempts in total | 140 = 7 competitors × 20, of which 120 paid |
| Timeout per attempt | 900 s |
| Concurrency | 4 (Monarch serialised to 1) |
| Cost ceiling in the plan | US$ 40 (the run stops if reached) |
| Cost band | models about US$ 6 (the same tasks cost US$ 3.15 for three models on 4 Sep); Monarch US$ 18 to 30 (one live authoring cost US$ 0.91) |
| Approval | `approved_by` is empty; Carlos confirms the round before it starts |

## What the report shows

Per competitor: strict pass rate with error bars, pass rate, infrastructure
failure rate (retried, excluded from the denominator), cache hit rate, cost.
Paired comparisons against the baseline on identical attempt sets with
McNemar's test. For Monarch: wall-clock and cost per phase (authoring,
execution), cost per model of its team, questions asked, and the reason when
it declines to build a workflow. Every figure carries its source line (task
set, count, competitor, run id, price-table version, share of attempts with
missing cost). Audience: internal.

## Known limitations of this round

- `simple.sf_opp_closed_won`: the approval rule does not allow `is_closed`,
  `is_won` and `probability`, which the models set as real Salesforce would.
  All three models failed it on 4 Sep for that reason. Fixing the rule needs
  Lucas's sign-off and changes the task hash.
- The simulated apps' OpenAPI documents carry no request or response schemas,
  so Monarch's knowledge base declares update actions without body fields. In
  the first live attempt Monarch declined to build the workflow for that
  reason. The seeds are being regenerated with an open body declaration; the
  round waits for that.
- 29 of 686 actions in seven apps were not imported by Monarch (id collisions
  after normalisation); Salesforce and Gmail, the two apps the tasks use, are
  complete.
- GLM 5.3 prices are Z.ai's list rates until the Fireworks rate is confirmed.

## How to run it

```
/monarch-benchmark --product simulated-apps --plan pilot-monarch-create-run
```

The skill shows this configuration for confirmation, runs the doctor checks,
and starts the round only after an explicit yes. Then `wb grade` and
`wb report`. Next round after this one: run-only mode (feature 004), where
Monarch executes a known-correct workflow per task and only its engine is
measured.
