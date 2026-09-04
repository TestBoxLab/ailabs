# Deferred items for the `/monarch-benchmark` skill

The bench-wide list (sandbox for the harnesses, `wb doctor --record`, and the
smaller items carried from features 002 to 006) lives with the CLI:
`monarch-benchmark/workflowbench/differs.md`. Only what is specific to the
skill is listed here.

- `harness test` writes the proof file from the doctor's printed lines; once
  `wb doctor --record` exists, the skill calls it and stops parsing output.
- `tasks` shows drawn sets and manifests only after feature 005 is merged and
  the sets are committed; until then it lists the folders that exist.
- `check` cannot verify the Monarch tunnel end to end without the front door
  running; it reads a 502 from the tunnel as "tunnel up, front door down".
