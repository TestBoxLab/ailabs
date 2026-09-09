"""wb corpus declare: derive the dual-invariant contract for imported tasks.

AutomationBench tasks carry assertions only. Two mechanical rules give the
invariant without judgment calls:

  expected_changes  <- one matcher per assertion, from its type:
      *_field_equals / *_has_property / *_field_contains with a record id
          -> op "changed" on <service>.<collection>[id=<id>].<field>
      *_exists / *_sent / *_in_* (a record must appear)
          -> op "added" on <service>.<collection>[*]  (collection from the
             world model; "*" when the service only logs actions)
  allowed_changes   <- the product's side-effect file (config/side-effects.yaml
      for simulated-apps): housekeeping a real platform performs alongside
      the asked-for write (read markers, thread updates, the Salesforce
      is_closed/is_won pair when a stage closes). Kept short; the next run's
      unexpected_changes is the review queue for additions.

Derivation is deterministic, so re-running is idempotent. The contract hash
changes; tasks that already ran under the old contract will not regrade.

The scored domains (6 Sep 2026)
-------------------------------
The six scored AutomationBench domains use 335 assertion types, 203 of them
positive. `_TYPES` below was hand-written for the `simple` domain and covered
none of the rest, so 218 of the 600 scored tasks derived no matcher at all and
every real change a competitor made landed in `unexpected_changes`: in the Hard
round every competitor scored 0% for this reason alone.

Hand-listing 203 types would rot the moment the vendor adds one, so the
mapping is derived instead, from two sources that are already ground truth:

  * the service and collection come from the vendor's own world model
    (`WorldState`'s fields and each service's collections), matched against the
    assertion type's name, which is `<service>_<noun>_<verb>` throughout;
  * whether an assertion demands a change at all comes from the vendor's
    `negative_assertion` marker: a "not sent" / "not exists" assertion is
    satisfied by doing nothing, so it grants nothing.

`_COLLECTION_ALIAS` names the two dozen types whose noun is not its collection
(`gmail_email_*` reads `gmail.messages`, `zoom_action_exists` reads
`zoom.meetings`), each one read off the handler's source in
`vendor/automation-bench`. `_ID_KEYS` names the payload keys that point at a
record that already exists, which is what separates "change this record's
field" from "a new record must appear".
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from wb_orchestrator import config
from wb_orchestrator.config import SideEffects, load_side_effects  # noqa: F401  (re-export)
from wb_orchestrator.orchestrator import contract_hash

# assertion type -> (service, collection or "*", id key or None)
_TYPES: dict[str, tuple[str, str, str | None]] = {
    "airtable_record_exists": ("airtable", "*", None),
    "asana_action_exists": ("asana", "actions", None),
    "trello_action_exists": ("trello", "actions", None),
    "jira_action_exists": ("jira", "*", None),
    "jira_issue_exists_with_summary": ("jira", "*", None),
    "buffer_post_exists": ("buffer", "posts", None),
    "gmail_message_sent": ("gmail", "messages", None),
    "google_calendar_event_exists": ("google_calendar", "events", None),
    "google_sheets_row_exists": ("google_sheets", "rows", None),
    "hubspot_contact_exists": ("hubspot", "contacts", None),
    "hubspot_deal_exists": ("hubspot", "deals", None),
    "hubspot_contact_has_property": ("hubspot", "contacts", None),
    "mailchimp_subscriber_in_list": ("mailchimp", "*", None),
    "salesforce_case_exists": ("salesforce", "cases", None),
    "salesforce_note_exists": ("salesforce", "notes", None),
    "salesforce_task_exists": ("salesforce", "tasks", None),
    "salesforce_record_exists": ("salesforce", "$collection", None),
    "salesforce_contact_exists_with_field": ("salesforce", "contacts", None),
    "salesforce_lead_exists_with_field": ("salesforce", "leads", None),
    "salesforce_contact_field_equals": ("salesforce", "contacts", "contact_id"),
    "salesforce_lead_field_equals": ("salesforce", "leads", "lead_id"),
    "salesforce_lead_field_contains": ("salesforce", "leads", "lead_id"),
    "salesforce_field_equals": ("salesforce", "$collection", "record_id"),
    "slack_direct_message_sent": ("slack", "*", None),
    "slack_message_exists": ("slack", "messages", None),
    "slack_message_in_channel": ("slack", "messages", None),
    "zendesk_ticket_exists": ("zendesk", "tickets", None),
    "zoom_meeting_exists": ("zoom", "meetings", None),
    "zoom_meeting_exists_with_field": ("zoom", "meetings", None),
}

# Assertion field names that differ from the world-model field they check.
_FIELD_ALIAS = {"stage": "stage_name"}

# --- the scored domains: derived mapping -------------------------------------

# Assertion type -> the collection its handler actually reads, for the types
# whose name does not contain it. Each entry was read off the handler source in
# vendor/automation-bench/automationbench/rubric/assertions/.
_COLLECTION_ALIAS: dict[str, tuple[str, str]] = {
    "airtable_record_exists": ("airtable", "actions"),
    "calendly_action_exists": ("calendly", "scheduled_events"),
    "calendly_event_cancelled": ("calendly", "scheduled_events"),
    "calendly_event_count": ("calendly", "scheduled_events"),
    "calendly_event_exists": ("calendly", "scheduled_events"),
    "canva_export_job_created": ("canva", "jobs"),
    "docusign_cc_exists": ("docusign", "envelopes"),
    "facebook_page_photo_count": ("facebook_pages", "photos"),
    "facebook_page_photo_exists": ("facebook_pages", "photos"),
    "facebook_page_post_exists": ("facebook_pages", "posts"),
    "gmail_email_body_contains": ("gmail", "messages"),
    "gmail_email_sent_count": ("gmail", "messages"),
    "gmail_email_sent_to": ("gmail", "messages"),
    "gmail_email_subject_contains": ("gmail", "messages"),
    "google_sheets_cell_equals": ("google_sheets", "rows"),
    "instagram_photo_published": ("instagram", "media"),
    "salesforce_collection_count_equals": ("salesforce", "$collection"),
    "salesforce_field_contains": ("salesforce", "$collection"),
    "salesforce_field_equals": ("salesforce", "$collection"),
    "slack_direct_message_sent": ("slack", "messages"),
    "twilio_sms_sent": ("twilio", "sms_messages"),
    "twilio_sms_sent_to": ("twilio", "sms_messages"),
    "twitter_reply_exists": ("twitter", "tweets"),
    "zoom_action_exists": ("zoom", "meetings"),
}

# Payload keys that name a record that already exists. Their presence turns
# "a record must appear" into "this record's field must change".
_ID_KEYS = ("record_id", "row_id", "ticket_id", "conversation_id", "contact_id",
            "customer_id", "organization_id", "company_id", "invoice_id",
            "message_id", "meeting_id", "campaign_id", "lead_id", "case_id",
            "deal_id", "event_id", "user_id", "id")

# Sentinel: the world model has no such field, so nothing can be said about it.
_MISSING = object()

# Payload keys that name the field being asserted on that record.
_FIELD_KEYS = ("field", "property", "column", "target_column")

# Tag- and note-style assertions name the collection field they append to, so
# the matcher can stay on that one field of that one record.
_SUFFIX_FIELD = {
    "has_tag": "tags", "not_has_tag": "tags",
    "has_note": "notes", "has_comment": "comments", "has_message": "messages",
    "has_reply": "replies", "has_event": "events", "has_member": "members",
    "has_label": "label_ids", "has_property": None, "has_priority": "priority",
    "has_status": "status", "is_read": "is_read", "is_archived": "archived",
}


@lru_cache(maxsize=1)
def _world_collections() -> dict[str, list[str]]:
    """Service -> its collections, straight from the vendor's world model.

    # ponytail: read from WorldState rather than copied here; a second copy
    # would rot the moment the vendor adds a service.
    """
    from automationbench.schema.world import WorldState
    out: dict[str, list[str]] = {}
    for name, f in WorldState.model_fields.items():
        if name == "meta":
            continue
        args = getattr(f.annotation, "__args__", None)
        inner = args[0] if args else f.annotation
        out[name] = list(getattr(inner, "model_fields", {}))
    return out


@lru_cache(maxsize=None)
def _is_negative(assertion_type: str) -> bool:
    """The vendor's own marker: a negative assertion demands no change."""
    import automationbench.rubric.assertions  # noqa: F401  (registers handlers)
    from automationbench.rubric.registry import AssertionRegistry
    return AssertionRegistry.is_negative(assertion_type)


