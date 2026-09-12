# Sierra tau2 adapter

The source environment and grader run with `.external/tau2-env/Scripts/python.exe`
on Windows (set `WB_TAU2_PYTHON` elsewhere), outside WorkflowBench's dependency
environment. `WB_TAU2_ROOT` names the unchanged Sierra checkout; default
`.external/tau2-bench`. Version 1.0.1 at revision
`2174a603f6d014ef94473ffa95957f6ce27100db` is the current frozen source.

Run `wb_worlds/tau2/server.py` with that source Python, a private
`WB_TAU2_ADMIN_TOKEN`, `PYTHONUTF8=1`, and `PYTHON_DOTENV_DISABLED=1`. It binds localhost:18082 by
default; `WB_TAU2_URL` can point to a different private bind. The administration
token is host-only and must never enter native sandbox or Monarch application
credentials. `/health` reports readiness. Every attempt receives its own
in-memory source environment, even when an episode identifier is reused.

The adapter publishes the source domain operations and one common
`POST /tau2-retail/send_message` operation. That operation is the customer's
interface for both competitors. Its private prompt is built by the unchanged
Sierra UserSimulator. `attach_customer(callback, participant)` requires a callback
from the existing reserved provider path; no model calls originate in the source
server. The callback receives `{messages, tools, model, max_tokens}` and returns
`{content, tool_calls, usage, cost_usd}`. Tool calls have `id`, `name`, and an
`arguments` object. Participant inference shares the attempt's admitted budget.

Before finalization, call `set_termination(termination)` with WorkflowBench's
actual harness outcome. `finish()` writes `tau2-trajectory.json`; `close()` then
releases the private world. `positive_check` uses a separate source subprocess to
strictly replay saved mutating operations, verify the initial/final snapshots and
execute Sierra's unchanged `EvaluationType.ALL` reward. Read-only output bytes
remain protected by WorkflowBench's evidence manifest; upstream strict replay
intentionally replays only mutations. The source reward and WorkflowBench's
permitted-change result are retained separately.

## Two-task smoke

`config/products/tau2-retail.yaml` and
`config/plans/smoke-tau2-retail.yaml` select frozen source tasks 33 and 34 in
`tasks/tau2-retail-smoke/`. They change a default profile address and a pending
order address respectively. `smoke_rules.json` permits exactly five address
fields on the named source entity; it authorizes no other records, fields or
side effects. Source task records, policies, databases and reward definitions
are unchanged. Import refuses unreviewed task rules and differing frozen files.

The two tasks test integration and policy-dependent customer interaction. They
are related scenarios for one customer and are not a representative performance
sample. They use the original DB-only reward; tau2 in general can also grade the
trajectory. Do not pool these results with AutomationBench, EnterpriseOps-Gym,
AppWorld, a different tau2 split or an upstream leaderboard.

Free source-backed verification (PowerShell):

```powershell
$env:WB_TAU2_LIVE = '1'
uv run python -m pytest tests/test_tau2_live.py tests/test_tau2_import.py tests/test_worlds_tau2.py -q
```

These checks use scripted customer replies and source reference actions only for
adapter verification. They are not evaluated competitor attempts and make no
provider calls. The live paid smoke still requires the ordinary budget,
Monarch verification, isolated native acceptance and evidence gates.
