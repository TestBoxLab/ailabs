# State of the program

Where the Monarch benchmark stands, what is blocked, what is next. Replaces the
handoffs of 2, 3 and 8 September 2026.

Last updated **10 September 2026**. Read `HOW-WORKFLOWBENCH-WORKS.md` for the
machine, `PLAN.md` for the tracking surface, and
`../../docs/AI-LABS-UNBLOCK-PLAN-2026-09-08.md` for the milestone plan this note
summarises. Where the two disagree, the unblock plan is the authority on
milestones and the refreeze record on task hashes.

## 1. The one-paragraph version

The bench works offline and its machinery is done: declarative configuration,
frozen task sets, a Monarch competitor, HTML reports, a budget ledger and an
approval flow. Four paid rounds ran on 5 and 6 September, and **none of them
measured what it claimed to** — the approval rules they graded against were
broken. Those rules were re-derived on 9 and 10 September, which moved 23 task
hashes and made every stored attempt on them non-regradable. The next real
measurement is the 50-task gauntlet, gated on the milestones of the unblock
plan. Monarch now runs on Opus 5 through the Anthropic API on Railway, not
Bedrock.

## 2. Rounds that have run, and what each is worth

| Run | Plan | Date | Monarch | Best model | Worth |
|---|---|---|---|---|---|
| `smoke-frontier-001` | smoke-frontier | 2 Sep 2026 | not a competitor yet | Opus 90%, GPT-5.6 Sol 100% | machine check only, US$ 1.93 |
| `run-20260903-000243` | smoke-frontier | 3 Sep 2026 | not a competitor yet | Opus 18/20, GPT 20/20 | reproduces the above from config files, US$ 2.12 |
| `railway-round-001` | railway-round-001 | 4 Sep 2026 | not a competitor | three raw models, 80 attempts | US$ 3.15; report `out/report-run-20260904-125645-internal.md` |
| `run-20260905-022823` | tier-simple | 5 Sep 2026 | 0/20 | 50% | void: 7 attempts never ran (the bench sent no acknowledgement or inputs) |
| `run-20260905-154934` | tier-simple rerun | 5 Sep 2026 | 2/20 | GPT-5.6 Sol 60% first try | posted to Slack as "Easy"; fair for the models, not for Monarch |
| `run-20260905-204158` | tier-medium | 5 Sep 2026 | 1/19 | 20% | posted as "Average"; same caveat |
| `run-20260906-002313` | tier-complex | 6 Sep 2026 | 0/14 | 0% for everyone | void: the approval rule rejected the changes it had asked for. Held, never posted |
| `run-20260908-190209` | pilot-monarch-single | 8 Sep 2026 | 1 attempt, checker fail | — | the first clean single measurement; see below |
| `monarch-pilot-001` | Studio job | 8 Sep 2026 | 1 attempt, 409 actions | — | US$ 1.52 settled; task check failed on quality, not wiring |

Spend since 4 September 2026: **US$ 276**, of which Monarch US$ 170.

**Why the 5 and 6 September rounds are void.** Six defects in the derived
approval rules were found on 9 September. Four of them made a rule name a path
the simulated world can never produce, so a correct answer could not pass. The
Hard round scored 0% for every competitor on every task; re-grading the one
task whose hash still matched turned **0 of 11 into 9 of 11**. That round
measured a broken grader, not competence. Full record, with before/after hashes:
`rounds/2026-09-10-refreeze-derived-rules.md`.

**The 8 September single-task pilot** (`simple.airtable_find_update`) is the
first clean run of the current method: recipe in 197 s, no questions, dispatch
14 s, both reads reached the front door, run `success`, checker **fail**.
Monarch asked "does a VIP record already exist?" and AutomationBench's Airtable
mock does not evaluate `filterByFormula`, so it returned the existing non-VIP
record and Monarch skipped the creation. That is an AutomationBench patch for
Lucas, not a Monarch defect.

## 3. What is built

Features merged into `main`, each with spec, plan and tasks under `specs/`:

| # | What | State |
|---|---|---|
| 001 | Declarative benchmark configuration — a run is one product × one plan, inputs as YAML under `workflowbench/config/` | merged |
| 002 | Monarch as a competitor in create + run mode; cost from Langfuse | merged |
| 004 | Monarch in run-only mode (one known-correct recipe per task) | specified, not built |
| 005 | Task sets by difficulty tier; `wb corpus tiers` | built, sets frozen |
| 006 | HTML report and `wb summary` across rounds | built |
| 007 | Lab foundation: budget ledger, evidence journals, regrade, runtime manifests, the Studio | built on branch `007-benchmark-foundations` |
| 008–011 | Streaming Studio, outcome workspace, node architectures, Monarch runtime integration | in flight |

Capabilities that exist today, with where to check each:

- **Frozen task sets of any size**, drawn by rule (`wb corpus tiers`) or listed
  by id (`wb corpus slate`), hashed before any competitor runs.
  `workflowbench/tasks/` holds `tier-simple`, `tier-medium`, `tier-complex`,
  `random-10` (ten prompts each) and `achievable-50` (fifty).
