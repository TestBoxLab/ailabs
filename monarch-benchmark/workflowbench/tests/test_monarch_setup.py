"""T017/T019: `wb monarch setup` prepares one product's knowledge base, once, offline."""
from __future__ import annotations

import io

import pytest
import yaml

from tests.fake_fd import FakeFD
from tests.fake_langfuse import FakeLangfuse
from tests.fake_monarch import FakeMonarch
from wb_orchestrator import cli, config, monarch_setup
from wb_world import seeds

CONFIG = config.DEFAULT_CONFIG_DIR
PRODUCT = CONFIG / "products" / "simulated-apps.yaml"
HARNESS = CONFIG / "harnesses" / "monarch.yaml"
SERVICES = config.load_product(PRODUCT).services
SLUGS = [seeds.product_slug(s) for s in SERVICES]


@pytest.fixture()
def workspace(tmp_path):
    """A copy of the product file, so the kb file is written next to a throwaway."""
    d = tmp_path / "products"
    d.mkdir()
    product = d / PRODUCT.name
    product.write_text(PRODUCT.read_text(encoding="utf-8"), encoding="utf-8")
    return product, tmp_path / "seeds"


# The shipped harness reaches the front door through a tunnel; these tests are
# offline, so they pin the address the seeds were always generated for.
FRONT_DOOR = "http://host.docker.internal:9105"


def _run(product, out, fd_url, **kw) -> tuple[int, str]:
    buf = io.StringIO()
    env = {"MONARCH_FD_URL": fd_url, "FRONT_DOOR_URL": FRONT_DOOR, **kw.pop("env", {})}
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


def test_mounted_run_imports_and_writes_the_hash_file(workspace):
    product, out = workspace
    with FakeFD(fixtures_dir=out) as fd, FakeMonarch() as monarch, FakeLangfuse() as langfuse:
        code, text = _run(product, out, fd.url)
        assert code == 0, text
        # the import creates the product; a separate POST /v1/products made a
        # second, slugified product per app (verified 4 Sep 2026)
        assert not any(r["path"] == "/v1/products" for r in fd.requests)
        assert len(fd.imported) == 47
        assert monarch.requests == [] and langfuse.requests == []

    kb_file = product.with_name("simulated-apps.monarch-kb.yaml")
    doc = yaml.safe_load(kb_file.read_text(encoding="utf-8"))
    assert doc["product"] == "simulated-apps"
    assert doc["seeds_format"] == "public-api-seeds@1"
    assert doc["shim_public_url"] == "http://host.docker.internal:9105"
    assert list(doc["kb"]) == sorted(doc["kb"]) == sorted(SLUGS)
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


def test_setup_sends_the_fd_api_key_when_the_harness_names_one(workspace, tmp_path):
    """The Railway discovery service gates every /v1/* route (verified 4 Sep 2026)."""
    product, out = workspace
    harness = tmp_path / "monarch.yaml"
    harness.write_text(HARNESS.read_text(encoding="utf-8")
                       + "fd_api_key_env: FD_API_SHARED_SECRET\n", encoding="utf-8")
    with FakeFD(fixtures_dir=out, api_key="s3cret") as fd:
        buf = io.StringIO()
        code = monarch_setup.run(product, harness, out,
                                 {"MONARCH_FD_URL": fd.url, "FRONT_DOOR_URL": FRONT_DOOR,
                                  "FD_API_SHARED_SECRET": "s3cret"},
                                 buf)
        keyed = [r for r in fd.requests if r["path"].startswith("/v1/")]
    assert code == 0, buf.getvalue()
    assert keyed and all(r["headers"].get("X-Fd-Api-Key") == "s3cret" for r in keyed)


def test_grant_check_reports_the_open_question(workspace):
    product, out = workspace
    with FakeFD(fixtures_dir=out) as fd:
        _, text = _run(product, out, fd.url)
    assert "unknown (open question 2)" in text


def test_import_failure_names_the_slug(workspace, monkeypatch):
    product, out = workspace
    with FakeFD(fixtures_dir=out) as fd:
        real = monarch_setup._post

        def flaky(url, payload, step, timeout=None, headers=None):
            if url.endswith("/bench-slack/import"):
                raise monarch_setup.Stop(4, step, "boom")
            return real(url, payload, step, headers=headers)

        monkeypatch.setattr(monarch_setup, "_post", flaky)
        code, text = _run(product, out, fd.url)
    assert code == 4
    assert "[stop] import bench-slack: " in text


def test_cli_wires_the_subcommand(workspace, monkeypatch, capsys):
    product, out = workspace
    with FakeFD(fixtures_dir=out) as fd:
        monkeypatch.setenv("MONARCH_FD_URL", fd.url)
        monkeypatch.setenv("FRONT_DOOR_URL", FRONT_DOOR)
        code = cli.main(["monarch", "setup", "--product", str(product),
                         "--harness", "monarch", "--out", str(out)])
    assert code == 0
    assert "folders=47" in capsys.readouterr().out


def test_cli_returns_the_step_exit_code(workspace, monkeypatch):
    product, out = workspace
    with FakeFD() as fd:
        monkeypatch.setenv("MONARCH_FD_URL", fd.url)
        monkeypatch.setenv("FRONT_DOOR_URL", FRONT_DOOR)
        assert cli.main(["monarch", "setup", "--product", str(product), "--out", str(out)]) == 3
