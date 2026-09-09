# Contract: CLI additions

Feature 001's `wb run / resume / status / doctor / grade / report / corpus` and
feature 002's and 004's `wb monarch` additions are unchanged. This feature widens
one existing subcommand and adds one new one, both offline.

## `wb corpus import-ab` (changed: which domains it accepts, and where they land)

```
wb corpus import-ab --domains NAME[,NAME…]|all --dest DIR
```

- `--domains` already takes a comma list. It now also accepts the six scored
  domains by name — `finance, hr, marketing, operations, sales, support` — and
  the word **`all`**, meaning those six plus the baseline `simple`.
- `--dest` may contain `{domain}`, which is replaced per domain so one call
  writes one folder per domain. Without it, and with more than one domain, the
  command refuses rather than mixing domains in one folder.
- Nothing about the conversion changes: the rows carry the request text, the
  tools needed, the starting data and the assertions, and carry no approval rule.

```
$ uv run wb corpus import-ab --domains all --dest 'corpus/imported-{domain}'
simple:     200 written, 0 unchanged
finance:    100 written, 0 unchanged
hr:         100 written, 0 unchanged
marketing:  100 written, 0 unchanged
operations: 100 written, 0 unchanged
sales:      100 written, 0 unchanged
support:    100 written, 0 unchanged
total: 800 tasks in 7 folders
services seeded by these domains and NOT listed by product simulated-apps: none
```

The last line is FR-006. A non-empty answer names each missing service and exits
1, so nothing is drawn from a corpus the product cannot serve.

Exit codes: 0 imported; 1 a service is missing from the product; 2 bad arguments
(several domains without `{domain}` in `--dest`).

Approval rules still come from the existing command, run per folder:

```
uv run wb corpus declare corpus/imported-finance --overwrite --product simulated-apps
uv run wb corpus validate corpus/imported-finance
```

### World revisions: `--revision LABEL` and `--out DIR` (added 8 Sep 2026, milestone M1)

```
wb corpus import-ab --domains NAME[,NAME…]|all [--out DIR | --dest DIR] [--revision LABEL]
```

- `--out DIR` names the folder that holds one `imported-<domain>/` folder per
  domain. With neither `--out` nor `--dest` the folders land under `corpus/`,
  exactly as before. `--dest` keeps its old meaning (a pattern with
  `{domain}`); `--out` and `--dest` together are refused (exit 2).
- `--revision LABEL` (letters, digits, `.`, `_`, `-`) records the world the
  tasks were imported under: every task gets `info.world` with the package
  name (`automation-bench`), the installed package version and the label, and
  that block is part of `contract_sha256`. Rows recorded on such a set carry the
  suite id `workflowbench-synthetic@<version>`; sets that record no world keep
  `workflowbench-synthetic@0.1`. `wb report` and `wb summary` refuse to pool
  rounds of different suite ids.
- Without `--revision`, the import is refused (exit 2) when the installed
  package is not the upstream `1.0.6`, so a repaired world never lands in
  `corpus/` unlabelled.
- With `--revision`, `DIR/MANIFEST.yaml` is written after the import.

```
$ uv run wb corpus import-ab --domains all --revision evalrepair10 --out corpus-evalrepair10
simple:     200 written, 0 unchanged
finance:    100 written, 0 unchanged
…
total: 800 tasks in 7 folders
revision: evalrepair10 (automation-bench 1.0.6+evalrepair.10); manifest: corpus-evalrepair10/MANIFEST.yaml
services seeded by these domains and NOT listed by product simulated-apps: none
```

Then declare and validate per folder as above, and refresh the manifest.

## `wb corpus manifest DIR` (new, 8 Sep 2026)

```
wb corpus manifest DIR
```

Rewrites `DIR/MANIFEST.yaml` from the `imported-*` folders under `DIR` as they
are now: the revision label and world version the tasks record (a folder set
that mixes worlds is refused, exit 1), what `vendor/automation-bench/VENDORED-FROM.txt`
says about the installed copy, the import date kept from the previous manifest,
per-folder task counts, whether the folder's rules are declared, usable counts
(a non-empty approval rule and a matching hash, the two checks `wb corpus tiers`
applies), the totals and the list of tasks without a rule with their reasons.
Offline; writes only the manifest.

