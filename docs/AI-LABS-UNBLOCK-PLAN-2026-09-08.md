# AI Labs: plan to unblock paid experiments and make the lab functional

Date: 8 September 2026, settled with Lucas the same evening. Owner and approver: Lucas Wakigawa.
Direction of record: [AI-LABS-DIRECTION.md](AI-LABS-DIRECTION.md). Foundation work: `specs/007-lab-foundation/`.
Monarch runtime work: `specs/011-monarch-runtime-integration/`.

The plan answers one question: what has to happen, in what order, before AI Labs can run
the 50-task gauntlet (stock Monarch, bare Opus 5 and Lucas's experimental Monarch with the
PG-Waki graph, on both tracks) and keep running experiments every week after that. Every
claim about today's state was checked on 8 September on Lucas's machine, branch
`007-benchmark-foundations`. Effort figures are estimates in working days.

## 1. Decisions taken on 8 September

| # | Decision | Consequence |
|---|---|---|
| D1 | Three selectable competitors: **stock Monarch** (whatever it runs today), **bare** (no Monarch, nothing), and **Lucas's versioned experiments** (Monarch with the latest PG-Waki graph seeded, the version that scored about 67 %) | Two Monarch instances; a graph-version import; the bench-side Studio architectures are not the gauntlet arm |
| D2 | Monarch runs on plain Opus 5 through the Anthropic API. No Bedrock | The "custom build" label for direct keys goes away; the price table already matches Anthropic's rates; the provider is recorded as Anthropic |
| D3 | Both tracks, as separate rounds: one-off agentic request; workflow creation plus execution | Two plan files per task set; results never pooled across tracks |
| D4 | Rounds launch from the web app and from the CLI | One engine, one results store, one ledger; the Studio and `wb` are two front doors |
| D5 | Lucas approves. His own launches run at once; a launch by Carlos creates an approval request and waits | `approved_by` becomes an approval record; the constitution and `CLAUDE.md` are updated |
| D6 | Suite revision `1.0.6+evalrepair.10` | The dependency migration comes first; the corpus is re-imported under that revision |
| D7 | Monarch hosted on Railway, in the workspace Lucas and Carlos share (Lucas is admin) | Lucas deploys; no tunnel changes on Carlos's side are needed |
| D8 | One Railway instance per Monarch version (stock; lab) | Identities never share a database; the seeded graph is hashed into the lab identity |
| D9 | The PG-Waki graph enters the lab instance through a bench-side import over Monarch's API, the way `wb monarch setup` already imports the mocked-API seeds | Needs an import path on the Enterprise side (Feature Discovery or the product-graph source) |
| D10 | Bare arm: the raw Opus 5 API loop and Claude Code in a container are both selectable and may run at the same time | The API loop runs as soon as the paid gate opens; Claude Code joins when its container passes the isolation checks |
| D11 | The 56 unrelated files at the repo root are ignored in `.gitignore`, not moved or deleted | Done on 8 September |

## 2. The finish line: what "functional" means

