"""Which world serves a product's attempts (feature 026).

A dictionary and a lazy import. Three implementations do not need a plugin system;
this repository already has one in `wb_studio/genesis_plugins.py` for the case that
genuinely did.

Lazy matters more than it looks. The external benchmarks run out of process in their
own environments -- AppWorld pins pydantic below 2.0 and this project needs 2.0, so
they could not share one even if we wanted to -- and the offline suite runs with none
of them present. A missing source is a named refusal from `prerequisites()`, never an
ImportError at start-up.
"""
from __future__ import annotations

from importlib import import_module

#: world name -> (module, attribute). Registered when the adapter exists, not before:
#: a name here that cannot be resolved is a broken product file waiting to happen.
WORLDS: dict[str, tuple[str, str]] = {
    "automation-bench": ("wb_world.episode", "Episode"),
    "appworld": ("wb_worlds.appworld.adapter", "AppWorldWorld"),
    "tau2": ("wb_worlds.tau2.adapter", "Tau2World"),
    "enterprise-ops-gym": ("wb_worlds.enterprise_ops.adapter", "EnterpriseOpsWorld"),
}

DEFAULT = "automation-bench"


class UnknownWorld(KeyError):
    """A product named a world that is not registered."""

    def __str__(self) -> str:          # KeyError repr quotes the message; this does not
        return self.args[0]


def known() -> list[str]:
    return sorted(WORLDS)


def resolve(name: str | None) -> type:
    """The adapter class for a world name; the AutomationBench world when unnamed."""
    key = name or DEFAULT
    try:
        module, attr = WORLDS[key]
    except KeyError:
        raise UnknownWorld(
            f"unknown world {key!r}; the products under test can name: {', '.join(known())}"
        ) from None
    return getattr(import_module(module), attr)