```
$ uv run wb corpus manifest corpus-evalrepair10
corpus-evalrepair10: revision evalrepair10, world automation-bench 1.0.6+evalrepair.10
  finance      100 tasks, 100 usable, declared
  …
total: 800 tasks, 795 usable, 5 without a rule
[ok] write corpus-evalrepair10/MANIFEST.yaml
```

Exit codes: 0 written; 1 no `imported-*` folder under DIR, or the folders mix worlds.

## `wb run` (changed: the installed world must be the recorded one)

`wb run` and `wb resume` refuse a task set whose recorded world version is not
the installed `automation-bench` version, naming both, before anything is
spent:

```
config error in config/plans/tier-simple.yaml: tasks: this task set was imported
under automation-bench 1.0.6, but the installed world is automation-bench
1.0.6+evalrepair.10; …
```

A set that records no world counts as `1.0.6`, the only world the bench had
before it recorded one. The frozen sets under `tasks/` therefore do not run on
the repaired world; new sets are drawn from the corpus imported under it.

## `wb corpus tiers` (new)

```
wb corpus tiers --seed N [--per-tier 10] [--corpus DIR]… [--out DIR]
```

- `--seed` is required. It is recorded in the manifest, and the same seed over
  the same corpus produces byte-identical output.
- `--per-tier` defaults to 10: how many prompts each drawn set holds.
- `--corpus` may be repeated; it defaults to every `corpus/imported-*` folder.
  The folder's name after `imported-` is the domain.
- `--out` defaults to `tasks/`: the four folders and the manifest are written
  under it.
- **Offline. No key, no network, no model money.** It reads the corpus folders
  and writes only under `--out`.

```
$ uv run wb corpus tiers --seed 20260904
corpus: 7 folders, 800 tasks, 795 usable
  excluded 5: 4 with no approval rule (unmapped assertion types), 1 whose hash
  does not match its content — see the manifest
measure: services seeded + expected changes + tools needed
cuts: simple <= 9 < medium <= 12 < complex
draw (seed 20260904, 10 per set):
  tier-simple   10 prompts — simple 7, finance 3
  tier-medium   10 prompts — finance 2, hr 2, marketing 2, operations 2, sales 1, simple 1
  tier-complex  10 prompts — hr 1, marketing 2, operations 2, sales 2, support 3
  random-10     10 prompts — simple 3, sales 2, support 2, hr 1, marketing 1, operations 1
[ok] write tasks/tier-simple/ tasks/tier-medium/ tasks/tier-complex/ tasks/random-10/
random-10 is drawn from the usable corpus minus the thirty tier tasks, so the
four sets share no task
[ok] write tasks/tiers-manifest.yaml
every drawn task keeps its corpus hash; info.tier and info.domain are not hashed
```

- Every drawn file is a copy of its corpus file with `info.tier` and
  `info.domain` added and `contract_sha256` unchanged.
- A tier with fewer usable tasks than `--per-tier` makes the command refuse,
  naming the tier and how many it found; nothing is written. The same happens if
  fewer than `--per-tier` tasks remain for the random set once the three tiers
  have been drawn.
- Re-running with the same seed rewrites the same bytes; a different seed is a
  different task set, and the manifest says which seed made it.

Exit codes: 0 written; 1 a tier has too few usable tasks; 2 bad arguments;
3 a corpus folder is missing or empty.

## `wb corpus validate` (unchanged, used on the drawn folders)

```
$ uv run wb corpus validate tasks/tier-complex
corpus: 10 tasks | noop failures: 0 | oracle failures: 0 | oracle unsupported: 10 |
invariant undeclared: 0 | contract drift: 0
OK
```

Contract drift 0 on a drawn folder is the proof of FR-019: the copies still carry
the hash of their corpus originals.

## `wb run` (changed: what the banner says about size)

The banner states a round's size in the agreed words, for every plan, before
anything is spent:

```
plan tier-complex, mode create-run, product simulated-apps
prompts: 10; attempts per prompt and competitor: 2; attempts per competitor: 20 = 10 × 2
competitors: 7; attempts in the round: 140
cost ceiling US$ 40; approved_by: (none) — refusing
```

A bare per-competitor total is never printed on its own.
