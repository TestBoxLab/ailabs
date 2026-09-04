# Contract: CLI additions and changes

Feature 001's `wb run / resume / status / grade / corpus`, feature 002's
`wb monarch setup` and feature 004's `wb monarch recipes` are unchanged. This
feature changes what `wb report` writes and adds one command.

## `wb report` (changed output, no new required flag)

```
wb report RUN_ID [--audience internal|public-rung2] [--baseline COMPETITOR]
                 [--no-sort]
```

- The markdown file is unchanged in shape and content.
- The HTML file, written to the same path
  (`out/report-<run>-<audience>.html`), is no longer the escaped markdown. It is
  the page of `contracts/report.md`: header, metrics table, comparison table,
  task matrix with its details table, failures table, provenance block, and a
  source line under every table.
- `--no-sort` omits the inline column-sorting script (research R5). The page is
  fully readable without it; the flag exists so a page can be shipped as pure
  markup.
- Exit codes unchanged: 0 written; 1 the audience gate refused, or the run does
  not exist, with the reason on stderr.
- No new flag is required to get the new page: an existing invocation produces
  it.

Printed output gains nothing beyond the two existing `wrote <path>` lines.

## `wb summary` (new)

```
wb summary (--runs A,B,C[,D] | --plans P1,P2,P3[,P4])
           [--audience internal|public-rung2] [--baseline COMPETITOR]
           [--out FILE.html]
```

- Exactly one of `--runs` and `--plans`. `--runs` names run ids in the order
  they should appear. `--plans` names plans and uses the **most recent run of
  each**, printing which run it picked:

  ```
  tier-simple      -> run-20260906-101122 (started 2026-09-06T10:11:22Z)
  tier-medium      -> run-20260906-113045
  tier-complex     -> run-20260906-125501
  random-10        -> run-20260906-140233
  ```

- `--out` defaults to `out/summary-<YYYYMMDD-HHMMSS>-<audience>.html`.
- `--baseline` is used for the per-round comparison figures where a round does
  not name one itself; a round's own plan baseline wins.
- The page contains, per `contracts/report.md` section 9: the header with each
  round's size line, one metrics table per round with its own source line, the
  aggregate table, the stratification check when a random-draw round is present,
  and the sentence stating that paired comparisons are never pooled across
  rounds.
- The audience gate is applied per round, exactly as `wb report` applies it. A
  round the gate empties makes the command refuse, naming that round.
- Two to six rounds. Fewer than two is refused (`wb report` is the command for
  one round); more than six is refused because the page stops being readable.
- Exit codes: 0 written; 1 a named run or plan does not exist, a plan has no
  run, the gate refused, or fewer than two rounds were named. Nothing is written
  on any non-zero exit.

Example:

```
$ uv run wb summary --plans tier-simple,tier-medium,tier-complex,random-10 \
      --audience internal --out out/summary-tiers-001.html
tier-simple   -> run-20260906-101122
tier-medium   -> run-20260906-113045
tier-complex  -> run-20260906-125501
random-10     -> run-20260906-140233
wrote out/summary-tiers-001.html (4 rounds, 5 competitors, 560 attempts)
```

## What does not change

- No command spends money. `wb report` and `wb summary` read the results store
  and nothing else; both run offline with no key in the environment.
- No new dependency is introduced by either command.
- The results store schema is untouched; no migration.
