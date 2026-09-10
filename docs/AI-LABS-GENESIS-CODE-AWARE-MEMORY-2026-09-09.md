# Genesis: code awareness and a memory that does not bloat

Research note, 9 September 2026, evening. Lucas asked for two things on top of
the Genesis brainstorm: Genesis should be code-aware, with an index of Monarch
Enterprise refreshed daily so it always knows the current state; and it needs
a memory system that stays useful without growing without bound. This note
records what the field does in 2026, what already exists in the repo, and a
recommendation to carry into the feature 019 spec.

## What exists today

- Genesis has a protocol (`wb_studio/GENESIS.md`), a board with six stages, a
  chat, a library of sources (Saved or Analyzed), `record_analysis` so it does
  not re-analyse unchanged evidence, and one lab tool (`lab_action`) that reads
  runs, searches research and saves cards. Paid work goes through approval.
- The repo's knowledge layer is Graphify (`graphify-out/`, `GRAPH_REPORT.md`),
  required reading before architecture questions per `CLAUDE.md`. It is not
  installed on Lucas's machine today, so the graph is stale here.
- Monarch is a sibling clone (`../monarch`): 5,323 tracked files, mostly
  TypeScript (2,083 `.ts`, 226 `.tsx`), 253 Markdown, 125 SQL, 115 Terraform,
  124 MB. The rounds so far ran a fork branch that lives only on Carlos's
  machine, not stock `main` (see the memory note of 8 Sep).

## Part 1 — Code awareness: a daily index of Monarch Enterprise

### What the field converged on

Three layers, increasingly combined, and the index is now treated as a cost
and accuracy control plane rather than a convenience:

1. **Syntactic graphs from tree-sitter** (Aider's repo map, Graphify,
   Codebase-Memory). Deterministic, local, no model needed. Codebase-Memory
   indexes Django (49K nodes, 196K edges) in about 6 s into one SQLite file,
   re-indexes only files whose XXH3 hash changed (about four times faster than
   a full rebuild), and recomputes only the affected Louvain communities. Its
   agent answered with quality 0.83 against 0.92 for a grep-and-read explorer,
   at about 1,000 tokens per query instead of 10,000 and 2.3 tool calls
   instead of 4.8.
2. **Resolved symbols through a language server** (SCIP, LSP bridges). Needed
   when "which definition does this call reach" matters; costs one RPC per
   call site, heavy on large TypeScript projects.
3. **Embeddings** (Cursor, CocoIndex) for natural-language search over chunks,
   synced by Merkle diffs. Useful, but a second store to run and nothing the
   graph cannot approximate for our questions.

Two conclusions follow. Graphs win on cost, not always on accuracy, so a grep
and file-read fallback stays. And incrementality is table stakes: content
hashes, file watchers or a post-pull hook.

Graphify specifically: `graphify update .` re-extracts only changed files;
`--code-only` uses deterministic AST parsing with no API key; docs, PDFs and
images need a model and are tracked in `cost.json`; every edge is tagged
EXTRACTED, INFERRED or AMBIGUOUS; the report carries god nodes, surprising
connections, design rationale mined from `NOTE`, `WHY` and `HACK` comments, and
the commit it was built from; `graphify hook install` rebuilds on commit and
branch switch.

### Recommendation

- **One deterministic index, rebuilt daily, no model.** A scheduled job
  (`wb genesis index`, Studio cron on the host) does `git fetch` and checkout
  of the agreed Monarch ref, then `graphify update . --code-only` into a
  Genesis-owned folder, and records the commit, node and edge counts, and the
  time. Cost: zero. Time: seconds for a repo this size.
- **Docs weekly, with a ceiling.** Monarch's 253 Markdown files (ADRs,
  runbooks) need model extraction. Run them once a week under a ledger
  reservation (default US$ 2), never nightly.
- **Tools, not dumps.** Genesis gets `code_search` (a scoped subgraph),
  `code_explain` (one symbol with its neighbours), `code_path` (between two
  symbols), `code_read` (a file range) and `code_changes` (what moved since a
  commit), all read-only through `lab_action`. It must cite file and symbol.
- **A daily "what changed in Monarch" record, written by code.** Between
  yesterday's and today's commit: files touched per graph community, god nodes
  touched, migrations added, routes added or removed, package version bumps.
  Filed in the library as a source of type "repository", dated. Genesis may
  add one sentence of interpretation, clearly marked as its own.
- **The current state of Monarch lives in one bounded file** (see Part 2),
  rewritten by the index job from the report and the change record, not by
  the model. That is what "always knows the latest status" means in practice:
  the file is regenerated, so it cannot drift.
- **Which ref.** The fork the rounds ran is not `main`. The index should
  follow whatever the harness names as the build under test
  (`MONARCH_BUILD`, `MONARCH_BUILD_COMMIT`), with `main` as a second index
  only if someone asks for it. One index per ref, never mixed.
