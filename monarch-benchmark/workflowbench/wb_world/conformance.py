"""Feature 008: is every catalogue action TRUE against the simulated apps?

Monarch's own `validate-seeds.mjs` is static: it says a seed file has the right
shape, never that the request runs or that the declared response is the response
the front door really returns. A wrong Google Sheets response schema passed it
and made Monarch refuse every Sheets task.

This module executes each action -- in process, over an Episode, through the
same URL mapping `wb_arms/http_shim.py::_rest` uses -- and gives one of six
verdicts. Design note: docs/superpowers/specs/2026-09-04-seed-conformance-design.md
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from wb_world.episode import Episode, load_task_file
from wb_world.openapi import load_schemas

# The corpus folders the worlds are drawn from, anchored to the package so the
# check works from any working directory (the CLI and the setup gate share it).
CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"


def default_corpus_dirs() -> list[Path]:
    return sorted(p for p in CORPUS_DIR.glob("imported-*") if p.is_dir())


TOKEN = re.compile(r"\{\{(\w+)\}\}")
_STEP = re.compile(r"\.(\w+)|\[(\d+)\]")

# Reads and lists carry the contract the builder plans against; writes need
# inputs this check cannot always invent, so setup only warns about them.
READ_METHODS = {"GET", "HEAD"}
# `not_executable` is this check's own limitation, never the seed's fault.
BENIGN = {"ok", "not_executable", "no_handler"}
# What the seed generator emits when it has no real example for an id. Sending
# one asks for a record that does not exist, in any world.
PLACEHOLDER_IDS = {"001401", "1", "example", "None", ""}
# Tenant-scoping segments the simulated apps ignore: one world is one tenant, so
# any value routes identically and refusing them would check nothing.
TENANT_IDS = {"companyid", "company_id", "companydomain", "accountid", "account_id",
              "realmid", "realm_id", "tenantid", "tenant_id", "subdomain", "siteid"}


@dataclass
class Row:
    service: str
    action_id: str
    method: str
    verdict: str
    detail: str = ""
    thin: bool = False
    url: str = ""

    @property
    def is_read(self) -> bool:
        return self.method in READ_METHODS


@dataclass
class Report:
    rows: list[Row] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)   # service -> why

    def totals(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.rows:
            out[r.verdict] = out.get(r.verdict, 0) + 1
        return dict(sorted(out.items()))

    def failed_services(self, reads_only: bool = False) -> list[str]:
        """Services with a real mismatch, worst first by count."""
        bad: dict[str, int] = {}
        for r in self.rows:
            if r.verdict in BENIGN or (reads_only and not r.is_read):
                continue
            bad[r.service] = bad.get(r.service, 0) + 1
        return [s for s, _ in sorted(bad.items(), key=lambda kv: (-kv[1], kv[0]))]

    def print_table(self, stdout) -> None:
        for service in sorted({r.service for r in self.rows}):
            rows = [r for r in self.rows if r.service == service]
            bad = [r for r in rows if r.verdict != "ok"]
            print(f"\n{service}  ({len(rows) - len(bad)}/{len(rows)} ok)", file=stdout)
            for r in rows:
                mark = "ok " if r.verdict == "ok" else "!! "
                thin = "  [extract_thin]" if r.thin else ""
                key = r.action_id.split(":", 1)[-1]
                print(f"  {mark}{key:<38} {r.verdict:<17} {r.detail[:90]}{thin}", file=stdout)
        print("\ntotals: " + ", ".join(f"{k}={v}" for k, v in self.totals().items()),
              file=stdout)
        for service, why in sorted(self.skipped.items()):
            print(f"skipped {service}: {why}", file=stdout)

    def write_json(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"totals": self.totals(), "skipped": self.skipped,
             "rows": [asdict(r) for r in self.rows]}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")


# -- the extract path grammar: `$`, `$.a.b`, `$.a[0].b`; no wildcards ---------

def resolve(path: str, body: Any) -> Any:
    """The engine's extract grammar (packages/executor/src/engine/extract.ts)."""
    if not path.startswith("$"):
        return None
    cur = body
    for m in _STEP.finditer(path[1:]):
        key, index = m.group(1), m.group(2)
        if key is not None:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
        else:
            if not isinstance(cur, list) or int(index) >= len(cur):
                return None
            cur = cur[int(index)]
    return cur