| # | Capability | Today |
|---|---|---|
| 1 | A clean checkout reproduces the offline baseline | Done: 1091 tests pass, 3 skipped, 11 min |
| 2 | A paid round launches from the CLI or the Studio inside the weekly ledger: maximum spend reserved before dispatch, settled from the provider receipt, reconciled against billing | **Done for API-loop competitors (8 Sep night):** every provider request is reserved, claimed and settled (`wb_arms/reservations.py`); the round's maximum liability is admitted before the first attempt; `wb budget reconcile` imports usage exports; `wb doctor` probes go through the ledger (bare Opus 5 verified, US$ 0.013). Monarch and native competitors stay refused until M5 and M7 |
| 3 | Frozen task sets of any stated size, drawn by rule or listed by id, hashed before any competitor runs, on the chosen suite revision | **Done:** `wb corpus slate` freezes a set from an id list with a manifest; `tasks/achievable-50` is frozen on `1.0.6+evalrepair.10` (50 prompts, two ids also in tier sets, recorded); the corpus is re-imported as `corpus-evalrepair10/` (800 usable); a set runs only on the world it was imported under |
| 4 | Competitors: bare API loop, Claude Code, stock Monarch, Lucas's versioned Monarch experiments | Bare API loop **ready** (doctor passed through the ledger). Claude Code still refused (M7). Stock Monarch: Carlos's Railway instance answers (backend, fdapi), the bench env points at it, but rounds need his ngrok front door or the fork tree (M5 T5.0). Lab version: `wb monarch knowledge` generates the lab seeds from the reconstructed catalog (257 of 273 entries mapped) but the builder does not read seed descriptions yet (Deyton) |
| 5 | Two tracks kept apart | **Done in plans:** `track` is a plan field in the config hash; two gauntlet plans per set. Studio jobs still one-off only (M4) |
| 6 | Evidence per attempt: event journal, snapshots, manifests, regrade revisions | Done offline (feature 007) |
| 7 | Reports: round page, paired comparisons with source lines, cross-round summary, Studio outcomes, evidence drilldowns | Round page, summary and Studio outcomes done; drilldowns and per-domain views partial |
| 8 | Research loop: experiment registry with duplicate check, pre-registration, Trello status, weekly readout | Scaffolding only (`research/`, empty experiment ledger) |
| 9 | Approval flow per D5 | **Done:** `WB_OPERATOR` names the launcher; Lucas's launches run, others create an approval request (`wb approvals`, `wb approve`, `wb deny`, `wb run --request`); `approved_by` in plan files is ignored; constitution §IV and `CLAUDE.md` updated |

The lab is functional when rows 2, 3, 4, 5 and 9 are done and one pre-registered paid round
has run end to end from each front door with its report.

**Ready to trigger on 8 September, 23:00:** the control-only gauntlet rounds
`achievable-50-bare-request` and `achievable-50-bare-workflow` (bare Opus 5 beside the answer
key, 50 prompts, 100 attempts per competitor, ceiling US$ 40 each, liability US$ 40 admitted
against US$ 299.60 available). Command, from `monarch-benchmark/workflowbench`:

```bash
WB_OPERATOR=lucas uv run --frozen wb run --product simulated-apps --plan achievable-50-bare-request
```

**Monarch stock arm, state at 8 Sep 20:50 (local).** Done from this session after Lucas opened
permissions: `fdapi` redeployed from the `ailabs-deploy` tree with the hosted-front-door seeds,
47 apps imported (`wb monarch setup`, knowledge file re-pinned, commit c49485b), the hosted
Studio wired to the instance through Railway references, `wb monarch verify` and the Studio's
Verify both passing (backend, session, knowledge base, Langfuse), readiness `ready`,
`launchable: true`. Pilot `monarch-pilot-001` from the web app: one task, one attempt, 409
recorded actions, workflow authored and executed through
`https://ailabs-studio-production.up.railway.app/front-door`, US$ 1.52 settled into the hosted
ledger; the task check failed (a quality outcome, not a wiring failure). **Monarch rounds
launch from the web app**: a Studio job with the 50 `achievable-50` tasks and the architecture
`default-monarch-enterprise`, beside the Opus 5 runner for Without Monarch; the attempt ceiling
is US$ 3.00, so 50 attempts reserve at most US$ 150. CLI rounds with Monarch from a laptop still
need a tunnel (this machine has none), so the CLI plans keep the bare arms only.

**Earlier note (23:30), kept for the record.** The fork tree is not only on Carlos's machine after all:
`origin/ailabs/unattended-authoring` in `TestBoxLab/monarch` carries the deployed commit
`2ede4b3e` (plus one), the Railway Dockerfiles, the direct-Anthropic provider and the FD
migrations; it is checked out as branch `ailabs-deploy` in `C:/Users/Lucas Wakigawa/Documents/monarch`.
The hosted Studio now serves the bench's world at
`https://ailabs-studio-production.up.railway.app/front-door` (relay to the attempt's shim,
no login on that path), and stock seeds naming that front door are generated and validated
(`out/monarch-seeds-studio`, 47 products, 686 actions, 0 errors). Three steps remain, and the
first two are Lucas's because they change Carlos's shared instance and carry its secrets
(the auto-mode classifier refused them here):

