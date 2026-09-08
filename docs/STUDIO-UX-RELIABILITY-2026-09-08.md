# Studio UX and reliability pass

8 September 2026. Scope: AI Labs Studio, its run setup, outcome reporting,
activity/evidence inspection, architecture editor, product graph editor, and the
HTTP validation boundaries those flows use.

The local service is running at [AI Labs Studio](http://127.0.0.1:8765).
The existing eight runs remain available. This pass did not launch paid benchmark
work or paid analysis, change frozen tasks, or rewrite historical results.

## What changed

| Journey | Improvement |
|---|---|
| Start a run | Tasks → Approaches → Review. The selected scope persists between steps; the final action displays the maximum spend. Advanced settings and unavailable integrations have explicit disclosures. |
| Select tasks | Search, category and difficulty filters; select/deselect matching tasks; clear selection; reset filters; count selected tasks outside the current filters. No arbitrary task is preselected. |
| Choose approaches | Ready architectures appear before unavailable versions. Architectures use their own saved runners; unrelated runner choices are hidden when Without Monarch is off. Availability is refreshed when setup opens. |
| Review spend | Required name, task/approach limits, valid turn count, per-request reservation floor, decimal budget validation, and remaining weekly capacity are checked before launch. A disabled start action has a visible explanation. |
| Find a run | Searchable history with meaningful no-results copy, status-specific indicators, and a persistently reachable Monarch setups action. |
| Read outcomes | More compact hierarchy, full-width treatment for a single outcome, responsive comparisons and readable result links. Unknown money/time/action counts remain unavailable; zero and false outputs stay visible. Infrastructure outcomes remain distinct from graded failures. |
| Inspect evidence | Explicit close action, focus moves into the panel and returns to the outcome, raw copy includes its context, and clipboard failures explain how to recover. Evidence without a corresponding action node still opens its event. |
| Navigate | Named modal, tab panels, arrow/Home/End tab navigation, skip link, focus states, reduced-motion support and forced-color treatments. Mobile editors wrap controls and retain local canvas/table scrolling. |
| Recover | Persistent connection error with retry; readable non-JSON/network errors; stale streams and responses cannot overwrite the newly selected run. |

The daylight identity remains: paper/white surfaces, restrained green actions,
Segoe UI, quiet navigation and evidence-led content. The new layout is an
operating workspace, without ornamental summary metrics.

## Bugs fixed and evidence

| Failure | Fix | Regression evidence |
|---|---|---|
| Late report response assigned to a different selected run | Run and report sequence checks before assigning data; selection cleared at navigation commit | Browser: late report / stale stream checks |
| A burst of streamed events rebuilt unrelated controls and fetched a report per event | Frame-batched activity updates, debounced outcome refresh, visible-view rendering and preserved focus | Browser tab/focus checks; rendered live activity |
| Run start retried with a fresh ID after a lost response | Reuse the original request ID for an uncertain response; reject changed retry payloads; guard pending submission | Browser: one POST while pending and identical retry ID |
| Save response overwrote newer product graph edits | Compare the submitted snapshot, preserve newer edits and mark them unsaved | Browser: typing during save |
| Save response assigned the old record ID to a newly selected draft | Bind save completion to the original editor object | Browser: architecture and product graph selection races |
| Concurrent saves created competing writes | Coalesce saves for the same draft; refuse a second draft save while the first is pending | Browser: save call count; source guards |
| Stale graph validation replaced current problems | Sequence, object identity and graph snapshot checks | Browser: delayed validation race |
| Publishing could clear edits made while publication was in flight | Only mark the exact unchanged draft saved; retain newer edits | Source review and adjacent publication regressions |
| Product graph preparation could launch after the draft changed during save | Recheck draft identity and dirty state before the paid endpoint; guard pending preparation | Source review; offline execution suite |
| Malformed nodes/connections crashed graph validation | Validate structure before capability evaluation; reject non-string IDs/types and invalid node shapes | 24 new Python cases, including real localhost HTTP requests |
| Invalid task/version selections reached unhashable set operations | Type-check list elements before set membership | New Python selection cases; no jobs or budget holds created |
| Unknown costs rendered as $0.00; false/zero outputs looked missing | Explicit availability checks | Browser: unknown money, measured zero, false and zero output |
| Product-graph mode retained an architecture-only state badge | Preserve the mode class when updating editor status | Desktop/mobile editor inspection |

New tests: [test_studio_resilience.py](../monarch-benchmark/workflowbench/tests/test_studio_resilience.py).
Browser tests: [browser-regressions.js](../artifacts/studio-enhancement/browser-regressions.js).
The browser suite intercepts all mutation requests in memory; its save and launch
tests do not create production records or dispatch model calls.

## Research translated into implementation

| Source | Guidance applied |
|---|---|
| [NN/g: Progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/) | Keep task selection and launch decisions primary; reveal advanced execution controls and unavailable integrations on demand. |
| [Linear: A calmer interface for a product in motion](https://linear.app/now/behind-the-latest-design-refresh) | Reduce competition between navigation and the active task, keep action placement predictable, and strengthen hierarchy through density and alignment. |
| [Carbon: Empty states](https://carbondesignsystem.com/patterns/empty-states-pattern/) | Distinguish first use, no matching records, pending results and connection failures; offer a relevant next action. |
| [W3C: Modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) | Name the dialog, contain focus with native dialog behavior, provide a close control and sensible initial focus. |
| [W3C: Tabs pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/) | Connect tabs with named panels, use a single tab stop and implement arrow/Home/End navigation. |
| [NN/g: Visibility of system status](https://www.nngroup.com/articles/visibility-system-status/) | Explain waiting, reconnecting, failed requests, held spend and unsaved edits instead of silently changing state. |

These are design inputs. No user study was conducted, and no measured claim about
task completion speed is made.

## Verification

| Check | Observed result |
|---|---|
| First-party baseline suite: `.venv/Scripts/python.exe -m pytest tests -q` | **1,052 passed, 3 skipped**, 1,309.28 seconds. This run collected the existing 1,055 tests before the 24 new cases were added. |
| Final Studio suite, including new cases | **200 passed**, 8.72 seconds. Covers app, execution, paid gateway guards, outcomes, architectures, blueprints, comparison modes, runtime registry and resilience. |
| Browser regression suite | **22 passed**, repeated after final JavaScript changes. |
| Additional browser recovery checks | **4 passed**: disconnected startup, non-JSON errors, successful retry, focus restored after closing evidence. |
| Lighthouse: desktop evidence panel | Accessibility **100**, best practices **100**. [JSON report](../artifacts/studio-enhancement/lighthouse-evidence-desktop.json) |
| Lighthouse: mobile run review | Accessibility **100**, best practices **100**; all 27 checks passed. [JSON report](../artifacts/studio-enhancement/lighthouse-review-mobile.json) |
| Lighthouse: mobile product graphs | Accessibility **100**, best practices **100**. [JSON report](../artifacts/studio-enhancement/lighthouse-product-graphs-mobile.json) |
| Rendered layouts | Desktop 1440px and mobile 390px: overview, setup, architecture/product graph editors and evidence. No page-wide horizontal overflow in the inspected states. |
| JavaScript syntax | `node --check` passes for app.js, graph.js and pg.js. |
| Active service | Restarted only after confirming all eight runs were terminal. New backend rejects a null graph node with structured problems and an empty capability list. |

Bare `pytest -q` initially failed collection because the vendored benchmark and
the project both expose a `tests.conftest` package. Running the first-party
`tests` directory explicitly succeeded. The vendored test suite was not changed.

The required Impeccable detector ran once in degraded regex mode because its HTML
parser modules were absent. It flagged the existing comparison-bar width
transition, which was removed, and SVG `stroke-width`, which is an intentional
wire interaction and does not lay out HTML. The detector did not verify computed
contrast; browser accessibility checks and rendered inspection supply separate
evidence. Lighthouse scores are automated evidence, not a full accessibility
conformance assessment.

## Review and limits

The [UI patch](../artifacts/studio-enhancement/ui-changes.patch) compares the
final UI to copies captured at the start of this task. Studio was already
untracked in the working tree, so an ordinary Git diff alone does not show these
changes. Existing unrelated workspace edits were preserved.

Native harness isolation and the Enterprise runtime integration remain blocked
where the capability registry reports them unavailable. This pass validates
offline behavior and UI recovery; it does not certify live paid provider
execution, every browser, screen-reader behavior, or the absence of all bugs.
Frozen tasks and historical results were not rewritten. Nothing was pushed or
published externally.
