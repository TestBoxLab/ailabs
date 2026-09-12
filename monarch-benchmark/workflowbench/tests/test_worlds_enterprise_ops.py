"""EnterpriseOps-Gym as a product under test (feature 026, user story 1).

Offline. The world is a containerized service, so these tests use a recorded stand-in
rather than a container: what matters here is that the adapter keeps each attempt's
worlds private, produces a snapshot the differ can read, refuses the operations only
the lab may call, and runs the source's own verifiers the source's own way.

The shapes below are not invented. They come from counting every verifier and every
server in all 649 tasks of the dataset's `oracle` set (research.md, spike S1):
`verifier_type` is always `database_state`, `validation_config` is always
`{query, expected_value, comparison_type}`, the comparisons are `equals` 3,346,
`greater_than` 143, `contains` 6 and `less_than` 1, and 88 tasks span two servers.

The one test that needs a real container is in the quickstart, run by hand.
"""
from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from wb_world import adapter as adapter_mod
from wb_world import registry
from wb_worlds.enterprise_ops.adapter import (ADMIN_PATHS, SERVERS, EnterpriseOpsWorld,
                                              _sorted_rows, db_filename, headers_for,
                                              matches, server_url)


def test_the_world_satisfies_the_contract():
    assert adapter_mod.unsatisfied(EnterpriseOpsWorld) == []
    assert registry.resolve("enterprise-ops-gym") is EnterpriseOpsWorld


def test_it_is_not_imported_until_asked_for():
    """Registered lazily: a machine with no container runtime still runs the suite."""
    import subprocess
    import sys
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys, wb_world.registry; "
         "print('wb_worlds.enterprise_ops.adapter' in sys.modules)"],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    assert out.stdout.strip() == "False", out.stderr


def test_a_missing_server_is_a_named_prerequisite_not_a_crash(monkeypatch):
    monkeypatch.setenv("WB_EOG_URL", "http://127.0.0.1:1")   # nothing listens here
    missing = EnterpriseOpsWorld.prerequisites()
    assert len(missing) == 1
    assert "EnterpriseOps-Gym" in missing[0] and "127.0.0.1:1" in missing[0]


def test_the_declared_services_are_the_seven_servers_the_dataset_names():
    assert EnterpriseOpsWorld.service_names() == list(SERVERS)
    assert "gym-itsm-mcp" in SERVERS and "sn-hr-internal" in SERVERS


def test_each_server_can_be_pointed_somewhere_of_its_own(monkeypatch):
    monkeypatch.setenv("WB_EOG_URL", "http://all.test")
    monkeypatch.setenv("WB_EOG_URL_GYM_ITSM_MCP", "http://itsm.test")
    assert server_url("gym-itsm-mcp") == "http://itsm.test"
    assert server_url("gym-calendar") == "http://all.test"


def test_a_context_key_with_stray_whitespace_still_makes_a_valid_header():
    """Three of the dataset's context keys carry a stray space upstream, and a header
    name with a space is not valid HTTP. The name is stripped; the value is not."""
    assert headers_for({" x-user-email ": "bob@techcorp.com", "x-auth-token": " tok "}) == {
        "x-user-email": "bob@techcorp.com", "x-auth-token": " tok "}


# --- the snapshot must be stable -------------------------------------------------

def test_rows_are_sorted_so_two_dumps_of_an_untouched_world_match():
    """SQLite promises no row order without an ORDER BY. Unsorted, every re-dump
    would read as collateral damage."""
    a = [{"id": 3, "x": "c"}, {"id": 1, "x": "a"}, {"id": 2, "x": "b"}]
    b = [{"id": 1, "x": "a"}, {"id": 3, "x": "c"}, {"id": 2, "x": "b"}]
    assert _sorted_rows(a) == _sorted_rows(b)


def test_rows_without_an_id_still_sort_stably():
    a = [{"x": "b"}, {"x": "a"}]
    assert _sorted_rows(a) == _sorted_rows(list(reversed(a)))


# --- their comparisons, their way ------------------------------------------------

def test_the_four_comparisons_the_dataset_actually_uses():
    assert matches([{"count": 1}], 1, "equals") is True
    assert matches([{"count": 2}], 1, "equals") is False
    assert matches([{"count": 5}], 3, "greater_than") is True
    assert matches([{"count": 3}], 3, "greater_than") is False
    assert matches([{"count": 1}], 3, "less_than") is True
    assert matches([{"summary": "Search Algorithm Beta"}], "Algorithm", "contains") is True
    assert matches([{"summary": "something else"}], "Algorithm", "contains") is False