@lru_cache(maxsize=None)
def _split_type(assertion_type: str) -> tuple[str, str, str] | None:
    """(service, collection, rest) for an assertion type, or None if unknown."""
    alias = _COLLECTION_ALIAS.get(assertion_type)
    services = _world_collections()
    if alias:
        service, collection = alias
        rest = assertion_type[len(service) + 1:]
        return service, collection, rest
    # longest service name first, so google_sheets beats nothing and
    # facebook_pages is not read as facebook.
    for service in sorted(services, key=len, reverse=True):
        if assertion_type != service and not assertion_type.startswith(service + "_"):
            continue
        rest = assertion_type[len(service) + 1:]
        for collection in sorted(services[service], key=len, reverse=True):
            singular = collection[:-3] + "y" if collection.endswith("ies") else (
                collection[:-1] if collection.endswith("s") else collection)
            for noun in (collection, singular):
                if rest == noun or rest.startswith(noun + "_"):
                    return service, collection, rest[len(noun):].lstrip("_")
        return service, "*", rest
    return None

def default_side_effects() -> SideEffects:
    """The simulated-apps product's side-effect list."""
    product = config.load_product(config.resolve_name_or_path("simulated-apps", "product"))
    return load_side_effects(config.from_workflowbench(product.side_effects))


