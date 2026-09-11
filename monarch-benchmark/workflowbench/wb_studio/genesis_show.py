"""`show`: Genesis points at what it changed, and a person decides whether to go.

Feature 024, stage S1. Genesis often changes something a long way from the conversation
— it files a card, reads a run, notices the week's allowance is nearly spent — and today
the only way to say so is a sentence the reader has to act on by hand.

**The server never navigates anything.** WCAG's glossary puts a change of viewport on
the change-of-context list, and 3.2.5 permits one "only by user request, or a mechanism
is available to turn off such changes". A real `<a href="#run/x">` in the turn stream is
a user request by definition, and it also gives middle-click-to-a-new-tab, copy link,
the back button, and an address that can be sent to someone else. Moving the screen
without being asked buys nothing over that and owes a whole conformance mechanism.

So this tool validates a route, records the act as a tool call like every other lab
action — `tool_started` / `tool_completed`, into the turn record, the Trace pane and
`genesis/activity.jsonl` — and returns a receipt. "Why did my screen move?" never needs
asking, because it did not; and "why is Genesis pointing me here?" has an answer on the
page.

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
PREFIXES = ('#run/', '#report/', '#round/', '#genesis/t/')
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
    "link in your turn, next to one line saying why. It does NOT move anyone's screen — "
    "the person clicks it, or does not. Use it when what you did lives somewhere else: a "
    "run you read, a card you filed, the budget page when the allowance is short. Routes: "
    + ", ".join(EXACT[:6]) + ", #run/<id>, #report/<id>, #round/<id>. One show per turn is "
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
    """The receipt. The client turns it into a link; nothing here touches the screen."""
    route = check_route(payload.get("route"))
    label = str(payload.get("label") or "").strip()[:80] or _label_for(route)
    why = str(payload.get("why") or "").strip()[:300]
    return {"route": route, "label": label, "why": why, "moved": False}


TOOLS = {"show": show}