1. Ship the seeds: copy `out/monarch-seeds-studio/bench-*` into
   `Documents/monarch/feature-discovery/api/src/seeds/fixtures/public-api-seeds/`, then from
   `Documents/monarch` on branch `ailabs-deploy`: `railway up --service fdapi --detach`
   (Carlos's runbook step; rollback = the same with seeds regenerated for his ngrok host).
   Then, from the bench with `FRONT_DOOR_URL=https://ailabs-studio-production.up.railway.app/front-door`
   in `.env`: `uv run --frozen wb monarch setup --product simulated-apps` (imports by slug, writes
   the knowledge file), and the org grant (`bench-seeds.sh` step 4 or `grants-only.sh`).
2. Wire the hosted Studio to the instance with Railway variable references, no values typed:
   `railway variables --service ailabs-studio --set 'MONARCH_URL=https://${{backend.RAILWAY_PUBLIC_DOMAIN}}' --set 'MONARCH_FD_URL=https://${{fdapi.RAILWAY_PUBLIC_DOMAIN}}' --set 'FD_API_SHARED_SECRET=${{fdapi.FD_API_SHARED_SECRET}}' --set 'MONARCH_PASSWORD=${{backend.SEED_ADMIN_PASSWORD}}' --set 'LANGFUSE_OTLP_AUTH=${{backend.LANGFUSE_OTLP_AUTH}}' --set 'LANGFUSE_URL=https://us.cloud.langfuse.com' --set 'FRONT_DOOR_URL=https://ailabs-studio-production.up.railway.app/front-door' --set 'BENCH_ORG_ID=<from railway.env>'`
   (run under `MSYS_NO_PATHCONV=1` in Git Bash). The bench derives the Langfuse key pair from
   the OTLP header. `MONARCH_BUILD` and `MONARCH_ATTEMPT_CEILING_USD=3.00` are already set.
3. Verify the instance: `uv run --frozen wb monarch verify` from the bench (or Verify in the
   Studio). A passing record (backend, session, knowledge base, Langfuse) admits the Monarch
   competitors in `wb run` and in the Studio for two hours, for that backend only; the refusal
   otherwise says which check failed. Monarch rounds then launch from the web app (its front
   door is on Railway); CLI rounds with Monarch from a laptop still need a tunnel, which this
   machine does not have (no ngrok).

The lab instance (second Railway instance from `ailabs-deploy` with the lab seeds from
`wb monarch knowledge`) and Claude Code in a container (M7) remain open.

## 3. Where we are on 8 September

- Branch `007-benchmark-foundations` holds the whole foundation increment uncommitted:
  budget ledger, evidence journals, regrade, runtime manifests, the Studio with product
  graphs and the offline Enterprise adapter.
- Keys: the repo-root `.env` has the Anthropic, OpenAI, Fireworks, Moonshot and Google
  keys. The CLI reads `monarch-benchmark/workflowbench/.env`, which does not exist here;
  the Studio reads both. No Monarch, Langfuse or front-door variables are set.
- Weekly ledger (`research/budget.sqlite3`): US$ 0.39 spent this week, US$ 299.61 free.
- Pinned dependency: AutomationBench 1.0.6 at `4a8e106`, vendored. The repaired candidate
  `1.0.6+evalrepair.10` (ApplicationBench tree `7ac9559`) passed its own suite in a
  separate copy (`.references/ApplicationBench/vendor/automation-bench`), with two known
  hash-link failures documented in `specs/007-lab-foundation/candidate-validation.md`.
- Monarch: `TestBoxLab/monarch` is private; Lucas's GitHub and Railway logins work from
  this machine. No checkout next to the repo. The 4 to 6 September rounds used a Railway
  fork branch (`feat/railway-dev-deploy`, commit `797a8e5d1`) with Anthropic keys.
- `wb monarch setup` already talks to Feature Discovery: lists `/v1/seeds`, imports each
  product with `/v1/seeds/<slug>/import`, records one `kb_hash` per product.
- Docker Desktop is installed but its engine is not running (needed for the Claude Code
  container). Codex on this host failed sandbox provisioning.
- The Studio keeps one results store per job (`out/studio/<job>/results.sqlite3`); the
  CLI uses `out/wb.sqlite3`. Studio jobs are hard-coded to the one-off track.
- The 50-task gauntlet is the ApplicationBench `achievable50` slate: 50 ids, eight or
  nine per scored domain, no `simple.*` task. All 50 exist in today's corpus and none sits
  in a frozen set. On the new revision they must be re-checked after the import.
- The 67 % result is identified: arm `matrix-v912-opus-max`, Monarch v9.12 with Claude Opus 5
  at max effort, 403/600 = 67.2 % on suite 1.0.6+evalrepair.10, 26 August 2026, US$ 337.84,
  paired wins 60 / losses 32 (recovered transcript in `Monarch_Main/_recovery/transcripts/`).
  The graph file that run consumed is gone with the deleted MonarchBench workspace. The nearest
  surviving knowledge artifact is the bridge-v8 reviewed catalog
  `Monarch_Main/ATLAS/backend/config/bridge-v8-zapier-hard50-reviewed-capabilities-enriched-4a8e106-v2.json`
  (2.2 MB, 273 entries, 43 product contexts, sha256 `7aea3d99…`). The lab version is therefore
  a **reconstruction** of that lineage, never "the 67 % artifact".
- Carlos's Railway deployment (`monarch-dev`, workspace "Waki's Projects", Lucas is admin) runs
  a fork branch `feat/railway-dev-deploy` that exists only on Carlos's machine (deployed
  commit `2ede4b3e`, 8 September). It carries the direct-Anthropic provider, the Railway
  Dockerfiles and HTTP transports, the telemetry contract and the seeds. Stock Enterprise on
  GitHub is Bedrock-only and strips direct keys; the fork is what runs Opus 5 through Anthropic.
  On 8 September evening: backend, fdapi and the orchestrator answer; the `web` service's last
  deploy failed.