def _field_seeded(initial_state: dict[str, Any], service: str, collection: str,
                  rid: Any, field: str) -> bool:
    """True when the seeded record already carries that field."""
    records = (initial_state.get(service) or {}).get(collection)
    if not isinstance(records, list):
        return False
    rec = next((r for r in records
                if isinstance(r, dict) and str(r.get("id")) == str(rid)), None)
    return isinstance(rec, dict) and field in rec


def _object_collection(a: dict[str, Any]) -> str | None:
    """`object_type: "Opportunity"` names the collection `opportunities`.

    Some Salesforce assertions say which object they mean this way rather than
    with a `collection` key; without it the matcher widens to `salesforce.*`,
    which the diff's real paths never produce.
    """
    obj = a.get("object_type")
    if not isinstance(obj, str) or not obj:
        return None
    name = obj.strip().lower()
    return name if name.endswith("s") else (
        name[:-1] + "ies" if name.endswith("y") else name + "s")


def _seeded_record(initial_state: dict[str, Any], service: str, collection: str,
                   rid: Any) -> bool:
    """True when `rid` names a record the initial state already carries."""
    records = (initial_state.get(service) or {}).get(collection)
    return isinstance(records, list) and any(
        isinstance(r, dict) and str(r.get("id")) == str(rid) for r in records)


def _action_log(assertion_type: str, initial_state: dict[str, Any]) -> bool:
    """True when this assertion's service records actions as a keyed log."""
    split = _split_type(assertion_type)
    if split is None:
        return False
    service, collection, rest = split
    if collection != "actions" and not rest.startswith("action_"):
        return False
    return isinstance((initial_state.get(service) or {}).get("actions"), dict)


def _rows_are_nested(assertion_type: str, initial_state: dict[str, Any]) -> bool:
    """True for a sheets assertion whose seed nests rows under spreadsheets."""
    if not assertion_type.startswith("google_sheets_"):
        return False
    gs = initial_state.get("google_sheets") or {}
    return "rows" not in gs and bool(gs.get("spreadsheets"))


