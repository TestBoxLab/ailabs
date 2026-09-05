"""Feature 008: every catalogue action executed against the simulated apps.

The static validator checks the shape of a seed; this checks that the seed is
TRUE -- the request runs, the declared response schema is the response the front
door really returns, and every extract resolves.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from wb_world import conformance

# A corpus task whose google_sheets state is rich enough to read a real range
# from: the check picks it by itself, these tests only need it to exist.
CORPUS = [Path("corpus")]


def _write_seed(dirpath: Path, name: str, action: dict) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "_meta.json").write_text(json.dumps(
        {"display_name": "Google-Sheets (benchmark)", "domain": "front.door",
         "host_pattern": "front.door", "login_url": None, "requires_login": False}))
    p = dirpath / f"{name}.json"
    p.write_text(json.dumps(action))
    return p


def _sheets_read(schema: dict, extract: dict | None = None,
                 url: str | None = None) -> dict:
    """The Google Sheets values read, the action the wrong schema broke."""
    return {
        "business_action": {
            "id": "bench-google-sheets:read:values", "label": "Read a value",
            "product_id": "bench-google-sheets", "product_domain": "front.door",
            "area": "values", "verb": "read", "state": "active",
            "source_url": "https://front.door/openapi/google_sheets.json",
            "first_seen_at": "2026-09-03T00:00:00.000Z",
            "last_seen_at": "2026-09-03T00:00:00.000Z",
        },
        "implementations": [{
            "id": "impl_read_values", "source": "public", "idempotent": True,
            "discovered_at": "2026-09-03T00:00:00.000Z",
            "creates_entities": [],
            "http_template": {
                "call_type": "rest", "transport_mode": "header_only",
                "auth_scheme": "none", "auth_captured": False,
                "steps": [{
                    "method": "GET",
                    "url_template": url or ("https://front.door/google_sheets/v4/spreadsheets/"
                                            "{{spreadsheetId}}/values/{{range}}"),
                    "headers_template": {}, "body_template": None,
                    "response_template": {
                        "status": 200,
                        "extract": extract if extract is not None else
                                   {"range": "$.range", "values": "$.values"},
                        "schema": schema,
                    },
                }],
            },
            "parameters": [
                {"name": "spreadsheetId", "classification": "entity_reference",
                 "entity_type": "spreadsheet", "location": "path", "type": "string",
                 "required": True, "example_value": "001401",
                 "json_path": "$.steps[0].url.spreadsheetId", "constraints": {}},
                {"name": "range", "classification": "typed", "location": "path",
                 "type": "string", "required": True, "example_value": "A1:Z100",
                 "json_path": "$.steps[0].url.range", "constraints": {}},
            ],
        }],
    }


# The schema the front door really answers with: rows of cells.
TRUE_SCHEMA = {
    "type": "object",
    "properties": {
        "range": {"type": "string"},
        "majorDimension": {"type": "string"},
        "values": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
    },
    "required": ["range", "values"],
}

# The schema that slipped through the static validator: spreadsheet records.
WRONG_SCHEMA = {
    "type": "object",
    "properties": {
        "range": {"type": "string"},
        "values": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "title": {"type": "string"}},
            "required": ["id"]}},
    },
    "required": ["range", "values"],
}


@pytest.fixture(scope="module")
def corpus_dirs():
    return [p for p in sorted(Path("corpus").glob("imported-*")) if p.is_dir()]


def _verdicts(report) -> dict[str, str]:
    return {r.action_id: r.verdict for r in report.rows}


def test_correct_sheets_seed_is_ok(tmp_path, corpus_dirs):
    _write_seed(tmp_path / "bench-google-sheets", "read_values", _sheets_read(TRUE_SCHEMA))
    report = conformance.check(tmp_path, corpus_dirs)
    row = report.rows[0]
    assert row.verdict == "ok", row.detail


def test_wrong_sheets_schema_is_a_mismatch(tmp_path, corpus_dirs):
    _write_seed(tmp_path / "bench-google-sheets", "read_values", _sheets_read(WRONG_SCHEMA))
    report = conformance.check(tmp_path, corpus_dirs)
    row = report.rows[0]
    assert row.verdict == "schema_mismatch"
    assert "values" in row.detail                  # names the offending path


def test_extract_that_resolves_to_nothing_is_extract_empty(tmp_path, corpus_dirs):
    action = _sheets_read(TRUE_SCHEMA, extract={"rows": "$.values[0].id"})
    _write_seed(tmp_path / "bench-google-sheets", "read_values", action)
    report = conformance.check(tmp_path, corpus_dirs)
    assert report.rows[0].verdict == "extract_empty"
    assert "rows" in report.rows[0].detail


def test_a_route_the_app_does_not_serve_is_no_handler(tmp_path, corpus_dirs):
    """Declared in the OpenAPI document, absent from the router: a true finding
    about the catalogue, but not a false schema, so it never gates."""
    action = _sheets_read(TRUE_SCHEMA,
                          url="https://front.door/google_sheets/v4/spreadsheets/"
                              "{{spreadsheetId}}/nowhere/{{range}}")
    _write_seed(tmp_path / "bench-google-sheets", "read_values", action)
    report = conformance.check(tmp_path, corpus_dirs)
    assert report.rows[0].verdict == "no_handler"
    assert report.failed_services() == []


def test_a_rejected_request_is_request_rejected(tmp_path, corpus_dirs):
    """A route that exists but refuses the arguments sent."""
    action = _sheets_read(TRUE_SCHEMA)
    params = action["implementations"][0]["parameters"]
    # a spreadsheet id that is well-formed but names nothing in this world
    ss = next(p for p in params if p["name"] == "spreadsheetId")
    ss["classification"] = "typed"
    ss.pop("entity_type", None)
    ss["example_value"] = "ss_does_not_exist"
    _write_seed(tmp_path / "bench-google-sheets", "read_values", action)
    report = conformance.check(tmp_path, corpus_dirs)
    assert report.rows[0].verdict == "request_rejected"


def test_path_parameter_with_no_source_is_not_executable(tmp_path, corpus_dirs):
    action = _sheets_read(TRUE_SCHEMA)
    # a path token nobody declares and nothing can fill
    step = action["implementations"][0]["http_template"]["steps"][0]
    step["url_template"] += "/{{mysteryId}}"
    _write_seed(tmp_path / "bench-google-sheets", "read_values", action)
    report = conformance.check(tmp_path, corpus_dirs)
    assert report.rows[0].verdict == "not_executable"
    assert "mysteryId" in report.rows[0].detail


def test_read_whose_extracts_are_only_ids_is_flagged_thin(tmp_path, corpus_dirs):
    action = _sheets_read(TRUE_SCHEMA, extract={"range": "$.range"})
    action["implementations"][0]["http_template"]["steps"][0][
        "response_template"]["extract"] = {"spreadsheetId": "$.range"}
    _write_seed(tmp_path / "bench-google-sheets", "read_values", action)
    report = conformance.check(tmp_path, corpus_dirs)
    assert report.rows[0].thin is True


def test_services_filter_limits_the_check(tmp_path, corpus_dirs):
    _write_seed(tmp_path / "bench-google-sheets", "read_values", _sheets_read(WRONG_SCHEMA))
    _write_seed(tmp_path / "bench-gmail", "read_values", _sheets_read(WRONG_SCHEMA))
    report = conformance.check(tmp_path, corpus_dirs, services=["google_sheets"])
    assert {r.service for r in report.rows} == {"google_sheets"}


# -- the JSONPath resolver ---------------------------------------------------

@pytest.mark.parametrize("path,body,want", [
    ("$", {"a": 1}, {"a": 1}),
    ("$.a", {"a": 1}, 1),
    ("$.a.b", {"a": {"b": 2}}, 2),
    ("$.a[0]", {"a": [7, 8]}, 7),
    ("$.a[1].b", {"a": [{}, {"b": 3}]}, 3),
    ("$.missing", {"a": 1}, None),
    ("$.a[5]", {"a": [1]}, None),
    ("$.a.b", {"a": [1]}, None),          # dotted step into a list
])
def test_resolve(path, body, want):
    assert conformance.resolve(path, body) == want


# -- the report --------------------------------------------------------------

def test_report_writes_json_and_totals(tmp_path, corpus_dirs):
    seeds = tmp_path / "seeds"
    _write_seed(seeds / "bench-google-sheets", "read_values", _sheets_read(WRONG_SCHEMA))
    report = conformance.check(seeds, corpus_dirs)
    out = tmp_path / "conformance.json"
    report.write_json(out)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["totals"]["schema_mismatch"] == 1
    assert doc["rows"][0]["action_id"] == "bench-google-sheets:read:values"
    text = io.StringIO()
    report.print_table(text)
    assert "google_sheets" in text.getvalue()
    assert "schema_mismatch" in text.getvalue()


def test_failed_services_ignores_not_executable(tmp_path, corpus_dirs):
    action = _sheets_read(TRUE_SCHEMA)
    action["implementations"][0]["http_template"]["steps"][0]["url_template"] += "/{{mysteryId}}"
    _write_seed(tmp_path / "bench-google-sheets", "read_values", action)
    report = conformance.check(tmp_path, corpus_dirs)
    assert report.failed_services() == []


# -- the gate in `wb monarch setup` ------------------------------------------

def _gate(tmp_path, action, service: str = "google_sheets") -> tuple[int, str]:
    """Run only the gate, the way monarch_setup calls it."""
    from wb_orchestrator import monarch_setup
    seeds = tmp_path / "seeds"
    _write_seed(seeds / f"bench-{service.replace('_', '-')}", "action", action)
    buf = io.StringIO()
    try:
        monarch_setup._conform_gate(seeds, [service], buf)
        return 0, buf.getvalue()
    except monarch_setup.Stop as stop:
        return stop.code, buf.getvalue() + str(stop)


def test_gate_stops_before_import_on_a_false_read(tmp_path):
    code, text = _gate(tmp_path, _sheets_read(WRONG_SCHEMA))
    assert code == 2
    assert "nothing imported" in text
    assert "bench-google-sheets:read:values" in text


def test_gate_passes_a_true_read(tmp_path):
    code, text = _gate(tmp_path, _sheets_read(TRUE_SCHEMA))
    assert code == 0
    assert "true against the simulated apps" in text


def test_gate_only_warns_when_a_write_fails(tmp_path):
    """A write needs inputs the check cannot always invent, so it never stops."""
    action = _sheets_read(TRUE_SCHEMA)
    impl = action["implementations"][0]
    step = impl["http_template"]["steps"][0]
    step["method"] = "POST"
    step["url_template"] = ("https://front.door/google_sheets/v4/spreadsheets/"
                            "{{spreadsheetId}}/values/{{range}}:append")
    step["body_template"] = {"values": "{{values}}"}
    step["headers_template"] = {"content-type": "application/json"}
    action["business_action"]["id"] = "bench-google-sheets:create:values"
    action["business_action"]["verb"] = "create"
    code, text = _gate(tmp_path, action)
    assert code == 0                       # warned, not stopped
    assert "[stop]" not in text


# -- not crying wolf: what must NOT be reported as a seed defect -------------

def test_an_optional_field_left_empty_is_not_a_mismatch(tmp_path, corpus_dirs):
    """A record with no value for an optional field is not a false schema."""
    schema = json.loads(json.dumps(TRUE_SCHEMA))
    schema["properties"]["majorDimension"] = {"type": "string"}
    assert conformance.schema_diffs(schema, {"range": "A1", "values": [],
                                             "majorDimension": None}) == []


def test_an_unfillable_required_query_parameter_is_not_executable(tmp_path, corpus_dirs):
    """Filling it with a literal would earn a 404 that says nothing about the seed."""
    action = _sheets_read(TRUE_SCHEMA)
    step = action["implementations"][0]["http_template"]["steps"][0]
    step["url_template"] += "?channel={{channel}}"
    action["implementations"][0]["parameters"].append(
        {"name": "channel", "classification": "entity_reference", "entity_type": "channel",
         "location": "query", "type": "string", "required": True,
         "json_path": "$.steps[0].url.channel", "constraints": {}})
    _write_seed(tmp_path / "bench-google-sheets", "read_values", action)
    report = conformance.check(tmp_path, corpus_dirs)
    assert report.rows[0].verdict == "not_executable"
    assert "channel" in report.rows[0].detail


def test_an_unsubstituted_baseurl_variable_is_not_a_seed_defect(tmp_path, corpus_dirs):
    """BambooHR's {companyDomain}: a whole-service mapping fault, never a lie."""
    action = _sheets_read(TRUE_SCHEMA)
    _write_seed(tmp_path / "bench-bamboohr", "read_x", action)
    report = conformance.check(tmp_path, corpus_dirs, services=["bamboohr"])
    if report.rows:                            # bamboohr is in the corpus
        assert report.rows[0].verdict == "not_executable"
        assert report.failed_services() == []