def present(path: str, body: Any) -> bool:
    """Does every step of `path` exist in `body`, whatever its value?

    `{"summary": null}` HAS a summary key: the handler wrote it, the record just
    carries no value for it. `resolve` cannot tell that from an absent key, and
    treating the two alike blamed the seed for an optional the fixture left
    blank.
    """
    if not path.startswith("$"):
        return False
    cur = body
    for m in _STEP.finditer(path[1:]):
        key, index = m.group(1), m.group(2)
        if key is not None:
            if not isinstance(cur, dict) or key not in cur:
                return False
            cur = cur[key]
        else:
            if not isinstance(cur, list) or int(index) >= len(cur):
                return False
            cur = cur[int(index)]
    return True


def _empty(value: Any) -> bool:
    """Did the extract path resolve to nothing at all?

    A PRESENT but empty collection is not nothing: `{"Accounts": []}` is the
    right answer from a world that seeds no accounts, the engine binds a real
    array, and the step that iterates it simply runs zero times. Counting `[]`
    and `{}` as empty blamed the catalogue for the fixture -- 29 of the read
    findings of 4 Sep 2026 were Xero, Zendesk and LinkedIn collections the
    corpus never seeded, every one of them a correct seed.
    """
    return value is None or value == ""


# -- the small stdlib schema validator ---------------------------------------

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool,
          "integer": int, "number": (int, float), "null": type(None)}


def schema_diffs(schema: dict, value: Any, path: str = "$", limit: int = 3) -> list[str]:
    """Type, required keys, nested objects and array item shapes. Not a full
    JSON Schema: enough to catch "declared object, got array of arrays" and
    "declared required key, absent", which is what a false seed looks like."""
    out: list[str] = []

    def walk(sch: Any, val: Any, at: str) -> None:
        if len(out) >= limit or not isinstance(sch, dict):
            return
        want = sch.get("type")
        # A record that simply leaves an optional field empty is not a false
        # seed: `null` here says this row has no job title, not that the
        # declared contract is wrong.
        if val is None and want != "null":
            return
        if want and want in _TYPES:
            # bool is an int in Python; the engine's JSON types are not.
            ok = isinstance(val, _TYPES[want]) and not (
                want in ("integer", "number") and isinstance(val, bool))
            if not ok:
                out.append(f"{at}: expected {want}, got {_kind(val)}")
                return
        if isinstance(val, dict):
            for key in sch.get("required") or []:
                if key not in val:
                    out.append(f"{at}.{key}: expected required key, got absent")
                    if len(out) >= limit:
                        return
            for key, sub in (sch.get("properties") or {}).items():
                if key in val:
                    walk(sub, val[key], f"{at}.{key}")
        elif isinstance(val, list) and isinstance(sch.get("items"), dict):
            for i, item in enumerate(val[:3]):     # a bad row shows in the first few
                walk(sch["items"], item, f"{at}[{i}]")

    walk(schema, value, path)
    return out


def is_error_body(body: Any) -> bool:
    """Did the app refuse this request, in any of the shapes it uses?

    Only `{"error": {"code": ...}}` was recognised, so three other spellings were
    schema-checked as successes and the seed was blamed for a record the app
    never returned: Zendesk answers `{"error": "RecordNotFound", ...}`, LinkedIn
    `{"success": false, "error": ...}` and Twitter `{"errors": [...]}`.

    `success: false` alone is enough; `success: true` beside an `error` key is
    not an error at all (a field legitimately NAMED "error" would be typed).
    """
    if not isinstance(body, dict):
        return False
    if body.get("success") is False:
        return True
    if isinstance(body.get("errors"), list) and body["errors"]:
        return True
    err = body.get("error")
    if isinstance(err, str) and err:
        return True
    if isinstance(err, dict) and err:
        return True
    # Zoom refuses with a bare `{"code": 404, "message": ...}` and no `error`
    # key at all. A failing HTTP status beside a message is a refusal; a `code`
    # that is not an integer status (a coupon code) is an ordinary field.
    code = body.get("code")
    if isinstance(code, int) and not isinstance(code, bool) and code >= 300 \
            and "message" in body:
        return True
    return False


def _kind(v: Any) -> str:
    if isinstance(v, bool):
        return "boolean"
    for name, t in (("object", dict), ("array", list), ("string", str),
                    ("integer", int), ("number", float), ("null", type(None))):
        if isinstance(v, t):
            return name
    return type(v).__name__


# -- one world per service ---------------------------------------------------

