# Part 3 failures and verification

Date: 2026-10-25 (Australia/Sydney). Environment: WSL, Python 3.14, configured
`gemini-3.8-flash`; basic sequential Host retained for comparison with Part 2.

## 1. Startup could claim success after a factory/server failure

The original startup trace showed a dead server thread followed by "Servers
are running". Part 2 intentionally left that launcher defect unchanged: it used
fixed sleeps and did not propagate the background thread's exception.

Part 3 replaces CLI daemon-thread startup with an async supervisor. Readiness
is reported only after every Uvicorn server reports that it has started and no
server task has already exited. Factory errors, bind failures, startup deadline
expiry, and runtime exceptions propagate to the CLI. Every exit requests
shutdown of the servers owned by that invocation. Test mode waits for readiness
and returns a nonzero exit code if any request fails.

Verification includes controlled delayed/timeout/failure paths, an actual
occupied Uvicorn port, and real supervised A2A listeners whose discovery cards
were fetched before clean shutdown. The factory-failure CLI test returns 1 and
asserts that no readiness message was emitted.

## 2. Empty output could be mistaken for a successful answer

Code review found that an empty A2A stream returned the literal string
`No response received`. A completed task with empty text could also return an
empty string, and only the first artifact was considered. These were audited
edge paths, not failures seen in the earlier successful model conversations.

`extract_response_text()` now accepts a direct Message or completed task,
returns text across all artifacts, and raises on failed, unsupported, or empty
responses. The Part 2 event-converter and failed-task guard remain in place.
Regression tests exercise empty streams/tasks, direct messages, multiple
artifacts, and failed tasks carrying partial artifacts.

## 3. Logs attributed unrelated activity to Customer Data

Part 2 output showed Host, Support, and HTTP client activity with the fixed
`[CUSTOMER_DATA_AGENT]` label. Agent modules called root `basicConfig` during
import, so the first imported module won before the CLI's configuration ran.

Agent modules no longer configure root logging. `configure_logging()` belongs
to the entry point and uses the actual logger name. Live-fixture server entry
points opt in explicitly, preserving the scenario instrumentation. A subprocess
regression verifies that importing the application leaves root handlers intact;
real listener logs now identify `run_agents` and `httpx` separately.

## 4. Answers misrepresented actions and unverified policies

Part 2 observations included Support saying no ticket was created even though
Customer Data had just created it, future engineering-escalation promises with
no contact tool, and an unsupported "1–3 business days" hold-release estimate.
Passing database checks and the ten-scenario keyword checks did not detect these
prose issues.

Both instructions now distinguish records that existed before the request from
actions completed earlier in the current workflow. Support is explicitly told
to report the upstream ticket creation while avoiding a duplicate. It must not
promise team contact, refunds, cancellations, or specific provider timeframes
without supported evidence. The forthcoming live output comparison checks
whether the observed wording improves; instructions alone are not a guarantee.

## 5. A test-file edit temporarily broke two subprocess checks

While adding the real-listener test, an unrestricted text replacement inserted
`import httpx` into the Python snippets embedded in two subprocess tests, at an
invalid indentation. The application listener tests passed, but those two tests
raised CalledProcessError and the 16-test run failed.

The edit was restricted to the module import section and the snippets restored.
Subprocess checks now include captured stderr in assertion failures so a future
syntax/import failure is visible instead of hidden behind CalledProcessError.
The complete regression rerun result is recorded below. This was a test-edit
failure, not evidence of a new application event-loop defect.

## Results and comparison

- Structural checks: pending final capture.
- Quality/client regression checks: pending final capture.
- Seven-request live suite: pending.
- Provided ten-scenario suite and Part 2 comparison: pending.

The original Part 2 transcripts remain under `scenario_runs/part2.*`. Part 3
outputs will be saved separately as `scenario_runs/part3.*` with the same model,
queries, seed dataset, and basic Host mode. Timing from single runs is not a
benchmark; different wording or call choices alone do not establish a fix.

## Limits

The A2A/ADK experimental and SequentialAgent deprecation warnings remain; the
assignment explicitly requires the sequential class. This checkpoint does not
change dependency versions or implement later routing modes. Notebook behavior
is covered only by the import-guard test, not a full notebook session. The
provided ten-scenario harness remains a broad smoke test, supplemented by
explicit lifecycle, database-effect, context, and failure-injection checks.
