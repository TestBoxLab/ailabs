"""Opt-in integration against the genuine isolated Sierra source, with no provider calls."""
import copy
import json
import os
import secrets
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from grader.grade import grade
from wb_worlds.tau2.adapter import Tau2World

pytestmark = pytest.mark.skipif(os.environ.get("WB_TAU2_LIVE") != "1", reason="Set WB_TAU2_LIVE=1 for the isolated Sierra source integration")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def live_source(tmp_path_factory):
    python = ROOT / ".external/tau2-env/Scripts/python.exe"
    if not python.is_file():
        pytest.fail("Sierra source Python is missing")
    folder = tmp_path_factory.mktemp("tau2-source")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    token = secrets.token_hex(32)
    env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
    env.update(WB_TAU2_ADMIN_TOKEN=token, PYTHONUTF8="1", LOGURU_LEVEL="ERROR", PYTHON_DOTENV_DISABLED="1", LITELLM_LOCAL_MODEL_COST_MAP="True")
    with (folder / "server.log").open("w", encoding="utf-8") as log:
        proc = subprocess.Popen([str(python), str(ROOT / "wb_worlds/tau2/server.py"), "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    pytest.fail((folder / "server.log").read_text())
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                        assert json.load(response)["benchmark"] == "tau2"
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail("private source server did not become ready")
            yield {"WB_TAU2_URL": f"http://127.0.0.1:{port}", "WB_TAU2_ADMIN_TOKEN": token,
                   "WB_TAU2_PYTHON": str(python), "WB_TAU2_ROOT": str(ROOT / ".external/tau2-bench"), "LOGURU_LEVEL": "ERROR"}
        finally:
            proc.terminate()
            proc.wait(timeout=10)


@pytest.fixture
def configured(live_source, monkeypatch):
    for name, value in live_source.items():
        monkeypatch.setenv(name, value)


def task(number):
    return json.loads((ROOT / f"tasks/tau2-retail-smoke/tau2.retail.{number}.json").read_text(encoding="utf-8"))


def finish(world, folder):
    world.artifacts_dir = folder
    final = world.finish()
    world.close()
    return grade(world.task, world.snapshot0, final, world=Tau2World, artifacts=folder)


@pytest.mark.parametrize("number", ["33", "34"])
def test_real_source_success_null_and_unrequested_write(configured, tmp_path, number):
    frozen = task(number)
    null = Tau2World(frozen, f"null-{number}")
    null_grade = finish(null, tmp_path / "null")
    assert null_grade["assertions_passed"] is False
    assert null_grade["passed"] is False
    assert null_grade["ungraded"] is False, null_grade["error"]
    correct = Tau2World(frozen, f"correct-{number}")
    for action in frozen["source_ref"]["task"]["evaluation_criteria"]["actions"]:
        correct.api_fetch("POST", "/tau2-retail/" + action["name"], body=json.dumps(action["arguments"]))
    success = finish(correct, tmp_path / "correct")
    assert success["passed"] is True, success
    assert success["positive"]["reward"] == 1.0
    assert success["positive"]["reward_basis"] == ["DB"]
    assert success["n_changes"] == 5
    assert success["collateral_damage"] == 0
    stray = Tau2World(frozen, f"stray-{number}")
    for action in frozen["source_ref"]["task"]["evaluation_criteria"]["actions"]:
        stray.api_fetch("POST", "/tau2-retail/" + action["name"], body=json.dumps(action["arguments"]))
    stray.api_fetch("POST", "/tau2-retail/modify_user_address", body=json.dumps({
        "user_id": "yusuf_rossi_9620", "address1": "Unrequested address", "address2": "", "city": "Seattle", "country": "USA", "state": "WA", "zip": "98195"}))
    damaged = finish(stray, tmp_path / "stray")
    assert damaged["passed"] is False
    assert damaged["ungraded"] is False, damaged["error"]
    assert damaged["collateral_damage"] > 0
    assert all("yusuf_rossi_9620" in c["path"] for c in damaged["invariant"]["unexpected_changes"])


def test_real_source_customer_is_private_and_uses_attached_callback(configured, tmp_path):
    world = Tau2World(task("33"), "customer")
    requests = []
    def callback(request):
        requests.append(request)
        return {"content": "I am Noah Patel and want help with my order.", "usage": {"input_tokens": 10, "output_tokens": 5}, "cost_usd": 0}
    world.attach_customer(callback, {"model": "scripted-offline", "max_tokens": 256})
    reply = json.loads(world.api_fetch("POST", "/tau2-retail/send_message", body=json.dumps({"message": "Hello, how can I help?"})))
    assert reply == {"message": "I am Noah Patel and want help with my order.", "stopped": False}
    assert len(requests) == 1
    assert requests[0]["model"] == "scripted-offline"
    assert requests[0]["max_tokens"] == 256
    assert "parent" in requests[0]["messages"][0]["content"]
    assert requests[0]["messages"][-1] == {"role": "user", "content": "Hello, how can I help?"}
    assert "parent house" not in json.dumps(world.interfaces().spec("tau2-retail", "http://front-door"))
    world.artifacts_dir = tmp_path
    world.finish()
    world.close()
    evidence = json.loads((tmp_path / "tau2-trajectory.json").read_text())
    assert evidence["messages"][-1]["role"] == "user"
    assert evidence["messages"][-1]["cost"] == 0


def test_real_source_tampering_and_revision_drift_are_refused(configured, tmp_path):
    frozen = task("33")
    wrong = copy.deepcopy(frozen)
    wrong["info"]["world"]["revision"] = "0" * 40
    with pytest.raises(RuntimeError, match="frozen version/revision"):
        Tau2World(wrong, "wrong-revision")
    world = Tau2World(frozen, "tamper")
    action = frozen["source_ref"]["task"]["evaluation_criteria"]["actions"][-1]
    world.api_fetch("POST", "/tau2-retail/" + action["name"], body=json.dumps(action["arguments"]))
    world.artifacts_dir = tmp_path
    final = world.finish()
    world.close()
    path = tmp_path / "tau2-trajectory.json"
    evidence = json.loads(path.read_text())
    evidence["messages"][-1]["content"] = "fabricated output"
    path.write_text(json.dumps(evidence))
    result = grade(frozen, world.snapshot0, final, world=Tau2World, artifacts=tmp_path)
    assert result["ungraded"] is True
    assert result["passed"] is False
    assert "Returned:" in result["error"] and "fabricated output" in result["error"]


def test_real_source_abnormal_termination_keeps_its_original_reward_gate(configured, tmp_path):
    frozen = task("34")
    world = Tau2World(frozen, "timeout")
    for action in frozen["source_ref"]["task"]["evaluation_criteria"]["actions"]:
        world.api_fetch("POST", "/tau2-retail/" + action["name"], body=json.dumps(action["arguments"]))
    world.set_termination("timeout")
    result = finish(world, tmp_path)
    assert result["passed"] is False
    assert result["ungraded"] is False
    assert result["positive"]["reward"] == 0.0
    assert "timeout" in result["positive"]["info"]["note"]
    assert result["collateral_damage"] == 0


def test_real_telecom_customer_tools_stay_on_the_private_callback(configured, tmp_path):
    from wb_worlds.tau2.importer import convert_task, source_pin, source_root, domain_policy
    source = source_root()
    data = source / "data/tau2/domains/telecom"
    row = json.loads((data / "tasks.json").read_text())[0]
    frozen = convert_task(row, "telecom", source_pin(source, "telecom/base"), domain_policy(data, "telecom"))
    world = Tau2World(frozen, "telecom-customer")
    requests = []
    def callback(request):
        requests.append(request)
        return {"content": "I am abroad and my mobile data is not working.", "cost_usd": 0}
    world.attach_customer(callback, {"model": "scripted-offline"})
    assert json.loads(world.send_message("Hello, how can I help?"))["stopped"] is False
    names = {tool["name"] for tool in requests[0]["tools"]}
    assert "toggle_roaming" in names
    assert "/tau2-telecom/toggle_roaming" not in world.interfaces().spec("tau2-telecom", "http://front-door")["paths"]
    world.close()
