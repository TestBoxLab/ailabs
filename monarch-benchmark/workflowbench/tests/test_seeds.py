"""T015: the seed generator writes a complete, valid public-api-seeds folder set."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wb_world import seeds
from wb_world.openapi import build_all

SHIM = "http://host.docker.internal:9105"


def _expected_operations() -> int:
    return sum(len(methods) for doc in build_all(SHIM).values() for methods in doc["paths"].values())


@pytest.fixture(scope="module")
def generated(tmp_path_factory) -> tuple[Path, seeds.Summary]:
    out = tmp_path_factory.mktemp("seeds")
    return out, seeds.generate(out, SHIM)


def _actions(out: Path):
    for f in sorted(out.rglob("*.json")):
        if f.name != "_meta.json":
            yield f, json.loads(f.read_text(encoding="utf-8"))


def test_one_folder_per_service_and_one_file_per_operation(generated):
    out, summary = generated
    expected = _expected_operations()
    assert expected > 600
    assert len(summary.folders) == 47
    assert summary.operations_in_spec == expected
    assert summary.files_written == expected
    assert sorted(p.name for p in out.iterdir() if p.is_dir()) == sorted(summary.folders)
    assert all(name.startswith("bench-") for name in summary.folders)
    assert len(list(_actions(out))) == expected


def test_meta_file_per_folder(generated):
    out, summary = generated
    for name in summary.folders:
        meta = json.loads((out / name / "_meta.json").read_text(encoding="utf-8"))
        assert meta["domain"] == "host.docker.internal"
        assert meta["host_pattern"] == "host.docker.internal"
        assert meta["requires_login"] is False
        assert meta["login_url"] is None
        assert meta["display_name"].endswith("(benchmark)")


def test_every_action_has_the_shape_the_importer_needs(generated):
    out, _ = generated
    for path, doc in _actions(out):
        ba, impls = doc["business_action"], doc["implementations"]
        assert ba["verb"] in {"create", "read", "list", "update", "delete"}, path
        assert ba["product_id"] == path.parent.name
        step = impls[0]["http_template"]["steps"][0]
        assert impls[0]["http_template"]["auth_scheme"] == "none", path
        assert step["url_template"].startswith(SHIM + "/"), path
        rt = step["response_template"]
        assert isinstance(rt["schema"], dict) and rt["schema"], path
        assert rt["extract"] and all(v.startswith("$.") for v in rt["extract"].values()), path
        if ba["verb"] == "create":
            assert impls[0]["creates_entities"][0]["identifier_path"] == "$.id", path
        else:
            assert "creates_entities" not in impls[0], path


def test_action_ids_unique_within_a_folder(generated):
    out, summary = generated
    for name in summary.folders:
        ids = [json.loads(f.read_text(encoding="utf-8"))["business_action"]["id"]
               for f in (out / name).glob("*.json") if f.name != "_meta.json"]
        assert len(ids) == len(set(ids)), name


def test_validate_finds_no_gap_on_the_generated_set(generated):
    out, _ = generated
    assert seeds.validate(out) == []


def test_validate_names_the_gap_on_a_corrupted_file(generated, tmp_path):
    out, _ = generated
    folder = tmp_path / "bench-slack"
    folder.mkdir()
    victim = next(f for f, _ in _actions(out) if f.parent.name == "bench-slack")
    doc = json.loads(victim.read_text(encoding="utf-8"))
    doc["implementations"][0]["http_template"]["steps"][0]["response_template"]["extract"] = {}
    (folder / victim.name).write_text(json.dumps(doc), encoding="utf-8")
    gaps = seeds.validate(tmp_path)
    assert [g.file for g in gaps] == [victim.name]
    assert "extract" in gaps[0].gap


def test_two_generations_are_byte_identical(generated, tmp_path):
    out, _ = generated
    again = tmp_path / "again"
    seeds.generate(again, SHIM)
    for f, _ in _actions(out):
        rel = f.relative_to(out)
        assert (again / rel).read_bytes() == f.read_bytes(), rel


def test_validate_names_a_malformed_url_template(generated, tmp_path):
    out, _ = generated
    folder = tmp_path / "bad-url" / "bench-trello"
    folder.mkdir(parents=True)
    victim = next(f for f, _ in _actions(out) if f.parent.name == "bench-trello")
    doc = json.loads(victim.read_text(encoding="utf-8"))
    doc["implementations"][0]["http_template"]["steps"][0]["url_template"] = SHIM + "/trello/cards/{{}}"
    (folder / victim.name).write_text(json.dumps(doc), encoding="utf-8")
    gaps = seeds.validate(tmp_path / "bad-url")
    assert len(gaps) == 1 and "malformed placeholder" in gaps[0].gap
