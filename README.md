# TestBox AI Labs

Internal lab for evaluating and improving TestBox's AI products. Leads: Lucas Wakigawa and Carlos Mattos.

Current direction: [AI Labs direction](docs/AI-LABS-DIRECTION.md). Implementation: [foundation plan](specs/007-lab-foundation/plan.md). Research pipeline: [Trello](https://trello.com/b/ntJfbkLx/ai-labs-research-experiments).

## Projects

| Folder | What it is | Start here |
|---|---|---|
| `monarch-benchmark/` | Benchmark of Monarch against off-the-shelf models and agents (WorkflowBench) | `monarch-benchmark/PLAN.md`, then `monarch-benchmark/docs/ai-labs-context.html` |

## Conventions

- Every file in this repository is written in English.
- Current scientific decisions live in docs/AI-LABS-DIRECTION.md; implementation plans and versioned evidence link to the Trello research pipeline. Historical plans retain their original context.
- Experiments have a USD 300 weekly budget. Paid launches require verified shared reservations and billing; the atomic ledger and bounded Studio Gemini dispatch are implemented; valid credentials and provider invoice reconciliation remain outstanding. See [implementation status](specs/007-lab-foundation/implementation.md). CI and local setup use offline checks.

## Local run workspace

Start from this repository:

```powershell
uv run --project monarch-benchmark/workflowbench --frozen wb studio --port 8765
```

Open http://127.0.0.1:8765. **New run** offers all 800 imported AutomationBench
requests grouped by category, model reasoning variants, additional prompt instructions,
and a shared run budget. Overview leads with task requirements and scope changes;
Activity and Raw evidence preserve the execution detail.

**Monarch setups** saves immutable architecture/prompt experiment drafts based on
Monarch_Main presets. These drafts are not executable until the Monarch adapter and
runtime snapshot are implemented. They do not modify Monarch_Main or frozen presets.

Optional reasoning review uses Gemini medium, cites retained events, and draws from
the same run and weekly budget. It does not override grading. Sol medium analysis
and native Claude Code/Codex execution are not connected. Credentials are now configured. The approved Google pilot passed at an estimated
$0.017971; native and Fireworks execution remain pending.

See [outcome workspace implementation](specs/009-outcome-workspace/implementation.md)
for evidence, controls, and remaining integration work.


The [node architecture editor](specs/010-node-architectures/implementation.md) adds
connected graph enrichment, agents, prompt changes and versioned publication.
Fireworks model discovery is connected (306 models at the last refresh); the first
approved Google pilot passed at an estimated $0.017971. Published graph execution,
native harnesses and Fireworks inference remain separate pending integrations.
