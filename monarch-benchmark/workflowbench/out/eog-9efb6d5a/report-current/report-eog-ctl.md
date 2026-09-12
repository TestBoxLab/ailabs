# WorkflowBench report — eog-ctl

suite `enterprise-ops-gym@271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle` · config `1b289e61ebc68d9f86d75894f0a382bc29a0a48be0cba5ef4bfc4daf88320034` · k=1

Tasks: enterprise-ops-gym 271f2c357f763376997dfd16807fcde2474ae41b, split itsm/oracle. The source supplies SQL verifiers over stored final SQLite databases using the source comparison semantics; WorkflowBench checks that nothing else changed and requires normal completion. These results are not the source benchmark's published score.

EnterpriseOps-Gym publishes no reference solution. No answer-key ceiling is asserted; the initial task set uses reviewed rules for permitted changes.

This two-task smoke checks integration and grading. It does not estimate general performance or isolate the effect of Monarch's architecture from its models and harness.

## Per-arm results

| arm | strict pass ± SEM | first try | after retry | retries | pass^k | infra rate | cache hit | cost (USD) |
|---|---|---|---|---|---|---|---|---|
| `setup-validation-correct` | 100.0% ± 0.0% | 100.0% ± 0.0% | 100.0% ± 0.0% | 0 | 100.0% ± 0.0% | 0.0 | n/a | 0.0 |
| `setup-validation-null` | 0.0% ± 0.0% | 0.0% ± 0.0% | 0.0% ± 0.0% | 0 | 0.0% ± 0.0% | 0.0 | n/a | 0.0 |
  
  `src: enterprise-ops-gym@271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle · v271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle · n=2 · setup-validation-correct · eog-ctl` · contracts: 19c9eb51, 1ee0cd10
  
  `src: enterprise-ops-gym@271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle · v271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle · n=2 · setup-validation-null · eog-ctl` · contracts: 19c9eb51, 1ee0cd10

## Paired comparisons

- `setup-validation-null` vs `setup-validation-correct`: **0W / 2L** (both 0, neither 0, infra-dropped 0) · McNemar b=0 c=2 p=0.4795
  `src: enterprise-ops-gym@271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle · v271f2c357f763376997dfd16807fcde2474ae41b/itsm/oracle · n=2 · setup-validation-null+setup-validation-correct · eog-ctl`

## Grading evidence


### task_20251217_153037_688_97d7df7d_be0bd794 — setup-validation-correct

Strict pass: True. Completion: completed. Evidence: C:\Users\Lucas Wakigawa\Documents\AILabs\monarch-benchmark\workflowbench\out\eog-9efb6d5a\e\eog-ctl\episodes\task_20251217_153037_688_97d7df7d_be0bd794\setup-validation-correct\t0\regrades\447857e0aecb400ab8d4267fb8159292.json.

```json
{
  "assertions_passed": true,
  "positive_source": "EnterpriseOps-Gym SQL verifiers",
  "positive": {
    "verifiers": [
      {
        "name": "verify_service_update_notification_sent",
        "type": "database_state",
        "gym_name": "gym-itsm-mcp",
        "comparison": "equals",
        "passed": true,
        "expected": 1,
        "got": [
          {
            "COUNT(*)": 1
          }
        ]
      },
      {
        "name": "verify_incident_service_updated",
        "type": "database_state",
        "gym_name": "gym-itsm-mcp",
        "comparison": "equals",
        "passed": true,
        "expected": 1,
        "got": [
          {
            "COUNT(*)": 1
          }
        ]
      }
    ]
  },
  "invariant": {
    "passed": true,
    "missing_expected": [],
    "unexpected_changes": [],
    "count_violations": [],
    "n_changes": 2
  },
  "source_collateral": null,
  "disagreement": false,
  "ungraded": false,
  "error": null
}
```

### task_20251218_063226_501_97d7df7d_8fd400d1 — setup-validation-correct

Strict pass: True. Completion: completed. Evidence: C:\Users\Lucas Wakigawa\Documents\AILabs\monarch-benchmark\workflowbench\out\eog-9efb6d5a\e\eog-ctl\episodes\task_20251218_063226_501_97d7df7d_8fd400d1\setup-validation-correct\t0\regrades\4d49fccffd3849768f0c736fffdc9f2e.json.

```json
{
  "assertions_passed": true,
  "positive_source": "EnterpriseOps-Gym SQL verifiers",
  "positive": {
    "verifiers": [
      {
        "name": "verify_printer_priority_alert_sent",
        "type": "database_state",
        "gym_name": "gym-itsm-mcp",
        "comparison": "equals",
        "passed": true,
        "expected": 1,
        "got": [
          {
            "COUNT(*)": 1
          }
        ]
      },
      {
        "name": "verify_network_priority_alert_sent",
        "type": "database_state",
        "gym_name": "gym-itsm-mcp",
        "comparison": "equals",
        "passed": true,
        "expected": 1,
        "got": [
          {
            "COUNT(*)": 1
          }
        ]
      }
    ]
  },
  "invariant": {
    "passed": true,
    "missing_expected": [],
    "unexpected_changes": [],
    "count_violations": [],
    "n_changes": 2
  },
  "source_collateral": null,
  "disagreement": false,
  "ungraded": false,
  "error": null
}
```

### task_20251217_153037_688_97d7df7d_be0bd794 — setup-validation-null

Strict pass: False. Completion: completed. Evidence: C:\Users\Lucas Wakigawa\Documents\AILabs\monarch-benchmark\workflowbench\out\eog-9efb6d5a\e\eog-ctl\episodes\task_20251217_153037_688_97d7df7d_be0bd794\setup-validation-null\t0\regrades\70ac75f56efc4d0b8da9a1434a5b8dff.json.

