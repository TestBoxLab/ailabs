"""The lab seeds: the stock seeds with descriptions from a reviewed knowledge catalog.

Unblock plan (8 Sep 2026) M6, T6.3 groundwork. Lucas's experimental knowledge
("PG-Waki", `research/architectures/pg-waki/v1/provenance.md`) is a catalog of
reviewed action semantics: for each AutomationBench Zapier tool, its purpose,
what it does not do, whether repeating it is safe, where the records sit in
its response and what its arguments mean; plus one paragraph per product on
how its records relate. Monarch learns products from seed folders only
(`POST /v1/seeds/<slug>/import` replays a fixture folder), so the knowledge
enters the lab instance as a second seed set, generated here.

The lab set is the stock set (`wb_world.seeds.generate`) with ONE difference:
`business_action.description` of every matched action carries the catalog's
text, and the first action of every product opens with the product's
paragraph, prefixed "Product:". Nothing the importer keys on or the executor
runs -- ids, verbs, labels, url templates, parameters, extracts, schemas,
`_meta.json` -- moves by a byte, so the two sets validate alike and run alike.
The SPEC (`local-docs/benchmark/seed-format/SPEC.md` §2) stores `description`
and does not serve it to the builder today; making the builder read it is a
Monarch-side change, and `_meta.json` has exactly five keys, none for prose.

Matching is an explicit table, never a guess: `config/products/<product>.
knowledge-map.yaml` maps a catalog id (`zapier:<app>_<tool>`) to a bench action
id (`bench-<app>:<verb>:<object>`). Entries without a row, actions without an
entry, and rows the catalog does not carry are listed in
`<out>/KNOWLEDGE-MAPPING.yaml` with the catalog's sha256 and the counts. Two
things from the catalog are kept only where the seed can honour them: a record
location only when the seed's own response schema reaches that path, an
argument's meaning only when the seed has a parameter of that name (the
Zapier tools and the REST routes spell most arguments differently).

Deterministic: the same catalog, table and stock set give the same bytes.
`ok.txt` gains `knowledge_sha256` and `knowledge_source` next to the seed
version, and its digest is recomputed, so the lab instance's knowledge-base
hash file can record which knowledge it was taught.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from wb_world import seeds

_ACTION_ID = re.compile(r"bench-[a-z0-9-]+:(create|read|list|update|delete):[a-z0-9-]+")
_ORIGIN_APP = re.compile(r"[^:]+$")
HEADING = "Reviewed knowledge (PG-Waki)"
READ_ONLY = "Read-only: nothing changes, so it is safe to repeat."
RULE = ("An explicit table, one row per catalog entry, names the bench action that performs "
        "the entry's operation over the simulated app (same product, same resource, same "
        "kind of effect); several entries may name one action when they are aliases or "
        "special cases of its route. An entry without a row is catalog-only and an action "
        "without an entry is bench-only; neither is guessed. A record location is carried "
        "only when the seed's response schema reaches it; an argument's meaning only when "
        "the seed has a parameter of that name.")


class KnowledgeError(Exception):
    """A catalog, a table or a seed set this module cannot use; the message says why."""


@dataclass
class Catalog:
    source: str                       # file name only: the path may carry a user name
    sha256: str
    generator: str
    entries: dict[str, dict[str, Any]]   # catalog id -> contract
    contexts: dict[str, str]             # product slug -> the product's paragraph


@dataclass
class KnowledgeMap:
    source: str
    sha256: str
    rows: dict[str, str]              # catalog id -> bench action id
    notes: dict[str, str] = field(default_factory=dict)


@dataclass
class Report:
    counts: dict[str, int]
    matched: list[dict[str, str]]
    catalog_only: list[str]
    bench_only: list[str]
    report_path: Path
    knowledge_source: str
    knowledge_sha256: str


# ------------------------------------------------------------------- inputs

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def product_slug_for(origin: str) -> str:
    """`automationbench:zapier:google_sheets` -> `bench-google-sheets`."""
    m = _ORIGIN_APP.search(origin or "")
    return seeds.product_slug(m.group(0)) if m else ""


def load_catalog(path) -> Catalog:
    """Read a PG-Waki catalog; refuse anything that is not one, saying which key is off."""
    path = Path(path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise KnowledgeError(f"cannot read the knowledge catalog {path}: {e}") from e
    if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
        raise KnowledgeError(f"{path.name}: a knowledge catalog has an `entries` list")
    entries: dict[str, dict[str, Any]] = {}
    for i, entry in enumerate(doc["entries"]):
        cid = (entry or {}).get("source_action_id") if isinstance(entry, dict) else None
        contract = (entry or {}).get("contract") if isinstance(entry, dict) else None
        if not isinstance(cid, str) or not cid or not isinstance(contract, dict):
            raise KnowledgeError(f"{path.name}: entries[{i}] needs a `source_action_id` "
                                 f"string and a `contract` object")
        if cid in entries:
            raise KnowledgeError(f"{path.name}: `source_action_id` {cid} appears twice")
        entries[cid] = contract
    if not isinstance(doc.get("product_contexts"), list):
        raise KnowledgeError(f"{path.name}: a knowledge catalog has a `product_contexts` list")
    contexts: dict[str, str] = {}
    for i, ctx in enumerate(doc["product_contexts"]):
        if not isinstance(ctx, dict) or not isinstance(ctx.get("summary"), str):
            raise KnowledgeError(f"{path.name}: product_contexts[{i}] needs a `summary` string")
        slug = product_slug_for(str(ctx.get("product_origin") or ""))
        if not slug:
            raise KnowledgeError(f"{path.name}: product_contexts[{i}] needs a `product_origin`")
        contexts[slug] = " ".join(ctx["summary"].split())
    return Catalog(source=path.name, sha256=_sha256(path),
                   generator=str(doc.get("generator_version") or ""),
                   entries=entries, contexts=contexts)


def load_map(path) -> KnowledgeMap:
    """Read the explicit table; every right-hand side must be a well-formed action id."""
    path = Path(path)
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise KnowledgeError(f"cannot read the knowledge map {path}: {e}") from e
    rows = (doc or {}).get("rows") if isinstance(doc, dict) else None
    if not isinstance(rows, dict) or not rows:
        raise KnowledgeError(f"{path.name}: a knowledge map has a non-empty `rows` mapping")
    for cid, bid in rows.items():
        if not isinstance(cid, str) or not isinstance(bid, str) or not _ACTION_ID.fullmatch(bid):
            raise KnowledgeError(f"{path.name}: row {cid!r}: {bid!r} is not a bench action id "
                                 f"(bench-<app>:<verb>:<object>)")
    notes = (doc or {}).get("notes") or {}
    if not isinstance(notes, dict):
        raise KnowledgeError(f"{path.name}: `notes` must be a mapping of catalog id to text")
    return KnowledgeMap(source=path.name, sha256=_sha256(path), rows=dict(rows),
                        notes={str(k): str(v) for k, v in notes.items()})


def map_path_for(product_path) -> Path:
    """`config/products/<name>.yaml` -> `config/products/<name>.knowledge-map.yaml`."""
    p = Path(product_path)
    return p.with_name(f"{p.stem}.knowledge-map.yaml")


# ---------------------------------------------------------------- the text

def _pointer_to_path(pointer: str) -> str:
    """JSON pointer `/a/b/0` -> the executor's `$.a.b[0]`; '' for a malformed one."""
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        return ""
    out = "$"
    for seg in pointer[1:].split("/"):
        if not seg:
            return ""
        out += f"[{seg}]" if seg.isdigit() else f".{seg}"
    return out