def _count_only(rest: str) -> bool:
    """A count assertion is a guard ("create exactly one"), not a demand.

    The count it asserts may well be the count the world already has, so the
    change is granted as allowed and never required.
    """
    return rest.endswith("count") or rest.endswith("count_equals")


def _already_holds(a: dict[str, Any], initial_state: dict[str, Any],
                   service: str, collection: str, rid: Any, field: str | None) -> bool:
    """True when the asserted value is already the value in the initial state.

    `quickbooks_invoice_field_equals(qi_603, voided, "false")` on an invoice
    that starts unvoided asks for that invoice to be *left alone*. Requiring
    such a matcher to match would fail every correct competitor, so it is
    granted as allowed rather than demanded as expected.
    """
    if field is None or rid is None or "value" not in a:
        return False
    records = (initial_state.get(service) or {}).get(collection)
    if not isinstance(records, list):
        return False
    rec = next((r for r in records
                if isinstance(r, dict) and str(r.get("id")) == str(rid)), None)
    if rec is None:
        return False
    if field in rec:
        current = rec[field]
    else:
        # A field the seed leaves out still has the schema's default, and that
        # default is the value the world starts with. `voided` on a QuickBooks
        # invoice is the case that found this: the seed omits it, the schema
        # defaults it to False, and the task asserts "false" to mean "leave it".
        current = _schema_default(service, collection, field)
        if current is _MISSING:
            return False
    return str(current).strip().lower() == str(a["value"]).strip().lower()


def _schema_default(service: str, collection: str, field: str) -> Any:
    """The vendor world model's default for one field, or _MISSING."""
    from automationbench.schema.world import WorldState
    f = WorldState.model_fields.get(service)
    if f is None:
        return _MISSING
    args = getattr(f.annotation, "__args__", None)
    state = args[0] if args else f.annotation
    col = getattr(state, "model_fields", {}).get(collection)
    if col is None:
        return _MISSING
    item_args = getattr(col.annotation, "__args__", None)
    item = item_args[0] if item_args else col.annotation
    spec = getattr(item, "model_fields", {}).get(field)
    if spec is None or spec.is_required():
        return _MISSING
    return spec.get_default(call_default_factory=False)


def _content_of(a: dict[str, Any]) -> dict[str, Any]:
    """The assertion's own content, as `where` keys over a logged action's params.

    Only scalars are pinned: a nested object would make the rule demand an exact
    shape the prompt never asked for.
    """
    where: dict[str, Any] = {}
    for field, value in (a.get("fields") or {}).items():
        if isinstance(value, (str, int, float, bool)):
            where[f"params.fields.{field}"] = value
    for key in ("tableName", "listId", "channel"):
        if isinstance(a.get(key), (str, int, float, bool)):
            where[f"params.{key}"] = a[key]
    # A container alone ("this base", "this workspace") says nothing about which
    # write was asked for, so it never pins a rule on its own.
    if not where:
        return {}
    if isinstance(a.get("applicationId"), (str, int, float, bool)):
        where["params.applicationId"] = a["applicationId"]
    return where


