# Deferred items for the `/monarch-benchmark` skill

Things Carlos asked for on 4 Sep 2026 that the skill does not fully deliver
yet. Each item says what exists today, what is missing, and where it goes.

## 1. Proof of life for every harness and model

**Ask.** Configuring a harness must leave evidence that it worked at some
point with the models listed for it: one small call ("hello") and the
recorded answer. Nothing sophisticated; a stored, dated proof, so nobody has
to re-verify by hand before every round.

**Today.** `wb doctor --arms <models>` makes one cheap tool call per model
(and repeats it to probe the prompt cache) and prints OK/FAIL, but the result
is not stored anywhere. For Monarch, `wb doctor --arms monarch` checks the
four services and, with `--monarch-probe`, one authoring request.

**To build.** Subcommand `harness test <harness> [--model NAME ...]`:

- runs the doctor for each harness + model pair (cents; asks first);
- writes `config/harnesses/proofs/<harness>@<model>.yaml` with: date, the
  harness and model file names, the model id and provider, the request sent
  (the doctor's fixed prompt), the answer's first line, whether the tool call
  worked, whether the cache reported, cost of the probe, and the `wb` commit;
- `harness list` and `check` show the last proof per pair and its age, and
  warn when a plan names a pair with no proof or a proof older than 30 days;
- the proof is evidence, not a gate: a round can still run without it, but
  the confirmation block says "no proof of life for <pair>".

Where: `references/harness.md` (subcommand) and `references/check.md` (the
warning). Code side: a `wb doctor --record` flag that writes the proof file
so the skill does not parse terminal output. Feature to spec: small, offline
except the probe itself.

## 2. Sandbox for the competitors that run on this machine (future)

**Ask.** The models driven by the bench today (the API tool loop, Claude Code
headless) run in the bench's own process on Carlos's machine, with the API
keys in `workflowbench/.env`. There is no sandbox, so data could leak during
a round: a competitor's tool call, a coding agent's shell, a logged prompt.
Carlos wants each harness to run inside a dev container of its own, holding
that harness's API key, with the provider calls made from inside the
container, and the bench talking to the container over a narrow interface.

**Today.** Nothing. The API tool loop gives models only the three world
tools (no file or shell access), which limits what a raw model can reach,
but the process boundary is the bench's own. Monarch already runs elsewhere
(Railway) and reaches the bench only through the front door.

**Later, to spec as its own feature.** One container image per harness kind
(`api`, `claude-code`, later `codex`, `gemini-cli`); the container receives
the task request and the front door address, holds the provider key as a
secret, and returns the attempt's transcript and token usage; the world
stays in the bench process behind the front door (the same path Monarch
uses today), so the container never sees the snapshot. Open questions: how
the world tools are exposed (the front door already serves REST; the API
tool loop would move to HTTP tools instead of in-process calls), how
`EpisodeRow` gets tokens and cost from inside the container, Docker on
Windows for the bench machine, and cost of the extra hop per tool call.
Constitution rules unchanged: same request text, nothing grades itself,
cost complete, API-key billing only.

Marked future on purpose: it changes how every non-Monarch competitor runs
and needs its own brainstorm, spec and pilot comparison (a round in
containers must reproduce a round without them before it replaces it).