- **Audience.** Anything Genesis learns from Monarch's code is internal-only.
  A memory entry or a card derived from the code carries that mark and never
  reaches a public report.

## Part 2 — Memory that stays useful

### What the field learned

- **Bounded, curated core beats an ever-growing store.** Hermes Agent keeps
  two files injected into every session: `MEMORY.md` (2,200 characters, about
  800 tokens, 8 to 15 entries) and `USER.md` (1,375 characters). A write past
  the limit returns an error rather than silently dropping entries, so the
  agent must merge with `replace` before adding. Everything else, all past
  sessions, sits in SQLite with FTS5 full-text search: unlimited, about 20 ms
  a query, no model call. Entries are scanned for injection before they are
  accepted, because they enter the system prompt.
- **Forgetting must be governed, not incidental.** The 2026 surveys agree
  that most teams build storing and retrieval and skip updating, compression
  and forgetting, and that wrong or stale entries accumulate quietly and add
  noise to every later retrieval. Without management, memory grows linearly
  and retrieval slows. Repeated summarisation distorts facts (semantic drift)
  and errors in an evolving memory are cumulative. The recommended shapes:
  decay of accessibility instead of deletion, a hot buffer with a probation
  period before promotion, budget-aware forgetting policies, and a guarantee
  that safety-critical records survive.
- **Consolidate offline.** Letta's sleep-time agent works while the primary
  agent is idle, rewriting the shared memory blocks; the primary reads them at
  any time. Frequency is a dial: more runs, more tokens, better memory.
- **Compaction is a rate-distortion problem.** What every layer gets wrong is
  deciding what to keep by recency or attention before the question is known,
  with no way back. So keep the full record somewhere cheap and compact only
  the part that enters the prompt.
- **Vendor numbers do not survive reproduction.** Mem0, Zep and Letta publish
  benchmark figures that fell by 10 to 20 points under other harnesses. Any
  memory we ship needs our own small evaluation.

### Recommendation

Three tiers with hard budgets, and a nightly job that keeps them honest.

| Tier | What | Budget | Who writes it |
|---|---|---|---|
| Core | `LAB.md`: what Genesis has learned about the lab, its rules and the people. Injected every turn. | 2,500 characters, about 900 tokens | Genesis, through add, replace and remove; a write past the budget fails |
| Core | `MONARCH.md`: current build, commit, last index time, communities and god nodes, last change record, open incidents. Injected every turn. | 2,500 characters | The index job, from data; the model never edits it |
| Working | One notes block per card, with evidence ids. | 4,000 characters per card | Genesis while it works the card |
| Record | Everything, append-only, off-prompt: cards, analyses, library sources, run verdicts and events, the code index, every chat turn. | Disk only | The Studio, as today; FTS5 over turns and analyses |

Rules that stop bloat and drift:

- **Nothing enters core without a record id.** Every core entry cites the
  record it came from. Consolidation rewrites an entry from its record, never
  from the previous wording, so summaries of summaries cannot drift.
- **Probation.** A new fact goes to a "recent" section of `LAB.md` and is
  promoted after seven days only if it was retrieved or cited again; else it
  drops back to the record, where search still finds it.
- **Decay by access, not deletion.** The nightly job marks core entries not
  cited in 30 days as stale; the next night removes them from core. The
  record keeps them. Pinned entries (decisions from `PLAN.md`, the fixed
  rules, the spending gate) never decay.
- **Sleep, nightly, bounded.** After the index job: read the day's new
  records, propose core edits within the budget, flag contradictions between
  a new source or run and an Analyzed card, write the daily brief. Reserved in
  the weekly ledger like any paid request, default US$ 0.50 a night.
- **Retrieval shows its work.** Every recalled record shows source and date;
  Genesis cites ids in answers, as the protocol already demands.
- **Injection scan.** Core files are scanned before a write is accepted, since
  they enter the system prompt; a library source can contain anything.
- **Our own evaluation.** Twenty questions about the lab whose answers live in
  records, run weekly: recall, wrong answers, tokens per answer. Reported in
  the Genesis view, not in a benchmark report.

### What not to adopt

- A hosted memory service (Mem0, Zep). Our facts are lab records with ids; a
  second store that extracts facts with a model and re-ranks them would
  duplicate the library and hide provenance. The spending gate also prefers
  no per-call vendor.
- A vector store. FTS5 over records plus the code graph covers the questions
  Genesis asks; embeddings can be added behind the same tool later if recall
  in the weekly evaluation says so.
- Learned forgetting (RL-trained consolidators). It can delete what it should
  not, and we cannot audit why.

## Cost and effort

