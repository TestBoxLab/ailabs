"""EnterpriseOps-Gym as a product under test (feature 026, user story 1).

Licence and provenance: LEGAL.md beside this file. Apache-2.0, ServiceNow AI
Research / Mila / Universite de Montreal.

The world is a containerized service per domain, and it turned out to be less work
than the plan assumed (research.md, spike S1). Each domain image runs a FastAPI
application that already publishes an OpenAPI 3.1 document -- 79 paths and 108
operations for ITSM -- so nothing is wrapped or guessed, and Monarch's discovery can
map it as it stands.

Four endpoints carry the whole adapter:

  POST /api/seed-database   {database_id, sql_content}  -> a private world
  GET  /api/database-state  x-database-id header         -> the snapshot
  GET  /api/download-db-file                             -> the SQLite file itself
  DELETE /api/delete-database                              -> teardown

An attempt can hold more than one world: 88 of the 649 tasks in the `oracle` set are
`hybrid` and span two servers. So everything here is per server -- one database, one
snapshot key, one stored SQLite file each -- and every verifier names the server it
checks with `gym_name`.

The verifiers are the source's own SQL with their own expected values and their own
comparison, run at grading time against the stored SQLite files with the standard
library. Their checks run exactly as shipped, and grading stays offline, out of
process and regradable.

Nothing here is imported at start-up: `wb_world/registry.py` imports it lazily, and a
world that is not reachable is a named refusal from `prerequisites()`.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wb_world.adapter import PositiveResult, canonical

#: The seven servers the dataset names, counted across all 649 tasks of the `oracle`
#: set. These are the snapshot's top-level keys and what a product declares.
SERVERS = ("gym-calendar", "gym-email-mcp", "gym-google-drive-mcp", "gym-itsm-mcp",
           "gym-teams-mcp", "sn-csm-server", "sn-hr-internal")

#: Where each server answers: WB_EOG_URL_GYM_ITSM_MCP, else WB_EOG_URL for a
#: single-server round, else the URL the task's own configuration names.
URL_ENV = "WB_EOG_URL"
DEFAULT_URL = "http://127.0.0.1:18005"

#: Operations only the lab may call. They sit on the same surface as the world's real
#: work, and a competitor that reached them could write the expected result with one
#: query (`/api/sql-runner`), read the verifier's own target, or erase the evidence
#: (`/api/reset-database`). The front door removes them from the published document
#: and refuses them on the wire; this adapter reaches them with its own client.
ADMIN_PATHS = (
    "/api/seed-database", "/api/sql-runner", "/api/reset-database",
    "/api/clone-database", "/api/delete-database", "/api/database-state",
    "/api/download-db-file", "/api/schema", "/api/sample-data",
)

_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]+")
_TIMEOUT = 120


def server_url(name: str, fallback: str | None = None) -> str:
    """The base URL for one server, most specific setting first."""
    # `-` survives _SAFE_ID, and an environment variable cannot hold one.
    key = f"{URL_ENV}_{re.sub(r'[^A-Za-z0-9]+', '_', name).upper()}"
    return (os.environ.get(key) or os.environ.get(URL_ENV) or fallback or DEFAULT_URL).rstrip("/")


def headers_for(context: dict[str, Any] | None) -> dict[str, str]:
    """The task's own identity headers, passed through unchanged in value.

    Three of the context keys carry stray whitespace upstream (`'x-user-email '`),
    and a header name with a space is not valid HTTP. The name is stripped so the
    request can be made at all; the value, and the benchmark's data, are untouched.
    """
    return {str(k).strip(): str(v) for k, v in (context or {}).items() if str(k).strip()}


class _Server:
    """One of an attempt's worlds: its base URL, its private database, its headers."""

    def __init__(self, config: dict[str, Any], database_id: str):
        self.name = config.get("mcp_server_name") or "gym"
        self.url = server_url(self.name, config.get("mcp_server_url"))
        self.database_id = database_id
        self.seed_file = config.get("seed_database_file")
        self.seed_sql = config.get("seed_sql")
        self.headers = headers_for(config.get("context"))

    def request(self, method: str, path: str, body: bytes | None = None,
                extra: dict[str, str] | None = None) -> bytes:
        headers = {"x-database-id": self.database_id, "Content-Type": "application/json",
                   **self.headers, **(extra or {})}
        req = urllib.request.Request(f"{self.url}{path}", method=method.upper(),
                                     headers=headers, data=body)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return r.read()

    def admin(self, method: str, path: str, body: dict | None = None) -> Any:
        raw = self.request(method, path, json.dumps(body).encode() if body is not None else None)
        return json.loads(raw or b"null")


