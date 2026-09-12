"""Tests for the Option B HTTP shim."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from wb_arms.http_shim import EpisodeHTTPShim
from wb_world.episode import Episode, load_task_file

ROOT = Path(__file__).resolve().parents[1]


def _post(url: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def test_http_shim_three_tools_and_isolation():
    task = load_task_file(sorted((ROOT / "tasks").glob("*.json"))[0])
    ep = Episode(task, "shim-test")
    shim = EpisodeHTTPShim(ep).start()
    try:
        out = _post(f"{shim.url}/search", {"query": "salesforce update"})
        assert "salesforce" in out["result"].lower()
        enc = _post(f"{shim.url}/encode", {"text": "doctor"})
        assert enc["result"] == "ZG9jdG9y"
        fetch = _post(f"{shim.url}/fetch", {
            "method": "GET",
            "url": "https://yourinstance.salesforce.com/services/data/v61.0/sobjects/Contact/" +
                   task["info"]["assertions"][0].get("contact_id",
                       task["info"]["assertions"][0].get("record_id", ""))})
        assert "error" not in fetch or fetch.get("result")
        assert len(ep.tool_calls) == 3          # every hop lands on the Episode
    finally:
        shim.stop()
