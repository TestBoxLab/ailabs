# Handoff prompt — continue the AI Labs bench work in Codex

Copy everything below the line into a fresh Codex session (GPT-6 Astra) opened at
`C:\Users\cgmat\Desktop\TestBox\ailabs`. Written 10 September 2026 by the Claude
session that did the work described.

---

You are continuing work on the TestBox AI Labs benchmark. Read this whole brief
before touching anything.

## Where to get your bearings

Read, in this order:

1. `AGENTS.md` — the working agreement. Your instructions.
2. `monarch-benchmark/docs/HOW-WORKFLOWBENCH-WORKS.md` — how the machine works:
   what an attempt is, the two judges, how a round is read. Every claim cites a
   file and line.
3. `monarch-benchmark/docs/STATE-OF-THE-PROGRAM.md` — where things stand.
   **Section 12 is the session you are continuing**: the six defects found, what
   was fixed, and what is still open, in priority order.
4. `monarch-benchmark/docs/BOUNDARY-BENCH-AND-MONARCH.md` — who owns which data.
5. `CLAUDE.md` — project rules. It is longer than `AGENTS.md` and carries the
   methodology, the file map and the plain-names glossary. **Task 1 below is to
   reconcile the two.**

## What this project is

A recurring benchmark of **Monarch** (TestBox's product: it maps a SaaS platform
and turns a plain-language request into a runnable workflow) against raw language
models and coding agents doing the same tasks. The code is **WorkflowBench**, a
Python CLI called `wb`, under `monarch-benchmark/workflowbench/`.

Rules that every change must respect (`PLAN.md` §1.1): the same request text for
every competitor; nothing grades itself; pass = expected result present AND
nothing else changed AND normal finish; every task frozen by hash before any
competitor runs; cost is complete; API-key billing only.

## Environment

- Python 3.13 managed by `uv`. Always `uv run`, never bare `python`.
  ```
  cd monarch-benchmark/workflowbench
  uv run python -m pytest tests -q          # about 27 minutes, 1900+ tests
  ```
- Windows. The full suite is slow: run it detached and wait, never inside a
  10-minute tool call.
- Secrets in `monarch-benchmark/workflowbench/.env` (gitignored). `wb` loads it
  itself, so **`wb run` is never a free validation check** — it spends money.
- AutomationBench is vendored at `workflowbench/vendor/automation-bench`
  (gitignored, re-clonable).
- Sibling Monarch checkout at `../monarch`, Railway project `monarch-dev`.

## Money and approval

- **Either Carlos or Lucas approves a paid round.** An agent never approves its
  own: the name on the approval is the person who asked for it.
- Every paid launch sets `WB_OPERATOR="<name>"`.
- Smoke scale (at most 20 attempts per competitor) needs no approval record.
- Weekly ledger: US$ 300, `research/budget.sqlite3`.
- **Before any `wb run`, state the number of attempts and a cost band.**

## Language

Conversation with Carlos in **Portuguese**. Every file in the repository in
**English** — no exceptions, including comments and commit messages. In prose and
config use the plain names, not the code identifiers: *competitor* not arm, *task
set* not suite, *attempt* not episode, *approval rule* not contract/invariant,
*answer key* not oracle.

---

# Your three tasks

## Task 1 — make the repository work for Codex

`AGENTS.md` exists but carries only the working agreement. `CLAUDE.md` carries the
methodology, the file map, the plain-names glossary, the benchmark-specific rules
and the pipeline. A Codex session reading only `AGENTS.md` would miss most of it.

Reconcile them so **nothing about method, tooling or governance changes just
because the harness changed**. Specifically:

- Everything in `CLAUDE.md` that is a *rule* or a *fact about this repository*
  must be reachable from `AGENTS.md` — either inlined or by an explicit pointer.
- The eleven project skills under `.claude/skills/` are Claude-specific
  (`monarch-benchmark`, and ten `speckit-*`). Codex cannot invoke them. Decide,
  and write down, what a Codex session does instead: the `speckit-*` skills are
  a spec→plan→tasks pipeline, and `monarch-benchmark` is a round-preparation
  helper. Record the equivalent procedure in prose so the method survives.
- `.specify/memory/constitution.md` governs all features. Make sure `AGENTS.md`
  points at it.
- Do not delete the Claude-specific files. Carlos may return to a Claude session.

Verify by reading `AGENTS.md` alone and asking whether you could run a round
correctly. If not, it is not done.

## Task 2 — keep fixing what is plainly broken

Carlos's ruling, 10 September: **the remaining items are operational corrections
of things that are certainly wrong, not differences of approach, so they do not
need Lucas's sign-off.** Fix them.

In priority order:

1. **Why does Monarch read and not write?** This is the live question. After the
   front-door migration, one attempt on `simple.airtable_find_update` reached
   `completed` with two `GET /airtable/base_crm/Contacts` at 200 — and wrote
   nothing (`n_changes=0`). The suspected cause: the AutomationBench Airtable
   mock does not evaluate `filterByFormula`, so a "does a VIP already exist?"
   lookup returns the existing non-VIP record and the builder concludes there is
   nothing to create. **Confirm or refute this against the vendored mock before
   spending on any round** — a round would otherwise measure the same trap four
   times. If confirmed, the fix is in `vendor/automation-bench`.

