"""The live Product Graph that Monarch Enterprise uses, read from its discovery
service. Read only: this module sends GET requests and nothing else, and the
Studio exposes it through GET routes only. Nothing here can change Monarch.

The discovery service is the `fd_url` of the Monarch harness, gated by the
`x-fd-api-key` header when the harness names the variable (the Railway
deployment does). Answers are cached for a minute so a page of clicks does not
turn into a page of requests.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from wb_orchestrator.monarch_setup import expand, fd_headers
from wb_studio.enterprise import Setup

CACHE_S = 60
TIMEOUT_S = 20.0
PAGE = 200


class LiveGraphUnavailable(Exception):
    """The graph cannot be read right now; the message says why, in plain words."""


def fetch(url: str, headers: dict) -> dict:
    """One GET, JSON back. Tests replace this; nothing else in the module touches the network."""
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise LiveGraphUnavailable(f"Monarch's discovery service answered {exc.code} for {url.split('?')[0]}") from exc
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise LiveGraphUnavailable(f"Monarch's discovery service could not be reached: {exc}") from exc


_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def _cached(url: str, headers: dict) -> dict:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(url)
        if hit and now - hit[0] < CACHE_S:
            return hit[1]
    data = fetch(url, headers)
    with _lock:
        _cache[url] = (now, data)
    return data


def forget() -> None:
    with _lock:
        _cache.clear()


def service(studio) -> tuple[str, dict]:
    """The discovery service's base URL and headers from the Monarch harness, or why there is none."""
    setup = Setup(studio)
    harness = setup.harness
    if harness is None:
        raise LiveGraphUnavailable("The Monarch harness could not be loaded: " + "; ".join(setup.problems))
    if not harness.fd_url:
        raise LiveGraphUnavailable("The Monarch harness names no discovery service (fd_url).")
    try:
        base = expand(harness.fd_url, setup.env, "fd_url").rstrip("/")
    except Exception as exc:  # expand raises on an unset variable
        raise LiveGraphUnavailable(str(exc)) from exc
    return base, fd_headers(harness, setup.env)


def _pages(base: str, headers: dict, path: str) -> list[dict]:
    items, cursor = [], None
    for _ in range(50):  # ponytail: 10 000 rows is far beyond any product graph today
        query = {"limit": PAGE, **({"cursor": cursor} if cursor else {})}
        page = _cached(f"{base}{path}?{urllib.parse.urlencode(query)}", headers)
        items.extend(page.get("items") or [])
        cursor = page.get("next_cursor")
        if not cursor:
            break
    return items


def _stamp(base: str) -> dict:
    return {"source": urllib.parse.urlsplit(base).netloc, "read_only": True,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def products(studio) -> dict:
    """Every product the live graph knows, with how many business actions each holds."""
    base, headers = service(studio)
    rows = _pages(base, headers, "/v1/products")
    items = [{"slug": r.get("slug"), "name": r.get("display_name") or r.get("slug"), "domain": r.get("domain"),
              "actions": int(r.get("business_action_count") or 0), "replayable": int(r.get("replayable_action_count") or 0),
              "database": bool(r.get("is_database")), "last_run_at": r.get("last_run_started_at")}
             for r in rows if r.get("slug")]
    items.sort(key=lambda p: (p["name"] or "").lower())
    return {**_stamp(base), "products": items}


def actions(studio, slug: str) -> dict:
    """The business actions stored for one product, as the discovery service lists them."""
    base, headers = service(studio)
    rows = _pages(base, headers, f"/v1/products/{urllib.parse.quote(slug, safe='')}/business-actions")
    items = [{"key": r.get("action_key"), "label": r.get("label") or r.get("action_key"), "area": r.get("area") or "",
              "verb": r.get("verb") or "other", "state": r.get("state") or "", "target": r.get("target_kind"),
              "implemented": bool(r.get("has_implementation")), "sources": r.get("implementation_sources") or [],
              "verified": r.get("replay_verified"), "contract_version": r.get("contract_version"),
              "first_seen_at": r.get("first_seen_at"), "last_seen_at": r.get("last_seen_at")}
             for r in rows if r.get("action_key")]
    items.sort(key=lambda a: (a["area"].lower(), a["label"].lower()))
    return {**_stamp(base), "product": slug, "actions": items}