```json
{
  "assertions_passed": false,
  "positive_source": "EnterpriseOps-Gym SQL verifiers",
  "positive": {
    "verifiers": [
      {
        "name": "verify_service_update_notification_sent",
        "type": "database_state",
        "gym_name": "gym-itsm-mcp",
        "comparison": "equals",
        "passed": false,
        "expected": 1,
        "got": [
          {
            "COUNT(*)": 0
          }
        ]
      },
      {
        "name": "verify_incident_service_updated",
        "type": "database_state",
        "gym_name": "gym-itsm-mcp",
        "comparison": "equals",
        "passed": false,
        "expected": 1,
        "got": [
          {
            "COUNT(*)": 0
          }
        ]
      }
    ]
  },
  "invariant": {
    "passed": false,
    "missing_expected": [
      {
        "after_contains": "SVC_002",
        "count": 1,
        "op": "changed",
        "path": "gym-itsm-mcp.incident[id=INC_004].service",
        "service": "gym-itsm-mcp"
      },
      {
        "count": 1,
        "op": "added",
        "path": "gym-itsm-mcp.notification[id=*]",
        "service": "gym-itsm-mcp",
        "where": {
          "email": "elena.petrov@techcorp.com",
          "incident_id": "INC_004",
          "org_id": "ORG_001",
          "status": "sent",
          "subject": "Service Association Updated for Assigned Incident",
          "type": "alert"
        }
      }
    ],
    "unexpected_changes": [],
    "count_violations": [
      {
        "matcher": {
          "after_contains": "SVC_002",
          "count": 1,
          "op": "changed",
          "path": "gym-itsm-mcp.incident[id=INC_004].service",
          "service": "gym-itsm-mcp"
        },
        "want": 1,
        "got": 0
      },
      {
        "matcher": {
          "count": 1,
          "op": "added",
          "path": "gym-itsm-mcp.notification[id=*]",
          "service": "gym-itsm-mcp",
          "where": {
            "email": "elena.petrov@techcorp.com",
            "incident_id": "INC_004",
            "org_id": "ORG_001",
            "status": "sent",
            "subject": "Service Association Updated for Assigned Incident",
            "type": "alert"
          }
        },
        "want": 1,
        "got": 0
      }
    ],
    "n_changes": 0
  },
  "source_collateral": null,
  "disagreement": false,
  "ungraded": false,
  "error": null
}
```

### task_20251218_063226_501_97d7df7d_8fd400d1 — setup-validation-null

Strict pass: False. Completion: completed. Evidence: C:\Users\Lucas Wakigawa\Documents\AILabs\monarch-benchmark\workflowbench\out\eog-9efb6d5a\e\eog-ctl\episodes\task_20251218_063226_501_97d7df7d_8fd400d1\setup-validation-null\t0\regrades\441a6fb1531541269c6f98f3d815db8a.json.

```json
{
  "assertions_passed": false,
  "positive_source": "EnterpriseOps-Gym SQL verifiers",
  "positive": {
    "verifiers": [
      {
        "name": "verify_printer_priority_alert_sent",
        "type": "database_state",
        "gym_name": "gym-itsm-mcp",
        "comparison": "equals",
        "passed": false,
        "expected": 1,
        "got": [
          {
            "COUNT(*)": 0
          }
        ]
      },
      {
        "name": "verify_network_priority_alert_sent",
        "type": "database_state",
        "gym_name": "gym-itsm-mcp",
        "comparison": "equals",
        "passed": false,
        "expected": 1,
        "got": [
          {
            "COUNT(*)": 0
          }
        ]
      }
    ]
  },
  "invariant": {
    "passed": false,
    "missing_expected": [
      {
        "count": 1,
        "op": "added",
        "path": "gym-itsm-mcp.notification[id=*]",
        "service": "gym-itsm-mcp",
        "where": {
          "email": "carlos.rodriguez@techcorp.com",
          "incident_id": "INC_003",
          "org_id": "ORG_001",
          "status": "sent",
          "subject": "Priority Escalation for Aging Incidents",
          "type": "alert"
        }
      },
      {
        "count": 1,
        "op": "added",
        "path": "gym-itsm-mcp.notification[id=*]",
        "service": "gym-itsm-mcp",
        "where": {
          "email": "elena.petrov@techcorp.com",
          "incident_id": "INC_004",
          "org_id": "ORG_001",
          "status": "sent",
          "subject": "Priority Escalation for Aging Incidents",
          "type": "alert"
        }
      }
    ],
    "unexpected_changes": [],
    "count_violations": [
      {
        "matcher": {
          "count": 1,
          "op": "added",
          "path": "gym-itsm-mcp.notification[id=*]",
          "service": "gym-itsm-mcp",
          "where": {
            "email": "carlos.rodriguez@techcorp.com",
            "incident_id": "INC_003",
            "org_id": "ORG_001",
            "status": "sent",
            "subject": "Priority Escalation for Aging Incidents",
            "type": "alert"
          }
        },
        "want": 1,
        "got": 0
      },
      {
        "matcher": {
          "count": 1,
          "op": "added",
          "path": "gym-itsm-mcp.notification[id=*]",
          "service": "gym-itsm-mcp",
          "where": {
            "email": "elena.petrov@techcorp.com",
            "incident_id": "INC_004",
            "org_id": "ORG_001",
            "status": "sent",
            "subject": "Priority Escalation for Aging Incidents",
            "type": "alert"
          }
        },
        "want": 1,
        "got": 0
      }
    ],
    "n_changes": 0
  },
  "source_collateral": null,
  "disagreement": false,
  "ungraded": false,
  "error": null
}
```
