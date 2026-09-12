"""Source catalogue setup is isolated from the 47 AutomationBench products."""
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from wb_orchestrator import cli, config, external_catalogue, monarch_setup

HARNESS = config.DEFAULT_CONFIG_DIR / "harnesses" / "monarch.yaml"
SOURCE = config.DEFAULT_CONFIG_DIR / "products" / "enterprise-ops-gym.yaml"
URL = "http://source-front-door.test"
SLUG = "bench-enterprise-ops-gym-gym-itsm-mcp"


@pytest.fixture
def source_setup(tmp_path, monkeypatch):
    product = tmp_path / SOURCE.name
    product.write_bytes(SOURCE.read_bytes())
    tasks = tmp_path / "frozen-tasks"
    tasks.mkdir()
    out = tmp_path / "source-seeds"
    calls = {"generate": [], "validate": [], "get": [], "post": []}

    def generate(resolved_product, task_dir, output, url):
        calls["generate"].append((resolved_product.name, Path(task_dir), output, url))
        output.mkdir()
        return external_catalogue.CatalogueSummary(8, 8, [SLUG], {"gym-itsm-mcp": SLUG}, "pack-hash")

    def get(url, step, **kw):
        calls["get"].append((url, step))
        if url.endswith("/v1/seeds"):
            return {"items": [{"slug": "bench-gmail"}, {"slug": SLUG}]}
        assert url.endswith(f"/{SLUG}/diff")
        return {"slug": SLUG, "kb_hash": None, "seed_hash": "source-seed-hash"}

    def post(url, payload, step, **kw):
        calls["post"].append((url, payload, step))
        return {"slug": SLUG, "after": {"kb_hash": "source-seed-hash"},
                "seed_hash": "source-seed-hash", "in_sync": True, "actions_imported": 8}

    def forbidden(*args, **kw):
        raise AssertionError("AutomationBench generation/conformance must not run for source products")

    monkeypatch.setattr(external_catalogue, "generate", generate)
    monkeypatch.setattr(monarch_setup, "_generate", forbidden)
    monkeypatch.setattr(monarch_setup, "_conform_gate", forbidden)
    monkeypatch.setattr(monarch_setup, "_run_seed_validator", lambda *args: calls["validate"].append(args[0]))
    monkeypatch.setattr(monarch_setup, "_get", get)
    monkeypatch.setattr(monarch_setup, "_post", post)
    return SimpleNamespace(product=product, tasks=tasks, out=out, calls=calls)


def run(site, **kw):
    buf = io.StringIO()
    code = monarch_setup.run(site.product, HARNESS, site.out,
        {"MONARCH_FD_URL": "http://fd.test", "FRONT_DOOR_URL": URL}, buf, **kw)
    return code, buf.getvalue()


def test_source_setup_requires_frozen_tasks_before_generation_or_import(source_setup):
    code, text = run(source_setup)
    assert code == 2 and "--tasks" in text
    assert source_setup.calls == {"generate": [], "validate": [], "get": [], "post": []}


@pytest.mark.parametrize("option", [{"knowledge": "catalog.json"}, {"knowledge_map": "map.yaml"}])
def test_source_setup_refuses_automationbench_knowledge_mapping(source_setup, option):
    code, text = run(source_setup, tasks=source_setup.tasks, **option)
    assert code == 2 and "knowledge" in text and "source" in text
    assert source_setup.calls["generate"] == [] and source_setup.calls["post"] == []


def test_source_knowledge_command_refuses_synthetic_catalogue(source_setup):
    buf = io.StringIO()
    code = monarch_setup.lab_seeds(source_setup.product, HARNESS, source_setup.out,
        {"FRONT_DOOR_URL": URL}, buf, knowledge_path="catalog.json")
    assert code == 2 and "source" in buf.getvalue()
    assert source_setup.calls["generate"] == []


def test_source_setup_writes_namespaced_kb_and_guards_absence(source_setup):
    code, text = run(source_setup, tasks=source_setup.tasks)
    assert code == 0, text
    calls = source_setup.calls
    assert calls["generate"] == [("enterprise-ops-gym", source_setup.tasks, source_setup.out, URL)]
    assert calls["validate"] == [source_setup.out]
    assert calls["post"] == [(f"http://fd.test/v1/seeds/{SLUG}/import", {"expected_hash": None}, f"import {SLUG}")]
    path = source_setup.product.with_name("enterprise-ops-gym.monarch-kb.yaml")
    kb = config.load_monarch_kb(path, config.load_product(source_setup.product))
    assert kb.kb == {SLUG: "source-seed-hash"}
    assert "source-native live smoke" in text and "47" not in text


