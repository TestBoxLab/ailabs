# WorkflowBench report — eog-ctl

suite `enterprise-ops-gym@271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle` · config `1b289e61ebc68d9f86d75894f0a382bc29a0a48be0cba5ef4bfc4daf88320034` · k=1

Tasks: enterprise-ops-gym 271f2c357f763376997dfd16807fcde2474ae41b, split itsm/oracle. The source supplies SQL verifiers over stored final SQLite databases using the source comparison semantics; WorkflowBench checks that nothing else changed and requires normal completion. These results are not the source benchmark's published score.

EnterpriseOps-Gym publishes no reference solution. No answer-key ceiling is asserted; the initial task set uses reviewed rules for permitted changes.

## Per-arm results

| arm | strict pass ± SEM | first try | after retry | retries | pass^k | infra rate | cache hit | cost (USD) |
|---|---|---|---|---|---|---|---|---|
| `setup-validation-correct` | 100.0% ± 0.0% | 100.0% ± 0.0% | 100.0% ± 0.0% | 0 | 100.0% ± 0.0% | 0.0 | n/a | 0.0 |
| `setup-validation-null` | 0.0% ± 0.0% | 0.0% ± 0.0% | 0.0% ± 0.0% | 0 | 0.0% ± 0.0% | 0.0 | n/a | 0.0 |
  
  `src: enterprise-ops-gym@271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle · v271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle · n=2 · setup-validation-correct · eog-ctl` · contracts: 19c9eb51, 1ee0cd10
  
  `src: enterprise-ops-gym@271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle · v271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle · n=2 · setup-validation-null · eog-ctl` · contracts: 19c9eb51, 1ee0cd10

## Paired comparisons

- `setup-validation-correct` vs `setup-validation-null`: **2W / 0L** (both 0, neither 0, infra-dropped 0) · McNemar b=2 c=0 p=0.4795
  `src: enterprise-ops-gym@271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle · v271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle · n=2 · setup-validation-correct+setup-validation-null · eog-ctl`
