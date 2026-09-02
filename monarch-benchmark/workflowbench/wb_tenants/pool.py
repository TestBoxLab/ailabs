"""M5 tenant pool manager per BUILD-SPEC §2.7: lease/provision/verify_clean/
teardown, per-tenant locks, tracked-resource teardown, orphan sweep.

The pool logic (leasing, locking, dirty-gating, capacity accounting) is
vendor-neutral and tested here. The Google Workspace backend (template import
via Admin SDK, ephemeral users) plugs in as a TenantBackend once the dev
tenant exists — that access request is the M5 blocker, not this code.
verify_clean gates token spend: an episode never starts on a dirty tenant
(reset failure = infra:tenant_reset_failed).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Protocol


class TenantBackend(Protocol):
    def provision(self, tenant_id: str, template: str) -> None: ...
    def verify_clean(self, tenant_id: str) -> bool: ...
    def teardown(self, tenant_id: str) -> None: ...


@dataclass
class Tenant:
    tenant_id: str
    template: str | None = None
    leased_by: str | None = None
    dirty: bool = False
    resources: list[dict[str, Any]] = field(default_factory=list)  # tracked for teardown


class TenantResetFailed(Exception):
    """Surface as termination infra:tenant_reset_failed."""


class TenantPool:
    def __init__(self, backend: TenantBackend, tenant_ids: list[str],
                 resets_per_hour: float = 6.0):
        self._backend = backend
        self._tenants = {t: Tenant(t) for t in tenant_ids}
        self._locks = {t: threading.Lock() for t in tenant_ids}
        self._pool_lock = threading.Lock()
        self.resets_per_hour = resets_per_hour
        self.reset_count = 0

    def capacity_episodes_per_day(self) -> float:
        """The M5 first-deliverable arithmetic: tenants x resets/hour x 24."""
        return len(self._tenants) * self.resets_per_hour * 24

    def lease(self, episode_id: str, template: str) -> Tenant:
        with self._pool_lock:
            free = next((t for t in self._tenants.values()
                         if t.leased_by is None), None)
            if free is None:
                raise RuntimeError("no free tenant (parallelism is tenant-capped)")
            free.leased_by = episode_id
        self._locks[free.tenant_id].acquire()
        try:
            self._backend.provision(free.tenant_id, template)
            free.template = template
            if not self._backend.verify_clean(free.tenant_id):
                free.dirty = True
                raise TenantResetFailed(
                    f"tenant {free.tenant_id} dirty after provision; episode must "
                    "not start (verify_clean gates token spend)")
            free.dirty = False
            return free
        except Exception:
            self._release_nolock(free)
            raise

    def release(self, tenant: Tenant) -> None:
        try:
            self._backend.teardown(tenant.tenant_id)
            self.reset_count += 1
            tenant.resources.clear()
        finally:
            self._release_nolock(tenant)

    def _release_nolock(self, tenant: Tenant) -> None:
        with self._pool_lock:
            tenant.leased_by = None
        lock = self._locks[tenant.tenant_id]
        if lock.locked():
            lock.release()

    def track(self, tenant: Tenant, kind: str, ref: str) -> None:
        tenant.resources.append({"kind": kind, "ref": ref})

    def orphan_sweep(self) -> list[dict[str, Any]]:
        """Resources still tracked on unleased tenants — the leak report."""
        orphans = []
        with self._pool_lock:
            for t in self._tenants.values():
                if t.leased_by is None and t.resources:
                    orphans.extend({"tenant": t.tenant_id, **r} for r in t.resources)
        return orphans
