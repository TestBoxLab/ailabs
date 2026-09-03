# WorkflowBench report — run-20260903-000243

audience: **internal** · suite `workflowbench-synthetic@0.1` · config `02bb91bf0f18d1bf` · k=1

## Per-arm results

| arm | strict pass ± SEM | pass^k | infra rate | cache hit | cost (USD) |
|---|---|---|---|---|---|
| `claude-opus-4-8/api` | 90.0% ± 10.0% | 90.0% ± 10.0% | 0.0 | 0.7357 | 1.312227 |
| `gpt-5.6-sol/api` | 100.0% ± 0.0% | 100.0% ± 0.0% | 0.0 | 0.8104 | 0.804594 |
| `oracle` | 100.0% ± 0.0% | 100.0% ± 0.0% | 0.0 | n/a | 0.0 |
  
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · claude-opus-4-8/api · run-20260903-000243` · contracts: 4a2dd47d, 7a0ebbef, 9ab50a80, b9cc657f, ba820706, d44c785a, defdeebf, e327964c, e4a3adbe, e747c8f6
  
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · gpt-5.6-sol/api · run-20260903-000243` · contracts: 4a2dd47d, 7a0ebbef, 9ab50a80, b9cc657f, ba820706, d44c785a, defdeebf, e327964c, e4a3adbe, e747c8f6
  
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · oracle · run-20260903-000243` · contracts: 4a2dd47d, 7a0ebbef, 9ab50a80, b9cc657f, ba820706, d44c785a, defdeebf, e327964c, e4a3adbe, e747c8f6

## Paired comparisons

- `gpt-5.6-sol/api` vs `claude-opus-4-8/api`: **2W / 0L** (both 18, neither 0, infra-dropped 0) · McNemar b=2 c=0 p=0.4795
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · gpt-5.6-sol/api+claude-opus-4-8/api · run-20260903-000243`
- `oracle` vs `claude-opus-4-8/api`: **2W / 0L** (both 18, neither 0, infra-dropped 0) · McNemar b=2 c=0 p=0.4795
  `src: workflowbench-synthetic@0.1 · v0.1 · n=20 · oracle+claude-opus-4-8/api · run-20260903-000243`
