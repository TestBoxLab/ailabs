# Quickstart: proving feature 006 works

All commands from `monarch-benchmark/workflowbench/`. **Every step is offline
and free.** This feature reads the results store and writes files; no step needs
a key, a network, Monarch, or approval.

## 1. The suite

```bash
uv sync
uv run python -m pytest tests -q
```

Expected: green, including the new files.

| Test file | Proves |
|---|---|
| `tests/test_html_report.py` | every metric of `contracts/report.md` section 1 against hand-computed values on a seeded store; the four tables present; infrastructure failures counted and excluded from the denominator in the same row; `n/a` where a denominator is 0 and no `inf` or `nan` anywhere; a competitor's error string escaped; the gate holding for `public-rung2`; the Monarch phase columns present with phases and absent without; the header's size line (SC-001 to SC-005, SC-007) |
| `tests/test_summary.py` | `wb summary` over three seeded rounds: three metrics tables, one aggregate table, the mean over the rounds where a competitor ran, the random draw beside the tier mean, the never-pooled sentence, and refusal on an unknown run or plan (SC-006) |
| `tests/test_m4.py` | the markdown report is unchanged, and the html file now contains `<table` (SC-008) |

## 2. The page for a real round (no money)

`out/wb.sqlite3` holds `run-20260904-125645`: 80 attempts, four competitors
(`claude-opus-5/api`, `gpt-5.6-sol/api`, `kimi-k3-fireworks/api`, `oracle`), the
10 pilot tasks, 2 repetitions.

```bash
uv run wb report run-20260904-125645 --audience internal \
    --baseline claude-opus-5/api
```

Expected on stdout:

```
wrote out/report-run-20260904-125645-internal.md
wrote out/report-run-20260904-125645-internal.html
```

Open the HTML file. It must contain, in order:

1. a header stating `prompts: 10 - attempts per prompt and competitor: 2 -
   per competitor: 20 = 10 x 2 - competitors: 4 - attempts in total: 80`;
2. a metrics table with four rows, `oracle` at 100.0% and `claude-opus-5/api`
   at 90.0% +/- 10.0% - the same values the markdown report shows;
3. a comparison table with three rows, each carrying a verdict, and `no
   significant difference at this size` where p is 0.4795 and 1.0;
4. a task matrix with 10 rows and 4 competitor columns, no domain and no tier
   column (no pilot task carries them), and a details table below it;
5. a failures table naming `simple.sf_opp_closed_won` with its unexpected change
   paths;
6. a provenance block with configuration hash `a5d4e4135f3f2385`, the task
   hashes and the audience.

Check the same file for what must **not** be there:

```bash
grep -c "inf\b\|nan\b" out/report-run-20260904-125645-internal.html   # 0
```

## 3. The public page (no money)

```bash
uv run wb report run-20260904-125645 --audience public-rung2
```

Expected: refused with `audience 'public-rung2' allows none of the run's
arms ...` - this round has no Monarch competitor and the public allowlist holds
only `monarch`. That refusal is the gate working; it is the same behaviour as
today.

## 4. The summary page (no money)

Once two or more rounds exist for the same competitors:

```bash
uv run wb summary --runs run-20260904-125645,run-20260904-150550 \
    --audience internal --out out/summary-check.html
```

Expected: one page with both rounds' metrics tables, each with its own source
line, an aggregate table with one row per competitor and the number of rounds
each mean covers, and the sentence `Paired comparisons are computed per round,
on that round's identical task set, and are never pooled across rounds.`

With the tier plans of feature 005 in place:

```bash
uv run wb summary --plans tier-simple,tier-medium,tier-complex,random-10 \
    --audience internal --out out/summary-tiers-001.html
```

Expected additionally: a per-tier column in the aggregate, and the
stratification block showing the random draw beside the mean of the three tiers.

## 5. Refusals worth seeing

```bash
uv run wb summary --runs run-20260904-125645                 # exit 1: needs two rounds
uv run wb summary --runs no-such-run,run-20260904-125645     # exit 1: names the run; writes nothing
uv run wb summary --runs a,b --plans c,d                     # exit 1: exactly one of the two
```
