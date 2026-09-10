# State of the program

Where the Monarch benchmark stands, what is blocked, what is next. Replaces the
handoffs of 2, 3 and 8 September 2026.

Last updated **10 September 2026**. Read `HOW-WORKFLOWBENCH-WORKS.md` for the
machine, `PLAN.md` for the tracking surface, and
`../../docs/AI-LABS-UNBLOCK-PLAN-2026-09-08.md` for the milestone plan this note
summarises. Where the two disagree, the unblock plan is the authority on
milestones and the refreeze record on task hashes.

**Continuation, 10 September:** the current corrections and remaining gates are
in section 13. Sections 1–12 retain the inherited historical account; their
Lucas-only approval and pending assertion-repair statements are superseded by
Carlos's ruling and the shared instructions in `../../AGENTS.md`.

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

## 12. Session of 9–10 September 2026: what changed and what is open

The whole of that session went into one finding: **the approval rules were
broken, and four paid rounds had measured that rather than any competitor.**

### The six defects, all in rules the bench derives itself

| Defect | Effect | Frozen tasks |
|---|---|---|
| An added subtree collapsed to `"<object>"` | collateral writes invisible | 12 of 40 |
| The rule named `google_sheets.spreadsheets[id=…]*`, a subtree the loader empties | **nobody could pass** | 12 |
| `<service>.actions[*]`, a list glob against a dict-keyed log | **nobody could pass** | 1 |
| `zoom.actions.*` on a service whose schema has no `actions` field | **nobody could pass** | 1 |
| A `where` clause compared `1200000` with `"1200000"` | rejected the write it had asked for | 5 |
| `id: None` collided, so an added record read as five edits | failed correct answers | — |

Two more accepted a wrong answer: a whole-service wildcard took any number of
unrequested writes, and an assertion pinning no value let a junk-only attempt
score.

Every one was found by running the frozen tasks against the simulator, never by
reading them. Two sweeps were discarded first for being heuristics — one
reported 1,168 false positives. **A heuristic over task files is not evidence;
a reproduction against the world is.**

### Also fixed

- **A production bug in the Monarch client.** `_buffered` asked the socket before
  the response buffer, so a first SSE frame that arrived with the headers was
  discarded. In a live round that can drop a real `awaiting_input` and make an
  attempt miss a question the builder asked. Worth a second pair of eyes.
- **`wb monarch verify` could not fail on the thing that mattered.** It never
  probed the front door, so it reported green while the environment named the
  tunnel and the knowledge base named the hosted Studio — the exact split that
  spent US$ 18.75 on two rounds measuring nothing. It now compares them.
- **The Studio's front-door relay** targeted a hardcoded loopback, so a CLI round
  could never reach its own shim through a hosted Studio.
  `STUDIO_FRONT_DOOR_TARGET` now names where the shim listens.
- **The seed deploy guards** compared a bare host against one carrying a path, so
  a front door served at `/front-door` was rejected by construction.

### Collateral damage is now measured

A verdict alone hides the difference between a competitor that takes the safe
path and one that finishes more prompts by making a bigger mess. Every attempt
carries a count; the technical page has two columns and the stakeholder page a
card in plain words. On the Easy round of 5 September it already separates the
field: Opus has the lowest pass rate of the models and the highest collateral
(8 attempts of 16), Monarch 1 of 20.

### Monarch executes again

After the migration, one attempt: `completed`, two `GET /airtable/base_crm/Contacts`
at 200 — the call that had failed all day — and a 13-second execution phase where
it had been 149 seconds of failure. It still did not pass the task: it read and
wrote nothing, which is now a question about the product, not the wiring.

### Open, in the order they matter

1. **Why Monarch read and did not write** on `simple.airtable_find_update`. The
   known trap is that the Airtable mock does not evaluate `filterByFormula`, so a
   "does a VIP already exist?" lookup returns the existing non-VIP record and the
   builder concludes there is nothing to create. If that is it, the fix is an
   AutomationBench patch and belongs with Lucas. **Worth settling before paying
   for a round that would measure the same trap four times.**
2. **PR #3** is open against `main` and carries all of the above.
3. **Re-vendor AutomationBench.** The tree here is plain `1.0.6`; `achievable-50`
   declares `1.0.6+evalrepair.10` and the patched source is not on this machine,
   so a run over that set stops at the world-revision guard. The four tier sets
   are unaffected.
4. **`simple.invoice_airtable_slack` has a weak assertion** — it pins the table
   but not the vendor or the amount, so a wrong invoice satisfies the positive
   half. Editing it is a pre-registration change and needs Lucas.
5. **Two Jira tasks stay collateral-blind**: their assertions carry no content for
   a `where` clause to pin. A limit of the vendor's data, not of the derivation.
6. **The schema synthesizer** is finished on the Monarch side and not yet
   deployed. `rounds/2026-09-10-fdapi-deploy-runbook.md` has the procedure; the
   check that matters is that the 47 `bench-*` products come back **unchanged**,
   because the synthesizer is not supposed to touch them.