def _derived_matcher(a: dict[str, Any],
                     initial_state: dict[str, Any] | None = None,
                     ) -> tuple[dict[str, Any] | None, bool]:
    """(matcher, is_demanded) for a scored-domain assertion.

    `is_demanded` is False when satisfying the assertion requires no change —
    the matcher is then granted as allowed, never required. A negative
    assertion ("not sent to", "not exists") returns (None, False): it is
    satisfied by doing nothing and so grants nothing.
    """
    initial_state = initial_state or {}
    atype = a["type"]
    if _is_negative(atype):
        return None, False
    split = _split_type(atype)
    if split is None:
        return None, False
    service, collection, rest = split
    if collection == "$collection":
        collection = a.get("collection") or _object_collection(a) or "*"

    # Google Sheets rows are not a flat collection: they live at
    # spreadsheets[id=..].worksheets[id=..].rows[<index>], and the index is
    # positional because a row carries row_id, not id. The matcher therefore
    # names the worksheet the assertion names and leaves the row open.
    if service == "google_sheets" and collection in ("rows", "worksheets"):
        ssid = a.get("spreadsheet_id") or a.get("spreadsheet")
        # The diff addresses a list item by its `id`, falling back to its
        # position when the record has none. These seeds carry the identifier
        # under `spreadsheet_id` about as often as under `id`, so the matcher
        # names the spreadsheet only when the seed really keys it that way.
        if ssid and _seeded_record(initial_state, "google_sheets",
                                   "spreadsheets", ssid):
            path = f"google_sheets.spreadsheets[id={ssid}]*"
        else:
            path = "google_sheets.spreadsheets*"
        return {"service": service, "op": "*", "path": path}, True

    # An action log is a dict keyed by action_key, so the matcher names the one
    # key the assertion asks for rather than the whole log.
    if collection == "actions" or rest.startswith("action_"):
        key = a.get("action_key")
        base = f"{service}.actions"
        # The log key is minted during the run, so the matcher names the write's
        # own content instead, and `count` pins how many were asked for: doing
        # the requested thing 201 times is not doing the requested thing.
        m = {"service": service, "op": "*",
             "path": f"{base}.{key}*" if key else f"{base}*"}
        where = _content_of(a)
        if where:
            m["where"], m["count"] = where, 1
        return m, True

    # An id key only anchors the matcher to a record when it really names one
    # the world already carries. `slack_dm_sent_to`'s `user_id` is the
    # recipient of a new message, not a record id, and `row_id` is a sheet
    # coordinate; asking the seed settles which is which without a second list
    # to keep in step with the vendor's.
    rid = next((a[k] for k in _ID_KEYS
                if a.get(k) not in (None, "")
                and _seeded_record(initial_state, service, collection, a[k])), None)
    field = next((a[k] for k in _FIELD_KEYS if a.get(k)), None)
    if field is None:
        # "has_tag" / "has_note" and friends append to a named field of the
        # record they name; the suffix says which one.
        for suffix, named in _SUFFIX_FIELD.items():
            if rest.endswith(suffix) and named:
                field = named
                break
    field = _FIELD_ALIAS.get(field, field) if field else None

    if collection == "*":
        # A service that only logs actions has no stable path to the record: the
        # log key is minted during the run. The matcher names the write's own
        # content instead, and `count` pins how many were asked for, so doing the
        # requested thing 201 times is not a pass.
        m = {"service": service, "op": "*", "path": f"{service}.*"}
        where = _content_of(a)
        if where:
            m["where"], m["count"] = where, 1
        return m, True
    if rid is not None:
        # A record that already exists: allow that one field, or that record.
        path = f"{service}.{collection}[id={rid}]"
        demanded = not _already_holds(a, initial_state, service, collection, rid, field)
        return {"service": service, "op": "*",
                "path": f"{path}.{field}*" if field else f"{path}*"}, demanded
    # A record must appear. A "*_exists" assertion that the initial state
    # already satisfies (a count check, a seeded record) demands no change.
    return ({"service": service, "op": "added",
             "path": f"{service}.{collection}[*]"},
            not _count_only(rest))


