# Genesis report capability contract

author_report(run, maximum_usd?, retry?) starts or returns the existing workflow.
report_status(run) exposes stage, reason, child turn IDs and reviewed hashes.
report_evidence(run, attempt?, after?, limit?) reads a frozen packet in pages.
read_report_draft(run, after?, limit?) reads prose plus paged attempt analyses.
record_report_attempt writes analysis only in the assigned analysis turn.
write_report_draft writes complete prose only in the author/repair turn.

All mutation tools validate the current server-assigned turn and run. Worker
tool definitions AND dispatch enforce a read/draft-only role allowlist. The
model cannot directly publish, spend outside its turn, modify the evidence or
delegate additional unrestricted work. Publication is a validated server action
after a matching separate review; receipts are visible through the same tools.

GET report data adds authored, report_work and patterns. Existing numeric fields
and historical narrative remain backward compatible. The explicit analyze action
uses the new workflow and returns its actual current state, never a fabricated
completed narrative. Round reports keep individual publications run-scoped.

Additional evidence access:
- report_evidence(section="patterns", domain?, setup?) returns the same computed
  counts and percentage slices as the report, with run:index references.
- report_evidence(part="packet", attempt, after?, limit?) pages oversized complete
  evidence as lossless JSON characters; use the returned part and next_after.
- read_report_state(run, attempt, phase?, trial?, path?, after?, limit?) reads
  frozen JSON world state. No phase lists snapshot availability; explicit phase,
  trial and JSON key paths inspect source fields.

Preflight checks every prepared native prompt and tool definition against its
stage's startup floor before any reservation. Larger runs use sequential bounded
analysis batches. Recovery runs at server startup before live workers; explicit
retry is required after interruption, with previous work and billing retained.