def richest_tasks(corpus_dirs, services: set[str]) -> dict[str, Path]:
    """The task whose `initial_state[service]` is the largest JSON, per service:
    the richest fixture is the one most likely to hold a record every action can
    name."""
    best: dict[str, tuple[int, Path]] = {}
    for d in corpus_dirs:
        for p in sorted(Path(d).rglob("*.json")):
            try:
                state = json.loads(p.read_text(encoding="utf-8"))["info"]["initial_state"]
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                continue
            for service, blob in state.items():
                if service == "meta" or service not in services:
                    continue
                size = len(json.dumps(blob, default=str))
                if service not in best or size > best[service][0]:
                    best[service] = (size, p)
    return {s: p for s, (_, p) in best.items()}


def _entity_ids(state: Any, entity_type: str) -> list[str]:
    """Ids of records that look like `entity_type` anywhere in the world state.

    AB fixtures key collections by a plural noun (`spreadsheets`, `contacts`),
    so match the key on the singular/plural of the entity type and take the
    `id` of each record under it.
    """
    # `company` lives under `companies`: an -ies plural was unreachable when the
    # only candidates were the word itself plus an "s".
    wanted = {entity_type, entity_type + "s", entity_type.rstrip("s"),
              entity_type + "es"}
    if entity_type.endswith("y"):
        wanted.add(entity_type[:-1] + "ies")
    found: list[str] = []

    def walk(node: Any, key: str | None) -> None:
        if isinstance(node, dict):
            if key in wanted and "id" in node and isinstance(node["id"], (str, int)):
                found.append(str(node["id"]))
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for item in node:
                if key in wanted and isinstance(item, dict) and \
                        isinstance(item.get("id"), (str, int)):
                    found.append(str(item["id"]))
                walk(item, key)

    walk(state, None)
    # A record is reached both as a list item and by the recursive descent, so
    # the same id lands twice; order is kept because the first one wins.
    return list(dict.fromkeys(found))


def _any_id(state: Any) -> str | None:
    """Fallback: the first `id` in the world, so a path token is at least real."""
    if isinstance(state, dict):
        v = state.get("id")
        if isinstance(v, (str, int)):
            return str(v)
        for sub in state.values():
            got = _any_id(sub)
            if got:
                return got
    elif isinstance(state, list):
        for item in state:
            got = _any_id(item)
            if got:
                return got
    return None


def _named_values(state: Any) -> dict[str, Any]:
    """Names a parameter may legitimately take from this world.

    Three sources: the names of the record collections (`accounts` -> a
    Salesforce `sobject` parameter), the human names on the records, and the
    titles of nested collections (`sheet_title` -> a real worksheet, so a Sheets
    `range` is a range that exists). Without these, a path parameter gets a
    literal and the app rejects a request this check invented.
    """
    out: dict[str, Any] = {}
    collections: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    collections.append(key)
                if key in ("title", "name") and isinstance(value, str) and value:
                    out.setdefault("title", value)
                    out.setdefault("name", value)
                # A range names a worksheet, not the workbook, so remember the
                # titles of the nested collections separately.
                if key in ("worksheets", "sheets", "tabs") and isinstance(value, list):
                    for row in value:
                        if isinstance(row, dict) and isinstance(row.get("title"), str):
                            out.setdefault("sheet_title", row["title"])
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(state)
    if collections:
        # Salesforce-style "which object?" parameters take a real collection.
        # `type` is deliberately NOT here: it means "meeting type" to Zoom and
        # "record type" to Salesforce, and guessing turns a good route into a
        # 404 this check would then blame on the seed.
        for key in ("sobject", "sobjectType", "objectType"):
            out.setdefault(key, collections[0].rstrip("s").capitalize())
    return out


def _record_fields(state: Any) -> dict[str, Any]:
    """Field names seen on records in the world, for filling a body template."""
    out: dict[str, Any] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if not isinstance(v, (dict, list)) and k not in out and v not in (None, ""):
                    out[k] = v
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(state)
    return out


def _literal(param: dict) -> Any:
    """A plausible value of the parameter's declared type, last resort."""
    enum = (param.get("constraints") or {}).get("enum_options") or []
    if enum:
        return enum[0].get("value")
    return {"integer": 1, "number": 1, "boolean": True,
            "array": [], "object": {}}.get(param.get("type"), "test")