class EnterpriseOpsWorld:
    """One attempt on one EnterpriseOps-Gym task, over its own private databases."""

    # The contract's four values, declared on the class so `adapter.unsatisfied` can
    # check it without constructing one -- constructing one seeds a database.
    artifacts_dir: Any = None
    snapshot0: dict[str, Any] | None = None
    tool_calls: tuple = ()
    events: tuple = ()

    def __init__(self, task: dict[str, Any], episode_id: str, frozen_time: str | None = None):
        self.task = task
        self.episode_id = episode_id
        # One database id per attempt. A retried attempt must not see the aborted
        # one's writes, and this is what keeps them apart.
        self.database_id = _SAFE_ID.sub("-", f"wb-{episode_id}")[:85] + "-" + uuid.uuid4().hex
        ref = task.get("source_ref") or {}
        configs = ref.get("servers") or []
        if not configs:
            raise ValueError("the task records no servers; it should not have been imported")
        self.servers = {c["mcp_server_name"]: _Server(c, self.database_id) for c in configs}
        self.tool_calls: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self._journal = None
        self._closed = False
        self._specs: dict[str, dict[str, Any]] = {}
        self._schemas: dict[str, dict[str, Any]] = {}
        seeds = {}
        for name, server in self.servers.items():
            seeds[name] = _seed_sql(server)
            expected = (ref.get("seed_sha256") or {}).get(name)
            if expected:
                root = Path(os.environ.get("WB_EOG_DBS", ".external/enterprise-ops-dbs")).resolve()
                path = (root / server.seed_file).resolve()
                if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError(f"seed database hash mismatch for {name}")
        try:
            for name, server in self.servers.items():
                server.admin("POST", "/api/seed-database",
                             {"database_id": self.database_id, "sql_content": seeds[name]})
            self.snapshot0 = self.snapshot()
        except BaseException:
            self.close()
            raise

    # -- the three tools -------------------------------------------------------
    def api_search(self, query: str, top_k: int = 5) -> str:
        """The worlds' own interface documents are the search surface."""
        self.tool_calls.append({"tool": "api_search", "query": query})
        words = [w for w in re.split(r"\W+", query.lower()) if w]
        hits = []
        for name in self.servers:
            for path, ops in self._public_spec(name).get("paths", {}).items():
                if path in ADMIN_PATHS:
                    continue
                for method, op in ops.items():
                    blob = f"{path} {op.get('summary', '')} {op.get('operationId', '')}".lower()
                    if any(w in blob for w in words):
                        hits.append({"service": name, "method": method.upper(), "path": path,
                                     "summary": op.get("summary") or op.get("operationId"),
                                     "operation": op,
                                     "components": self._public_spec(name).get("components", {})})
        return self._observe("api_search", {"query": query, "top_k": top_k},
                             lambda: json.dumps(hits[:top_k]))

    def api_fetch(self, method: str, url: str, params: str | None = None,
                  body: str | None = None) -> str:
        self.tool_calls.append({"tool": "api_fetch", "method": method, "url": url})
        return self._observe("api_fetch",
                             {"method": method, "url": url, "params": params, "body": body},
                             lambda: self._call(method, url, params, body))

    def base64_encode(self, text: str) -> str:
        self.tool_calls.append({"tool": "base64_encode"})
        return self._observe("base64_encode", {"text": text},
                             lambda: base64.b64encode(text.encode()).decode())

    def _call(self, method: str, url: str, params: str | None, body: str | None) -> str:
        name, path = self._route(url)
        if name is None:
            return _error(404, f"no server of this product serves {url!r}; "
                               f"the services are {', '.join(sorted(self.servers))}")
        # Decode once, up front. Every check below reads the decoded path and the
        # target sent on the wire is re-encoded from it. Mixing the two forms is what
        # broke: the admin guard read the raw path while the surface check read the
        # decoded one, and the decoded one was then sent as the request target --
        # `/locations/name/TechCorp%20NYC%20Headquarters` became a space in the
        # request line, which urllib refuses outright.
        path = urllib.parse.unquote(path)
        if any(path.startswith(a) for a in ADMIN_PATHS):
            # Refused here as well as at the front door: a world reached by any other
            # route is still the same world.
            return _error(403, f"{path} is an administrative operation of the product "
                               f"under test, not part of the task")
        if method.upper() == "GET" and path == "/openapi.json":
            return json.dumps(self._public_spec(name))
        public = self._public_spec(name)
        route, separator, query = path.partition("?")
        permitted = any(method.lower() in ops and
                        re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", p), route)
                        for p, ops in public.get("paths", {}).items())
        if not permitted:
            return _error(403, f"{method.upper()} {route} is outside this task's published tool mode")
        path = urllib.parse.quote(route, safe="/") + separator + query
        if params:
            path = f"{path}?{urllib.parse.urlencode(json.loads(params))}"
        try:
            return self.servers[name].request(method, path,
                                              body.encode() if body else None
                                              ).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            # The shim turns {"error": {"code": N}} back into HTTP status N, so an
            # application error reaches the competitor as the world's own answer
            # rather than as a harness failure.
            return _error(e.code, e.read().decode("utf-8", "replace"))

    def _route(self, url: str) -> tuple[str | None, str]:
        """`/<server>/<path>` when the first segment names one of this attempt's
        servers; otherwise the only server, when there is only one."""
        path = url if url.startswith("/") else "/" + url.split("://", 1)[-1].split("/", 1)[-1]
        head, _, rest = path.lstrip("/").partition("/")
        if head in self.servers:
            return head, "/" + rest
        if len(self.servers) == 1:
            return next(iter(self.servers)), path
        return None, path

    def _observe(self, tool: str, arguments: dict, call):
        event = {"sequence": len(self.events), "kind": "tool", "tool": tool,
                 "arguments": dict(arguments), "started_at": datetime.now(timezone.utc).isoformat()}
        self.events.append(event)
        if self._journal is not None:
            self._journal.tool({**event, "status": "running"})
        try:
            value = call()
            event.update(status="completed", result=value)
            return value
        except Exception as exc:
            event.update(status="error", error=str(exc))
            raise
        finally:
            event["finished_at"] = datetime.now(timezone.utc).isoformat()
            if self._journal is not None and event.get("status") in ("completed", "error"):
                self._journal.tool(event, self.snapshot if event["status"] == "completed" else None)

    # -- snapshots -------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """`{server: {table: [rows]}}`, rows sorted, which is what diff_snapshots eats.

        Sorting is not tidiness: two dumps of an untouched world must be identical or
        every re-dump would read as collateral damage, and SQLite promises no row
        order without an ORDER BY.
        """
        out = {}
        for name, server in self.servers.items():
            tables = (server.admin("GET", "/api/database-state") or {}).get("table_data") or {}
            if name not in self._schemas:
                self._schemas[name] = (server.admin("GET", "/api/schema") or {}).get("schema") or {}
            out[name] = {t: _snapshot_rows(rows, self._schemas[name].get(t, {}))
                         for t, rows in tables.items()}
        return canonical(out)

    def finish(self) -> dict[str, Any]:
        self.snapshot1 = self.snapshot()
        # The verifiers are SQL and grading happens later in another process, so the
        # databases themselves are the evidence. Stored beside the snapshots.
        if self.artifacts_dir:
            for name in self.servers:
                self.download_db(name, Path(self.artifacts_dir) / db_filename(name))
        return self.snapshot1

    def download_db(self, name: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.servers[name].request("GET", "/api/download-db-file"))
        return dest

    def close(self) -> None:
        """Idempotent: called from a `finally` that may run twice, and a world left
        behind is a database file nothing will ever delete."""
        if self._closed:
            return
        self._closed = True
        for server in self.servers.values():
            try:
                server.admin("DELETE", "/api/delete-database", {"database_id": self.database_id})
            except Exception:
                pass   # teardown must never turn a finished attempt into a failed one

    def attach_journal(self, directory: str | Path) -> None:
        if self._journal is not None or self.events:
            raise RuntimeError("attach the journal before any tool use and only once")
        from wb_results.evidence import AttemptJournal
        self._journal = AttemptJournal(Path(directory), self.snapshot0)

    def record_agent_event(self, entry: dict) -> None:
        if self._journal is not None:
            self._journal.agent(entry)

    # -- the published surface --------------------------------------------------
    def _spec(self, name: str) -> dict[str, Any]:
        if name not in self._specs:
            self._specs[name] = json.loads(self.servers[name].request("GET", "/openapi.json"))
        return self._specs[name]

    def _public_spec(self, name):
        document = copy.deepcopy(self._spec(name))
        ref = (getattr(self, "task", {}) or {}).get("source_ref") or {}
        selected = set(ref.get("selected_tools") or [])
        restricted = set(ref.get("restricted_tools") or [])
        paths = {}
        for path, ops in document.get("paths", {}).items():
            if path in ADMIN_PATHS:
                continue
            public = {}
            for method, op in ops.items():
                tool = re.sub(r"[^a-z0-9]+", "_", op.get("summary", "").lower()).strip("_")
                if (selected and tool not in selected and op.get("operationId") not in selected) or tool in restricted:
                    continue
                # The lab injects source credentials/database identity for both
                # competitors. Neither must know or override those headers.
                op["parameters"] = [v for v in op.get("parameters", []) if v.get("in") != "header"]
                public[method] = op
            if public:
                paths[path] = public
        document["paths"] = paths
        # Keep only schemas referenced by permitted operations; admin seed schemas
        # and unrelated operations are not task-visible knowledge.
        schemas = document.get("components", {}).get("schemas", {})
        needed, pending = {}, [paths]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                reference = value.get("$ref", "")
                key = reference.removeprefix("#/components/schemas/")
                if reference.startswith("#/components/schemas/") and key not in needed and key in schemas:
                    needed[key] = schemas[key]
                    pending.append(schemas[key])
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        document["components"] = {"schemas": needed}
        return document

    def interfaces(self):
        return _Interfaces({name: self._public_spec(name) for name in self.servers})

    # -- the class methods ------------------------------------------------------
    @classmethod
    def service_names(cls) -> list[str]:
        return list(SERVERS)

    @classmethod
    def prerequisites(cls) -> list[str]:
        """Never starts anything to find out; it runs before money is reserved."""
        url = os.environ.get(URL_ENV, DEFAULT_URL).rstrip("/")
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=5) as r:
                r.read()
        except Exception as exc:
            return [f"an EnterpriseOps-Gym domain server answering at {url} "
                    f"(set {URL_ENV}, or {URL_ENV}_<SERVER> per server; start one with "
                    f"`docker run -p 18005:8005 <enterpriseops-gym-mcp-DOMAIN image>`) "
                    f"-- {type(exc).__name__}"]
        return []

    @classmethod
    def positive_check(cls, task: dict[str, Any], snapshot0: dict[str, Any],
                       snapshot1: dict[str, Any], artifacts: Any = None) -> PositiveResult:
        """The source's own verifiers: their query, their expected value, their
        comparison, unchanged.

        Every verifier names the server it checks (`gym_name`), and a hybrid task has
        two -- running them all against the first database would fail 88 of the 649
        tasks for the wrong reason.
        """
        ref = task.get("source_ref") or {}
        verifiers = ref.get("verifiers") or []
        only = next(iter(s["mcp_server_name"] for s in (ref.get("servers") or [])), None)
        results, connections = [], {}
        try:
            for v in verifiers:
                cfg = v.get("validation_config") or {}
                name = v.get("gym_name") or only
                conn = connections.get(name) or _open(artifacts, name, connections)
                sql = cfg.get("query") or cfg.get("sql")
                got = [dict(r) for r in conn.execute(sql)] if sql else None
                results.append({"name": v.get("name"), "type": v.get("verifier_type"),
                                "gym_name": name, "comparison": cfg.get("comparison_type"),
                                "passed": matches(got, cfg.get("expected_value"),
                                                  cfg.get("comparison_type", "equals")),
                                "expected": cfg.get("expected_value"), "got": got})
        finally:
            for conn in connections.values():
                conn.close()
        return PositiveResult(
            passed=all(r["passed"] for r in results) if results else False,
            detail={"verifiers": results},
            source="EnterpriseOps-Gym SQL verifiers",
            side_effects=None,   # the source has no collateral finding of its own
        )


class _Interfaces:
    """Each world's own OpenAPI document, minus the operations only the lab may call.

    The documents live in `self.documents`, not `self.spec`: the front door asks for
    `spec(service, public_url)`, and an attribute of that name would shadow it.
    """

    def __init__(self, documents: dict[str, dict[str, Any]]):
        self.documents = documents
        self.admin_paths = ADMIN_PATHS

    def services(self) -> list[str]:
        return list(self.documents)

    def spec(self, service: str, public_url: str) -> dict[str, Any]:
        document = self.documents[service]
        paths = {p: ops for p, ops in document.get("paths", {}).items() if p not in ADMIN_PATHS}
        return {**document, "servers": [{"url": f"{public_url}/{service}"}], "paths": paths}

    def rest_url(self, service: str, rest: str) -> str:
        return f"/{service}/{rest}"


def db_filename(server: str) -> str:
    return f"world-{_SAFE_ID.sub('-', server)}.sqlite"


def _open(artifacts: Any, name: str, cache: dict) -> sqlite3.Connection:
    path = _artifact(artifacts, db_filename(name))
    if path is None:
        raise FileNotFoundError(
            f"the attempt did not store {db_filename(name)}, so the benchmark's own "
            f"verifiers cannot be run; the attempt is ungraded, not failed")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cache[name] = conn
    return conn


def matches(got: Any, want: Any, comparison: str | None = "equals") -> bool:
    """Match benchmark/verifier.py at upstream commit 271f2c357f763376997dfd16807fcde2474ae41b.

    SQL result extraction uses a scalar for one cell, a dict for one multi-column
    row, and the original list otherwise. Upstream uses Python comparison without
    coercion; do not inherit AutomationBench's number-as-text forgiveness here.
    """
    value = got
    if isinstance(got, list) and len(got) == 1:
        value = got[0]
        if isinstance(value, dict) and len(value) == 1:
            value = next(iter(value.values()))
    if comparison not in ("equals", "greater_than", "less_than", "contains"):
        raise ValueError(f"unknown comparison_type {comparison!r} in an EnterpriseOps-Gym verifier")
    try:
        if comparison == "equals":
            return value == want
        if comparison == "greater_than":
            return value > want
        if comparison == "less_than":
            return value < want
        return want in str(value)
    except (TypeError, ValueError):
        return False


def _snapshot_rows(rows: list[dict], schema: dict) -> list[dict]:
    """Expose native primary keys as snapshot identity without changing source data."""
    keys = [k for k, declaration in schema.get("columns", {}).items()
            if isinstance(declaration, str) and "PRIMARY KEY" in declaration.upper()]
    for constraint in schema.get("constraints", []):
        match = re.fullmatch(r"PRIMARY KEY\s*\(([^)]+)\)", constraint, re.IGNORECASE)
        if match:
            keys = [key.strip() for key in match[1].split(",")]
    if not keys:
        if rows:
            raise ValueError("cannot snapshot a nonempty table without a source primary key")
        return []
    normalized = []
    for row in rows:
        identity = row[keys[0]] if len(keys) == 1 else json.dumps([row[k] for k in keys])
        if identity is None:
            raise ValueError("cannot snapshot a null source primary key")
        if "id" in row and row["id"] != identity:
            raise ValueError("source id conflicts with the table primary key")
        normalized.append({**row, "id": identity})
    return _sorted_rows(normalized)


def _sorted_rows(rows: Any) -> Any:
    if not isinstance(rows, list):
        return rows
    def key(row):
        if isinstance(row, dict):
            for k in ("id", "sys_id", "number", "pk"):
                if k in row:
                    return (0, str(row[k]))
        return (1, json.dumps(row, sort_keys=True, default=str))
    return sorted(rows, key=key)


def _seed_sql(server: _Server) -> str:
    """The task's own seed, read from the extracted domain databases."""
    if server.seed_sql:
        return server.seed_sql
    if not server.seed_file:
        raise ValueError(f"{server.name} records no seed database; the task should not "
                         f"have been imported")
    root = Path(os.environ.get("WB_EOG_DBS", ".external/enterprise-ops-dbs"))
    path = root / server.seed_file
    if not path.is_file():
        raise FileNotFoundError(f"seed database {server.seed_file} not found under {root} "
                                f"(set WB_EOG_DBS to the unpacked gym_dbs.zip)")
    return path.read_text(encoding="utf-8", errors="replace")


def _artifact(artifacts: Any, name: str) -> Path | None:
    if artifacts is None:
        return None
    if isinstance(artifacts, dict):
        value = artifacts.get(name) or artifacts.get(Path(name).stem)
        return Path(value) if value else None
    path = Path(artifacts) / name
    return path if path.is_file() else None


def _error(code: int, message: str) -> str:
    return json.dumps({"error": {"code": code, "message": message}})
