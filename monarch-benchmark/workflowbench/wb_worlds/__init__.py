"""One subpackage per external benchmark that WorkflowBench can run as a product.

Each subpackage holds three things and nothing else: an adapter (the world behind
the three tools, plus that source's own check), an importer (its tasks as our task
files), and a legal note. They sit together because the licence boundary runs
between sources, not through them -- `wb_worlds/appworld/` is the only place that
knows AppWorld content must never be written into this public repository.

Shared machinery stays in `wb_world/` where it already lives. Nothing here is
imported at start-up: `wb_world/registry.py` imports an adapter lazily, so a
missing source package is a named refusal rather than an ImportError, and the
offline suite runs with none of the three installed.
"""
