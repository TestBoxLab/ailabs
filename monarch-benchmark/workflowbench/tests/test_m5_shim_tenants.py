"""Tests for the Option B HTTP shim and the M5 tenant pool logic."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from wb_arms.http_shim import EpisodeHTTPShim
from wb_tenants.pool import TenantPool, TenantResetFailed
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


class FakeBackend:
    def __init__(self, dirty_tenants=()):
        self.dirty = set(dirty_tenants)
        self.provisioned, self.torn_down = [], []

    def provision(self, tenant_id, template):
        self.provisioned.append((tenant_id, template))

    def verify_clean(self, tenant_id):
        return tenant_id not in self.dirty

    def teardown(self, tenant_id):
        self.torn_down.append(tenant_id)


def test_tenant_pool_lease_release_capacity():
    be = FakeBackend()
    pool = TenantPool(be, ["t1", "t2"], resets_per_hour=6)
    assert pool.capacity_episodes_per_day() == 2 * 6 * 24
    a = pool.lease("ep1", "template-crm")
    b = pool.lease("ep2", "template-crm")
    with pytest.raises(RuntimeError, match="tenant-capped"):
        pool.lease("ep3", "template-crm")
    pool.track(a, "gmail_message", "msg-1")
    pool.release(a)
    assert be.torn_down == [a.tenant_id]
    c = pool.lease("ep3", "template-crm")     # freed tenant reusable
    assert c.tenant_id == a.tenant_id
    assert pool.orphan_sweep() == []          # teardown cleared tracked resources


def test_dirty_tenant_never_starts_episode():
    be = FakeBackend(dirty_tenants={"t1"})
    pool = TenantPool(be, ["t1"])
    with pytest.raises(TenantResetFailed):
        pool.lease("ep1", "template-crm")
    # lease failed -> tenant released, no deadlock on retry
    with pytest.raises(TenantResetFailed):
        pool.lease("ep1-retry", "template-crm")


def test_orphan_sweep_reports_leaks():
    be = FakeBackend()
    pool = TenantPool(be, ["t1"])
    t = pool.lease("ep1", "tpl")
    pool.track(t, "drive_file", "file-9")
    pool._release_nolock(t)                   # released without teardown = leak
    orphans = pool.orphan_sweep()
    assert orphans == [{"tenant": "t1", "kind": "drive_file", "ref": "file-9"}]
