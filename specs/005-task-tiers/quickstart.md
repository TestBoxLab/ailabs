# Quickstart: proving feature 005 works

All commands from `monarch-benchmark/workflowbench/`. **Nothing in this feature
spends model money**, needs a key or reaches the network. The four rounds that
use its output are separate decisions and are listed last, gated.

## Offline (every developer, CI)

```bash
uv sync
uv run python -m pytest tests -q
```

Expected: all tests green — the existing suite plus `tests/test_tiers.py` and
the additions to `tests/test_corpus.py`, `tests/test_config.py` and
`tests/test_run_config.py`.

What the new tests prove, mapped to the spec:

| Test file | Proves |
|---|---|
| `test_tiers.py` | the score (services except the bookkeeping key, plus expected changes, plus tools); the cut points on a synthetic corpus; a tie landing in the lower tier; two draws with one seed identical byte for byte and a third with another seed different; a drawn copy's hash equal to its original's; the round-robin spread over a tier's domains; a task with no approval rule and one whose hash does not match both excluded and named; a tier short of usable tasks refusing (SC-004 – SC-008) |
| `test_corpus.py` | the import accepts the six scored domains and `all`, writes one folder per domain, and reports services the product does not list (SC-001, SC-003) |
| `test_config.py` | the four plans load and validate; each names its set, the seven competitors, the baseline and no approval (SC-009) |
| `test_run_config.py` | the banner's arithmetic in the agreed words, and that the hashes of the 200 already-imported tasks did not move when the ignore list changed (SC-009, data-model §8) |

## The real corpus and the real draw (offline, free, ~minutes)

1. **Import the six scored domains** and the baseline one:

   ```bash
   uv run wb corpus import-ab --domains all --dest 'corpus/imported-{domain}'
   ```

   Expected: 800 tasks in seven folders, and the last line reporting no service
   missing from the product. If it names a service, stop: add it to
   `config/products/simulated-apps.yaml` and `config/side-effects.yaml` before
   anything else.

2. **Derive the approval rules** per folder and validate:

   ```bash
   for d in finance hr marketing operations sales support; do
     uv run wb corpus declare "corpus/imported-$d" --overwrite --product simulated-apps
     uv run wb corpus validate "corpus/imported-$d"
   done
   ```

   Record how many tasks came out with unmapped assertion types — that number is
   spec Open Question 4 and the review queue for Lucas.

3. **Confirm the measure with Carlos and Lucas** (spec FR-013, Open Question 1)
   before the next step's output is committed. The command runs either way; the
   drawn folders are not committed until the measure is agreed.

4. **Draw the four sets**:

   ```bash
   uv run wb corpus tiers --seed 20260904
   ```

   Expected: the cut points, the four per-domain breakdowns, four folders of ten
   and the manifest. Then prove the freeze and the determinism:

   ```bash
   uv run wb corpus validate tasks/tier-complex     # contract drift: 0
   uv run wb corpus tiers --seed 20260904 --out /tmp/redraw
   diff -r tasks /tmp/redraw                        # no differences
   ```

5. **Commit** the six corpus folders, the four task sets and the manifest — the
   task sets only after step 3 is answered.

## The four rounds (each needs Carlos's approval of that specific run)

Not part of this feature. Each is a full round at smoke scale:
**prompts: 10; attempts per prompt and competitor: 2; attempts per competitor:
20 = 10 × 2; competitors: 7; attempts in the round: 140.** State that and a cost
band before asking, one round at a time:

```bash
uv run wb run --product simulated-apps --plan tier-simple
uv run wb grade <run id>
uv run wb report <run id> --audience internal --baseline claude-opus-5/api
```

then `tier-medium`, `tier-complex`, `random-10`. File each report under
`out/report-<plan>-001-internal.md`.

Read them as four separate rounds, never pooled: the question is whether the gap
between Monarch and the baseline changes from simple to complex, and whether the
random ten sit between the tiers. Drawing the four together in one view is
feature 006.