def _step(action: dict[str, Any]) -> dict[str, Any]:
    return action["implementations"][0]["http_template"]["steps"][0]


def _reachable(action: dict[str, Any], pointer: str) -> str:
    """The `$` path for `pointer` when the seed's response schema carries it, else ''."""
    path = _pointer_to_path(pointer)
    schema = _step(action).get("response_template", {}).get("schema")
    return path if path and seeds._schema_at(schema, path) is not None else ""


def _sentence(text: str) -> str:
    text = " ".join(str(text).split())
    return text if not text or text[-1] in ".!?" else text + "."


def _use(contract: dict[str, Any], action: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    """The lines one catalog entry adds to an action, and what the report says was carried."""
    lines: list[str] = []
    carried: dict[str, str] = {}
    behavior = contract.get("behavior") or {}
    purpose = (behavior.get("purpose") or {}).get("text") if isinstance(behavior.get("purpose"), dict) \
        else behavior.get("purpose")
    if purpose:
        lines.append(f"Purpose: {_sentence(purpose)}")
    does_not = [d.get("text") if isinstance(d, dict) else d for d in behavior.get("does_not") or []]
    does_not = [_sentence(d) for d in does_not if d]
    if does_not:
        lines.append("Does not: " + " ".join(does_not))
    mutation = contract.get("mutation") or {}
    if mutation.get("idempotency"):
        lines.append(f"Idempotency: {_sentence(mutation['idempotency'])}")
    elif mutation.get("semantics") == "none":
        lines.append(f"Idempotency: {READ_ONLY}")
    response = contract.get("response") or {}
    records: list[str] = []
    collection = _reachable(action, response.get("collection_path") or "")
    if collection:
        lines.append(f"Records in the response: the array at {collection}.")
        records.append(collection)
    record_id = _reachable(action, response.get("record_id_path") or "")
    if record_id:
        lines.append(f"Record id in the response: {record_id}.")
        records.append(record_id)
    produced = [p for p in (_reachable(action, f) for f in response.get("produced_fields") or [])
                if p and p not in records]
    if produced:
        lines.append("Produced fields: " + ", ".join(produced) + ".")
        records.extend(produced)
    if records:
        carried["records"] = ", ".join(records)
    params = {p["name"] for p in action["implementations"][0].get("parameters") or []}
    fields = [f for f in contract.get("request_fields") or [] if isinstance(f, dict) and f.get("name")]
    shared = [f for f in fields if f.get("description") and f["name"] in params]
    if shared:
        lines.append("Arguments: " + " ".join(f"{f['name']}: {_sentence(f['description'])}" for f in shared))
    carried["arguments"] = f"{len(shared)} of {len(fields)}"     # carried, of the tool's arguments
    return lines, carried


def describe(stock: str, uses: list[list[str]], product_context: str = "") -> str:
    """The lab description: product paragraph, the stock text, then the knowledge."""
    parts: list[str] = []
    if product_context:
        parts.append(f"Product: {_sentence(product_context)}")
    if stock.strip():
        parts.append(stock.strip())
    if len(uses) == 1:
        parts.append(f"{HEADING}:\n" + "\n".join(uses[0]))
    elif uses:
        body = "\n".join(f"Use {i}: " + "\n".join(lines) for i, lines in enumerate(uses, 1))
        parts.append(f"{HEADING}, {len(uses)} uses of this action.\n{body}")
    return "\n\n".join(parts)


# ------------------------------------------------------------------ the set

def _product_folders(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / "_meta.json").is_file())