- **The budget ledger**: every provider request is reserved, claimed and
  settled (`wb_arms/reservations.py`); the round's maximum liability is
  admitted before the first attempt; `wb budget reconcile` imports provider
  usage exports. Weekly ceiling US$ 300.
- **The approval flow** (decision D5): `WB_OPERATOR` names the launcher;
  Lucas's launches run at once, anyone else's creates an approval request
  (`wb approvals`, `wb approve`, `wb deny`, `wb run --request`). `approved_by`
  in plan files is ignored. Written into `.specify/memory/constitution.md` §IV.
- **Two tracks kept apart**: `track` is a plan field inside the config hash, so
  a one-off request round and a workflow round are never pooled.
- **Reports**: round page, paired comparisons with source lines, cross-round
  summary, Studio outcomes. Drilldowns and per-domain views are partial.
- **The hosted Studio**: <https://ailabs-studio-production.up.railway.app>,
  HTTP Basic Auth, deployed from the repo root with
  `railway up --service ailabs-studio --no-gitignore`.

Offline baseline on a clean checkout: **1091 tests pass, 3 skipped, about 11
minutes**. Reproduce with
`cd monarch-benchmark/workflowbench && uv sync && uv run python -m pytest tests -q`.

## 4. What is blocked, and on whom

| Blocked | Why | Owner |
|---|---|---|
| The 50-task gauntlet | Milestones M3 to M6 of the unblock plan | Lucas |
| Monarch rounds from the CLI on Carlos's laptop | Every seed embeds the front-door host in its `url_template`; a round runs only from a machine whose front door answers on that domain. Carlos's machine needs its ngrok tunnel up; Lucas's has none | Carlos / Lucas |
| A second Monarch instance (the lab version) | The served code is a fork branch. `origin/ailabs/unattended-authoring` in `TestBoxLab/monarch` carries the deployed commit `2ede4b3e`; stock Enterprise on GitHub is Bedrock-only and strips direct keys | Lucas |
| Claude Code as a second bare competitor | Its container must pass the isolation checks (M7); Docker Desktop is installed but its engine was not running on 8 Sep | Lucas |
| Signing off the re-derived approval rules | Three items below need Lucas | Lucas |
| A service account or API key for the bench organisation; the Opus 5 brain preset; a graph-version import route | Monarch side | Deyton |

**What still needs Lucas's sign-off** (from the refreeze record):

1. `simple.invoice_airtable_slack` has a weak assertion: `airtable_record_exists`
   pins the table but not the vendor or the amount, so a wrong invoice satisfies
   the positive half. Fixing it edits an assertion, not a derived rule.
2. The two Jira tasks stay collateral-blind — their assertions carry no content
   for a `where` clause to pin. A limit of the vendor's data.
3. The vendored AutomationBench here is plain `1.0.6` (commit `4a8e106`) while
   `achievable-50` declares `1.0.6+evalrepair.10`. His patched tree is not on
   this machine.

**Carlos is not blocking anything.** He launches through the approval-request
flow.

## 5. The 67% claim, and why the lab version is a reconstruction

The result the lab version descends from is identified: competitor
`matrix-v912-opus-max`, Monarch v9.12 with Claude Opus 5 at max effort,
403/600 = 67.2% on suite `1.0.6+evalrepair.10`, 26 August 2026, US$ 337.84,
paired wins 60 / losses 32.

**The graph file that run consumed is gone** with the deleted MonarchBench
workspace. The nearest surviving knowledge artifact is the bridge-v8 reviewed
catalog (2.2 MB, 273 entries, 43 product contexts, sha256 `7aea3d99…`). The lab
version is therefore a **reconstruction** of that lineage and must never be
labelled "the 67% artifact". Recorded in
`research/architectures/pg-waki/v1/provenance.md`.

## 6. Decisions of record, 8 September 2026

Settled with Lucas; the full table is section 1 of the unblock plan.

- **D1** Three selectable competitors: stock Monarch, bare (no Monarch), and
  Lucas's versioned experiments.
- **D2** Monarch runs on plain Opus 5 through the Anthropic API. **No Bedrock.**
  This retires the 3 September blocker, where none of Carlos's AWS SSO roles
  could call `bedrock:InvokeModel` in `us-west-2`.
- **D3** Both tracks run as separate rounds; results never pooled.
- **D4** Rounds launch from the web app and from the CLI, one engine behind both.
- **D5** Lucas approves; his own launches run at once.
- **D6** Suite revision `1.0.6+evalrepair.10`.
- **D7 / D8** Monarch on Railway, one instance per version, in the workspace
  Lucas and Carlos share.
- **D9** The PG-Waki graph enters the lab instance as fixture seeds imported
  over Monarch's API — there is no knowledge-artifact route.
- **D10** Both bare competitors (API loop and Claude Code in a container) are
  selectable and may run together.

