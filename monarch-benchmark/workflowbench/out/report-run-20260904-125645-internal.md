# WorkflowBench report — run-20260904-125645

audience: **internal** · suite `workflowbench-synthetic@0.1` · config `a5d4e4135f3f2385` · k=2

## Per-arm results

| arm | strict pass ± SEM | pass^k | infra rate | cache hit | cost (USD) |
|---|---|---|---|---|---|
| `claude-opus-5/api` | 90.0% ± 10.0% | 90.0% ± 10.0% | 0.0 | 0.8218 | 1.398598 |
| `gpt-5.6-sol/api` | 95.0% ± 5.0% | 90.0% ± 10.0% | 0.0 | 0.8254 | 0.75068 |
| `kimi-k3-fireworks/api` | 80.0% ± 13.3% | 80.0% ± 13.3% | 0.0 | 0.8189 | 1.001891 |
| `oracle` | 100.0% ± 0.0% | 100.0% ± 0.0% | 0.0 | n/a | 0.0 |
  
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · claude-opus-5/api · run-20260904-125645` · contracts: 4a2dd47d, 7a0ebbef, 9ab50a80, b9cc657f, ba820706, d44c785a, defdeebf, e327964c, e4a3adbe, e747c8f6
  
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · gpt-5.6-sol/api · run-20260904-125645` · contracts: 4a2dd47d, 7a0ebbef, 9ab50a80, b9cc657f, ba820706, d44c785a, defdeebf, e327964c, e4a3adbe, e747c8f6
  
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · kimi-k3-fireworks/api · run-20260904-125645` · contracts: 4a2dd47d, 7a0ebbef, 9ab50a80, b9cc657f, ba820706, d44c785a, defdeebf, e327964c, e4a3adbe, e747c8f6
  
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · oracle · run-20260904-125645` · contracts: 4a2dd47d, 7a0ebbef, 9ab50a80, b9cc657f, ba820706, d44c785a, defdeebf, e327964c, e4a3adbe, e747c8f6

## Paired comparisons

- `gpt-5.6-sol/api` vs `claude-opus-5/api`: **1W / 0L** (both 18, neither 1, infra-dropped 0) · McNemar b=1 c=0 p=1.0
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · gpt-5.6-sol/api+claude-opus-5/api · run-20260904-125645`
- `kimi-k3-fireworks/api` vs `claude-opus-5/api`: **0W / 2L** (both 16, neither 2, infra-dropped 0) · McNemar b=0 c=2 p=0.4795
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · kimi-k3-fireworks/api+claude-opus-5/api · run-20260904-125645`
- `oracle` vs `claude-opus-5/api`: **2W / 0L** (both 18, neither 0, infra-dropped 0) · McNemar b=2 c=0 p=0.4795
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · oracle+claude-opus-5/api · run-20260904-125645`
