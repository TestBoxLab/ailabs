# WorkflowBench report — pilot-m1-001

audience: **internal** · suite `workflowbench-synthetic@0.1` · config `8f94150357149cbd` · k=2

## Per-arm results

| arm | strict pass ± SEM | pass^k | infra rate | cache hit | cost (USD) |
|---|---|---|---|---|---|
| `bare/api/kimi-k3-fireworks` | 90.0% ± 10.0% | 90.0% ± 10.0% | 0.0 | 0.6923 | 0.746911 |
| `oracle/scripted` | 100.0% ± 0.0% | 100.0% ± 0.0% | 0.0 | n/a | 0.0 |
  
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · bare/api/kimi-k3-fireworks · pilot-m1-001` · contracts: 4a2dd47d, 7a0ebbef, 9ab50a80, b9cc657f, ba820706, d44c785a, defdeebf, e327964c, e4a3adbe, e747c8f6
  
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · oracle/scripted · pilot-m1-001` · contracts: 4a2dd47d, 7a0ebbef, 9ab50a80, b9cc657f, ba820706, d44c785a, defdeebf, e327964c, e4a3adbe, e747c8f6

## Paired comparisons

- `bare/api/kimi-k3-fireworks` vs `oracle/scripted`: **0W / 2L** (both 18, neither 0, infra-dropped 0) · McNemar b=0 c=2 p=0.4795
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · bare/api/kimi-k3-fireworks+oracle/scripted · pilot-m1-001`
