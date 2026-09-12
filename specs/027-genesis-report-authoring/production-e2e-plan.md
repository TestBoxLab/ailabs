# Production Genesis report test — prepared action

Requested run: f2799405-f9b3-4fb2-8e41-a517e9c39260 (106 recorded attempts).
Origin: https://ailabs-studio-production.up.railway.app
Service: ailabs-studio / 5f8d06d0-6c11-40f7-86f7-2ef3f60a5f50
Project: bbaa750f-5f82-419c-8ac7-9e01d838837f
Environment: production / e7ba2b19-18db-4a2b-8c82-e0fe250882d8
Observed deployment: fd75f5ca-4881-411f-a1c2-8fc239899881, SUCCESS.

## Verified before mutation

The authenticated production report returns the old schema, without authored,
report_work or patterns. All Genesis routes are keyed but harness_ready=false.
The run is completed with 106 results and recorded cost USD 51.06925921 against
its original USD 60 ceiling. Weekly available budget was USD 177.605857,
with USD 60.564947 held and USD 61.829196 settled. No paid work started.

Prepared source: .tmp/report-e2e-deployment/source, committed baseline
f716a5c570fa4bfa13fd80e5090301a090414fe1 plus 29 reviewed report-only overlay
files. The manifest records every hash and excluded mixed-file hunk.
Isolated source validation: 75 tests passed in 19.83s.
Primary workspace remains unchanged by staging.

## Access needed to preserve the deployed benchmark package

The local vendor copy identifies itself as 1.0.6+evalrepair.10. Production's
recorded world is 1.0.6. Adoption of evalrepair.10 remains suspended.
Do not deploy that local vendor or acquire/replace the benchmark source.

A temporary task-specific SSH key would permit read-only copying of the deployed
application source and its current unchanged vendor package. Read /app source
only; exclude environment files, credentials, local model sessions and /data.
Compare and preserve frozen package hashes. Remove the registered key immediately
in a finally cleanup, including on inspection failure, and verify removal.
Do not change any existing SSH key or security setting.

Automatic approval review rejected the earlier key registration because it would
grant persistent production access outside explicit test authorization. No key
was created or added. This access step awaits explicit Lucas approval.

## Once the exact deployed source is preserved

Review the deployment difference, preserve package/version/task bytes, validate
the isolated report overlay, and deploy only ailabs-studio. Verify the specific
deployment's SUCCESS status and public report contract before paid analysis.
Inspect source hashes and the run's committed/unknown liabilities before choosing
a report ceiling within its remaining allowance and the shared weekly budget.
Use Genesis's native report workflow, retain actual receipts, inspect and fix
any reported failures within the authorized ceiling, and verify full publication
with tests/browser/report-production.cjs (REPORT_REQUIRE_AUTHORED=1).
No evaluated attempts are rerun or regraded.
