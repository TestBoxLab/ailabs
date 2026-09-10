"""Durable, metadata-only telemetry; every receiver here is local and free."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from wb_orchestrator import langfuse_export as export


def reservation(**changes):
    return {"reservation_id": "run/task/request-1", "scope_id": "run/task",
            "maximum_microusd": 3000000, "actual_microusd": None,
            "created_at": "2026-09-10T10:00:00+00:00", "dispatched_at": None,
            "settled_at": None, "metadata_json": json.dumps({
                "model": "model-1", "provider": "openai", "purpose": "analysis",
                "api_key": "secret-value", "prompt": "private prompt",
                "error": "private error"}), **changes}


def record(path, value=None, **kwargs):
    with sqlite3.connect(path) as db:
        export.ensure_schema(db)
        export.record(db, value or reservation(), **kwargs)


@contextmanager
def receiver(response=None, on_receive=None):
    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            captured.append((self.path, dict(self.headers), json.loads(
                self.rfile.read(int(self.headers["Content-Length"])))))
            if on_receive:
                on_receive()
            if isinstance(response, str) and response.startswith('disconnect'):
                self.close_connection = True
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(response or {}).encode())

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            found = [] if response == 'disconnect_missing' else spans(captured)
            self.wfile.write(json.dumps({'data': [{'id': s['spanId'], 'traceId': s['traceId']} for s in found]}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield captured, {"LANGFUSE_URL": f"http://127.0.0.1:{server.server_port}",
                         "LANGFUSE_PUBLIC_KEY": "public", "LANGFUSE_SECRET_KEY": "private"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def spans(captured):
    return [span for _, _, body in captured for resource in body["resourceSpans"]
            for scope in resource["scopeSpans"] for span in scope["spans"]]


def attrs(span):
    return {a["key"]: next(iter(a["value"].values())) for a in span["attributes"]}


def test_record_is_atomic_unknown_safe_and_durable(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    record(path)
    with sqlite3.connect(path) as db:
        export.record(db, reservation(reservation_id="rolled-back"))
        db.rollback()
    assert export.status(path)["pending"] == 1
    assert export.flush(path, env={})["configured"] is False
    with receiver() as (captured, env):
        result = export.flush(path, env=env)
    assert result["sent"] == 1 and result["pending"] == 0
    [span] = spans(captured)
    a = attrs(span)
    assert a["langfuse.observation.type"] == "span"
    assert "langfuse.observation.model.name" not in a
    assert "langfuse.observation.cost_details" not in a
    assert "private prompt" not in json.dumps(captured)
    assert "secret-value" not in json.dumps(captured)
    assert "private error" not in json.dumps(captured)
    assert captured[0][0] == "/api/public/otel/v1/traces"
    assert captured[0][1]["X-Langfuse-Ingestion-Version"] == "4"
    assert len(span["traceId"]) == 32 and len(span["spanId"]) == 16


def test_known_zero_and_preserved_disjoint_usage(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    record(path, usage={"input": 5, "output": 2, "cache_read": 11, "cache_write": 3,
                        "prompt": "must not export"})
    record(path, reservation(actual_microusd=0, settled_at="2026-09-10T10:01:00Z"))
    with receiver() as (captured, env):
        export.flush(path, env=env)
    a = next(attrs(s) for s in spans(captured) if attrs(s)['langfuse.observation.type'] == 'generation')
    assert a["langfuse.observation.type"] == "generation"
    assert json.loads(a["langfuse.observation.cost_details"]) == {"total": 0}
    assert json.loads(a["langfuse.observation.usage_details"]) == {
        "input": 5, "output": 2, "cache_read_input_tokens": 11,
        "cache_creation_input_tokens": 3}


def test_monarch_and_attempt_summaries_never_duplicate_generation_cost(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    record(path, reservation(actual_microusd=1200000, metadata_json=json.dumps(
        {"harness": "monarch", "model": "claude-opus-5"})),
        usage={"input": 100, "output": 10}, trace_ids=["a" * 32])
    with sqlite3.connect(path) as db:
        export.record_summary(db, "attempt-1", {"scope_id": "run/task", "passed": False,
                              "termination": "timeout", "cost_usd": 1.2,
                              "output": "private output", "snapshot": {"secret": True}})
    with receiver() as (captured, env):
        export.flush(path, env=env)
    assert len(spans(captured)) == 2
    for span in spans(captured):
        a = attrs(span)
        assert a["langfuse.observation.type"] == "span"
        assert "langfuse.observation.cost_details" not in a
        assert "langfuse.observation.usage_details" not in a
        assert "langfuse.observation.model.name" not in a
    assert "private output" not in json.dumps(captured)
    assert "a" * 32 in json.dumps(captured)


def test_partial_rejection_retries_same_ids_and_source_is_persistent(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    record(path)
    with receiver({"partialSuccess": {"rejectedSpans": "1"}}) as (first, env):
        assert export.flush(path, env=env)["errors"] == 1
    assert export.status(path)["pending"] == 1
    record(path)
    with receiver() as (second, env):
        assert export.flush(path, env=env)["sent"] == 1
    assert spans(first)[0]["spanId"] == spans(second)[0]["spanId"]
    assert spans(first)[0]["traceId"] == spans(second)[0]["traceId"]
    other = tmp_path / "other.sqlite3"
    record(other)
    with receiver() as (third, env):
        export.flush(other, env=env)
    assert spans(third)[0]["traceId"] != spans(first)[0]["traceId"]


def test_delivery_ack_does_not_hide_concurrent_receipt(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    record(path)
    with receiver(on_receive=lambda: record(path, reservation(actual_microusd=20))) as (_, env):
        assert export.flush(path, env=env)["pending"] == 2
    with receiver() as (captured, env):
        assert export.flush(path, env=env)["pending"] == 0
    a = next(attrs(s) for s in spans(captured) if attrs(s)['langfuse.observation.type'] == 'generation')
    assert json.loads(a["langfuse.observation.cost_details"])["total"] == .00002


def test_unconfigured_kick_and_status_do_not_create_files(tmp_path):
    path = tmp_path / "missing.sqlite3"
    export.kick(path, env={})
    assert export.status(path)["pending"] == 0
    assert not path.exists()


def test_disabled_export_retains_pending_even_with_credentials(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    record(path)
    with receiver() as (captured, env):
        result = export.flush(path, env={**env, "WB_LANGFUSE_ENABLED": "0"})
    assert result["configured"] is False
    assert result["pending"] == 1
    assert captured == []


def test_summary_unknown_update_clears_previous_cost(tmp_path):
    path = tmp_path / "results.sqlite3"
    with sqlite3.connect(path) as db:
        export.record_summary(db, "attempt", {"cost_usd": 1})
        export.record_summary(db, "attempt", {})
    with receiver() as (captured, env):
        export.flush(path, env=env)
    assert "langfuse.observation.metadata.cost_usd" not in attrs(spans(captured)[0])


def test_kick_coalesces_a_receipt_arriving_during_delivery(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    record(path)
    first, release, second = threading.Event(), threading.Event(), threading.Event()

    def on_receive():
        if not first.is_set():
            first.set()
            release.wait(3)
        else:
            second.set()

    with receiver(on_receive=on_receive) as (captured, env):
        export.kick(path, env=env)
        assert first.wait(3)
        record(path, reservation(actual_microusd=50))
        export.kick(path, env=env)
        release.set()
        assert second.wait(3), "a coalesced kick must send the newer receipt"
    assert len(spans(captured)) == 3


def test_connection_failure_keeps_pending_without_exporting_error_text(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    record(path)
    with receiver() as (_, env):
        pass  # The receiver's port is now closed.
    result = export.flush(path, env=env, timeout=.2)
    assert result['pending'] == 1 and result['errors'] == 1 and result['sent'] == 0


@pytest.mark.parametrize("ack", ["unexpected response", {"error": "receiver rejected it"}])
def test_invalid_ack_keeps_history_pending(tmp_path, ack):
    path = tmp_path / "ledger.sqlite3"
    record(path)
    with receiver(ack) as (_, env):
        result = export.flush(path, env=env)
    assert result["errors"] == 1 and result["pending"] == 1


def test_invalid_usage_cannot_become_inferred_cost(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    record(path, usage={"input": -1, "output": True, "cache_read": float("nan")})
    with receiver() as (captured, env):
        export.flush(path, env=env)
    assert "NaN" not in json.dumps(captured)
    assert "langfuse.observation.usage_details" not in attrs(spans(captured)[0])


def test_v4_never_updates_an_exported_span_or_bills_a_receipt_twice(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    with receiver() as (captured, env):
        record(path)
        export.flush(path, env=env)
        record(path, reservation(actual_microusd=25), usage={"input": 1})
        export.flush(path, env=env)
        record(path, reservation(actual_microusd=25), outcome="error")
        export.flush(path, env=env)
    seen, total = {}, 0
    for span in spans(captured):
        identity = span['spanId']
        assert identity not in seen or seen[identity] == span, 'v4 observations are immutable after ingestion'
        if identity not in seen:
            total += json.loads(attrs(span).get('langfuse.observation.cost_details', '{}')).get('total', 0)
        seen[identity] = span
    assert total == .000025


@pytest.mark.parametrize('found', [True, False])
def test_lost_ack_never_reposts_and_reconciles_only_observed_records(tmp_path, found):
    path = tmp_path / 'ledger.sqlite3'
    record(path, reservation(actual_microusd=25))
    with receiver('disconnect' if found else 'disconnect_missing') as (captured, env):
        assert export.flush(path, env=env)['uncertain'] == 2
        assert export.flush(path, env=env)['sent'] == 0
        result = export.reconcile(path, env=env)
        assert result['confirmed'] == (2 if found else 0)
        assert result['uncertain'] == (0 if found else 2)
    assert len(captured) == 1, 'an ambiguous acknowledgement must never duplicate a paid generation'
