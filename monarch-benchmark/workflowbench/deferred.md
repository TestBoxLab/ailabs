# Deferred items for WorkflowBench (`wb`)

Things decided or requested that the bench does not do yet. Each item says what
exists today, what is missing, and where it goes. The skill
`/monarch-benchmark` (`.claude/skills/monarch-benchmark/`) drives this CLI; its
own deferred items point here.

## 1. Sandbox: every competitor harness in its own dev container (future)

**Ask (Carlos, 4 Sep 2026).** The competitors the bench drives on this
machine (the API tool loop, Claude Code headless) run in the bench's own
process with the API keys read from `workflowbench/.env`. There is no sandbox,
so data could leak during a round: a competitor's tool call, a coding agent's
shell, a logged prompt. Each harness should run inside a dev container of its
own, holding only that harness's API key, with the provider calls made from
inside the container; the bench talks to the container over a narrow
interface and never hands it the world.

**Today.** Nothing of that. The API tool loop exposes only the three world
tools (search the API catalogue, call an API, base64), so a raw model has no
file or shell access, but the process boundary is the bench's own. Monarch is
the exception: it runs elsewhere (Railway) and reaches the bench only through
the HTTP front door, which is the shape the sandbox should generalise.

**Later, as its own feature (brainstorm first).**

- One container image per harness kind (`api`, `claude-code`; later `codex`,
  `gemini-cli`, `opencode`). The container receives the task request and the
  front door address, holds the provider key as a secret, makes the model
  calls, and returns the attempt's transcript, tokens and cost.
- The world stays in the bench process behind the front door (the path
  Monarch already uses), so the container never sees the snapshot and cannot
  grade anything (rule 3).
- `EpisodeRow` unchanged: the container's result is mapped onto the same
  fields the in-process harness fills today.
- Open questions: how the world tools are exposed to a model inside the
  container (the API tool loop would move from in-process calls to HTTP calls
  against the front door); Docker on the Windows bench machine; the cost of
  an extra hop per tool call; how a round in containers is proven to
  reproduce a round without them before it replaces it.
- Rules unchanged: same request text, nothing grades itself, cost complete,
  API-key billing only, config hash per run (the image digest joins it).

## 2. `wb doctor --record`: stored proof of life per harness and model

**Ask.** Configuring a harness must leave dated evidence that it worked with
the models listed for it: one small call and the recorded answer.

**Today.** `wb doctor --arms <models>` makes one cheap tool call per model
and prints OK/FAIL, cache probe and token counts; nothing is stored. The
skill's `harness test` writes `config/harnesses/proofs/<harness>@<model>.yaml`
from the printed lines.

**To build.** A `--record` flag on `wb doctor` that writes the proof file
itself (date, harness, model file, model id, provider, the fixed prompt, tool
call worked, cache reported, cost, `wb` commit) so the skill stops parsing
terminal output; `wb run`'s banner names pairs with no proof or a proof older
than 30 days (warning, never a gate).

## 3. Smaller items carried from features 002 to 006

- `wb_report/audiences.yaml`: the public allowlist matches the literal
  `monarch`; real rows are `monarch@<sha>[+branch]`, so a public report needs
  a `monarch@*` pattern before it can show Monarch. (PLAN.md §5)
- `config.py::_hashed_harness` keeps `release: null` in every harness hash so
  the two smoke runs of 3 Sep keep their config hash; drop that line the next
  time the hash is allowed to move and old runs are re-hashed.
- Monarch has no run-cancel route and no workflow-rename route: a timed-out
  execution is stopped only by deleting the workflow (create + run) or waiting
  it out (run-only); recipe names live on the bench side only.
- `MonarchArm._billed` (generations already priced, per episode) grows for the
  life of the arm; fine for a round, unbounded in principle.
- Seed generator: `example_value` of body fields and `entity_type` come from
  heuristics over the simulated apps' data; spot-check per app before relying
  on entity linking. Windows path length: the longest generated seed path is
  131 characters; keep the out folder shallow.
- GLM 5.3 through Fireworks is priced with Z.ai's list rates until the
  Fireworks rate is confirmed (`config/models/glm-5.3-fireworks.yaml`).