- Every seed embeds the front-door host (Carlos's ngrok domain) in its `url_template`, so a
  round can only run from a machine whose front door answers on that domain. Moving the front
  door means regenerating the seeds and redeploying `fdapi` from the fork tree.
- The Studio is hosted: https://ailabs-studio-production.up.railway.app (service `ailabs-studio`
  in `monarch-dev`, HTTP Basic Auth, volume at `/data` for jobs and the ledger, deployed from the
  repo root with `railway up --service ailabs-studio --no-gitignore`; see `Dockerfile` and
  `.railwayignore`).

## 4. Milestones, in dependency order

Each milestone lists what exists, the tasks, the evidence that closes it, the owner and
the spend. Code tasks follow the house rules: short spec when the change is not trivial,
tests first, no "done" without runnable output.

### M0. Housekeeping and baseline (1 day, Lucas)

- T0.1 Commit the 007 increment on its branch, frozen sets untouched. Evidence: `git status`
  clean apart from the ignored files; suite green on the committed tree.
- T0.2 One place for keys: make `monarch-benchmark/workflowbench/.env` canonical (what the
  CLI reads), copy the root keys there, extend both `.env.example` files with the Monarch,
  front-door and Langfuse variable names for both instances.
- T0.3 Clone `TestBoxLab/monarch` at the commit the Railway instances will run as the sibling
  `../monarch`; the Monarch harness reads its version from that checkout.
- T0.4 Start the Docker engine and record `docker version` (needed by M7).
- T0.5 Rebuild `graphify-out/` or remove the graph rule from `CLAUDE.md`.

### M1. Dependency migration to `1.0.6+evalrepair.10` (2 days)

Exists: the validated candidate copy and its provenance notes; `wb corpus import-ab
--domains all`; `wb corpus declare`; the revision-aware manifests of feature 005.

- T1.1 Replace `vendor/automation-bench` with the repaired tree (`7ac9559`), lock it, and
  record the swap and the two known hash-link failures in a provenance note; the old
  revision stays reachable by tag for regrading historical rows.
- T1.2 Import the corpus under the new revision into `corpus-evalrepair10/` (add
  `--revision` and `--out` to `import-ab`); derive approval rules; every manifest, report
  and round doc names the revision; reports refuse to pool across revisions.
- T1.3 The old frozen sets stay as records; new draws come from the new corpus only.
- T1.4 Suite green; `wb doctor` offline checks pass against the new world.

### M2. The task sets and their plans (1 day, no spend)

