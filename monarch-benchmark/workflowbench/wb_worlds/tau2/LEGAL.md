# τ²-bench — licence and provenance

**Source**: <https://github.com/sierra-research/tau2-bench>
**Authors**: Sierra Research
**Licence**: MIT License, "Copyright (c) 2025 Sierra Research" (read from the
repository's own `LICENSE` file, 11 September 2026)
**Checked**: 11 September 2026

## What we use

The domain environments, their tools, their tasks and their reward. The package is
`tau2`; domains live under `src/tau2/domains/`.

## Two things a reader of our numbers has to know

**1. The version matters.** The source's own release notes state that results
produced with versions below 1.0.1 are not comparable with 1.0.1 and later, and that
affected leaderboard entries were re-graded. The version is part of the source pin,
and the importer refuses a version below 1.0.1 as non-comparable.

**2. Their reward is not end-state only.** It is composite: it can score the actions
taken and the information communicated, not only the state reached. Every other
product we run is graded on the end state alone.

We take their reward **whole and unchanged**, because filtering it down to its
database component would be manufacturing a metric τ² does not define — which is
editing another benchmark's answer key by a quieter route. Instead every report on
this product carries a sentence saying the positive half is composite and partly
scores the path, so a τ² pass rate is never read as the end-state-only pass rate the
other products report.

## The second paid participant

A model plays the customer inside every attempt. It is pinned in the product
configuration, so it enters the configuration hash; its tokens are reserved and
settled in the weekly ledger with the competitor's, because an attempt has one cost,
not a cost and a footnote; and every report says a model sat inside the measurement
loop.

## Retained source material

The isolated Sierra checkout holds the package and original domain databases.
The two imported task manifests retain the MIT-licensed source task record and
policy, with source revision and data hashes. Those files include private customer
instructions and expected actions: only the host importer and independent grader
may read them. Competitors receive the public policy, common bridge brief and
published domain operations; they never receive the task record or snapshots.

The initial retail smoke uses source tasks 33 and 34. Their original reward basis
is `DB`; neither invokes the natural-language model judge. The importer explicitly
excludes other `NL_ASSERTION` tasks until a separately reserved source-judge path
exists. It never removes a source reward component to make a task runnable.