### One caution for whoever runs the next round

The bench now refuses more than it used to, and each refusal is load-bearing:
knowledge-base drift, front-door disagreement, an operator name, a world
revision. When one fires, read it before working around it — every one of them
was added because something silently measured nothing.

## 13. Codex continuation, 10 September 2026

Carlos's final comparability rule preserves AutomationBench's world, routes, seeds
and assertions, including known limitations. WorkflowBench may fix its approval-rule
translation. Bad tasks may be excluded with a record or reported upstream, never
silently altered. Evalrepair adoption is suspended pending Lucas's clarification.

AGENTS.md requires the entire CLAUDE.md, constitution and HARNESS-PROCEDURES.md.
Codex and Claude share the method, file map, glossary and round gates; all eleven
Claude skill files remain intact. The runtime approver defaults and local
WB_APPROVERS now recognize Carlos or Lucas by first or full name; an explicit
restricted override still works. The failing Carlos reproduction and 34 passing
approval/CLI tests verify the governance alignment without creating real approvals.

The Airtable filter trap and weak invoice assertion are reproduced but intentionally
preserved. Runnable characterizations and upstream issue drafts (not submitted) are
in [the limitations record](rounds/2026-09-10-upstream-limitations.md). No task was
removed or redrawn. Temporary simulator/assertion edits were fully reverted before
any paid attempt. The vendor is clean at upstream 1.0.6; dependency pin and installed
package agree. Four tier plans resolve; achievable-50 retains its revision block.

Extra Jira writes were already caught by frozen counts. The wrong-summary
collateral-count limit is documented. The retained Salesforce approval-rule fix
accepts the correct whole-record addition. Only its task hash changes; requests,
initial data and vendor assertions are identical.
[Evidence and hashes](rounds/2026-09-10-invoice-jira-corrections.md).

Deployment evidence is in [the merged-branch record](rounds/2026-09-10-merged-monarch-deploy.md).
The deployment passed all six verification checks; the catalogue remains 47
products, 686 actions, 47 in sync. Carlos identified Langfuse as the usage source;
[historical usage accounting](rounds/2026-09-10-historical-cost-accounting.md)
reserved US$ 34.064 for the observed gap without certifying provider invoices.

The one requested diagnostic ran as `run-20260910-155059`. Monarch's stored final
poll is `success`, and the front-door log contains four Airtable GETs, all 200.
The VIP lookup again returned the Active record; the create step was skipped and
the world did not change. WorkflowBench recorded `infra:harness_crash` because
the merged product used `claude-opus-4-6`, absent from its frozen price table.
The US$ 25 reservation remains held with unknown billing; the row's zero dollar
value is not zero cost. No repeat was launched and no refusal was overridden.
[Diagnostic evidence](rounds/2026-09-10-post-deploy-diagnostic.md).
Langfuse subsequently yielded 22 generations, US$ 0.89375475 observed cost.
A versioned successor price table now covers the deployed writer and records
direct Anthropic routing, with original configuration preserved and all five
relevant plan hash moves documented. Its 129 offline pricing/config tests pass.
The diagnostic result remains the original refusal; no second paid attempt ran.

Final validation: detached full suite completed with 1,916 passed, 2 skipped and
one real corpus/task rule-hash mismatch. The source corpus now carries the same
permitted Salesforce rule as its drawn copy; old versions are archived. All 31
affected refreeze/real-world/scored-derivation tests then passed. The later
approval and price configuration changes separately passed 34 and 129 tests.
The full suite was not rerun after those focused corrections. Graphify's code
graph was refreshed; vendor and upstream task fields were checked unchanged.

## 14. PR #3 CI and complete WorkflowBench telemetry (10 September)

Carlos authorized correcting, committing and pushing the CI fixes and requested
WorkflowBench execution/spending history in Langfuse. Main through `290852f`
was integrated without conflicts. The CI runs offline tests and corpus
validation, never infrastructure deployment. The 13 original failures were
reproduced and fixed; the next run found one stale pilot price hash, now traced
to the documented successor table and corrected without changing task data.

Ledger transitions and attempt summaries now queue metadata-only telemetry,
covering API/native/Studio/Genesis/embedding calls. Unknown usage keeps the hold;
Monarch costs link the original generations. V4 immutable billing observations
and durable send claims prevent cost duplication: ambiguous delivery requires
read-side confirmation, never a blind retry. CLI commands are documented in
`workflowbench/config/README.md`. This does not certify provider invoices,
merge local/hosted ledgers, backfill history automatically or deploy Studio.

The final focused group passed 51 tests; both CI corpus checks passed. A real
zero-cost telemetry span was delivered and read from Langfuse without calling a
model. Full local/remote validation and the final merge-readiness outcome are
tracked in [the session record](rounds/2026-09-10-pr3-ci-and-langfuse.md).
