"""T017/T019: `wb monarch setup` prepares one product's knowledge base, once, offline."""
from __future__ import annotations

import io

import pytest
import yaml

from tests.fake_fd import FakeFD
from tests.fake_langfuse import FakeLangfuse
from tests.fake_monarch import FakeMonarch
from wb_orchestrator import cli, config, monarch_setup

CONFIG = config.DEFAULT_CONFIG_DIR
PRODUCT = CONFIG / "products" / "simulated-apps.yaml"
HARNESS = CONFIG / "harnesses" / "monarch.yaml"
SERVICES = config.load_product(PRODUCT).services


@pytest.fixture()
def workspace(tmp_path):
    """A copy of the product file, so the kb file is written next to a throwaway."""
    d = tmp_path / "products"
    d.mkdir()
    product = d / PRODUCT.name
    product.write_text(PRODUCT.read_text(encoding="utf-8"), encoding="utf-8")
    return product, tmp_path / "seeds"


def _run(product, out, fd_url, **kw) -> tuple[int, str]:
    buf = io.StringIO()
    env = {"MONARCH_FD_URL": fd_url, **kw.pop("env", {})}
    code = monarch_setup.run(product, HARNESS, out, env, buf, **kw)
    return code, buf.getvalue()


def test_seeds_not_mounted_stops_with_the_override_snippet(workspace):
    product, out = workspace
    with FakeFD() as fd:                      # no fixtures dir: /v1/seeds is empty
        code, text = _run(product, out, fd.url)
    assert code == 3
    assert monarch_setup.FIXTURES_MOUNT_PATH in text
    assert str(out.resolve()) in text
    assert "docker-compose.override.yaml" in text
    assert "discovery service" in text
    assert not product.with_name("simulated-apps.monarch-kb.yaml").exists()
    assert out.is_dir()                        # generation ran; only the mount is missing


def test_seeds_not_mounted_registers_nothing(workspace):
    product, out = workspace
    with FakeFD() as fd:
        _run(product, out, fd.url)
        assert fd.products == {}
        assert fd.imported == {}


def test_mounted_run_registers_imports_and_writes_the_hash_file(workspace):
    product, out = workspace
    with FakeFD(fixtures_dir=out) as fd, FakeMonarch() as monarch, FakeLangfuse() as langfuse:
        code, text = _run(product, out, fd.url)
        assert code == 0, text
        assert sorted(fd.products) == sorted(f"bench-{s}" for s in SERVICES)
        assert len(fd.imported) == 47
        assert monarch.requests == [] and langfuse.requests == []

    kb_file = product.with_name("simulated-apps.monarch-kb.yaml")
    doc = yaml.safe_load(kb_file.read_text(encoding="utf-8"))
    assert doc["product"] == "simulated-apps"
    assert doc["seeds_format"] == "public-api-seeds@1"
    assert doc["shim_public_url"] == "http://host.docker.internal:9105"
    assert list(doc["kb"]) == sorted(doc["kb"]) == sorted(f"bench-{s}" for s in SERVICES)
    assert doc["kb"] == fd.imported
    assert "actions_imported" in text and "kb_hash" in text
    # loadable by the config layer that `wb run` uses
    config.load_monarch_kb(kb_file, config.load_product(product))


def test_second_run_is_byte_identical_and_exits_zero(workspace):
    product, out = workspace
    kb_file = product.with_name("simulated-apps.monarch-kb.yaml")
    with FakeFD(fixtures_dir=out) as fd:
        assert _run(product, out, fd.url)[0] == 0
        first = kb_file.read_bytes()
        code, text = _run(product, out, fd.url)
    assert code == 0
    assert kb_file.read_bytes() == first
    assert "unchanged" in text


def test_discovery_service_unreachable_names_the_address(workspace):
    product, out = workspace
    fd = FakeFD().start()
    url = fd.url
    fd.stop()
    code, text = _run(product, out, url)
    assert code == 4
    assert text.startswith("[ok] generate") and f"[stop] mounted: discovery service unreachable at {url}/v1/seeds" in text


def test_missing_environment_variable_is_named(workspace):
    product, out = workspace
    buf = io.StringIO()
    code = monarch_setup.run(product, HARNESS, out, {}, buf)
    assert code == 4
    assert "[stop] config: fd_url: environment variable MONARCH_FD_URL is not set" in buf.getvalue()


def test_generation_gap_stops_before_anything_is_written(workspace, monkeypatch):
    product, out = workspace
    from wb_world import seeds
    monkeypatch.setattr(monarch_setup.seeds, "generate", lambda *a, **k: (_ for _ in ()).throw(
        seeds.SeedGap([seeds.Gap("bench-slack_create_x.json", "response_template.extract is empty")])))
    with FakeFD(fixtures_dir=out) as fd:
        code, text = _run(product, out, fd.url)
        assert fd.products == {}
    assert code == 2
    assert "response_template.extract is empty" in text
    assert "[stop] generate: 1 gap(s); nothing written" in text
    assert not out.exists()
    assert not product.with_name("simulated-apps.monarch-kb.yaml").exists()


def test_grant_check_reports_the_open_question(workspace):
    product, out = workspace
    with FakeFD(fixtures_dir=out) as fd:
        _, text = _run(product, out, fd.url)
    assert "unknown (open question 2)" in text


def test_import_failure_names_the_slug(workspace, monkeypatch):
    product, out = workspace
    with FakeFD(fixtures_dir=out) as fd:
        real = monarch_setup._post

        def flaky(url, payload, step, timeout=None):
            if url.endswith("/bench-slack/import"):
                raise monarch_setup._Stop(4, step, "boom")
            return real(url, payload, step)

        monkeypatch.setattr(monarch_setup, "_post", flaky)
        code, text = _run(product, out, fd.url)
    assert code == 4
    assert "[stop] import bench-slack: " in text


def test_cli_wires_the_subcommand(workspace, monkeypatch, capsys):
    product, out = workspace
    with FakeFD(fixtures_dir=out) as fd:
        monkeypatch.setenv("MONARCH_FD_URL", fd.url)
        code = cli.main(["monarch", "setup", "--product", str(product),
                         "--harness", "monarch", "--out", str(out)])
    assert code == 0
    assert "folders=47" in capsys.readouterr().out


def test_cli_returns_the_step_exit_code(workspace, monkeypatch):
    product, out = workspace
    with FakeFD() as fd:
        monkeypatch.setenv("MONARCH_FD_URL", fd.url)
        assert cli.main(["monarch", "setup", "--product", str(product), "--out", str(out)]) == 3
