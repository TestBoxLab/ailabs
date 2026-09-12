# Contract — what a report on an external product must say

**Feature**: [026-external-benchmark-products](../spec.md) · **Date**: 2026-09-11

Written from data, never typed by hand, in the shape `wb_studio/caveats.py` already
produces caveats. One report, no internal-versus-public division, as of 11 September 2026.

## The comparability sentence (FR-028)

Every run and round report on an external product carries it. Built from the source pin
and the product's declared checker:

> The tasks come from **{benchmark}** {version}, split **{split}**, pinned at import.
> The benchmark's own {checker} decided whether the expected result is present; this
> lab's approval rule decided whether anything else changed. Our task hash covers the
> request text and the approval rule, not the benchmark's own checks, so these rows are
> frozen jointly with that pinned version.

That last clause is not decoration. It is the honest statement of what decision D1 costs
us, and the spec requires it to be visible rather than buried in a plan.

### The extra sentence when the positive half is not end-state only

Appended when the product's `positive_half_is_end_state_only` is false — τ² today:

> This benchmark's own score is composite and partly scores the actions taken, not only
> the state reached. Do not read this pass rate as the end-state-only pass rate the other
> products report.

### The paid-participant sentence (FR-029)

Appended when the product declares participants:

> Each attempt contained a second paid party: a **{role}** played by **{model}**. Its
> tokens are counted in the cost shown.

## No pooling across products (FR-030)

Any comparison — a paired table, a mean, a cohort, a standings row — that would span two
products is refused, naming both:

> These rows come from different products under test ({a} and {b}). They are not
> comparable and are not pooled.

This is the load-bearing guard of the whole feature. The moment a second product exists,
the cheapest mistake in the lab is a table with two incomparable numbers in it, and a
refusal in code is the only thing that reliably prevents it.

## Both halves of the verdict are visible

A failed attempt says which half failed. Where a source has its own side-effect finding —
AppWorld does — it is shown beside ours, and a disagreement between the two is shown as a
disagreement rather than resolved into one number.

An attempt whose source checker failed to produce a verdict is reported as **ungraded**,
with the error, and is excluded from pass-rate denominators with its exclusion counted.
It is never quietly a failure.

## Everything else is unchanged

Figures carry their source line, as they already do. Pass rates carry their Wilson
interval. The answer key is the ceiling line and the scripted checks are the floor, drawn
per product. None of this is new; it simply now happens once per product instead of once.
