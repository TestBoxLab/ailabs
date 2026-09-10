"""Durable metadata-only OTLP export; HTTP never runs in the ledger transaction.

Langfuse attribute mapping: https://langfuse.com/integrations/native/opentelemetry
Unknown billing and Monarch accounting are spans, never inferred generations.
"""
from __future__ import annotations

import base64
import atexit
import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

_FIELDS = {"model", "provider", "billing_provider", "harness", "purpose", "episode_id",
           "run_id", "task_id", "config_hash", "contract_sha256", "version"}
_USAGE = {"input": "input", "output": "output", "cache_read": "cache_read_input_tokens",
          "cache_write": "cache_creation_input_tokens"}
_workers: dict[str, threading.Thread] = {}
_worker_lock = threading.Lock()


def ensure_schema(connection):
    """Use the caller's transaction, including source identity on first creation."""
    connection.execute("CREATE TABLE IF NOT EXISTS telemetry_source (id INTEGER PRIMARY KEY CHECK(id=1), source_id TEXT NOT NULL)")
    connection.execute("INSERT OR IGNORE INTO telemetry_source VALUES (1, ?)", (uuid.uuid4().hex,))
    connection.execute("""CREATE TABLE IF NOT EXISTS telemetry_outbox (
        identity TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL,
        delivered INTEGER NOT NULL DEFAULT 0, attempted INTEGER NOT NULL DEFAULT 0)""")
    if 'attempted' not in {r[1] for r in connection.execute('PRAGMA table_info(telemetry_outbox)')}:
        connection.execute('ALTER TABLE telemetry_outbox ADD COLUMN attempted INTEGER NOT NULL DEFAULT 0')


def _text(value):
    if not isinstance(value, str) or not value or len(value) > 500:
        return None
    if any(ord(c) < 32 for c in value) or re.search(r"sk-(?:ant-|lf-)?[A-Za-z0-9_-]{12}|Bearer |Basic |PRIVATE KEY", value):
        return None
    return value


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _metadata(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            value = {}
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if k in _FIELDS and _text(v) is not None}


def _previous(connection, identity):
    row = connection.execute("SELECT payload FROM telemetry_outbox WHERE identity=?", (identity,)).fetchone()
    return json.loads(row[0]) if row else {}


def _save(connection, identity, value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    connection.execute("""INSERT INTO telemetry_outbox(identity,payload,revision) VALUES (?,?,1)
        ON CONFLICT(identity) DO UPDATE SET payload=excluded.payload, revision=revision+1
        WHERE payload<>excluded.payload""", (identity, payload))


def record(connection, reservation: dict, *, usage: dict | None = None,
           outcome: str | None = None, trace_ids: list | None = None):
    """Queue the latest safe request state; omitted receipts retain earlier usage."""
    ensure_schema(connection)
    r = dict(reservation)
    identity = "request:" + r["reservation_id"]
    value = _previous(connection, identity)
    value.update(kind="request", identity=r["reservation_id"], scope=r["scope_id"])
    value["metadata"] = {**value.get("metadata", {}),
                         **_metadata(r.get("metadata", r.get("metadata_json", {})))}
    for key in ("created_at", "dispatched_at", "settled_at", "maximum_microusd", "actual_microusd"):
        if key in r:
            value[key] = r[key]
    if usage is not None:
        value["usage"] = {k: v for k, v in usage.items() if k in _USAGE and _number(v)}
    if _text(outcome) is not None and re.fullmatch(r"[A-Za-z0-9_.:/-]+", outcome):
        value["outcome"] = outcome
    if trace_ids is not None:
        value["trace_ids"] = sorted({t for t in trace_ids if isinstance(t, str) and re.fullmatch(r"[a-fA-F0-9]{32}", t)})
    _save(connection, identity, value)
    # V4 observations are immutable. Each ledger receipt owns exactly one
    # immutable generation; later accounting events cannot bill it again.
    billing_id = 'billing:' + r['reservation_id']
    if _number(value.get('actual_microusd')) and not _monarch(value['metadata']) and not _previous(connection, billing_id):
        _save(connection, billing_id, {**value, 'kind': 'billing'})


def record_summary(connection, identity, summary: dict):
    """Attempt summaries own no billable generation, even when they report cost."""
    ensure_schema(connection)
    key = "summary:" + identity
    value = _previous(connection, key)
    value.update(kind="summary", identity=identity,
                 scope=summary.get("scope_id") or summary.get("run_id") or identity,
                 metadata=_metadata(summary))
    for field in ("started_at", "finished_at", "termination"):
        if _text(summary.get(field)) is not None:
            value[field] = summary[field]
    if isinstance(summary.get("passed"), bool):
        value["passed"] = summary["passed"]
    if _number(summary.get("cost_usd")):
        value["cost_usd"] = summary["cost_usd"]
    else:
        value.pop("cost_usd", None)
    value.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    _save(connection, key, value)


def _nano(value):
    try:
        return str(int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1_000_000_000))
    except (AttributeError, TypeError, ValueError, OverflowError):
        return "0"


def _id(source, value, length):
    return hashlib.sha256((source + ":" + value).encode()).hexdigest()[:length]


