# AppWorld — licence and provenance

**Source**: <https://github.com/StonyBrookNLP/appworld>
**Site**: <https://appworld.dev>
**Paper**: arXiv 2407.18901 (ACL 2024, best resource paper)
**Authors**: Stony Brook University
**Licence**: Apache License 2.0, with an added redistribution requirement — see below
**Checked**: 11 September 2026

## The redistribution requirement, in plain words

AppWorld is deliberately split in two so that its tasks do not leak into training
corpora:

- **Plain text, Apache-2.0**: agent baselines, evaluation utilities, the execution
  shell, tests for public code, tutorials and guides.
- **Packed, Apache-2.0 plus a condition**: the app implementations, the interface
  code and documentation, the task solutions and the evaluation programs. These ship
  as encrypted `.bundle` files, and **any public redistribution of them, or of
  anything derived from them, must itself be in encrypted form**.

**This repository is public.** Therefore no AppWorld content is committed here, in
any form. Not a task, not a request text, not an interface description, not an
answer key, not a fixture copied out of one.

## How we stay on the right side of that

- AppWorld is installed separately, into a directory named by `APPWORLD_ROOT` that
  lives **outside** this repository. Its conventional location is in `.gitignore` as
  a second guard.
- Our task files record **identifiers only** — the AppWorld `task_id`, the split and
  the source pin. The request text is read from the installed package at run time.
- Test fixtures under `tests/fixtures/external/appworld/` hold our own recorded
  shapes — what a snapshot looks like, what `.evaluate()` returns — never their task
  or answer-key content.
- `wb corpus import-appworld` asserts what it wrote before it finishes.

If you are about to commit something and you are unsure whether it came from
AppWorld, it did. Leave it out.

## Splits

Everything is released for `train` and `dev`. For `test_normal` and
`test_challenge` only the evaluation programs are released, not the reference
solutions — so those splits are gradeable but cannot carry an answer key, and the
answer-key competitor is the ceiling line on every figure we draw. We import from
`train` and `dev`; the importer refuses the test splits by name and says why.

## What we never modify

Their evaluation. `.evaluate()` is called and its `success`, `passes` and `fails`
are kept whole. Their own collateral-damage finding is recorded **beside** ours, not
merged into it, and a disagreement between the two is shown as a disagreement.

## Comparability

Our numbers will not match their leaderboard: we add our own collateral half, our
harness differs, and we run train and dev rather than the test splits their board
reports. Every report on this product says so.
