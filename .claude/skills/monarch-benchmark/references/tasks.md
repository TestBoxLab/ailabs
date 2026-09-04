# `tasks` — look at the task sets

**Read only.** A task's prompt, starting data and approval rule are frozen by
hash before any competitor runs. This subcommand lists and shows; it never
edits. If the user asks for an edit, say it needs Lucas's sign-off and that it
makes old rows non-regradable.

All commands run from `monarch-benchmark/workflowbench/`.

## `tasks list`

Every folder under `workflowbench/` holding task JSON files, with its count and
whether a manifest sits beside it:

```bash
uv run python -c "
from pathlib import Path
for d in sorted(Path('.').iterdir()):
    if not d.is_dir() or d.name in {'vendor', 'out', 'graphify-out', '.venv'}: continue
    for sub in [d, *[x for x in sorted(d.iterdir()) if x.is_dir()]]:
        n = len(list(sub.glob('*.json')))
        if n:
            man = 'manifesto' if list(sub.glob('*manifest*')) else 'sem manifesto'
            print(f'{str(sub).replace(chr(92), \"/\"):32} {n:4} tarefas   {man}')
"
```

Today that is `tasks` (the 10 pilot tasks, the set every shipped plan runs) and
`corpus/imported-simple` (the 200-task corpus). A folder is used in a plan by
writing its path in `tasks:`.

A manifest records how a set was drawn — the seed and the source corpora. A set
without one was assembled by hand.

## `tasks show <folder>`

Each task id and the request text every competitor receives, identically:

```bash
uv run python -c "
from wb_world.episode import load_suite
suite = load_suite('<folder>')
print(len(suite), 'tarefas')
for t in suite:
    print(f\"\n{t['task']}\n  {t['prompt'][1]['content']}\")
"
```

Show the text as it is — do not translate the prompts. They are the request
every competitor gets, byte for byte; that is the whole point.

To see which services a set touches (useful before trimming a product):

```bash
uv run python -c "
from wb_world.episode import load_suite
used = {s for t in load_suite('<folder>') for s in t['info']['initial_state']}
print(', '.join(sorted(used)))
"
```

## Drawing a new set is a different command

Task sets by difficulty are drawn by the bench, not by this skill:

```bash
uv run wb corpus tiers --help
```

It draws four frozen sets from the corpora with a recorded seed
(`--seed`, `--per-tier`, `--corpus`, `--out`), so the same seed redraws the same
bytes. It is feature 005 and **may not be merged in this checkout** — run the
`--help` above first; if it errors, say the command is not available here yet
rather than improvising a draw.

Never draw a set by copying files by hand: a set without a recorded seed cannot
be redrawn, and the round loses its source line.