def test_a_number_written_as_text_does_not_match_upstream():
    assert matches([{"n": 1200000}], "1200000", "equals") is False


def test_an_unknown_comparison_is_not_quietly_a_pass():
    """Their data says four exist. A fifth appearing upstream must be visible, not
    graded by guesswork."""
    with pytest.raises(ValueError, match="unknown comparison_type"):
        matches([{"n": 1}], 1, "approximately")


# --- their verifiers, run against the stored databases ----------------------------

def a_database(directory: Path, server: str, rows: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    db = directory / db_filename(server)
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE incident (id INTEGER PRIMARY KEY, state TEXT)")
        for i in range(rows):
            c.execute("INSERT INTO incident VALUES (?, 'closed')", (i + 1,))
    return db


def a_task(verifiers, servers=("gym-itsm-mcp",)):
    return {"task": "eog.probe", "prompt": "close the incident",
            "source_ref": {"domain": "itsm", "verifiers": verifiers,
                           "servers": [{"mcp_server_name": s} for s in servers]},
            "info": {"expected_changes": [{"service": "gym-itsm-mcp", "op": "changed", "path": "*"}]}}


def a_verifier(expected, comparison="equals", gym_name="gym-itsm-mcp", name="incidents"):
    return {"verifier_type": "database_state", "name": name, "gym_name": gym_name,
            "validation_config": {"query": "SELECT COUNT(*) AS count FROM incident",
                                  "expected_value": expected, "comparison_type": comparison}}


def test_a_verifiers_query_expected_value_and_comparison_are_used_as_shipped(tmp_path):
    a_database(tmp_path, "gym-itsm-mcp", rows=2)
    r = EnterpriseOpsWorld.positive_check(a_task([a_verifier(2)]), {}, {}, artifacts=tmp_path)
    assert r.passed is True
    assert r.source == "EnterpriseOps-Gym SQL verifiers"
    assert r.detail["verifiers"][0]["got"] == [{"count": 2}]
    assert r.side_effects is None, "this source has no collateral finding of its own"


def test_a_verifier_that_does_not_hold_fails_and_shows_both_numbers(tmp_path):
    a_database(tmp_path, "gym-itsm-mcp", rows=1)
    r = EnterpriseOpsWorld.positive_check(a_task([a_verifier(2)]), {}, {}, artifacts=tmp_path)
    assert r.passed is False
    v = r.detail["verifiers"][0]
    assert v["expected"] == 2 and v["got"] == [{"count": 1}]


def test_all_verifiers_must_hold(tmp_path):
    a_database(tmp_path, "gym-itsm-mcp", rows=2)
    task = a_task([a_verifier(2, name="ok"), a_verifier(99, name="not ok")])
    assert EnterpriseOpsWorld.positive_check(task, {}, {}, artifacts=tmp_path).passed is False


def test_a_task_with_no_verifiers_does_not_pass(tmp_path):
    a_database(tmp_path, "gym-itsm-mcp", rows=2)
    assert EnterpriseOpsWorld.positive_check(a_task([]), {}, {}, artifacts=tmp_path).passed is False


def test_each_verifier_runs_against_the_server_it_names(tmp_path):
    """88 of the 649 tasks span two servers. Running every verifier against the first
    database would fail all of them for the wrong reason."""
    a_database(tmp_path, "gym-itsm-mcp", rows=2)
    a_database(tmp_path, "gym-calendar", rows=7)
    task = a_task([a_verifier(2, gym_name="gym-itsm-mcp", name="itsm"),
                   a_verifier(7, gym_name="gym-calendar", name="calendar")],
                  servers=("gym-itsm-mcp", "gym-calendar"))
    r = EnterpriseOpsWorld.positive_check(task, {}, {}, artifacts=tmp_path)
    assert r.passed is True
    assert [v["gym_name"] for v in r.detail["verifiers"]] == ["gym-itsm-mcp", "gym-calendar"]


def test_a_missing_database_raises_so_the_attempt_is_ungraded(tmp_path):
    """Not passed and not failed: a checker that cannot answer is a fact about our
    run, not about the competitor. `grade()` turns this into `ungraded`."""
    with pytest.raises(FileNotFoundError):
        EnterpriseOpsWorld.positive_check(a_task([a_verifier(1)]), {}, {}, artifacts=tmp_path)


def test_an_ungradable_attempt_is_neither_passed_nor_failed(tmp_path):
    from grader.grade import grade

    g = grade(a_task([a_verifier(1)]), {"gym-itsm-mcp": {}}, {"gym-itsm-mcp": {}},
              world=EnterpriseOpsWorld, artifacts=tmp_path)
    assert g["ungraded"] is True and g["passed"] is False
    assert "world-gym-itsm-mcp.sqlite" in g["error"]


# --- the operations only the lab may call ----------------------------------------

def test_the_admin_operations_are_named():
    for path in ("/api/sql-runner", "/api/seed-database", "/api/reset-database",
                 "/api/delete-database", "/api/database-state", "/api/download-db-file"):
        assert path in ADMIN_PATHS


class _Offline(EnterpriseOpsWorld):
    """The adapter with its network removed, so the refusals can be tested offline."""

    def __init__(self, servers=("gym-itsm-mcp",)):
        self.database_id = "wb-test"
        self.tool_calls, self.events, self._journal, self._closed = [], [], None, False
        self.servers = {name: None for name in servers}
        self._specs = {name: {
            "openapi": "3.1.0", "info": {"title": name, "version": "1.0.0"},
            "paths": {"/incidents": {"get": {"summary": "list incidents",
                                             "operationId": "list_incidents"}},
                      "/api/sql-runner": {"post": {"summary": "run sql",
                                                   "operationId": "sql_runner"}}}}
            for name in servers}
        self.snapshot0 = {}

    def _spec(self, name):
        return self._specs[name]


def test_a_competitor_cannot_reach_the_administrative_operations():
    """One query against /api/sql-runner would write the expected result directly."""
    out = json.loads(_Offline()._call("POST", "/api/sql-runner", None,
                                      json.dumps({"query": "UPDATE incident SET state='closed'"})))
    assert out["error"]["code"] == 403
    assert "administrative operation" in out["error"]["message"]


def test_the_published_document_does_not_advertise_them():
    spec = _Offline().interfaces().spec("gym-itsm-mcp", "http://front.door")
    assert "/incidents" in spec["paths"]
    assert "/api/sql-runner" not in spec["paths"]
    assert spec["servers"][0]["url"] == "http://front.door/gym-itsm-mcp"


def test_search_does_not_surface_them_either():
    hits = json.loads(_Offline().api_search("sql runner incidents"))
    assert any(h["path"] == "/incidents" for h in hits)
    assert not any(h["path"].startswith("/api/") for h in hits)


class _Recording:
    """A server that records the target it was handed instead of sending it."""

    def __init__(self):
        self.target = None

    def request(self, method, path, body=None, extra=None):
        self.target = path
        return b'{"ok": true}'


def _with_location_route():
    world = _Offline()
    world._specs["gym-itsm-mcp"]["paths"]["/locations/name/{name}"] = {
        "get": {"summary": "location by name", "operationId": "location_by_name"}}
    world.servers["gym-itsm-mcp"] = _Recording()
    return world, world.servers["gym-itsm-mcp"]


def test_a_path_value_with_a_space_reaches_the_world_still_encoded():
    """`/locations/name/TechCorp%20NYC%20Headquarters` is a route and a value the
    shipped ITSM document and its seed data both contain.

    The decoded path was sent as the request target. `urllib` refuses a space
    outright -- `InvalidURL: URL can't contain control characters` -- and a server
    that accepted it would read the target as `/locations/name/TechCorp`. Either way
    a real EOG task fails, and the approval rule reads that as the competitor
    failing rather than as our own bug.
    """
    world, server = _with_location_route()
    out = world._call("GET", "/locations/name/TechCorp%20NYC%20Headquarters", None, None)
    assert json.loads(out) == {"ok": True}, out
    assert " " not in server.target, "a space in the request target is not sendable"
    assert server.target == "/locations/name/TechCorp%20NYC%20Headquarters"


def test_the_permission_check_reads_the_decoded_path():
    """Decoding still has to happen, just not on the way to the wire: an encoded
    separator must not slip past the published-surface check as one segment."""
    world, server = _with_location_route()
    out = json.loads(world._call("GET", "/locations/name/Tech%2FCorp", None, None))
    assert out["error"]["code"] == 403
    assert server.target is None, "a refused call must not reach the world"


def test_an_encoded_administrative_path_is_refused_as_administrative():
    """The admin guard read the raw path while everything after it read the decoded
    one. Two forms of the same path in one function is how a guard gets walked past."""
    out = json.loads(_Offline()._call("POST", "/api/%73ql-runner", None,
                                      json.dumps({"query": "UPDATE incident SET state='closed'"})))
    assert out["error"]["code"] == 403
    assert "administrative operation" in out["error"]["message"]


def test_a_call_to_no_known_server_is_refused_by_name():
    out = json.loads(_Offline(("gym-itsm-mcp", "gym-calendar"))._call("GET", "/nowhere/x", None, None))
    assert out["error"]["code"] == 404
    assert "gym-calendar" in out["error"]["message"]


def test_the_front_door_refuses_them_on_the_wire():
    """Two doors, one rule: a world reached by any other route is still the world."""
    from wb_arms.http_shim import EpisodeHTTPShim

    shim = EpisodeHTTPShim(_Offline()).start()
    try:
        req = urllib.request.Request(f"{shim.url}/gym-itsm-mcp/api/sql-runner", method="POST",
                                     data=b"{}", headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403
    finally:
        shim.stop()


def test_the_front_door_refuses_them_without_help_from_the_world():
    """The door is the one that must not need the adapter to remember (FR-034).

    The test above cannot tell the two doors apart: this adapter refuses the call
    itself and the shim turns its error envelope into the same 403. So this one
    hands the shim a world that answers everything, which is the case the door
    exists for -- a world added later whose `admin_paths` is all it declares.
    """
    from wb_arms.http_shim import EpisodeHTTPShim

    class _Obliging:
        """Declares its administrative paths and guards nothing."""
        reached = []

        def interfaces(self):
            return _Offline().interfaces()

        def api_fetch(self, method, url, params=None, body=None):
            _Obliging.reached.append(url)
            return json.dumps({"rows": [{"secret": "written"}]})

    shim = EpisodeHTTPShim(_Obliging()).start()
    try:
        req = urllib.request.Request(f"{shim.url}/gym-itsm-mcp/api/sql-runner", method="POST",
                                     data=b"{}", headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403
        assert _Obliging.reached == [], "the door let an administrative call reach the world"
    finally:
        shim.stop()


@pytest.mark.parametrize("url", ["/gym-itsm-mcp/api/sql-runner", "/api/sql-runner",
                                 "http://host/gym-itsm-mcp/api/reset-database"])
def test_the_tool_surface_refuses_them_too(url):
    """Two surfaces, one world, so one rule. `POST /fetch` takes a URL the competitor
    wrote; refusing only on the REST path left the shorter way in open."""
    from wb_arms.http_shim import EpisodeHTTPShim

    class _Obliging:
        reached = []

        def interfaces(self):
            return _Offline().interfaces()

        def api_fetch(self, method, url, params=None, body=None):
            _Obliging.reached.append(url)
            return json.dumps({"rows": [{"secret": "written"}]})

    shim = EpisodeHTTPShim(_Obliging()).start()
    try:
        req = urllib.request.Request(f"{shim.url}/fetch", method="POST",
                                     data=json.dumps({"method": "POST", "url": url}).encode(),
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403
        assert _Obliging.reached == [], f"/fetch let {url} reach the world"
    finally:
        shim.stop()


def test_the_tool_surface_still_passes_ordinary_calls():
    """The guard must not close the door on the world's real work."""
    from wb_arms.http_shim import EpisodeHTTPShim

    class _Plain:
        reached = []

        def interfaces(self):
            return _Offline().interfaces()

        def api_fetch(self, method, url, params=None, body=None):
            _Plain.reached.append(url)
            return json.dumps({"incidents": []})

    shim = EpisodeHTTPShim(_Plain()).start()
    try:
        req = urllib.request.Request(f"{shim.url}/fetch", method="POST",
                                     data=json.dumps({"method": "GET",
                                                      "url": "/gym-itsm-mcp/incidents"}).encode(),
                                     headers={"Content-Type": "application/json"})
        assert urllib.request.urlopen(req).status == 200
        assert _Plain.reached == ["/gym-itsm-mcp/incidents"]
    finally:
        shim.stop()


def test_upstream_comparisons_keep_types_and_single_row_shape():
    assert matches([{"x": 1, "y": 2}], {"x": 1, "y": 2}, "equals") is True
    assert matches([{"n": "5"}], 3, "greater_than") is False
    assert matches([{"n": 3}], "5", "less_than") is False
    assert matches([], [], "equals") is True
    assert matches([{"n": None}], None, "equals") is True


def test_teardown_uses_published_delete_method_once():
    from unittest.mock import Mock
    ep = _Offline()
    server = Mock()
    ep.servers = {"gym-itsm-mcp": server}
    ep.close()
    ep.close()
    server.admin.assert_called_once_with("DELETE", "/api/delete-database", {"database_id": "wb-test"})


def test_native_primary_keys_keep_edits_on_the_same_snapshot_row():
    from wb_worlds.enterprise_ops.adapter import _snapshot_rows
    from wb_world.snapshot import diff_snapshots
    schema = {"columns": {"incident_id": "TEXT PRIMARY KEY NOT NULL", "service": "TEXT"}}
    before = [{"incident_id": "INC_002", "service": "z"}, {"incident_id": "INC_001", "service": "b"}]
    after = [{"incident_id": "INC_001", "service": "b"}, {"incident_id": "INC_002", "service": "a"}]
    changes = diff_snapshots({"gym": {"incident": _snapshot_rows(before, schema)}},
                             {"gym": {"incident": _snapshot_rows(after, schema)}})
    assert changes == [{"service": "gym", "op": "changed", "path": "gym.incident[id=INC_002].service", "before": "z", "after": "a"}]


def test_snapshot_identity_uses_declared_composite_keys_and_handles_enum_columns():
    from wb_worlds.enterprise_ops.adapter import _snapshot_rows
    schema = {"columns": {"user_id": "TEXT", "role_id": "TEXT", "status": {"type": "ENUM"}},
              "constraints": ["PRIMARY KEY (user_id, role_id)"]}
    rows = _snapshot_rows([{"user_id": "U1", "role_id": "R1", "status": "active"}], schema)
    assert rows[0]["id"] == '["U1", "R1"]'


def test_tool_mode_filters_public_document_and_rejects_undeclared_operations():
    ep = _Offline()
    ep.task = {"source_ref": {"selected_tools": ["list_incidents"]}}
    ep._specs["gym-itsm-mcp"]["paths"]["/users/"] = {"post": {"summary": "Add New User", "operationId": "add_new_user_users__post"}}
    spec = ep.interfaces().spec("gym-itsm-mcp", "http://front.door")
    assert "/incidents" in spec["paths"]
    assert "/users/" not in spec["paths"]
    rejected = json.loads(ep.api_fetch("POST", "/users/", body="{}"))
    assert rejected["error"]["code"] == 403


def test_raw_openapi_is_sanitized_and_search_carries_input_schemas():
    ep = _Offline()
    ep._specs["gym-itsm-mcp"]["paths"]["/incidents"]["get"]["parameters"] = [{"name": "number", "in": "query", "schema": {"type": "string"}}]
    raw = json.loads(ep.api_fetch("GET", "/openapi.json"))
    assert "/api/sql-runner" not in raw["paths"]
    hits = json.loads(ep.api_search("incidents"))
    assert hits[0]["operation"]["parameters"][0]["name"] == "number"


def test_source_seed_drift_is_rejected_before_provisioning(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from wb_worlds.enterprise_ops import adapter
    seed = tmp_path / "seed.sql"
    seed.write_text("changed", encoding="utf-8")
    monkeypatch.setenv("WB_EOG_DBS", str(tmp_path))
    admin = Mock()
    monkeypatch.setattr(adapter._Server, "admin", admin)
    task = {"source_ref": {"servers": [{"mcp_server_name": "gym-itsm-mcp", "seed_database_file": "seed.sql"}], "seed_sha256": {"gym-itsm-mcp": "0" * 64}}}
    with pytest.raises(ValueError, match="seed.*hash"):
        EnterpriseOpsWorld(task, "drift")
    admin.assert_not_called()


def test_retry_invocations_use_distinct_private_database_names(monkeypatch):
    from wb_worlds.enterprise_ops import adapter
    monkeypatch.setattr(adapter._Server, "admin", lambda *args, **kwargs: {})
    task = {"source_ref": {"servers": [{"mcp_server_name": "gym-itsm-mcp", "seed_sql": "SELECT 1;"}]}}
    first = EnterpriseOpsWorld(task, "same-episode")
    second = EnterpriseOpsWorld(task, "same-episode")
    assert first.database_id != second.database_id
    assert first.episode_id == second.episode_id == "same-episode"
