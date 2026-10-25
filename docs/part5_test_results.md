# Part 5: failures, verification, and remaining issues

Date: 2026-10-25. WSL Python 3.14, configured Gemini model unchanged.

## Observed failures versus injected failures

The first parallel concurrency/regression run passed all 27 tests, and the first
dedicated live fixture passed. However, manual review of the first ten-scenario
attempt found an unsupported external-action offer in the cancellation response:
"we can assist in forwarding your request to the billing department." No tool
can forward requests. It also referred to an unverified account billing portal.
The same attempt also invented a "typically 15–60 minutes" reset-link expiry in
the search answer and described one open plus one in-progress ticket as "two open
tickets" in the cross-agent dependency answer. The search answer suggested
unverified administrator reset capabilities. All smoke/execution assertions passed: this demonstrates their
semantic coverage gap, not permission to call the answer fully correct.

The initial summary instruction prohibited claims of unperformed actions but did
not explicitly prohibit offers or promises. Support's stronger existing guidance
did not reliably carry through synthesis. The correction explicitly prohibits
forwarding/contact/cancellation/refund offers and invented product navigation or
timeframes (including reset-link expiry), unverified administrator capabilities,
and conflating in-progress with open statuses. The first attempt is preserved as part5-initial.*, followed by a full
final live fixture and ten-scenario rerun. Final answer review is recorded in the
comparison. Instruction changes are probabilistic mitigation, not enforcement of
all possible wording; no broad semantic validator is claimed.

An intermediate live rerun also said "active and not locked". The fixture has an
active/disabled account status but no lockout field, so this was an unsupported
inference. A further summary instruction explicitly distinguishes active status
from unknown lockout state and prohibits inference of unexposed diagnostic fields.
Intermediate evidence is retained as part5-live-intermediate.json. The final
full live and ten-scenario runs use all of these instruction corrections.

## Stalled intermediate provider call and missing total deadline

During the intermediate live rerun, Customer Data sent its second Gemini request
for the missing customer at 18:49:38 and no response was logged after more than
four minutes. Support had finished at 18:49:47. This locates the wait in the
provider/model path; the underlying cause was not established. The Host correctly
did not synthesize from Support alone, but the run had to be interrupted.

The client configures HTTP read-idle timeouts rather than an overall workflow
deadline. Stream activity can extend waiting; the idle timeout did not bound this
whole case. The owned fixture was interrupted and cleaned up, then test-only
asyncio.wait_for deadlines were added (180 seconds per dedicated live request,
240 per supplied scenario). No blind retry inside a request was added, because
writes may already have occurred. Final runs start fresh fixtures. Production
end-to-end deadline/cancellation/retry semantics remain an explicit limitation;
this checkpoint does not claim to have solved provider reliability.

The concurrency test deliberately fails Support after both workers start. The
RuntimeError propagates and the summary does not run. The live fixture deliberately
stops the Support server; the Host reports an A2A failed task with HTTP 503/network
communication failure. Customer Data may already have emitted a partial answer,
but the client does not treat it as successful completion. These are expected
injected failures that verify inherited error propagation, not surprise defects.

## Live remote error event exposed a parallel cancellation failure

A later full live run passed all six normal requests, but the stopped-Support
case did not deliver a terminal failed task. The Host logged Support's HTTP 503
at 18:58:21, followed by an ADK "Agent run cancelled" message, while the client
waited until the new 180-second overall deadline raised TimeoutError. Evidence
is preserved as scenario_runs/part5-outage-timeout.txt. The initial fixture had
passed this outage, so a single success had not established reliable behavior.

The inherited outer event converter raises on error_message events. With
ParallelAgent, this can interrupt the merged event generator while sibling
workers are suspended. Inspection of the installed ADK merger showed its event
resume signals and task-group cleanup; raising inside a worker is the supported
error path exercised by our deterministic test. The correction is a small
ParallelRemoteA2aAgent subclass that raises remote error events inside the worker
before yielding them to the outer converter. It preserves normal events and
retains the shared outer converter for the other modes. No installed SDK files
were changed. A new regression covers the actual error-event shape; 28 tests
pass. The final full live run passed all seven requests on this correction, including
a terminal RuntimeError failed-task result for stopped Support. The 180-second
deadline was not needed. This verifies the correction live, not from the stub
test alone. It does not guarantee cancellation behavior for every SDK/provider
failure shape.