def derive(task: dict[str, Any], side_effects: SideEffects) -> dict[str, Any]:
    """Return {"expected": [...], "allowed": [...], "unmapped": [types]}."""
    expected: list[dict[str, Any]] = []
    unmapped: list[str] = []
    # Matchers for assertions that satisfying requires no change: granted, so a
    # competitor that does touch the record is not punished for it, but never
    # required, so a competitor that leaves it alone still passes.
    granted: list[dict[str, Any]] = []
    initial_state = task["info"].get("initial_state", {})
    for a in task["info"].get("assertions", []):
        spec = _TYPES.get(a["type"])
        if spec is not None and _action_log(a["type"], initial_state):
            # Same story as the sheets rows below: an action log is a dict
            # keyed by action_key, so a flat `<service>.actions[*]` matcher
            # can never match anything the world actually records.
            spec = None
        elif spec is not None and _rows_are_nested(a["type"], initial_state):
            # `_TYPES` was written for the `simple` domain, whose pilot tasks
            # seed a flat google_sheets.rows. The scored domains use the
            # vendor's real shape - rows inside worksheets inside spreadsheets -
            # so where the seed is nested the derived matcher is the right one.
            spec = None
        if spec is None:
            if _is_negative(a["type"]):
                continue                    # satisfied by doing nothing
            m, demanded = _derived_matcher(a, initial_state)
            if m is None:
                unmapped.append(a["type"])
                continue
            target = expected if demanded else granted
            if m not in target:
                target.append(m)
            continue
        service, collection, id_key = spec
        if collection == "$collection":
            collection = a.get("collection") or _object_collection(a) or "*"
        field = _FIELD_ALIAS.get(a.get("field") or a.get("property") or "", a.get("field") or a.get("property"))
        rid = a.get(id_key) if id_key else None
        if rid and field:
            # A field the seed already carries diffs as `changed`; one it omits
            # diffs as `added`, because the record gains the key. Pinning
            # `changed` in that second case demands an op the world never
            # produces, so the matcher follows the seed.
            present = _field_seeded(initial_state, service, collection, rid, field)
            m = {"service": service, "op": "changed" if present else "*",
                 "path": f"{service}.{collection}[id={rid}].{field}"}
        elif field and collection != "*":
            # property asserted on a record found by a non-id key: created or changed
            m = {"service": service, "op": "*", "path": f"{service}.{collection}[*].{field}"}
        else:
            m = {"service": service, "op": "added",
                 "path": f"{service}.{collection}[*]" if collection != "*" else f"{service}.*"}
            if collection == "*":
                # See _derived_matcher: an action log has no stable path, so the
                # matcher pins the write's content and how many were asked for.
                where = _content_of(a)
                if where:
                    m["where"], m["count"] = where, 1
        if m not in expected:
            expected.append(m)

    seeded = set(task["info"].get("initial_state", {}).keys())
    touched = seeded | {m["service"] for m in expected} | {m["service"] for m in granted}
    allowed: list[dict[str, Any]] = list(granted)
    paths = " ".join(m["path"] for m in expected)
    for service, cond, matchers in side_effects:
        if service in touched and (cond is None or cond in paths):
            allowed.extend(m for m in matchers if m not in allowed)
    return {"expected": expected, "allowed": allowed, "unmapped": sorted(set(unmapped))}


def declare_dir(src: str | Path, out: str | Path | None = None,
                overwrite: bool = False, side_effects: SideEffects | None = None) -> dict[str, Any]:
    """Write declared copies. out=None means in place (only with overwrite).

    `side_effects` is a loaded list; None means the simulated-apps product's file.
    """
    if side_effects is None:
        side_effects = default_side_effects()
    src = Path(src)
    dst = Path(out) if out else src
    if dst == src and not overwrite:
        raise ValueError("declaring in place rewrites contract hashes; pass overwrite=True")
    dst.mkdir(parents=True, exist_ok=True)
    report = {"declared": 0, "already_declared": 0, "unmapped": {}, "tasks": []}
    for p in sorted(src.glob("*.json")):
        task = json.loads(p.read_text(encoding="utf-8"))
        info = task["info"]
        if info.get("expected_changes") and not overwrite:
            report["already_declared"] += 1
            if dst != src:
                (dst / p.name).write_text(json.dumps(task, indent=1, default=str), encoding="utf-8")
            continue
        d = derive(task, side_effects)
        if d["unmapped"]:
            report["unmapped"][task["task"]] = d["unmapped"]
        info["expected_changes"] = d["expected"]
        info["allowed_changes"] = d["allowed"]
        task["contract_sha256"] = contract_hash(task)
        (dst / p.name).write_text(json.dumps(task, indent=1, default=str), encoding="utf-8")
        report["declared"] += 1
        report["tasks"].append({"task": task["task"], "n_expected": len(d["expected"]),
                                "n_allowed": len(d["allowed"])})
    return report