class _Filler:
    """Values for a step's `{{tokens}}`, from the seed and the world's state.

    The rule that keeps the report believable: a *path* token may only be filled
    from real world data or from an enum. Inventing one (`range=test`) produces a
    request the app rightly rejects, which would read as a false seed when it is
    only this check's ignorance -- so an unfillable path token makes the action
    `not_executable` instead.
    """

    def __init__(self, params: list[dict], state: Any):
        self.by_name = {p.get("name"): p for p in params if p.get("name")}
        self.state = state
        self.fields = _record_fields(state)
        self.names = _named_values(state)

    def _entity_id(self, name: str, param: dict) -> Any:
        """An id of the RIGHT entity from this world, or None.

        Falling through to a generic `id` field hands a draft route a message id
        and earns a 404 that would read as a false seed. The parameter's own name
        is a second legitimate clue ("employeeId" -> the employees collection).
        """
        for hint in (str(param.get("entity_type") or ""),
                     re.sub(r"(_?id|Id)$", "", name)):
            ids = _entity_ids(self.state, hint) if hint else []
            if ids:
                return ids[0]
        return None

    def _from_world(self, name: str, param: dict) -> Any:
        """A value this world really carries for `name`, or None."""
        if name.lower() in TENANT_IDS and not self._entity_id(name, param):
            # ...unless the world really holds the record it names. LinkedIn's
            # `company_id` addresses a COMPANY; the same spelling scopes the whole
            # baseUrl for Recruitee. A real id is always the better answer.
            return "001401"                  # ignored by the router; any value routes
        if param.get("classification") == "entity_reference":
            return self._entity_id(name, param)
        # A parameter named like a collection in the world (`sobject`, `type`)
        # takes that collection's name; one named like a record field takes the
        # field's value (`title`, `range` -> a real worksheet title).
        for source in (self.names, self.fields):
            if name in source:
                return source[name]
        low = name.lower()
        for source in (self.names, self.fields):
            for key, value in source.items():
                if key.lower() == low:
                    return value
        # A range names a sheet ("Parking Spots!A1:Z100"): the title of a real
        # worksheet is the only value that reads anything back. Without this the
        # Sheets values read -- the action this whole check exists for -- can
        # never run.
        sheet = self.names.get("sheet_title")
        if low in ("range", "ranges") and sheet:
            return f"{sheet}!A1:Z100"
        return None

    def value(self, name: str, *, path: bool = False) -> tuple[Any, bool]:
        """(value, from_the_world). `(None, False)`: nothing can fill it."""
        param = self.by_name.get(name) or {}
        got = self._from_world(name, param)
        if got is not None:
            return got, True
        enum = (param.get("constraints") or {}).get("enum_options") or []
        if enum:
            return enum[0].get("value"), False
        if not param:
            return (None, False)
        # An entity reference this world cannot satisfy, whose example is one of
        # the generator's stock placeholders, is unanswerable: sending it earns
        # a "not found" that says nothing about the seed. A hand-written example
        # ("msg_4202") is still a legitimate source.
        if path and param.get("classification") == "entity_reference"                 and str(param.get("example_value")) in PLACEHOLDER_IDS:
            return (None, False)
        # A real example the seed author wrote is a legitimate source. The
        # generator's filler word "example" is not: sending it into a path
        # produces a request the app rightly rejects, which would read as a
        # false seed when it is only this check's ignorance.
        example = param.get("example_value")
        if example not in (None, "", "example"):
            return example, False
        if path:
            return (None, False)
        return _literal(param), False


def _render_url(url_template: str, filler: _Filler) -> tuple[str, list[str]]:
    """The engine's render: path tokens raw and required, query pairs dropped
    when the token is unfilled (render.ts)."""
    head, _, query = url_template.partition("?")
    missing: list[str] = []

    def path_token(m):
        value, _ = filler.value(m.group(1), path=True)
        if value is None:
            missing.append(m.group(1))
            return m.group(0)
        return str(value)

    path = TOKEN.sub(path_token, head)
    pairs = []
    for pair in query.split("&") if query else []:
        name, _, token = pair.partition("=")
        tok = TOKEN.fullmatch(token)
        if not tok:
            pairs.append(pair)
            continue
        param = filler.by_name.get(tok.group(1)) or {}
        # A REQUIRED query parameter is part of the address, exactly like a path
        # one: filling it with a literal asks for a channel named "test" and
        # earns a 404 that says nothing about the seed.
        required = bool(param.get("required"))
        value, from_world = filler.value(tok.group(1), path=required)
        if value is None:
            if required:
                missing.append(tok.group(1))
            continue
        # Only send an optional pair the world backs: a made-up filter would
        # narrow a list to nothing and read as an empty extract.
        if not required and not from_world:
            continue
        pairs.append(f"{name}={value}")
    return (path + ("?" + "&".join(pairs) if pairs else "")), missing