def _attribute(key, value):
    if isinstance(value, bool):
        item = {"boolValue": value}
    elif isinstance(value, (int, float)):
        item = {"doubleValue": value}
    else:
        item = {"stringValue": value if isinstance(value, str) else json.dumps(value, sort_keys=True)}
    return {"key": key, "value": item}


def _monarch(meta):
    return any(str(meta.get(k, '')).lower().startswith('monarch')
               for k in ('harness', 'provider', 'billing_provider'))


def _span(source, value):
    meta = {**value.get("metadata", {}), "source_id": source,
            "scope_id": value["scope"], "identity": value["identity"]}
    actual = value.get("actual_microusd")
    known = _number(actual)
    generation = value["kind"] == "billing"
    if value["kind"] in ("request", "billing"):
        meta["billing_status"] = "known" if known else "unknown"
        if _number(value.get("maximum_microusd")):
            meta["reserved_usd"] = value["maximum_microusd"] / 1e6
        if known:
            meta["actual_usd"] = actual / 1e6
        meta["outcome"] = value.get("outcome") or ("settled" if known else "dispatched" if value.get("dispatched_at") else "reserved")
        if "usage" in value:
            meta["usage"] = value["usage"]
        if "trace_ids" in value:
            meta["monarch_trace_ids"] = value["trace_ids"]
    else:
        meta.update({k: value[k] for k in ("termination", "passed", "cost_usd") if k in value})
    attributes = {"langfuse.observation.type": "generation" if generation else "span",
                  "langfuse.trace.name": "WorkflowBench " + value["kind"],
                  "langfuse.session.id": _id(source, value["scope"], 32),
                  "langfuse.trace.metadata.source_id": source,
                  "langfuse.trace.metadata.scope_id": value["scope"]}
    attributes.update({"langfuse.observation.metadata." + k: v for k, v in meta.items()})
    if generation:
        attributes["langfuse.observation.cost_details"] = json.dumps({"total": actual / 1e6})
        if meta.get("model"):
            attributes["langfuse.observation.model.name"] = meta["model"]
        if "usage" in value:
            attributes["langfuse.observation.usage_details"] = json.dumps({_USAGE[k]: v for k, v in value["usage"].items()})
    start = value.get("dispatched_at") or value.get("started_at") or value.get("created_at")
    end = value.get("settled_at") or value.get("finished_at") or start
    return {"traceId": _id(source, value["scope"], 32),
            "spanId": _id(source, json.dumps(value, sort_keys=True, separators=(',', ':')), 16),
            "name": "WorkflowBench " + value["kind"], "kind": 1,
            "startTimeUnixNano": _nano(start), "endTimeUnixNano": _nano(end),
            "attributes": [_attribute(k, v) for k, v in attributes.items()]}


def _credentials(env):
    from wb_orchestrator.config import derive_langfuse_keys
    values = dict(os.environ if env is None else env)
    if values.get("WB_LANGFUSE_ENABLED", "1").lower() in ("0", "false", "off"):
        return None
    derive_langfuse_keys(values)
    base = values.get("LANGFUSE_URL") or values.get("LANGFUSE_HOST")
    public, secret = values.get("LANGFUSE_PUBLIC_KEY"), values.get("LANGFUSE_SECRET_KEY")
    if not (base and public and secret):
        return None
    auth = base64.b64encode(f"{public}:{secret}".encode()).decode()
    return base.rstrip("/") + "/api/public/otel/v1/traces", "Basic " + auth


def status(path):
    """Read-only pending count; an unused ledger is not created by inspection."""
    if not Path(path).exists():
        return {"pending": 0, "uncertain": 0}
    try:
        with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=.1) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='telemetry_outbox'").fetchone():
                return {"pending": 0, "uncertain": 0}
            return {"pending": db.execute("SELECT count(*) FROM telemetry_outbox WHERE revision>delivered").fetchone()[0],
                    "uncertain": db.execute("SELECT count(*) FROM telemetry_outbox WHERE attempted>delivered AND attempted=revision").fetchone()[0]}
    except sqlite3.Error:
        return {"pending": None, "uncertain": None}


