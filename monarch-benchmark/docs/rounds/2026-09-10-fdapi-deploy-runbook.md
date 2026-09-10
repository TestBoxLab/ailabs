# Deploying the schema synthesizer to Railway

Prepared 10 Sep 2026, not yet executed. The Monarch session finished the OpenAPI
mapping feature — a response-schema synthesizer that falls back to an observed
body when the vendor's contract does not describe one. This is what it takes to
put that on the deployment the benchmark measures.

## What changes

Two commits sit above the revision the bench last verified (`d4d8da19f`):

| Commit | What |
|---|---|
| `3b81a02dd` | match the wire witness to the step's status |
| `b11c580cf` | record why response schemas are now synthesized |

**Both touch `feature-discovery/` only.** So this is an `fdapi` deploy: the
backend, the workflow orchestrator and the engine are unchanged and must not be
rebuilt.

## Before

1. **Confirm the tree is the revision you mean.** `railway up` uploads the
   working tree, not a git ref — an uncommitted edit ships silently.

   ```bash
   cd /c/Users/cgmat/Desktop/TestBox/monarch
   git status -sb && git log --oneline -1
   ```

   `.gitignore` and `feature-discovery/api/src/app.ts` are currently modified.
   Decide whether each belongs in the deploy before uploading.

2. **Record what is running now**, so a rollback has a target.

   ```bash
   bash local-docs/setup/scripts/railway-ops.sh status
   ```

3. **The bench must be idle.** A round in flight would see the catalogue change
   underneath it.

## Deploy

```bash
export PATH="/c/Users/cgmat/AppData/Roaming/npm:$PATH"
cd /c/Users/cgmat/Desktop/TestBox/monarch
railway whoami && railway status          # personal account, monarch-dev, production
railway up --service fdapi --detach       # rebuild: 5 to 12 minutes
```

Deploy is by upload, never from GitHub: the branch `feat/railway-dev-deploy`
stays local. `railway service redeploy` reuses the last image and would **not**
carry the new code.

## After

1. **The service is up.**

   ```bash
   bash local-docs/setup/scripts/railway-ops.sh status     # fdapi SUCCESS running=1
   ```

2. **The catalogue is intact.** The synthesizer changes how a schema is resolved,
   so this is the check that matters: the count must not move, and every app must
   still be in sync.

   ```bash
   bash local-docs/setup/scripts/bench-seeds.sh status     # expect 47 listed, 47 in_sync, 686 actions
   ```

3. **The knowledge base still matches what the bench froze.** If the synthesizer
   changed any stored schema, the per-app hashes move and every Monarch attempt
   is refused at `prepare()` with `knowledge base drift`.

   ```bash
   cd /c/Users/cgmat/Desktop/TestBox/ailabs/monarch-benchmark/workflowbench
   uv run wb monarch verify        # six checks, front_door included
   ```

   A drift here is not a failure of the deploy — it means the catalogue changed
   and the bench must re-import before it can measure. Re-run
   `wb monarch setup --product simulated-apps --no-conform`, which rewrites
   `config/products/simulated-apps.monarch-kb.yaml`, and note that this moves the
   config hash of any plan carrying the knowledge base.

4. **One attempt, end to end.** The tunnel must be up and the front door
   reachable, then:

   ```bash
   WB_OPERATOR="<your name>" uv run wb run --product simulated-apps --plan diag-front-door
   ```

   One attempt, no retry, about US$ 2 to 3. What to read: `terminations`
   should be `completed`, and the attempt's `front-door.jsonl` should carry
   application calls (`/airtable/...`), not only `/openapi/index.json`.

## Rollback

`railway service redeploy --service fdapi` and pick the previous deployment, or
`railway up` from a checkout of `d4d8da19f`. If the catalogue changed and the
bench already re-imported, roll the knowledge base back too — `git checkout` the
kb file and re-run `wb monarch setup`, in that order, or the drift check will
refuse every attempt.

## What this does not cover

The synthesizer targets **real** public APIs, where the vendor's spec is the
truth. It deliberately does not run on the bench front door: that serves an
OpenAPI transcribed from the real vendor while the bodies come from the
AutomationBench mock, and the two diverge (Gmail's `Message` shares no field
name between them). The `bench-*` seeds keep coming from the AI Labs generator,
which reads the mock. `bench-exclusion.test.ts` in the Monarch repo pins that.

So a correct deploy should leave the 47 bench products **unchanged**. If step 2
or 3 shows movement there, something crossed the boundary and is worth
understanding before measuring anything.
