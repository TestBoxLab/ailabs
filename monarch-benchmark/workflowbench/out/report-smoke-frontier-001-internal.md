# WorkflowBench report — smoke-frontier-001

audience: **internal** · suite `workflowbench-synthetic@0.1` · config `69bcbf692feb7bdb` · k=2

## Per-arm results

| arm | strict pass ± SEM | pass^k | infra rate | cache hit | cost (USD) |
|---|---|---|---|---|---|
| `bare/api/claude-opus-4-8` | 90.0% ± 10.0% | 90.0% ± 10.0% | 0.0 | 0.7692 | 1.39275 |
| `bare/api/gpt-5.6-sol` | 100.0% ± 0.0% | 100.0% ± 0.0% | 0.0 | 0.7453 | 0.536164 |
| `oracle/scripted` | 100.0% ± 0.0% | 100.0% ± 0.0% | 0.0 | n/a | 0.0 |
  
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · bare/api/claude-opus-4-8 · smoke-frontier-001` · contracts: 4a2dd47d, 7a0ebbef, 9ab50a80, b9cc657f, ba820706, d44c785a, defdeebf, e327964c, e4a3adbe, e747c8f6
  
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · bare/api/gpt-5.6-sol · smoke-frontier-001` · contracts: 4a2dd47d, 7a0ebbef, 9ab50a80, b9cc657f, ba820706, d44c785a, defdeebf, e327964c, e4a3adbe, e747c8f6
  
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · oracle/scripted · smoke-frontier-001` · contracts: 4a2dd47d, 7a0ebbef, 9ab50a80, b9cc657f, ba820706, d44c785a, defdeebf, e327964c, e4a3adbe, e747c8f6

## Paired comparisons

- `bare/api/gpt-5.6-sol` vs `bare/api/claude-opus-4-8`: **2W / 0L** (both 18, neither 0, infra-dropped 0) · McNemar b=2 c=0 p=0.4795
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · bare/api/gpt-5.6-sol+bare/api/claude-opus-4-8 · smoke-frontier-001`
- `oracle/scripted` vs `bare/api/claude-opus-4-8`: **2W / 0L** (both 18, neither 0, infra-dropped 0) · McNemar b=2 c=0 p=0.4795
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · oracle/scripted+bare/api/claude-opus-4-8 · smoke-frontier-001`
