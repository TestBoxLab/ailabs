"""`wb doctor` on the Monarch side: is the backend up, is the session good, is
the discovery service up, is the tracing service up. The paid authoring probe
is opt-in and must not fire without --monarch-probe."""
from __future__ import annotations

import socket

import pytest

from tests.fake_fd import FakeFD
from tests.fake_langfuse import FakeLangfuse
from tests.fake_monarch import FakeMonarch, Scenario
from wb_orchestrator import config, doctor

HARNESS = """\
name: monarch
kind: monarch
accepts: none
runnable: {runnable}
base_url: ${{MONARCH_URL}}
credential_env: MONARCH_TOKEN
login_email: dev-root@testbox.com
login_password_env: MONARCH_PASSWORD
fd_url: ${{MONARCH_FD_URL}}
shim_port: 9105
shim_public_host: host.docker.internal
langfuse_url: ${{LANGFUSE_URL}}
langfuse_public_key_env: LANGFUSE_PUBLIC_KEY
langfuse_secret_key_env: LANGFUSE_SECRET_KEY
price_table: monarch-team-bedrock
monarch_repo: ../../../monarch
modes: [create-run]
"""


def _harness(tmp_path, runnable=True):
    d = tmp_path / "harnesses"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "monarch.yaml"
    p.write_text(HARNESS.format(runnable=str(runnable).lower()), encoding="utf-8")
    return config.load_harness(p)


def _env(monarch, fd, lf):
    return {"MONARCH_URL": monarch, "MONARCH_FD_URL": fd, "LANGFUSE_URL": lf,
            "LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk",
            "MONARCH_PASSWORD": "monarch-dev"}


def _dead_url() -> str:
    """A port nothing listens on."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def stack():
    with FakeMonarch(Scenario()) as m, FakeFD() as fd, FakeLangfuse() as lf:
        yield m, fd, lf


def test_all_four_checks_pass_and_no_probe_by_default(tmp_path, stack):
    m, fd, lf = stack
    r = doctor.check_monarch(_harness(tmp_path), _env(m.url, fd.url, lf.url))

    assert r["provider"] == "monarch" and r["ok"] is True
    for k in ("backend", "backend_health", "fd", "langfuse"):
        assert r[k].startswith("OK "), (k, r[k])
    assert "authoring_probe" not in r
    assert not [q for q in m.requests if q["path"].rstrip("/").endswith("recipe/runs")]


def test_login_is_used_when_no_token_env(tmp_path, stack):
    m, fd, lf = stack
    doctor.check_monarch(_harness(tmp_path), _env(m.url, fd.url, lf.url))
    assert [q["path"] for q in m.requests].count("/api/auth/login") == 1


def test_preset_token_env_skips_login(tmp_path):
    with FakeMonarch(Scenario(preset_token="t")) as m, FakeFD() as fd, FakeLangfuse() as lf:
        env = {**_env(m.url, fd.url, lf.url), "MONARCH_TOKEN": "t"}
        r = doctor.check_monarch(_harness(tmp_path), env)
        assert r["backend_health"].startswith("OK ")
        assert "/api/auth/login" not in [q["path"] for q in m.requests]


def test_one_service_down_fails_only_that_key_and_names_the_address(tmp_path, stack):
    m, fd, lf = stack
    dead = _dead_url()
    r = doctor.check_monarch(_harness(tmp_path), _env(m.url, dead, lf.url))

    assert r["ok"] is False
    assert r["fd"].startswith("FAIL ") and dead in r["fd"]
    assert r["backend"].startswith("OK ") and r["langfuse"].startswith("OK ")


def test_unset_variable_is_a_fail_naming_the_variable(tmp_path, stack):
    m, fd, lf = stack
    env = _env(m.url, fd.url, lf.url)
    del env["LANGFUSE_URL"]
    r = doctor.check_monarch(_harness(tmp_path), env)
    assert r["ok"] is False
    assert r["langfuse"].startswith("FAIL ") and "LANGFUSE_URL" in r["langfuse"]


def test_probe_creates_then_cancels_one_authoring_run(tmp_path, stack):
    m, fd, lf = stack
    r = doctor.check_monarch(_harness(tmp_path), _env(m.url, fd.url, lf.url), probe=True)

    assert r["authoring_probe"].startswith("OK ") and "rr-1" in r["authoring_probe"]
    posts = [q["path"] for q in m.requests if q["method"] == "POST"]
    assert posts.count("/api/workflows/recipe/runs") == 1
    assert posts.count("/api/workflows/recipe/runs/rr-1/cancel") == 1


def test_run_doctor_includes_the_block_only_when_the_harness_is_runnable(tmp_path, stack):
    m, fd, lf = stack
    env = _env(m.url, fd.url, lf.url)

    _harness(tmp_path, runnable=True)
    got = doctor.run_doctor(keys=["monarch"], config_dir=tmp_path, env=env)
    assert [r["provider"] for r in got] == ["monarch"]

    _harness(tmp_path, runnable=False)
    assert doctor.run_doctor(keys=["monarch"], config_dir=tmp_path, env=env) == []

    assert doctor.run_doctor(keys=["monarch"], config_dir=tmp_path / "nope", env=env) == []


def test_a_providers_only_arms_list_skips_the_monarch_block(tmp_path, stack):
    """CI runs `wb doctor --arms <providers>` with no Monarch stack up; the block
    must not run there, let alone fail the job."""
    m, fd, lf = stack
    _harness(tmp_path)
    # ponytail: an unregistered key so check_provider stops at the lookup and
    # spends nothing; a real key here would bill a call whenever .env is loaded.
    got = doctor.run_doctor(keys=["not-a-provider"], config_dir=tmp_path,
                            env=_env(m.url, fd.url, lf.url))
    assert [r["provider"] for r in got] == ["not-a-provider"]
    assert m.requests == []


def test_arms_monarch_runs_the_block_and_no_provider(tmp_path, stack):
    m, fd, lf = stack
    _harness(tmp_path)
    got = doctor.run_doctor(keys=["monarch"], config_dir=tmp_path,
                            env=_env(m.url, fd.url, lf.url))
    assert [r["provider"] for r in got] == ["monarch"]
    assert got[0]["ok"] is True
    assert m.requests                       # monarch is not treated as a provider key


def test_format_report_prints_the_monarch_block(tmp_path, stack):
    m, fd, lf = stack
    _harness(tmp_path)
    text = doctor.format_report(doctor.run_doctor(keys=["monarch"], config_dir=tmp_path,
                                                  env=_env(m.url, fd.url, lf.url)))
    assert "[OK ] monarch" in text
    for k in ("backend", "backend_health", "fd", "langfuse"):
        assert f"{k}: OK " in text