- T2.1 `wb corpus slate --ids <file> --out tasks/achievable-50 --because "<why>"`: copies
  corpus task files unchanged; refuses, naming them, if an id is missing, has no approval
  rule or already sits in a frozen set; writes `tasks/achievable-50-manifest.yaml` with the
  selection rule and its source, the revision, every task's hash, legacy difficulty score
  and tier label, and the count per domain.
- T2.2 The id list `tasks/achievable-50-ids.txt` from the ApplicationBench achievable50
  record, the rule written above it.
- T2.3 `track` in plan files (`agentic-request` or `create-run`), part of the config hash.
- T2.4 Two plans: `config/plans/achievable-50-request.yaml` and
  `config/plans/achievable-50-workflow.yaml`. Competitors: `oracle`, `claude-opus-5/api`
  (baseline), `claude-opus-5/claude-code` (when M7 passes), `monarch-stock`, `monarch-lab`.
  One attempt per prompt plus one retry; audience internal; cost ceiling per section 5.
- T2.5 Pre-registration for each round under `research/experiments/`, one line each in
  `experiments.jsonl`, Trello cards. Frozen before launch.
- T2.6 Round docs under `monarch-benchmark/docs/rounds/` in the shape of the tier docs.

### M3. Paid dispatch and the approval flow (3 to 4 days)

Exists: `wb_orchestrator/budget.py` (reserve, claim, settle; US$ 300 per week),
`wb_studio/gateways.py` (per-request maximum from the rate card; Anthropic, OpenAI,
Fireworks, Gemini adapters), `_paid_launch_blocked` in `wb_orchestrator/cli.py`.

- T3.1 Route the CLI API loop through the reservation gateway: reserve the request
  maximum, claim, call, settle from the usage receipt; an unreadable receipt keeps the hold.
- T3.2 Round admission: reserve the round's maximum liability (attempts × per-attempt cap,
  capped by the plan's `cost_ceiling_usd`) before the first attempt; refuse with the
  shortfall when the week is short; settle down as attempts finish; retries and resume
  inherit the reservation and can never reset spend. Monarch attempts reserve the
  per-attempt ceiling the Studio already uses (`MONARCH_ATTEMPT_CEILING_USD`).
- T3.3 `wb budget reconcile`: import the week's provider usage (Anthropic Console usage or
  Admin API, OpenAI, Fireworks, Google, Langfuse totals for Monarch) and compare with the
  settled totals; the difference is recorded either way.
- T3.4 Approval per D5: the launcher's identity comes from `WB_OPERATOR` (CLI) or the Studio
  login. Lucas's launches are approved on creation. Any other launcher creates an approval
  request (`awaiting_approval`) that Lucas approves with `wb approve <id>` or in the Studio;
  the record stores who launched, who approved and when. `approved_by` in plan files is
  replaced by this record; the smoke-scale exception stays for scripted checks and doctor.
- T3.5 Replace the blanket refusal with capability checks: API-loop competitors allowed once
  T3.1 to T3.3 pass; Monarch competitors once their instance is verified (M5); Claude Code
  once its container passes (M7).
- T3.6 Write the approval rule into `.specify/memory/constitution.md` §IV and `CLAUDE.md`.
- T3.7 Tests: two rounds over-subscribing the same week; crash mid-attempt keeps its hold;
  resume keeps prior spend; Carlos-launch waits, Lucas-launch runs; refusal names the
  shortfall. First paid CLI pilot: two tasks × two models × one attempt, under US$ 1.

### M4. One engine behind the web app and the CLI (2 to 3 days)

- T4.1 One results store: Studio jobs write runs into `out/wb.sqlite3` with
  `launched_from: studio`; `wb report`, `wb summary` and the Studio outcome views read the
  same rows. Existing Studio job stores are imported once (`wb legacy-import`).
- T4.2 A Studio job is a plan: task set (any frozen set or slate), track, competitors,
  repetitions, ceiling; saved as a plan record with its config hash, so a CLI `wb run`
  and a Studio launch of the same plan are the same measurement.
- T4.3 Competitor picker per D1 and D10: stock Monarch, lab Monarch versions, bare API loop,
  Claude Code; any subset, run concurrently within the provider concurrency limits.