| Item | Cost | Effort |
|---|---|---|
| Daily code index, code-only | US$ 0 | 1 day: job, freshness record, `MONARCH.md` writer |
| Weekly docs extraction | up to US$ 2 a week | half a day |
| Code tools for Genesis | US$ 0 | 1 day |
| Core memory files, budgets, injection scan | US$ 0 | 1 day |
| Nightly sleep job, probation, decay | up to US$ 0.50 a night | 2 days |
| Memory evaluation | US$ 0 | half a day |

## Part 3 — What Genesis grows next (Lucas's choices, 9 Sep evening)

Chosen from a multiple-select brainstorm after feature 019 landed. Each item
runs under the ceilings already in place; nothing launches or pays for a run
without an approval card.

**Loops**
- Weekly research sweep: every Monday, one turn per library topic searches for
  new sources, files them, flags contradictions with Analyzed cards, and drops
  at most one hypothesis card per finding worth testing.
- Post-run debrief: every finished run gets a card with what was learned, the
  failure buckets in words, and the one experiment Genesis would run next with
  a cost band. Replaces the bare "run" trigger card.
- Evidence-to-proposal: when two runs disagree on a task or a failure bucket
  grows, Genesis writes an approval card with one changed factor, a control,
  the frozen set, a ceiling and a stop rule.
- Memory self-check: nightly, three random Known entries are re-read against
  the record; any that no longer hold are marked and dropped to the record.

**Capabilities**
- Skills it writes for itself: procedures (read a run, review a paper, grade a
  hypothesis) as files under `genesis/skills/`, versioned, injected when the
  task matches, improved after use with a note of what changed; editable by a
  person.
- Monarch patch proposals: from a failure and the code index, a card with a
  diff and `path:line` citations. Never applied, internal-only.

**Channels**
- Daily brief posted to Slack `#ailabs` each morning, linking to the board.
  Needs a Slack webhook or token in `.env`; not configured today.
- Weekly digest page: a public-safe report page built from the week's cards
  and runs, in the report style.
- Question cards: when unsure, Genesis asks on the board and the card waits.
- Identity file: `SOUL.md`, edited by Lucas, injected with the core memory:
  voice, priorities, what it must never do. **Built 9 Sep (feature 020, first
  item):** `wb_studio/memory.py` writes a starter text on first start; the
  Memory tab holds an editor with Save and Discard; only the interface writes
  it (op `soul`, scanned for injection, 2,500 characters); it enters every
  prompt before the core memory, and no Genesis tool can touch it.

**Governance**
- Confidence and provenance on every claim: record ids and a confidence word;
  a claim without them renders as Unknown.

Not chosen: second-opinion turns, deterministic notebooks, per-drop budgets,
weekly memory score, per-card change log.

Suggested order: identity file and confidence tags (a day), post-run debrief
and question cards (a day), skills (two days), weekly sweep and
evidence-to-proposal (two days), memory self-check (half a day), digest page
(a day), Slack brief once a webhook exists (half a day).

## Decisions for Lucas

1. Which Monarch ref the index follows: the build under test, `main`, or
   both as separate indexes.
2. The nightly ceiling for consolidation and the weekly ceiling for docs.
3. Whether the daily brief goes to the board only or also to `#benchmarks`.
4. Whether code-derived memory is internal-only (recommended) or may appear
   in public reports with the file names.

## Sources

- Hermes Agent memory: https://hermes-agent.nousresearch.com/docs/user-guide/features/memory and https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers
- Codebase-Memory (arXiv 2603.27277): https://arxiv.org/html/2603.27277v1
- "Code Isn't Memory" (arXiv 2606.22417): https://arxiv.org/pdf/2606.22417
- TypeScript repository indexing for code agents (arXiv 2604.18413): https://arxiv.org/pdf/2604.18413
- Coding-agent scaffold taxonomy, Aider's repo map (arXiv 2604.03515): https://arxiv.org/pdf/2604.03515
- Graphify: https://github.com/Graphify-Labs/graphify and https://graphify.com/blog/introducing-graphify
- CocoIndex incremental codebase indexing: https://cocoindex.io/blogs/index-codebase-v1/
- Sleep-time compute (Letta): https://www.letta.com/blog/sleep-time-compute/
- Always-On Agents survey (arXiv 2606.30306): https://arxiv.org/pdf/2606.30306
- Memory for Autonomous LLM Agents survey (arXiv 2603.07670): https://arxiv.org/html/2603.07670v1
- SSGM, governing evolving memory (arXiv 2603.11768): https://arxiv.org/html/2603.11768v1
- Rate-distortion view of memory compaction (arXiv 2607.08032): https://arxiv.org/abs/2607.08032
- Human-inspired memory architecture (arXiv 2605.08538): https://arxiv.org/pdf/2605.08538
- Memory framework comparisons: https://mnemoverse.com/docs/library/ai-memory-solutions-2026-q3 and https://vectorize.io/articles/best-ai-agent-memory-systems