## 7. What is next

The unblock plan's calendar, with milestones M0 to M8:

- **Week of 8 September 2026** — M0 housekeeping, M1 the dependency migration
  to `1.0.6+evalrepair.10`, M2 the task sets and plans, M3 started. Under US$ 5.
- **Week of 15 September 2026** — M3 done, M4 one engine behind both front
  doors, M5 both Monarch instances up and verified, M6 the graph version. Under
  US$ 30 in pilots.
- **Week of 22 September 2026** — the gauntlet on the one-off request track,
  report and readout. US$ 155 to 330, retry budget set to fit the week.
- **Week of 29 September 2026** — the gauntlet on the workflow track; Claude
  Code joins if M7 passed.

Two Monarch competitors on both tracks in one week exceed the US$ 300 weekly
ledger with retries. The ledger refuses the over-subscription; the levers are
the retry budget (dropping the retry halves the band) and running one track per
week.

## 8. Operational checklist before any round

1. **The front door must answer.** On Carlos's machine:
   `ngrok http --domain=imputable-tracklessly-kellan.ngrok-free.dev 127.0.0.1:9105`,
   verified with `curl http://127.0.0.1:4040/api/tunnels`. `wb doctor` does not
   check this yet (`workflowbench/deferred.md`).
2. **Monarch up**:
   `bash ../monarch/local-docs/setup/scripts/railway-ops.sh status`. `unlock`
   takes 8 to 12 minutes and rebuilds; `lock` is instant. Keep it locked when no
   round is running. Never run `railway up` from a plain `main` checkout — it
   uploads the working tree and would replace the fork build.
3. **Seeds deployed and in sync**: `bench-seeds.sh status`; the root `ok.txt`
   names the seeds version and sha.
4. **`wb monarch verify`** (or Verify in the Studio). A passing record — backend,
   session, knowledge base, Langfuse — admits the Monarch competitors for two
   hours, for that backend only. The refusal names the failing check.
5. **Hashes match**: the hashes in `docs/rounds/*.md` must agree with
   `config.resolve(...)`.
6. **Launch detached**, never inside a tool call that can time out:
   `echo y | uv run wb run --product simulated-apps --plan <plan>` under
   `nohup ... &`. `out/chain_rounds.sh` chains rounds behind an "at least one
   Monarch pass" gate.
7. **Post to Slack** `#ai-labs` (`C0BU26293CM`) with the Slack MCP plugin.

## 9. Standing rules

These do not change with features. The full set is `PLAN.md` §1.1 and
`.specify/memory/constitution.md`.

1. **No paid round without approval of that specific run.** Smoke scale and
   `wb doctor` are free to run. State the attempt count and a cost band first.
2. **Pre-registration.** Do not edit a task's prompt, starting data or approval
   rule after seeing results without Lucas's sign-off. Hash changes make stored
   attempts non-regradable — say so when it happens.
3. **Nothing grades itself.** The checker runs later, from stored snapshots.
4. **Files in English, conversation in Portuguese.** Plain language, no internal
   jargon in shared documents.
5. **Never pool across suite revisions or across tracks.**
6. **Pushes to `TestBoxLab/ailabs` happen only when Carlos asks.** The repo is
   public; nothing secret is tracked (`.env` and `*.sqlite3` are ignored).

## 10. Environment

- Repo: `C:\Users\cgmat\Desktop\TestBox\ailabs`, **off OneDrive**. On
  2 September 2026 OneDrive sync deleted tracked files, `.git/HEAD`,
  `.git/config` and `workflowbench/.env` from the working tree. The repo was
  rebuilt from a bundle and moved twice on 3 September. Do not put it back.
- Python 3.13 managed by `uv`. Keys in `workflowbench/.env` (gitignored;
  `.env.example` is tracked).
- AutomationBench vendored at `workflowbench/vendor/automation-bench`
  (gitignored, re-clone if missing), pinned at 1.0.6 commit `4a8e106`.
- The Monarch clone is the sibling `C:\Users\cgmat\Desktop\TestBox\monarch`.
- CI: `.github/workflows/ci.yml` (pull requests to `main` or manual; free) and
  `smoke.yml` (manual only; about US$ 2). Branch pushes trigger nothing.

## 11. Open items carried forward

In `workflowbench/deferred.md`, kept here so they are visible:

- A `wb doctor` check for the public front door.
- The conformance gate scoped to the plan's services (today `buffer`, `canva`
  and `twitter` block the setup gate, so the last import used `--no-conform`).
- Airtable `createdTime` schema type.
- 22 write actions in the task-set services still have no body, because their
  handlers take `**kwargs`.
- The Recruitee careers endpoint.
- A sandbox for competitor harnesses.
- `finance.annual_budget_prep` cannot be solved through the API by anyone —
  Sheets has no list-spreadsheets route and Drive is not seeded. Keep it or
  redraw it; Lucas decides.
- 27 approval rules still use a whole-service wildcard.