- T4.4 The Studio live view (builder frames, recipe nodes, front-door calls) works for CLI
  runs as well, since both go through the same orchestrator observer.

### M5. Two Monarch instances on Railway, Opus 5 through Anthropic (3 to 5 days, Lucas; Deyton for the operator API)

Blocker found on 8 September: the served code is the fork branch on Carlos's machine, and the
seeds pin his ngrok domain as the front door. Until Carlos hands over the fork tree (a git
bundle is enough), a second instance cannot be built and the seeds cannot be re-pointed; the
stock instance can be driven only while his tunnel is up. T5.0 below comes first.

- T5.0 Carlos: `git bundle create monarch-railway.bundle feat/railway-dev-deploy` and hand it
  over; Lucas checks it out beside the repo. Never run `railway-ops.sh up` or `unlock` from a
  plain `main` checkout: `railway up` uploads the working tree and would replace the fork build.

Exists: `wb_arms/monarch.py`, `monarch_client.py`, `http_shim.py` (create + run, streams,
front door, Langfuse cost), `wb_studio/enterprise.py` (probe, readiness, frozen manifest),
`wb monarch setup`, seeds v5.2, `tests/test_monarch_live.py`, the Railway ops script.

- T5.1 Deploy `monarch-stock` from the pinned Enterprise commit with Anthropic keys and the
  Opus 5 brain preset; deploy `monarch-lab` from the same commit as a separate service with
  its own Postgres and Feature Discovery. Record both builds (commit, branch, patch hash)
  in the runtime manifest; direct Anthropic keys are recorded as the provider, not as a
  deviation.
- T5.2 Harness files `config/harnesses/monarch-stock.yaml` and `monarch-lab.yaml` (own
  `MONARCH_*_URL`, credentials, Langfuse project and front-door address); the competitor
  name carries the commit and, for the lab, the graph version hash.
- T5.3 `wb monarch setup --instance stock|lab` against each; knowledge-base hash files per
  instance; drift refusal per instance.
- T5.4 Verification: the Studio probe and `wb doctor --arms monarch-stock,monarch-lab`
  report ready; `tests/test_monarch_live.py` passes against both.
- T5.5 One-off track adapter for the operator API (`POST /api/operator/runs`, stream,
  confirmations, reply): new thread per attempt, no automatic human answers, a
  clarification request recorded as assistance needed. Deyton: service account or API key
  for the bench and the brain preset.
- T5.6 Pilot: one task, one attempt, each track, each instance, under US$ 10.
- T5.7 Retire the fork identity (`797a8e5d1+feat/railway-dev-deploy`) from active plans;
  its rows stay as history.

### M6. The PG-Waki graph version in the lab instance (2 to 3 days once the artifact is located)

- T6.1 Done on 8 September: the run record is identified (section 3) and the consumed graph
  file is gone. Record the reconstruction in `research/architectures/pg-waki/v1/provenance.md`:
  source catalog path, bytes, sha256, entry and product counts, the run id it descends from,
  the label "reconstructed".
- T6.2 Confirmed on 8 September: no Enterprise or Feature Discovery route accepts a knowledge
  artifact. Product knowledge is imported from fixture folders shipped in the fdapi image
  (`POST /v1/seeds/<slug>/import` replays a committed fixture). So "seeding the graph" means:
  generate lab seeds whose action descriptions, non-effects, record locations and relationships
  come from the reconstructed catalog, ship them as fixtures of the lab instance's fdapi, import
  by slug, grant to the lab organisation. The bench never writes to Postgres directly.
- T6.3 `wb monarch graph import --instance lab --graph <file> --version <name>`: converts the
  artifact to the import format, imports it, reads back the hash, writes it to the lab's
  knowledge file; drift refusal before every round; the hash sits in the competitor name.
- T6.4 A version registry under `research/architectures/pg-waki/`: one folder per version,
  immutable, with the file, its hash, the fields changed since the parent, and the rounds
  that used it. New experiments are new versions; stock is never touched.

### M7. Claude Code in a container as the second bare arm (1 to 2 weeks)

Exists: `wb_arms/native_sandbox.py`, a fail-closed prohibition with the list of checks a
real runtime must pass.

