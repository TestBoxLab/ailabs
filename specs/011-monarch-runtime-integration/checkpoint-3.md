# Checkpoint 3: stock Enterprise adapter and the live workflow view

8 September 2026. Private local changes under `monarch-benchmark/workflowbench`; no push,
deployment, publication or paid experiment. Everything below ran against the offline fakes
(Monarch backend, discovery service, Langfuse); no real Monarch was contacted.

## What now actually executes

The Studio can launch **Default Monarch Enterprise** as a comparison version. It drives the
same competitor the CLI rounds used (`wb_arms/monarch.py`: create + run through Monarch's
own API, every application call through the bench's front door, cost read from Langfuse),
so a Studio attempt and a `wb run` attempt are the same measurement. What is new is what
you can see while it runs and what must be true before it may run.

| Piece | Before | Now |
|---|---|---|
| Launch | Refused with `adapter_required` | Allowed once a verification probe has passed against the deployment the harness names; refused otherwise, with the failing check named |
| Identity | "Default Monarch Enterprise", a GitHub pin only | `monarch@<sha>` from the checkout `monarch_repo` points at; `+<branch>` and `*` (dirty tree) mark a **custom build**, which is never called stock |
| Activity lane | Nothing (no Monarch attempts existed) | Two steps, *Build the workflow* and *Run the workflow*; one node per builder frame; the recipe's nodes drawn when the run starts and recoloured as the engine reports them; every front-door call as an application-action node |
| Run progress | Status polled every 2 s, `steps` discarded | The stock engine stream (`GET /api/engine/runs/:id/stream`) followed to the terminal frame; a backend without the route falls back to polling; either way every node whose state moved is reported |
| Budget | Not in the weekly ledger | A ceiling (`MONARCH_ATTEMPT_CEILING_USD`, default 25.00) is reserved and claimed before Monarch is called and settled with the Langfuse total; an unreadable cost keeps the hold and flags `billing=unknown` |

Still not verified, and said so in the picker and the manifest:

- **Provider path.** The stock product bills through Bedrock; the bench cannot observe what a
  deployment is wired to. The manifest records the price table's provider as a declaration
  (`provider_declared_not_observed: true`). The 4 to 6 Sep rounds ran a Railway branch with
  direct Anthropic keys; that is a custom build under this rule.
- **Served build.** The name comes from the local checkout, exactly as `wb run` names it. The
  deployment is assumed built from that checkout; nothing in the backend exposes its commit.
- **Engine stream on a real deployment.** Verified against the fake, which follows
  `engine.controller.ts` at the pinned commit; the Railway edge cut long SSE responses in
  the past, and the fallback to polling exists for that reason.

## Code

- `wb_arms/monarch_client.py`: `run_stream()` (engine SSE, same parser as the authoring
  stream), `run_recipe()`.
- `wb_arms/monarch.py`: `observer` hook (`authoring_started/frame/reply/finished`,
  `run_started/step/finished`); `_follow_run()` streams then polls; `_run_update()` diffs
  `steps` and logs each distinct view; `partial`, `blocked` and `done` are terminal.
- `wb_arms/http_shim.py`: the front door binds without a reverse DNS lookup (each bind
  stalled for seconds on this machine; 40 attempts took minutes).
- `wb_studio/enterprise.py` (new): `Setup` (harness, product, knowledge base, price table,
  environment, checkout identity), `verify()` and the stored probe, three-axis
  `readiness()`, the frozen runtime `manifest()`, `EnterpriseArm` (observer → Activity
  events, ledger reserve/settle, refusal on a moved identity).
- `wb_studio/runtime_registry.py`: the stock version's readiness comes from the probe; the
  GitHub pin stays the source axis.
- `wb_studio/app.py`: enterprise arm kind; `GET /api/architectures/enterprise`;
  `POST /api/architectures/enterprise/verify`.
- `wb_studio/static/app.js`, `style.css`: `workflow_recipe` / `workflow_step` events, builder
  and workflow node categories, pending/skipped states, the verify button and status in the
  launch dialog, the create-and-run wording in the review step.
- `tests/fake_monarch.py`: `Scenario.run_views`, the engine stream route, the run recipe route.

## How to use it

1. Clone `TestBoxLab/monarch` where `config/harnesses/monarch.yaml` says (`monarch_repo:
   ../../../monarch`) and check out the commit the deployment was built from. Without it the
   version is blocked: the build cannot be named.
2. Put `MONARCH_URL`, `MONARCH_FD_URL`, `MONARCH_PASSWORD` (or `MONARCH_TOKEN`),
   `LANGFUSE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` in `.env`; optionally
   `MONARCH_ATTEMPT_CEILING_USD`. `wb monarch setup` must have written the knowledge-base file.
3. New run → Approaches → **Verify Monarch connection**. The probe checks liveness, health
   with a session, the knowledge base Monarch holds against the frozen file, and Langfuse. It
   starts no authoring run and costs nothing. It expires after two hours or when the checkout
   moves.
4. Select the version, review (the run budget must cover one attempt's ceiling), start.
   Open Activity to watch the builder and the recipe nodes.

## Evidence

| Check | Result |
|---|---|
| `tests/test_monarch_live.py` (client stream, arm observer, poll fallback, failed run, question) | 7 passed |
| `tests/test_studio_enterprise.py` (readiness, probe, custom build, one attempt end to end, unknown cost, budget floor, moved checkout) | 8 passed |
| Registry, comparison modes, execution, app, client suites | 102 passed |
| Monarch arm, run-only, recipes, doctor suites | see the full-suite line below |
| Whole `tests/` directory | recorded in the session summary; `test_pilot_plan_offline` was run separately because of the DNS stall it exposed, now fixed in the shim |
| Browser (rehearsal Studio on port 8766 against the fakes) | Verify button ran the probe and flipped the version to launchable; one attempt showed both steps, two builder nodes, two recipe nodes ending *Done*, the Salesforce PATCH as an application action, and *All task checks passed* |

## Not done

- Bedrock access and a stock `main` deployment: the adapter refuses nothing on that axis
  because it cannot see it; the label and the manifest carry the declaration instead.
- The agentic-request track (`POST /api/operator/runs`) is not wired; only create + run.
- Blueprint `monarch` nodes still do not execute; the stock version is a whole-arm identity.
- Per-node run values (`GET /api/workflows/runs/:id/nodes/:nodeId/values`) are not fetched;
  the lane shows each node's status, message and progress, not its stored values.