def _render_body(body_template: Any, filler: _Filler) -> Any:
    if body_template is None:
        return None
    if isinstance(body_template, dict):
        out = {}
        for key, sub in body_template.items():
            rendered = _render_body(sub, filler)
            if rendered is not None:
                out[key] = rendered
        return out
    if isinstance(body_template, list):
        return [_render_body(v, filler) for v in body_template]
    if isinstance(body_template, str):
        tok = TOKEN.fullmatch(body_template)
        if tok:
            value, _ = filler.value(tok.group(1))
            return value                       # None prunes the key, as the engine does
        return TOKEN.sub(lambda m: str(filler.value(m.group(1))[0] or ""), body_template)
    return body_template


def front_door_to_world(url: str, schemas: dict) -> tuple[str, str] | None:
    """`https://<host>/<service>/<rest>` -> the service's baseUrl + rest, the
    same mapping wb_arms/http_shim.py::_rest does. None: unknown service."""
    from urllib.parse import urlsplit
    sp = urlsplit(url)
    parts = sp.path.lstrip("/").split("/", 1)
    service = parts[0]
    if service not in schemas:
        return None
    from wb_world.openapi import world_url
    rest = parts[1] if len(parts) > 1 else ""
    return service, world_url(service, rest, schemas) + (f"?{sp.query}" if sp.query else "")


def _required_in_schema(schema: Any, path: str | None) -> bool:
    """Does `schema` mark the field this extract path names as required?"""
    if not isinstance(schema, dict) or not isinstance(path, str):
        return False
    node = schema
    for m in _STEP.finditer(path[1:]):
        key = m.group(1)
        if key is None:                      # an index step: descend into items
            node = node.get("items") if isinstance(node, dict) else None
            continue
        if not isinstance(node, dict):
            return False
        if key not in (node.get("required") or []):
            return False
        node = (node.get("properties") or {}).get(key)
    return True


def _changed(before: dict, after: dict) -> bool:
    return json.dumps(before, sort_keys=True, default=str) != \
           json.dumps(after, sort_keys=True, default=str)


def check(seeds_dir, corpus_dirs, services: list[str] | None = None) -> Report:
    """Execute every action in `seeds_dir` against a world built from the corpus."""
    seeds_dir = Path(seeds_dir)
    schemas = load_schemas()
    actions = _load_actions(seeds_dir, schemas, services)
    report = Report()
    wanted = {svc for svc, _ in actions}
    tasks = richest_tasks(corpus_dirs, wanted)
    for service in sorted(wanted - set(tasks)):
        report.skipped[service] = "no corpus task carries this service's initial state"
    task_cache: dict[str, dict] = {}
    for service, doc in actions:
        if service not in tasks:
            continue
        task = task_cache.setdefault(service, load_task_file(tasks[service]))
        report.rows.append(_check_action(service, doc, task, schemas))
    return report


def _load_actions(seeds_dir: Path, schemas: dict,
                  services: list[str] | None) -> list[tuple[str, dict]]:
    """(service, action document) for every seed file, in a stable order."""
    keep = set(services) if services else None
    out: list[tuple[str, dict]] = []
    for folder in sorted(p for p in seeds_dir.iterdir() if p.is_dir()):
        for path in sorted(folder.glob("*.json")):
            if path.name == "_meta.json":
                continue
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                url = doc["implementations"][0]["http_template"]["steps"][0]["url_template"]
            except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue
            mapped = front_door_to_world(url, schemas)
            if mapped is None or (keep and mapped[0] not in keep):
                continue
            out.append((mapped[0], doc))
    return out