def flush(path, env=None, timeout=3, limit=100):
    """Deliver one bounded batch, acknowledging only each delivered revision."""
    credentials = _credentials(env)
    result = {**status(path), "configured": bool(credentials), "sent": 0, "errors": 0}
    if not credentials or not result["pending"]:
        return result
    try:
        with sqlite3.connect(path, timeout=min(timeout, 1)) as db:
            db.execute('BEGIN IMMEDIATE')
            source = db.execute("SELECT source_id FROM telemetry_source WHERE id=1").fetchone()[0]
            rows = db.execute("SELECT identity,payload,revision FROM telemetry_outbox WHERE revision>attempted AND revision>delivered ORDER BY rowid LIMIT ?", (max(1, min(int(limit), 100)),)).fetchall()
            for identity, _, revision in rows:
                db.execute('UPDATE telemetry_outbox SET attempted=? WHERE identity=?', (revision, identity))
        if not rows:
            return result
        spans = [_span(source, json.loads(payload)) for _, payload, _ in rows]
        body = {"resourceSpans": [{"resource": {"attributes": [_attribute("service.name", "workflowbench")]},
                 "scopeSpans": [{"scope": {"name": "workflowbench.accounting"}, "spans": spans}]}]}
        request = urllib.request.Request(credentials[0], data=json.dumps(body).encode(), headers={
            "Authorization": credentials[1], "Content-Type": "application/json",
            "x-langfuse-ingestion-version": "4"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            ack = json.loads(response.read() or b"{}")
        if not isinstance(ack, dict) or ack.get("error"):
            raise ValueError("Invalid telemetry acknowledgement")
        partial = ack.get("partialSuccess") or {}
        if not isinstance(partial, dict):
            raise ValueError("Invalid partial telemetry acknowledgement")
        if int(partial.get("rejectedSpans") or 0) or partial.get("errorMessage"):
            result["errors"] = 1
            if int(partial.get('rejectedSpans') or 0) == len(rows):
                _retry_rejected(path, rows)
        else:
            with sqlite3.connect(path, timeout=min(timeout, 1)) as db:
                for identity, _, revision in rows:
                    db.execute("UPDATE telemetry_outbox SET delivered=? WHERE identity=? AND revision=?", (revision, identity, revision))
            result["sent"] = len(rows)
    except urllib.error.HTTPError as exc:
        result['errors'] = 1
        if 400 <= exc.code < 500 and exc.code != 408:
            _retry_rejected(path, rows)
    except urllib.error.URLError as exc:
        result['errors'] = 1
        if isinstance(exc.reason, ConnectionRefusedError):
            _retry_rejected(path, rows)
    except (OSError, sqlite3.Error, ValueError, TypeError):
        result["errors"] = 1
    return {**result, **status(path)}


def _retry_rejected(path, rows):
    """Only a definite rejection permits another POST; timeouts are ambiguous."""
    try:
        with sqlite3.connect(path, timeout=1) as db:
            for identity, _, revision in rows:
                db.execute('UPDATE telemetry_outbox SET attempted=delivered WHERE identity=? AND revision=?', (identity, revision))
    except sqlite3.Error:
        pass  # Keep the uncertain send; read-side reconciliation can confirm it.


def reconcile(path, env=None, timeout=3, limit=10):
    """Acknowledge uncertain sends observed remotely; absence never proves failure."""
    credentials = _credentials(env)
    result = {**status(path), 'confirmed': 0, 'errors': 0, 'configured': bool(credentials)}
    if not credentials or not result['uncertain']:
        return result
    try:
        with sqlite3.connect(path) as db:
            source = db.execute('SELECT source_id FROM telemetry_source').fetchone()[0]
            rows = db.execute('SELECT identity,payload,revision FROM telemetry_outbox WHERE attempted=revision AND attempted>delivered LIMIT ?', (min(limit, 10),)).fetchall()
        for identity, payload, revision in rows:
            span = _span(source, json.loads(payload))
            start = datetime.fromtimestamp(int(span['startTimeUnixNano']) / 1e9, timezone.utc)
            from datetime import timedelta
            query = urllib.parse.urlencode({'filter': json.dumps([{'type': 'string', 'column': 'id', 'operator': '=', 'value': span['spanId']}]),
                'fromStartTime': (start - timedelta(seconds=1)).isoformat(),
                'toStartTime': (start + timedelta(seconds=1)).isoformat(), 'fields': 'core', 'limit': 2})
            request = urllib.request.Request(credentials[0].removesuffix('/otel/v1/traces') + '/v2/observations?' + query,
                                             headers={'Authorization': credentials[1]})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.load(response)
            if any(row.get('id') == span['spanId'] and row.get('traceId') == span['traceId'] for row in data.get('data', [])):
                with sqlite3.connect(path) as db:
                    db.execute('UPDATE telemetry_outbox SET delivered=? WHERE identity=? AND revision=?', (revision, identity, revision))
                result['confirmed'] += 1
    except (OSError, sqlite3.Error, ValueError, TypeError):
        result['errors'] = 1
    return {**result, **status(path)}


def kick(path, env=None):
    """Coalesce writes in one worker; failed delivery remains available for retry."""
    values = dict(os.environ if env is None else env)
    if not _credentials(values):
        return
    key = str(Path(path).resolve())

    def work():
        try:
            while True:
                result = flush(key, env=values)
                with _worker_lock:
                    if result["errors"] or not result['sent'] or not status(key)["pending"]:
                        _workers.pop(key, None)
                        return
        finally:
            with _worker_lock:
                if _workers.get(key) is threading.current_thread():
                    _workers.pop(key, None)

    with _worker_lock:
        if key in _workers:
            return
        thread = threading.Thread(target=work, name="workflowbench-langfuse", daemon=True)
        _workers[key] = thread
        thread.start()


def drain(timeout=4):
    """Bounded shutdown grace; abrupt exits leave durable pending rows."""
    deadline = time.monotonic() + timeout
    with _worker_lock:
        threads = list(_workers.values())
    for thread in threads:
        thread.join(max(0, deadline - time.monotonic()))


atexit.register(drain)
