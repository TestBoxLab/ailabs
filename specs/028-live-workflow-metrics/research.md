# Research and design decisions

Read 2026-09-11. Existing work: streaming Studio (008), outcome workspace (009),
Monarch runtime (011), measures.py and design audit of 10 September. The current
observatory preserves text blocks but hides node lanes; renderGraph rebuilds
the lane DOM for every event. Time currently coerces unknown to zero. Recipe
events contain node definitions; do not assume they contain all dependency edges.

[Inspect's log viewer](https://inspect.aisi.org.uk/log-viewer.html) exposes
incremental sample metrics and live transcripts. Adopt that connection between
progress and individual evidence. [Inspect sample dataframes](https://inspect.aisi.org.uk/dataframe.html)
distinguish total time, working time and retries. For this Studio, report only
the clock actually recorded and explicitly defer unsupported retry/wait splits.

Product choice: successful-task median and p90 beside all-attempt operational
completion, cost per successful task and harm. Also retain failed-task time,
tool errors, turns and phase time. These expose speed/cost/reliability tradeoffs
without a composite score. Small samples are descriptive. No causal or winner
claim is introduced by partial live values.