def _check_action(service: str, doc: dict, task: dict, schemas: dict) -> Row:
    action_id = str((doc.get("business_action") or {}).get("id") or "?")
    impl = doc["implementations"][0]
    step = impl["http_template"]["steps"][0]
    method = str(step.get("method", "GET")).upper()
    row = Row(service=service, action_id=action_id, method=method, verdict="ok")

    # A fresh world per action, so one write never poisons the next.
    ep = Episode(task, episode_id=f"conform-{action_id}")
    state = task["info"]["initial_state"].get(service, {})
    filler = _Filler(impl.get("parameters") or [], state)

    front_url, missing = _render_url(step["url_template"], filler)
    if missing:
        row.verdict, row.detail = "not_executable", \
            f"no value for path parameter(s) {', '.join(sorted(set(missing)))}"
        return row
    mapped = front_door_to_world(front_url, schemas)
    if mapped is None:
        row.verdict, row.detail = "not_executable", "url_template names no known service"
        return row
    # A `{var}` left in the service's own baseUrl (BambooHR's {companyDomain},
    # Recruitee's {company_id}) never reaches a router: the request would be
    # rejected for a reason that has nothing to do with this seed.
    leftover = re.findall(r"\{(\w+)\}", mapped[1])
    if leftover:
        row.verdict, row.detail = "not_executable",             f"the service baseUrl leaves {{{leftover[0]}}} unsubstituted"
        return row
    row.url = mapped[1]
    body = _render_body(step.get("body_template"), filler)

    # AutomationBench's `api_fetch` does NOT parse a URL's query string: the
    # front door (`wb_arms/http_shim.py::_rest`) splits it off and passes it as
    # `params`. Inlining it made the Sheets read ask for a spreadsheet named
    # `ss_parking?ranges=...`, a "not found" that read as a broken seed.
    from urllib.parse import parse_qs, urlsplit
    split = urlsplit(row.url)
    params = {k: v[-1] for k, v in parse_qs(split.query, keep_blank_values=True).items()}
    try:
        raw = ep.api_fetch(method, split._replace(query="").geturl(),
                           params=json.dumps(params) if params else None,
                           body=json.dumps(body) if body not in (None, {}) else None)
    except Exception as e:                       # AB routers raise on malformed input
        # A router that blew up on a body this check invented says nothing about
        # the seed; only a read, whose request carries no invented body, does.
        row.verdict = "request_rejected" if method in READ_METHODS else "not_executable"
        row.detail = f"{type(e).__name__}: {e}"[:200]
        return row
    try:
        response = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        row.verdict, row.detail = "schema_mismatch", "response is not JSON"
        return row

    err = response.get("error") if isinstance(response, dict) else None
    if isinstance(err, dict) and str(err.get("message") or "").startswith("No handler for"):
        # The simulated app declares the route in its OpenAPI document but its
        # router does not serve it (Xero's and QuickBooks' Reports). A true
        # finding -- the catalogue offers an action that cannot run -- but not a
        # false schema, so it is reported and never gates an import.
        row.verdict, row.detail = "no_handler", str(err.get("message"))[:200]
        return row
    if isinstance(err, dict) and err.get("code", 200) >= 300:
        # An error body is not the success contract, so it is never schema-checked:
        # the request was wrong (usually this check's fault), not the schema.
        row.verdict = "request_rejected"
        row.detail = f"{err.get('code')}: {err.get('message') or ''}"[:200]
        return row
    if is_error_body(response):
        # The same rule for the shapes that carry no code: a refusal is a refusal
        # whether the app spells it `{"error": "RecordNotFound"}`, `{"success":
        # false}` or `{"errors": [...]}`. Schema-checking these blamed the seed
        # for a record the request never asked for successfully.
        row.verdict = "request_rejected"
        row.detail = json.dumps(response)[:200]
        return row

    extracts = (step.get("response_template") or {}).get("extract") or {}
    row.thin = method in READ_METHODS and bool(extracts) and all(
        name.lower() in ("id", "ids") or name.lower().endswith("id")
        for name in extracts)

    schema = (step.get("response_template") or {}).get("schema")
    if isinstance(schema, dict):
        diffs = schema_diffs(schema, response)
        if diffs:
            row.verdict, row.detail = "schema_mismatch", "; ".join(diffs)
            return row

    # An optional field that this particular record leaves blank (a mail with no
    # cc) is not a false seed. Only a *required* empty extract, or an action
    # whose every extract is empty, says the declared outputs are not real.
    # A key the response CARRIES, even holding null, is not an empty extract:
    # the engine binds it and the value is the record's own "none here".
    empty = [name for name, path in extracts.items()
             if not isinstance(path, str)
             or (_empty(resolve(path, response)) and not present(path, response))]
    if empty:
        required = {name for name in empty
                    if _required_in_schema(schema, extracts.get(name))}
        if required or len(empty) == len(extracts):
            which = sorted(required) or sorted(empty)
            row.verdict, row.detail = "extract_empty",                 f"{', '.join(which)} resolve to nothing"
            return row

    if method not in READ_METHODS and not _changed(ep.snapshot0, ep.finish()):
        row.verdict, row.detail = "write_not_landed", "the world is unchanged after the write"
    return row
