# Research note · sandbox: one dev container per competitor harness

Read-only pass on 4 Sep 2026, before the brainstorm of feature 007. Nothing
was modified. Line references are to `monarch-benchmark/workflowbench/`.

## Machine

Docker Desktop 28.4.0 (Linux containers, 6 CPUs), WSL2 with Ubuntu-24.04. No
dev-container definition in the Monarch checkout to reuse; images would be
written from scratch.

## What leaves the bench process today

- `api` harness (`wb_arms/api_loop.py`): the prompt (`:458-461`) and the tool
  results (`_exec_tool`, `:132-147`, in-process against the `Episode`). The
  model never sees a snapshot. The key is read from the process environment
  (`:156-159`), which holds every provider key at once.
- `cli` harness, Claude Code headless (`wb_arms/cli_claude_code.py`): the whole
  `os.environ` minus the OAuth variables goes to the subprocess (`:84-85`),
  with `--permission-mode bypassPermissions` (`:30`) and a real shell; the task
  JSON is written into the work dir (`:70`); the world runs as an MCP server
  (`wb_world/server.py`) whose snapshot files land inside the agent's own work
  dir (`:67`), readable and in principle writable by the agent. Cost is
  self-reported by the CLI (`:126-135`).
- `monarch` harness (`wb_arms/monarch.py`): remote process; the bench serves a
  per-attempt front door (`:239-245`), the competitor sees only the request
  text and the front-door URL, and cost is read afterwards from Langfuse
  (`:268-297`). This already satisfies the sandbox contract.

## The narrowest container interface (keeps rule 3)

In: request text, front-door URL, budget (deadline, max turns), one provider
key. Out: an `ArmResult`-shaped JSON (termination, turns, tool calls, four
token counts, cost or raw tokens, flags, turn log, final text). The
`Episode`, both snapshots, the checks and `grade()` stay in the bench
(`wb_orchestrator/orchestrator.py:326, 369-373, 390-413`). The front door
exposes no snapshot or grading route (`wb_arms/http_shim.py:59-81`).

## What the `api` harness needs to run inside a container

- The three tools already exist as HTTP routes: `POST /search`, `/fetch`,
  `/encode` (`http_shim.py:74-97`), returning the same strings as in-process.
  Only `_exec_tool` changes.
- Missing: auth on the front door (a per-attempt bearer token), a bind policy
  for containers (`host.docker.internal`, ephemeral port per attempt; Monarch
  pins 9105 with `allow_reuse_address = False`), a result envelope carrying
  `InfraError` kind, `retryable` and `retry_after` across the process boundary
  (the orchestrator's retries depend on them, `orchestrator.py:336-353`).
- Pricing: keep it on the host from raw token counts (never trust a
  competitor's own cost figure; same rule as Monarch).

## Claude Code in a container

The whole arm moves inside (node + pinned `claude` CLI + python), with one key
injected by environment. Keep the MCP tool surface but make the in-container
MCP server a thin proxy to the host front door (no `Episode`, no snapshot
files inside the container); the snapshot is taken host-side by `ep.finish()`,
and the fold-back block (`cli_claude_code.py:96-108`) is deleted.

## Channel bench ↔ container on Windows

`docker run` with one JSON request on stdin and one JSON result on stdout,
one container per attempt (same shape as the CLI harness's `subprocess.run`,
`cli_claude_code.py:87-89`). A long-lived container with an HTTP server
amortises start-up but leaks state between attempts; a mounted work dir is
slow on Windows and recreates the "agent sees its cwd" problem.

## Overhead

No extra tokens (same tool schema, same result strings, same 100k
truncation). One localhost round trip per tool call (milliseconds). Container
start-up 1 to 3 s per attempt: visible in wall-clock, so the acceptance
comparison is on correctness and cost, not time.

## Configuration and hash

New optional harness keys on `api` and `cli`: `sandbox: true`, `image:
<registry/name@sha256:digest>`, `secrets: [KEY_ENV, ...]`. Include them in
the config hash only when `sandbox` is set (the same trick `_hashed_harness`
uses for Monarch-only fields, `config.py:566-580`), so today's hashes stay
stable; or take the hash move and clear the `release: null` debt at once
(`deferred.md`). `EpisodeRow` needs no change; per-row provenance can use
`flags` (`sandbox=<digest12>`) or the unused `env_fingerprint`.

## First slice and proof

`api` harness, one model, one image, the stdin/stdout channel: front-door
token and port handling (~15 lines), the container entrypoint with
`_exec_tool` over HTTP, a `SandboxedApiArm` on the host with the same
`run(ep, deadline) -> ArmResult` contract, host-side pricing. Proof in layers:
scripted competitors unchanged; one task through a mock provider both ways
with byte-identical `snapshot1` and tool calls; then one smoke plan (10 tasks
× 2) both ways, pass rates within the paired error bars, token counts within
a few percent, and no new cache flags (`cache_degraded`, `cache_reporting=
absent`). Keep `api.yaml` and `api-sandboxed.yaml` side by side until the
comparison passes.

## Questions for Carlos

1. Which harness first: `api` (one function changes) or `claude-code` (the
   larger exposure)? Recommendation: `api` as the plumbing proof, then
   `claude-code`; fix the snapshot-in-work-dir gap regardless.
2. Where the keys live: the bench reads `.env` and injects one key per
   container, or a real secret store.
3. Monarch counts as sandboxed and stays out of scope.
4. Docker Desktop on this laptop versus a Linux benchmark host.
5. Config-hash policy: conditional keys (hashes stable) or one hash move.
6. Port policy: sandboxed harnesses use ephemeral front-door ports; a plan
   mixing Monarch (fixed 9105) and sandboxed competitors needs a rule.
