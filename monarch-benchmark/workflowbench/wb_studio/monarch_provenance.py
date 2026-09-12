"""Capture available Monarch identity; project retained facts without live lookups."""
import hashlib
import json
import re


def _kb_hash(kb):
    return hashlib.sha256(json.dumps(kb, sort_keys=True).encode()).hexdigest() if kb else None


def capture(rc, env):
    """No network: declarations and local checkouts are not deployed-build proof."""
    from wb_orchestrator.config import from_workflowbench
    from wb_studio.enterprise import checkout_identity

    records = []
    for competitor in rc.competitors:
        harness = competitor.harness
        if harness.kind != "monarch":
            continue
        checkout = None
        try:
            checkout = checkout_identity(from_workflowbench(harness.monarch_repo, rc.config_dir, rc.runtime_root))
        except (OSError, ValueError):
            pass
        label = (env.get("MONARCH_BUILD") or "").strip()
        commit = (env.get("MONARCH_BUILD_COMMIT") or "").strip().lower()
        commit = commit if re.fullmatch(r"[0-9a-f]{40}", commit) else None
        declared = bool(label or commit)
        identity = {} if declared else checkout or {}
        records.append({"competitor_id": getattr(competitor, "name", None), "harness": getattr(harness, "name", None),
            "status": "declared" if declared else "checkout" if checkout else "not_recorded",
            "build_label": label or identity.get("version"), "commit": commit if declared else identity.get("commit"),
            "branch": identity.get("branch"), "dirty": identity.get("dirty"),
            "patch_sha256": identity.get("patch_sha256"), "checkout": checkout,
            "knowledge_base_sha256": _kb_hash(rc.monarch_kb.kb) if rc.monarch_kb else None,
            "model_families": dict(harness.model_families), "services": [],
            "note": "No deployed source attestation was captured. A checkout or operator declaration does not prove which code the remote services ran."})
    return records


_FIELDS = ("competitor_id", "harness", "build_label", "commit", "branch", "dirty", "patch_sha256", "knowledge_base_sha256", "note")
_SERVICE_FIELDS = ("service", "commit", "deployment_id", "image_digest", "source_sha256", "dirty", "status")


def _record(value, segment_id=None, recorded_at=None):
    status = value.get("status")
    result = {key: value.get(key) for key in _FIELDS}
    result.update(status=status if status in ("declared", "checkout", "verified") else "not_recorded",
                  segment_id=segment_id, recorded_at=recorded_at,
                  model_families=dict(value.get("model_families") or {}), services=[])
    for service in value.get("services") or []:
        if isinstance(service, dict):
            result["services"].append({key: service.get(key) for key in _SERVICE_FIELDS})
    return result


def project(job):
    """Read stored evidence only; absent historical identity is never backfilled."""
    records = []
    for segment in job.get("execution_segments") or []:
        for value in segment.get("monarch_provenance") or []:
            records.append(_record(value, segment.get("id"), segment.get("started_at")))
    settings = job.get("settings") or {}
    if not records:
        for arm in settings.get("arms") or []:
            if arm.get("kind") != "enterprise":
                continue
            served = arm.get("served") or {}
            checkout = served.get("checkout") or {}
            manifest = (job.get("execution_manifests") or {}).get(arm.get("id")) or {}
            source = manifest.get("source") or {}
            records.append(_record({**source, **checkout, "competitor_id": arm.get("id"), "harness": "monarch",
                "status": "declared" if checkout.get("declared") else "checkout" if checkout else "not_recorded",
                "build_label": served.get("version") or source.get("declared_build"),
                "knowledge_base_sha256": ((manifest.get("artifacts") or {}).get("knowledge_base") or {}).get("sha256"),
                "note": "Recorded declaration or checkout; the deployment was not independently attested."},
                recorded_at=job.get("created_at")))
    if not records:
        labels = list(dict.fromkeys(str(row.get("model") or row.get("arm") or "") for row in job.get("results") or []
                                   if str(row.get("model") or row.get("arm") or "").startswith("monarch@")))
        configured = job.get("resolved_config") or {}
        has_monarch = labels or any("monarch" in str(model).lower() for model in settings.get("models") or [])
        if has_monarch:
            kb = (configured.get("monarch_kb") or {}).get("kb")
            for label in labels or [None]:
                records.append(_record({"competitor_id": label, "build_label": label, "knowledge_base_sha256": _kb_hash(kb),
                    "note": "Exact deployed commit was not recorded. A competitor label alone does not establish deployment identity."}))
    return {"status": "recorded" if any(r["status"] != "not_recorded" for r in records)
            else "not_recorded" if records else "not_applicable", "segments": records}