2. **`simple.invoice_airtable_slack` has a weak assertion.** It pins the table
   but neither the vendor nor the amount, so an invoice with the wrong vendor and
   amount satisfies the positive half. The vendor's own handler supports a
   `fields` payload; the task omits it. Add it, then re-derive that task's rule
   and record the hash move in `docs/rounds/`.

3. **Two Jira tasks stay collateral-blind** — `simple.jira_auth_improvements`
   and `simple.new_lead_sf_jira`. Their assertions carry no content for a `where`
   clause to pin, so an unrequested Jira write is invisible. Decide whether to
   strengthen the assertions (a data change, like item 2) or to accept the limit
   and record it.

4. **Re-vendor AutomationBench.** The tree here is plain `1.0.6`;
   `tasks/achievable-50-manifest.yaml` declares `1.0.6+evalrepair.10` and a real
   run over that set stops at the world-revision guard. The patched source was
   not on this machine as of 10 September — ask Carlos where it is, then:
   ```
   uv run python scripts/vendor_automation_bench.py --source <tree> \
       --expect-version 1.0.6+evalrepair.10 --tree-id <id> --replace
   uv lock && uv sync
   ```
   The four tier sets are unaffected; only `achievable-50` is blocked.

5. **`workflowbench/deferred.md`** holds the rest.

### How to work on this code

The six defects fixed on 9–10 September were all found by **running the frozen
tasks against the simulator**, never by reading them. Two sweeps were discarded
first for being heuristics — one reported 1,168 false positives. A pattern over
task files is a hypothesis; a reproduction against the world is evidence.

Everything runs in-process and costs nothing:

```python
from wb_world.episode import Episode, load_task_file
from wb_world.snapshot import diff_snapshots
from grader.grade import grade
task = load_task_file("tasks/tier-simple/simple.airtable_find_update.json")
ep = Episode(task, episode_id="probe"); s0 = ep.snapshot()
ep.api_fetch("POST", "https://api.airtable.com/v0/base_crm/Contacts", body="...")
print(grade(task, s0, ep.snapshot()))
```

Strict TDD: write the failing test first, watch it fail **for the right reason**,
then fix. Several defects survived for weeks because a synthetic fixture asserted
the wrong shape.

## Task 3 — redeploy Monarch on Railway

Carlos merged the remote Monarch `main` into his working branch in the parallel
`monarch/monarch` repository, with fixes for problems that were affecting the AI
Labs benchmark. **That merged branch is the version the benchmark must run
against**, so Railway has to be redeployed from it.

`monarch-benchmark/docs/rounds/2026-09-10-fdapi-deploy-runbook.md` has the
procedure. It was written for an `fdapi`-only deploy — Carlos's merge is larger,
so **first determine which services the changed files belong to** and deploy only
those:

```bash
cd ../monarch
git log --oneline -5 && git status -sb
git diff --name-only <last-deployed-sha>..HEAD | cut -d/ -f1 | sort -u
```

Then, per the runbook:

```bash
export PATH="/c/Users/cgmat/AppData/Roaming/npm:$PATH"
railway whoami && railway status          # personal account, monarch-dev, production
railway up --service <service> --detach   # rebuild, 5 to 12 minutes
```

Three cautions:

- **`railway up` uploads the working tree, not a git ref.** An uncommitted edit
  ships silently. As of 10 September `.gitignore` and
  `feature-discovery/api/src/app.ts` were modified — decide about each.
- Deploy is never from GitHub: the branch stays local.
  `railway service redeploy` reuses the previous image and would not carry new code.
- **After deploying, the catalogue must be unchanged**: 47 products, 686 actions,
  47 in sync (`bash ../monarch/local-docs/setup/scripts/bench-seeds.sh status`).
  If it moved, the knowledge base must be re-imported before any attempt, and
  that moves the config hash of every plan carrying it.

Then verify end to end:

```bash
cd monarch-benchmark/workflowbench
uv run wb monarch verify                  # six checks, front_door included
WB_OPERATOR="<name>" uv run wb run --product simulated-apps --plan diag-front-door
```

That plan is one attempt, no retry, about US$ 2–3. Read `terminations` (should be
`completed`) and the attempt's `front-door.jsonl` (should carry `/airtable/...`
calls, not only `/openapi/index.json`).

---

## State as you inherit it

- **PR #3** is open: https://github.com/TestBoxLab/ailabs/pull/3 — 52 commits on
  `ailabs/collateral-judge`, merges cleanly with `main` (verified after PR #2
  landed; the two sides touch only `CLAUDE.md` and `wb_studio/app.py`, and in
  `app.py` they do not overlap).
- Suite: **1905 passed, 1 failed**. The failure is a Studio HTTP-timing flake on
  Windows — it names a different test each run and passes in isolation. CI runs
  on ubuntu-latest, where it does not appear. Do not chase it.
- The front door is migrated to the hosted Studio. The ngrok tunnel is still the
  pipe to this machine (`STUDIO_FRONT_DOOR_TARGET` on the Railway service), and
  it must be running for a CLI round:
  ```
  ngrok http --domain=imputable-tracklessly-kellan.ngrok-free.dev 127.0.0.1:9105
  ```
  `out/front_door_watch.sh` alerts if it goes quiet. It went down mid-round on
  9 September and cost US$ 9.91 in attempts that measured nothing.

## One thing to carry with you

The bench now refuses more than it used to: knowledge-base drift, front-door
disagreement, a missing operator name, a world revision. **Every one of those was
added because something silently measured nothing.** When a refusal fires, read it
before working around it.
