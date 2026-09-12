# Accuracy — what a number in a lab document must carry

From `PLAN.md` §1 and the constitution. Cite a finding as `accuracy:<id>`. These are the rules a
reader would use to decide whether to believe the page.

## A1 Every number traces to the measure that computed it
A rate, a delta, an interval or a cost names the run it came from. A number written by a model and
not by `measures`, `compare`, `failure_buckets` or `report` is a defect, whatever its value.

## A2 An interval, or no comparison
A difference between two setups is reported with its interval. A bare difference invites a
conclusion the data does not support.

## A3 Paired comparisons on identical sets
A competitor is compared with another only over the same tasks at the same repetitions. A
comparison across different sets is a defect even when both numbers are right.

## A4 The denominator is visible
A percentage says what it is a percentage of. "60% of failures" and "60% of attempts" are
different sentences.

## A5 Cost is complete
Cached and uncached tokens, at the versioned price table, for every competitor shown. A cost
without its basis is a defect.

## A6 The caveats the data demands are present
What `caveats.py` derives for this run appears on the page. A missing caveat is a defect even when
nothing on the page is false.

## A7 Nothing grades itself
A verdict rests on the checker's stored results, never on a competitor's own report of what it did.

## A8 Nothing on the page came from source code
There is one report and every reader sees it whole, so it carries no fact taken from anyone's
source code.

## A9 A small run is labelled as one
A run at smoke scale says so, and draws no conclusion.

## A10 The frozen identity is named
The task set and its hash, the config hash, the date. A report that cannot be reproduced from what
it prints is a defect.

## A11 A claim about why is marked as a hypothesis
Observed fact, grader verdict, causal hypothesis and experimentally supported finding are four
different things and the page says which it is showing.