## A brittle fixture assertion rejected a valid contextual answer

The next live attempt stopped at host_context because the fixture required the
literal customer name "A2A Fixture Five" in the final answer. The answer correctly
included the fixture's email, active status with unknown lockout state, ticket #1,
and exact issue text; the user had requested tickets and login help, not a name
restatement. This was a test expectation defect rather than lost context. The
assertion now checks the requested ticket issue and account email in the final
answer, separately from the exact ticket evidence reaching synthesis. Evidence
is retained in scenario_runs/part5-fixture-assertion.txt. The full suite is rerun;
this aborted attempt did not verify the outage correction.

## Preventive changes and evidence

Parallel Support cannot receive Customer Data's preceding output. Keeping both
agents able to write would permit duplicate ticket creation. Parallel mode removes
Support's create/status/priority tools and adds explicit guidance-only instructions;
Customer Data owns requested writes. The tool-filter regression proves the tools
are absent and that basic mode still has them. The live fixture verifies exactly
one requested high-priority ticket for customer 6 and a summary reporting ticket #2.
This mode-specific restriction also applies to a direct Support endpoint configured
in parallel mode; configure every server consistently.

Outputs are reset before worker execution and captured by matching worker name and
invocation ID. The summary reads both outputs from readonly state, with no conversation
history or tools. Missing/stale results raise instead of reusing earlier answers.
The real ADK test performs two turns in one session, then a worker failure. A shared
barrier requires both workers to start before either finishes; a sequential workflow
would time out. This proves concurrent scheduling without inferring it from timing.

## Verification

- 28/28 parallel, routing, quality, and client unit/regression tests passed.
- 35/35 supplied structural checks passed (14 agent, 17 A2A, 4 MCP).
- Dedicated live MCP/A2A fixture: 7/7 requests passed, exit 0. Six normal requests
  include direct lookup, direct general support, combined Host context, missing
  identity, one requested write, and absent customer. The seventh is the stopped
  Support request with expected explicit failure. Every successful Host case
  asserts one remote request per specialist and one synthesis model request.
- Captured live answers and expected outage error: scenario_runs/part5-live.json.
- Final same ten scenarios: 10/10 smoke and 10/10 execution contracts passed,
  exit 0, on commit b741f8b. Totals: 20 specialist HTTP calls, 46 specialist model
  requests plus 10 summary requests (56 total), 39 read-only MCP calls, 222.80
  summed seconds. Measurements and manual answer review: part5_comparison.md.
- Final semantic review still finds unsupported "for your account" wording in a
  global search without requester identity. This remains documented; automated
  passes are not a claim of complete factual correctness.

## Remaining risks

Both workers receive the original request independently; Support may repeat reads,
see a record before Customer Data changes it, or give advice that must be reconciled.
The summary prioritizes Customer Data for records/actions, but reconciliation and
wording remain model behavior, not a formal consistency guarantee. No transaction
spans the workflow. A failure after a write does not roll it back; retrying a request
is not guaranteed idempotent. Cancelling a local branch does not guarantee that
an already-started remote model/tool operation stops. The one-write fixture is
evidence for that case only.

The summary adds model work and cannot recover a failed worker. There is no automatic
fallback to sequential routing. Parallel mode always runs both workers, including
pure record queries; Part 4 remains available as a separate conditional mode.
No promise of lower cost or latency is made. Model requests are not token/cost data.
The supplied smoke tests are weak, supplemented with actual execution assertions;
answer review cannot guarantee every future model response.

The ADK emits experimental A2A and deprecated workflow-class warnings. No dependency
migration or compatibility-patch removal is included in this checkpoint.