def enrich(seed_dir, catalog: Catalog, kmap: KnowledgeMap) -> Report:
    """Rewrite the descriptions of a stock set in place and write the mapping report.

    Refuses a set that already carries knowledge (its manifest says so), a table
    row naming an action the set does not hold, and a folder with no manifest.
    """
    root = Path(seed_dir)
    manifest_path = root / "ok.txt"
    if not manifest_path.is_file():
        raise KnowledgeError(f"{root} has no ok.txt: generate the stock seeds first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("knowledge_sha256"):
        raise KnowledgeError(f"{root} already carries knowledge "
                             f"({manifest['knowledge_sha256'][:12]}); regenerate the stock set first")

    # every action of the set, by id, with the file that holds it; and per
    # product the first action (by file name), which carries the product paragraph
    actions: dict[str, tuple[Path, dict[str, Any]]] = {}
    first_id: dict[str, str] = {}
    for folder in _product_folders(root):
        for f in sorted(folder.glob("*.json")):
            if f.name == "_meta.json":
                continue
            doc = json.loads(f.read_text(encoding="utf-8"))
            actions[doc["business_action"]["id"]] = (f, doc)
            first_id.setdefault(folder.name, doc["business_action"]["id"])

    dangling = sorted(f"{cid} -> {bid}" for cid, bid in kmap.rows.items()
                      if cid in catalog.entries and bid not in actions)
    if dangling:
        raise KnowledgeError(f"{kmap.source} names {len(dangling)} action(s) this set does not "
                             f"hold; fix the table: " + "; ".join(dangling))

    uses: dict[str, list[tuple[str, list[str], dict[str, str]]]] = {}
    matched: list[dict[str, str]] = []
    for cid in sorted(kmap.rows):
        if cid not in catalog.entries:
            continue
        bid = kmap.rows[cid]
        lines, carried = _use(catalog.entries[cid], actions[bid][1])
        uses.setdefault(bid, []).append((cid, lines, carried))
        row = {"catalog": cid, "bench": bid, **carried}
        if cid in kmap.notes:
            row["note"] = kmap.notes[cid]
        matched.append(row)

    folders = [p.name for p in _product_folders(root)]
    with_context = sorted(slug for slug in folders if slug in catalog.contexts)
    touched = set(uses) | {first_id[slug] for slug in with_context}
    for bid in sorted(touched):
        f, doc = actions[bid]
        slug = f.parent.name
        context = catalog.contexts[slug] if first_id.get(slug) == bid and slug in with_context else ""
        entry_lines = [lines for _, lines, _ in uses.get(bid, [])]
        doc["business_action"]["description"] = describe(
            doc["business_action"].get("description") or "", entry_lines, context)
        f.write_text(seeds._dump(doc), encoding="utf-8")

    catalog_only = sorted(cid for cid in catalog.entries if cid not in kmap.rows)
    bench_only = sorted(bid for bid in actions if bid not in uses)
    rows_without_entry = sorted(cid for cid in kmap.rows if cid not in catalog.entries)
    without_context = sorted(slug for slug in folders if slug not in catalog.contexts)
    counts = {
        "catalog_entries": len(catalog.entries),
        "bench_actions": len(actions),
        "matched_entries": len(matched),
        "matched_actions": len(uses),
        "catalog_only": len(catalog_only),
        "bench_only": len(bench_only),
        "map_rows_without_catalog_entry": len(rows_without_entry),
        "products_with_context": len(with_context),
        "products_without_context": len(without_context),
    }
    report = {
        "knowledge_source": catalog.source,
        "knowledge_sha256": catalog.sha256,
        "knowledge_generator": catalog.generator,
        "knowledge_map": kmap.source,
        "knowledge_map_sha256": kmap.sha256,
        "seeds_version": manifest.get("version", seeds.VERSION),
        "rule": RULE,
        "counts": counts,
        "matched": matched,
        "catalog_only": catalog_only,
        # the table's own words on why an entry has no row, where it has them
        "catalog_only_reasons": {cid: kmap.notes[cid] for cid in catalog_only if cid in kmap.notes},
        "bench_only": bench_only,
        "map_rows_without_catalog_entry": rows_without_entry,
        "products_with_context": with_context,
        "products_without_context": without_context,
    }
    report_path = root / "KNOWLEDGE-MAPPING.yaml"
    # LF on every platform: the report is a document for people and git, not a seed
    report_path.write_text(yaml.safe_dump(report, sort_keys=False, allow_unicode=True, width=10 ** 6),
                           encoding="utf-8", newline="\n")

    manifest.update({
        "generated_from": "wb monarch knowledge",
        "knowledge_source": catalog.source,
        "knowledge_sha256": catalog.sha256,
        "knowledge_map": kmap.source,
        "knowledge_map_sha256": kmap.sha256,
        "sha256": seeds.folder_sha256(root),
    })
    manifest_path.write_text(seeds._dump(manifest), encoding="utf-8")
    return Report(counts=counts, matched=matched, catalog_only=catalog_only,
                  bench_only=bench_only, report_path=report_path,
                  knowledge_source=catalog.source, knowledge_sha256=catalog.sha256)