- T7.1 One immutable image with the Claude Code CLI pinned; later Codex.
- T7.2 Per-attempt runtime: clean home and workspace, only the front door reachable, the
  provider key through a broker or a scoped secret, wall-time and resource limits,
  cancellation kills every descendant.
- T7.3 Adversarial checks (feature 007, criterion 2): canaries for answers, grader code,
  snapshots, other attempts' state and unrelated credentials; every read must fail.
- T7.4 Evidence: the native event stream parsed into the journal; billing from the provider
  receipt; unknown cost keeps its hold.
- T7.5 Replace the prohibition with the verified runtime; `claude-opus-5/claude-code` joins
  the plans beside the API loop.

### M8. Reports, analysis and the research loop (first readout one week after the first round)

- T8.1 Round page drilldowns: overview, task comparison, exact events and state changes;
  per-domain and per-difficulty small multiples; every number computed once from the store.
- T8.2 Calibrated model analysis on completed evidence, budgeted through the ledger, unable
  to overwrite grading.
- T8.3 Experiment registry: duplicate check, parent links, decision field; Trello sync.
- T8.4 Weekly readout in `research/digests/`; Slack only when asked.
- T8.5 Difficulty classification v1, outcome-independent, reviewed sample, domain coverage.

## 5. Critical path, cost and calendar

Per-attempt costs known today: bare API loop US$ 0.07 on the simple pilot (4 September)
and US$ 0.26 on the scored domains in the ApplicationBench record; Monarch about US$ 1.50
per attempt in the September rounds. A 50-prompt round with one retry is 50 to 100 attempts
per competitor.

| Round | Competitors | Band per round |
|---|---|---|
| Gauntlet, one-off request track | bare API loop, monarch-stock, monarch-lab (Claude Code when ready) | bare US$ 4 to 26; each Monarch US$ 75 to 150; total US$ 155 to 330 |
| Gauntlet, workflow track | same | same band; Monarch authoring adds a little |

Two Monarch arms on both tracks in one week exceed the US$ 300 ledger with retries. The
ledger will refuse the over-subscription; the levers are the retry budget (50 attempts
without retry halves the band) and running one track per week. Planned calendar:

- Week of 8 September: M0, M1, M2, M3 started. Spend under US$ 5.
- Week of 15 September: M3 done, M4, M5 (both instances up and verified), M6 if the
  artifact is located. Spend under US$ 30 (pilots).
- Week of 22 September: gauntlet, one-off request track, report and readout. US$ 155 to 330,
  retry budget set to fit the week.
- Week of 29 September: gauntlet, workflow track; Claude Code joins if M7 passed.
- Afterwards: new PG-Waki versions as new rounds; BRIDGE historical replay only if Lucas
  wants the reproduction claim.

## 6. Open items that need someone other than Lucas

- Deyton: service account or API key for the bench organisation on both instances; the Opus
  5 brain preset; a graph-version import endpoint if Feature Discovery cannot take one.
- Carlos: nothing blocking. He launches through the approval request flow once M3 lands.

## 7. Risks

- The 67 % figure must be tied to a concrete graph file and run record before the lab
  identity carries that name; otherwise it is a reconstruction.
- The evalrepair.10 world changes all 600 initial states; the achievable-50 ids must be
  re-checked for approval rules after the import.
- Long streams through the Railway edge were cut before; the polling fallback exists and is
  exercised in the M5 pilot.
- Native harness attempts have no cost measurement yet; the first M7 pilot sets the band.
- Two Monarch instances double Langfuse and Railway costs; the ledger counts only provider
  spend unless infrastructure is added by hand.

## 8. What this plan does not do

No push to `TestBoxLab/ailabs`, no Slack post, no Monarch upstream merge, no edit to a
frozen task set, no pooling across suite revisions or tracks, and no lab version presented
as stock Monarch.

## 9. Tracking

Each milestone becomes a Trello card on the lab board. M2, M3.4, M4.2 and M6.3 get short
specs before code; M3, M7 and M8 are tracked in `specs/007-lab-foundation/tasks.md`; M5
and M6 in the feature 011 checkpoints. Update the "Today" column of section 2 whenever a
milestone closes, with the evidence path.