- `wb monarch setup` step 5 (product grants) is a static warning; the grant
  route is known now (`PUT /api/admin/product-access/orgs/<id>`), so the step
  can check and grant when a bench super-admin session is available.
- The 47 simulated apps' OpenAPI documents carry no request or response
  schemas; the seeds derive body fields from the AutomationBench data model
  and the corpus. When the documents gain schemas, prefer them.
- The conformance gate stops on any product service; buffer, canva and twitter (outside the four task sets) block a 47-app import. Gate should take the plan's services or an allowlist. Imported with --no-conform on 8 Sep.
- The public front door (ngrok tunnel to 9105) was down on 8 Sep and every Monarch dispatch got a 404 from ngrok; wb doctor must check the public URL answers with the shim's headers before a round (start a shim, curl the public URL).

## Stock Monarch Enterprise in the Studio: what the adapter cannot verify (8 Sep 2026)

**Today.** `wb_studio/enterprise.py` launches Default Monarch Enterprise only after a
verification probe (liveness, session, knowledge base, Langfuse) and names the build
from the checkout `monarch_repo` points at (`specs/011-monarch-runtime-integration/checkpoint-3.md`).

**Missing.** The provider path (Bedrock in the stock product) and the deployment's real
commit are not observable from the bench; both are recorded as declarations. A backend
route that reports its build identity and its model provider would close this. The
agentic-request track (`POST /api/operator/runs`) has no adapter. Per-node run values
are not fetched for the Activity lane.
## 4. Lab seeds and the PG-Waki knowledge (unblock plan M6, 8 Sep 2026)

- The knowledge lands in `business_action.description`, which the seed SPEC
  stores but does not serve to the builder today (SPEC §2: "not served to the
  builder"). Until Monarch's builder reads it (Deyton), the lab instance holds
  more words than the stock one and plans the same way. Argument semantics
  could also go into `constraints.helper_text`, the one prose field the builder
  does see per parameter; that changes parameter bytes and needs its own
  decision.
- 16 catalog entries have no bench action and are listed with reasons in the
  table's `notes` and in `KNOWLEDGE-MAPPING.yaml`. Two of them are seed gaps
  rather than missing routes: QuickBooks' `POST /vendor` and `POST /invoice`
  update or void when the body carries `Id`, and the seeds expose no `Id`
  parameter (`quickbooks_update_vendor`, `quickbooks_void_invoice`).
- Four bench products have no product paragraph in the catalog
  (facebook_conversions, facebook_lead_ads, linkedin_ads, linkedin_conversions)
  and 462 of the 686 actions have no entry; the catalog covers the Zapier
  "hard 50" tool set only.
- The lab set of 8 Sep was generated with the front door pinned to
  `http://host.docker.internal:9105` because `FRONT_DOOR_URL` is empty offline;
  regenerate with the lab instance's real front door before importing (T5.3).
- The vendored AutomationBench on this machine is plain `1.0.6`, while
  `tasks/achievable-50-manifest.yaml` declares `1.0.6+evalrepair.10`. The tests
  pass because `conftest.upstream_world` pins the installed world to the
  constant, but a real `wb run` over `achievable-50` would stop at the
  world-revision guard. Re-vendoring needs Lucas's patched source tree, which is
  not on this machine: `scripts/vendor_automation_bench.py --source <tree>
  --expect-version 1.0.6+evalrepair.10 --tree-id <id> --replace`, then `uv lock`
  and `uv sync`. The four tier sets and `check-collateral` declare no world
  revision, so they run unaffected. Seen 10 Sep 2026.
- `test_studio_runtime_controls.py::test_single_host_owner_excludes_other_process_and_releases_lock`
  fails on this machine: it spawns a subprocess with a 10 s timeout, and
  importing `wb_studio.runtime` alone takes 9.4 s here (measured), so the
  contender is killed before it can report the lock it correctly failed to take.
  The lock itself is fine; the margin is not. Raising the subprocess timeout, or
  importing less at module scope, would fix it. Lucas's test (bd2f2fa). Seen
  10 Sep 2026.
