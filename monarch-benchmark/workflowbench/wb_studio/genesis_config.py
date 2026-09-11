"""Genesis configuration (feature 022): which model each step of Genesis's work uses.

One JSON file, `genesis/config.json`, written only from the interface by a person and
read by the code that starts a turn. A step with no model named, or naming a route that
is not available, falls back to the cheapest available route by list price, never to the
first route in file order. The steps are the vocabulary of the configuration page; a
module that adds a step adds it here.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

# Every step of Genesis's work that spends a model turn, in the order the page shows them.
STEPS = ('chat', 'reading', 'review', 'ranking', 'consolidation', 'sweep', 'extraction', 'embedding', 'patch')
# Steps that judge or write take the strongest available route by list price until an admin names
# one (Lucas, 10 Sep 2026); every other step takes the cheapest.
DEFAULT_STRONG = ('review', 'patch')


def list_price(route_id: str) -> float:
    """Input plus output list price per million tokens; unknown routes sort last."""
    from wb_arms import providers
    p = providers.REGISTRY.get(route_id)
    return float('inf') if p is None else float(p.price_in) + float(p.price_out)


def cheapest(routes) -> dict | None:
    """The cheapest available route by list price; ties keep the earlier one."""
    available = [r for r in routes if r.get('available')]
    return min(available, key=lambda r: list_price(r['id'])) if available else None


def strongest(routes) -> dict | None:
    """The priciest available route by list price, the lab's stand-in for the strongest; unpriced routes never win."""
    available = [r for r in routes if r.get('available') and list_price(r['id']) != float('inf')]
    return max(available, key=lambda r: list_price(r['id'])) if available else cheapest(routes)


class Config:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'config.json'
        self.lock = threading.RLock()

    def read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding='utf8'))
        except (OSError, ValueError):
            data = {}
        models = data.get('models') if isinstance(data.get('models'), dict) else {}
        return {'models': {s: models.get(s) for s in STEPS}, 'steps': list(STEPS)}

    def set(self, payload: dict, routes=None) -> dict:
        """A person's change: `models` maps step to route id or null. Unknown steps and routes are refused."""
        models = payload.get('models')
        if not isinstance(models, dict):
            raise ValueError('models maps each step to a route id or null.')
        known = {r['id'] for r in (routes if routes is not None else self._routes())}
        current = self.read()['models']
        for step, route in models.items():
            if step not in STEPS:
                raise ValueError('Unknown step ' + str(step) + '; steps are ' + ', '.join(STEPS) + '.')
            if route is not None and route not in known:
                raise ValueError('Unknown route ' + str(route) + ' for ' + step + '.')
            current[step] = route
        with self.lock:
            self.path.write_text(json.dumps({'models': current}, indent=1), encoding='utf8', newline='\n')
        return self.read()

    @staticmethod
    def _routes():
        from wb_studio.genesis_harness import model_routes
        return model_routes()

    def route_for(self, step: str, routes=None) -> dict | None:
        """The route a step uses now: the configured one when it is available, else the cheapest available."""
        if step not in STEPS:
            raise ValueError('Unknown step ' + str(step))
        routes = list(routes if routes is not None else self._routes())
        wanted = self.read()['models'].get(step)
        chosen = next((r for r in routes if r['id'] == wanted and r.get('available')), None) if wanted else None
        return chosen or (strongest(routes) if step in DEFAULT_STRONG else cheapest(routes))

    def effective(self, routes=None) -> dict:
        """Step to route id as it would be used now, for the page and the state."""
        routes = list(routes if routes is not None else self._routes())
        return {s: (self.route_for(s, routes) or {}).get('id') for s in STEPS}
