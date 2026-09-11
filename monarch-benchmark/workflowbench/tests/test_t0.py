import json
from pathlib import Path


from grader.grade import grade
from grader.invariant import check_invariant
from grader.noop import validate_task
from ingester.graph_ingest import build_graph
from runner.arms import NullArm, OracleArm, SloppyArm
from wb_world.episode import Episode
from wb_world.snapshot import diff_snapshots

ROOT = Path(__file__).resolve().parents[1]
TASKS = sorted((ROOT / "tasks").glob("*.json"))
import automationbench
AB_SCHEMAS = Path(automationbench.__file__).parent / "tools" / "api" / "schemas"


def load(p):
    return json.loads(p.read_text())


def test_tasks_present():
    assert len(TASKS) == 10


def test_episode_isolation_and_frozen_clock():
    t = load(TASKS[0])
    e1, e2 = Episode(t, "a"), Episode(t, "b")
    e1.api_fetch("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/"
                 + e1.world.gmail.messages[0].id + "/trash")
    assert e2.snapshot() == e2.snapshot0            # e2 untouched by e1
    assert e1.world.meta.current_time == e2.world.meta.current_time  # deterministic clock


def test_service_gating():
    t = load(TASKS[0])
    ep = Episode(t, "gate")
    r = ep.api_fetch("GET", "https://api.hubapi.com/crm/v3/objects/contacts")
    assert "error" in r.lower() or "credential" in r.lower()


def test_oracle_passes_and_null_fails():
    for p in TASKS:
        t = load(p)
        ep = Episode(t, "oracle"); OracleArm().run(ep)
        g = grade(t, ep.snapshot0, ep.finish())
        assert g["passed"], (p.name, g)
        ep2 = Episode(t, "null"); NullArm().run(ep2)
        g2 = grade(t, ep2.snapshot0, ep2.finish())
        assert not g2["passed"], p.name


def test_sloppy_caught_by_invariant_not_assertions():
    t = load(TASKS[2])  # a gmail-seeded task
    ep = Episode(t, "sloppy"); SloppyArm().run(ep)
    g = grade(t, ep.snapshot0, ep.finish())
    assert g["assertions_passed"]                    # positive checks alone are fooled
    assert not g["invariant"]["passed"]              # the dual invariant is not
    assert not g["passed"]


def test_noop_validation_all_tasks():
    for p in TASKS:
        r = validate_task(load(p))
        assert r["ok"], r


def test_diff_and_matcher_semantics():
    s0 = {"svc": {"items": [{"id": "1", "x": 1}]}, "meta": {"t": 0}}
    s1 = {"svc": {"items": [{"id": "1", "x": 2}, {"id": "2", "x": 9}]}, "meta": {"t": 5}}
    ch = diff_snapshots(s0, s1)
    assert {c["op"] for c in ch} == {"changed", "added"}
    assert all(not c["path"].startswith("meta") for c in ch)
    inv = check_invariant(ch, expected=[{"service": "svc", "op": "changed", "path": "svc.items[id=1].x"}])
    assert not inv["passed"] and len(inv["unexpected_changes"]) == 1


def test_graph_ingest_counts():
    g = build_graph(AB_SCHEMAS)
    assert g["n_files"] == 47
    assert len(g["services"]) == 47
    assert len(g["actions"]) > 300
    a = next(x for x in g["actions"] if x["id"] == "salesforce.sobjects.contact.update")
    assert a["url"].endswith("/services/data/v61.0/sobjects/Contact/{id}")
    assert a["method"] == "PATCH"
