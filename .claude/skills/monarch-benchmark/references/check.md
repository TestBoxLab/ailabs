# `check --product <p> --plan <n>` — is this round ready?

Everything the run command checks before spending, **without running the round**.
Use it after writing config files, or when a round failed and it is not obvious
which piece is missing.

All commands run from `monarch-benchmark/workflowbench/`. Report each step as
**OK** or **FALTA**, in Portuguese, and finish with one line: ready, or the list
of what is missing.

## 1. Resolve

```bash
uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env')
from wb_orchestrator import config
rc = config.resolve('config/products/<product>.yaml', 'config/plans/<plan>.yaml')
print('product', rc.product.name, rc.product.kind, len(rc.product.services), 'services')
print('mode', rc.plan.mode, 'prompts', len(rc.tasks), 'reps', rc.plan.repetitions)
print('per_competitor', rc.attempts_per_competitor, 'total', rc.attempts_total)
print('competitors', [c.name for c in rc.competitors], 'baseline', rc.plan.baseline)
print('models', sorted(rc.models), 'harnesses', sorted(rc.harnesses))
print('monarch_kb', rc.monarch_kb is not None, 'recipes', rc.monarch_recipes is not None)
print('audience', rc.plan.audience, 'ceiling', rc.plan.cost_ceiling_usd, 'approved_by', rc.plan.approved_by)
print('hash', rc.hash)
"
```

If this raises, **show the `ConfigError` verbatim and stop** — every later step
depends on a config that resolves. Resolve already enforces the key checks, the
Monarch address checks, the smoke-scale rule and the baseline rule, so a clean
resolve is most of the answer.

Report the three attempt numbers the same way the run command does:
*tentativas por prompt e competidor · prompts · por competidor*.

## 2. `.env` variables

Every name the round needs, checked for presence, **never printed**:

```bash
uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env')
import os
from wb_orchestrator import config
rc = config.resolve('config/products/<product>.yaml', 'config/plans/<plan>.yaml')
names = {m.key_env for m in rc.models.values()}
import re
for h in rc.harnesses.values():
    for f in ('credential_env', 'login_password_env', 'fd_api_key_env',
              'langfuse_public_key_env', 'langfuse_secret_key_env'):
        if getattr(h, f, None): names.add(getattr(h, f))
    for f in ('base_url', 'fd_url', 'langfuse_url', 'shim_public_url'):
        names.update(re.findall(r'\\\$\{(\w+)\}', getattr(h, f, None) or ''))
for n in sorted(names):
    print(('OK   ' if os.environ.get(n) else 'FALTA'), n)
"
```

`credential_env` and `login_password_env` are alternatives — one of the two is
enough for Monarch.

## 3. Doctor — asks first, costs cents

```bash
uv run wb doctor --arms <the plan's model names, comma-joined>   # add ,monarch when Monarch is a competitor
```

**Do not run it without a yes.** Say exactly this before asking:
*"O doctor faz uma chamada de teste por modelo — \<N\> modelos, custa centavos.
Rodo? (sim/não)"* On "não", say the step was skipped and carry on with the rest.

Show the OK/FAIL lines as printed. `tool_call_works: True` is the pass; repeat
any `cache_warning`, because it means a paid round should not be planned
assuming cache savings on that provider.

## 4. Proof of life

Show the last stored proof for each harness+model pair the plan names, from
`config/harnesses/proofs/<harness>@<model>.yaml` (see `references/harness.md`):

```bash
uv run python -c "
import datetime, yaml
from pathlib import Path
today = datetime.date.today()
pairs = [('api', 'claude-opus-5')]   # from the plan's competitors
for h, m in pairs:
    pf = Path(f'config/harnesses/proofs/{h}@{m}.yaml')
    if not pf.is_file():
        print(f'SEM PROVA  {h}@{m}'); continue
    d = yaml.safe_load(pf.read_text(encoding='utf-8'))
    age = (today - d['date']).days
    print(('VELHA ' if age > 30 else 'OK    ') + f'{h}@{m}  {d[\"date\"]} ({age} dias)  {d.get(\"answer\")}')
"
```

**This is a warning, not a gate.** A round runs without a proof; the
confirmation block just says *"sem prova de vida para \<par\>"*. Offer
`harness test <harness> --model <name>` to record one.

## 5. Monarch block — only when a Monarch competitor is in the plan

- Knowledge base: `config/products/<product>.monarch-kb.yaml` must exist. Resolve
  already fails without it; if it is missing, say to run
  `uv run wb monarch setup --product <product>`.
- In `run-only` mode, also `config/products/<product>.monarch-recipes.yaml`,
  from `uv run wb monarch recipes`.
- Monarch must be up:
  `bash C:/Users/cgmat/Desktop/TestBox/monarch/local-docs/setup/scripts/railway-ops.sh status`
  (`unlock` if it is locked).
- The front door behind `FRONT_DOOR_URL` must be reachable:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "$FRONT_DOOR_URL"
```

  **200** = the tunnel is up. **502** = the tunnel answers but the front door
  behind it is down — that is the normal reading when no round is running, so
  report it as *"túnel de pé, porta da frente desligada"*, not as a failure.
  Anything else (000, a timeout) means the tunnel itself is down: restart ngrok,
  and if its host changed, rerun `wb monarch setup`.

## 6. Verdict

One block, in Portuguese: each step OK or FALTA, then either

> **Pronto para rodar.** `/monarch-benchmark --product <product> --plan <plan>`

or the numbered list of what is missing and which command fixes each one.
**`check` never runs the round**, even when everything is green.