def test_source_setup_guards_existing_hash_from_diff(source_setup, monkeypatch):
    old_get = monarch_setup._get
    def get(url, step, **kw):
        result = old_get(url, step, **kw)
        if url.endswith("/diff"):
            result["kb_hash"] = "old-source-kb"
        return result
    monkeypatch.setattr(monarch_setup, "_get", get)
    assert run(source_setup, tasks=source_setup.tasks)[0] == 0
    assert source_setup.calls["post"][0][1] == {"expected_hash": "old-source-kb"}


@pytest.mark.parametrize("diff", [
    {"slug": SLUG, "seed_hash": "source-seed-hash"},
    {"slug": SLUG, "kb_hash": "", "seed_hash": "source-seed-hash"},
    {"slug": "bench-gmail", "kb_hash": None, "seed_hash": "source-seed-hash"},
])
def test_source_setup_refuses_ambiguous_diff_without_unguarded_import(source_setup, monkeypatch, diff):
    old_get = monarch_setup._get
    monkeypatch.setattr(monarch_setup, "_get", lambda url, step, **kw: diff if url.endswith("/diff") else old_get(url, step, **kw))
    code, text = run(source_setup, tasks=source_setup.tasks)
    assert code == 4 and "diff" in text
    assert source_setup.calls["post"] == []


def test_source_setup_refuses_unfrozen_generator_input_without_import(source_setup, monkeypatch):
    def drift(*a):
        raise ValueError("a frozen task contract changed before catalogue generation")
    monkeypatch.setattr(external_catalogue, "generate", drift)
    code, text = run(source_setup, tasks=source_setup.tasks)
    assert code == 2 and "frozen task contract changed" in text
    assert source_setup.calls["get"] == [] and source_setup.calls["post"] == []


def test_source_setup_preserves_previous_kb_when_guard_rejects_import(source_setup, monkeypatch):
    path = source_setup.product.with_name("enterprise-ops-gym.monarch-kb.yaml")
    path.write_text("preserved old pin", encoding="utf-8")
    def conflict(url, payload, step, **kw):
        assert payload == {"expected_hash": None}
        raise monarch_setup.Stop(4, step, "409 kb_changed")
    monkeypatch.setattr(monarch_setup, "_post", conflict)
    code, text = run(source_setup, tasks=source_setup.tasks)
    assert code == 4 and "409 kb_changed" in text
    assert path.read_text(encoding="utf-8") == "preserved old pin"


def test_source_setup_refuses_import_with_unverified_result(source_setup, monkeypatch):
    monkeypatch.setattr(monarch_setup, "_post", lambda *a, **kw: {"after": {"kb_hash": "other"}, "in_sync": False})
    code, text = run(source_setup, tasks=source_setup.tasks)
    assert code == 4 and "import" in text
    assert not source_setup.product.with_name("enterprise-ops-gym.monarch-kb.yaml").exists()


def test_external_kb_rejects_legacy_service_slug(source_setup):
    path = source_setup.product.with_name("enterprise-ops-gym.monarch-kb.yaml")
    monarch_setup._write_kb(source_setup.product, "enterprise-ops-gym", URL, {"bench-gym-itsm-mcp": "old"}, env={})
    with pytest.raises(config.ConfigError, match=SLUG):
        config.load_monarch_kb(path, config.load_product(source_setup.product))


def test_cli_setup_forwards_frozen_task_directory(source_setup, monkeypatch):
    captured = []
    monkeypatch.setattr(monarch_setup, "run", lambda *a, **kw: captured.append((a, kw)) or 0)
    code = cli.main(["monarch", "setup", "--product", str(source_setup.product),
        "--tasks", str(source_setup.tasks), "--out", str(source_setup.out)])
    assert code == 0
    assert captured[0][1]["tasks"] == str(source_setup.tasks)
    assert captured[0][0][0] == source_setup.product


def test_cli_verify_uses_requested_source_product_and_harness(monkeypatch):
    from wb_studio import enterprise, app
    studios = []
    monkeypatch.setattr(app, "Studio", lambda **kw: SimpleNamespace())
    def verify(studio):
        studios.append(studio)
        return {"checks": [], "ok": True}
    monkeypatch.setattr(enterprise, "verify", verify)
    monkeypatch.setattr(enterprise, "probe_path", lambda studio: Path("source-verification.json"))
    assert cli.main(["monarch", "verify", "--product", "enterprise-ops-gym", "--harness", "monarch-enterprise-ops"]) == 0
    assert studios[0].enterprise_product == "enterprise-ops-gym"
    assert studios[0].enterprise_harness == "monarch-enterprise-ops"
