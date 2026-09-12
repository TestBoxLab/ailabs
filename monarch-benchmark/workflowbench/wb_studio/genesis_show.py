"""`show`: Genesis points at what it changed, and a person decides whether to go.

Feature 024, stage S1. Genesis often changes something a long way from the conversation
— it files a card, reads a run, notices the week's allowance is nearly spent — and today
the only way to say so is a sentence the reader has to act on by hand.

**The server never navigates anything; the reader's own setting may.** WCAG's glossary
puts a change of viewport on the change-of-context list, and 3.2.5 permits one "only by
user request, or a mechanism is available to turn off such changes". A real
`<a href="#run/x">` in the turn stream is a user request by definition, and it also gives
middle-click-to-a-new-tab, copy link, the back button, and an address that can be sent to
someone else. The link is the whole of what this tool produces.

Follow Genesis (`static/genesis.js`) is the other half, and it belongs to the reader
rather than to this tool. With it on — the default since feature 025, decision D3 — the
client scrolls to the route a `show` names, but only while a turn is running, only on the
surface the reader is already looking at, never into a hidden tab, and any wheel, key,
pointer or touch gesture stops it for the rest of the turn. Focus never moves. Turned off,
a `show` is a link and nothing else; that checkbox is the 3.2.5 mechanism.

So this tool validates a route, records the act as a tool call like every other lab
action — `tool_started` / `tool_completed`, into the turn record, the Trace pane and
`genesis/activity.jsonl` — and returns a receipt. "Why is Genesis pointing me here?" has
an answer on the page, and "why did my screen move?" has one in the status bar that says
Following Genesis, next to the control that stops it.

The validation is the security half. The route is written by a model, travels to the
client and is put in an `href`. Anything that is not a known in-app hash is refused.
"""
from __future__ import annotations

import re

# Every address the Studio answers to. A route is one of these exactly, or one of the
# prefixed ones followed by an identifier. Keep this in step with the route switch in
# `static/app.js` and `static/workspace.js`.
EXACT = ('#reports', '#runs', '#budget', '#runtime', '#studio', '#launch', '#leaderboard',
         '#genesis', '#genesis/board', '#genesis/library', '#genesis/memory',
         '#genesis/activity', '#genesis/digest', '#genesis/settings')
PREFIXES = ('#run/', '#report/', '#round/', '#genesis/t/', '#studio/')
# Identifiers the Studio itself mints: hex ids, task names, setup ids, event anchors.
# Deliberately narrow — no quotes, no angle brackets, no colon, so a route can never
# break out of an attribute or carry a scheme.
SEGMENT = re.compile(r"[A-Za-z0-9._@+-]{1,120}(?:/[A-Za-z0-9._@+-]{1,120}){0,3}")
# A dot is allowed inside an id (task names carry them) but `..` never is: it is the
# one sequence that turns a narrow identifier back into a path.
TRAVERSAL = re.compile(r"\.\.")
MAX = 200

PROTOCOL = (
    "show(route, label, why): point the reader at a place in the Studio. It renders as a "
    "link in your turn, next to one line saying why. You never move the screen yourself: "
    "the reader's own Follow setting decides whether the page goes there, and any gesture "
    "of theirs stops it. Use it when what you did lives somewhere else: a "
    "run you read, a card you filed, the budget page when the allowance is short, the "
    "architecture you are building. Routes: "
    + ", ".join(EXACT[:6]) + ", #run/<id>, #report/<id>, #round/<id>, #studio/<architecture id>. One show per turn is "
    "usually enough; a turn that ends in three links has not decided anything."
)


def check_route(value) -> str:
    """One in-app route, or a ValueError whose sentence the model can act on."""
    if not isinstance(value, str):
        raise ValueError("show needs a route, like '#run/6022e89f' or '#budget'.")
    route = value.strip()
    if not route:
        raise ValueError("show needs a route, like '#run/6022e89f' or '#budget'.")
    if len(route) > MAX:
        raise ValueError(f"That route is longer than {MAX} characters; it is not an address the Studio uses.")
    if TRAVERSAL.search(route):
        raise ValueError(f"'{route}' is not an address the Studio uses: '..' is not part of any id.")
    if route in EXACT:
        return route
    for prefix in PREFIXES:
        if route.startswith(prefix):
            rest = route[len(prefix):]
            if SEGMENT.fullmatch(rest):
                return route
            raise ValueError(f"'{route}' is not an address the Studio uses: the part after {prefix} "
                             "is an id, and may hold only letters, digits, dot, dash, underscore, at, plus and slash.")
    raise ValueError(f"'{route}' is not a place in the Studio. Use one of: " + ", ".join(EXACT) +
                     ", or #run/<id>, #report/<id>, #round/<id>, #genesis/t/<thread>.")


def _label_for(route: str) -> str:
    if route in EXACT:
        return "Open " + route.lstrip("#").replace("genesis/", "").replace("/", " ").strip() or "Open it"
    kind, _, rest = route.lstrip("#").partition("/")
    return f"Open {kind} {rest.split('/')[0]}"


def show(genesis, payload: dict) -> dict:
    """The receipt. The client turns it into a link; nothing here touches the screen.

    It used to carry `"moved": False`. Nothing read it, and it told the model the one
    thing the server cannot know: whether the reader's Follow setting took them there.
    """
    route = check_route(payload.get("route"))
    label = str(payload.get("label") or "").strip()[:80] or _label_for(route)
    why = str(payload.get("why") or "").strip()[:300]
    return {"route": route, "label": label, "why": why}


TOOLS = {"show": show}


def direct_request(text):
    """Only a complete, unambiguous page-opening command avoids a model request."""
    match = re.fullmatch(
        r'(?:(?:please|can you|could you)\s+)?(?:open|show|go to|take me to|navigate to)\s+'
        r'(?:the\s+)?([a-z ]+?)(?:\s+page)?(?:\s+please)?[.!?]?',
        str(text or '').strip().lower())
    if not match:
        return None
    routes = {'budget': '#budget', 'reports': '#reports', 'runs': '#runs',
              'runtime': '#runtime', 'studio': '#studio', 'leaderboard': '#leaderboard',
              'research board': '#genesis/board', 'library': '#genesis/library',
              'memory': '#genesis/memory', 'genesis settings': '#genesis/settings'}
    route = routes.get(match[1])
    return {'route': route, 'why': 'You asked to open this page.'} if route else None
