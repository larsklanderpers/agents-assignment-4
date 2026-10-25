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
without supported evidence. The seven-request rerun produced: "Ticket #2 was created earlier in this workflow;
I reused it without creating a duplicate." SQLite confirmed exactly one created
ticket. The same answer explicitly said ticket creation does not automatically
contact engineering or guarantee a timeframe. This verifies the observed
improvement in that run; instructions alone are not a deterministic guarantee.

## 5. A test-file edit temporarily broke two subprocess checks

While adding the real-listener test, an unrestricted text replacement inserted
`import httpx` into the Python snippets embedded in two subprocess tests, at an
invalid indentation. The application listener tests passed, but those two tests
raised CalledProcessError and the 16-test run failed.

The edit was restricted to the module import section and the snippets restored.
Subprocess checks now include captured stderr in assertion failures so a future
syntax/import failure is visible instead of hidden behind CalledProcessError.
The subsequent complete 16-test rerun passed; results are recorded below. This was a test-edit
failure, not evidence of a new application event-loop defect.

## Results and comparison

- Structural checks: 35/35 passed (4 toolset, 14 agent, 17 A2A).
- Quality/client regression checks: 16/16 passed after correcting the test edit, including actual HTTP listener startup/shutdown and an occupied-port failure.
- Seven-request live suite: 7/7 passed, exit code 0, including explicit failed-task reporting after Support was stopped.
- Provided ten-scenario suite: 10/10 passed, exit code 0. `part3_comparison.md` compares the saved Part 2 and Part 3 transcripts and metrics.

The original Part 2 transcripts remain under `scenario_runs/part2.*`. Part 3
outputs are saved separately as `scenario_runs/part3.*` with the same model,
queries, seed dataset, and basic Host mode. Timing from single runs is not a
benchmark; different wording or call choices alone do not establish a fix.

## Limits

The A2A/ADK experimental and SequentialAgent deprecation warnings remain; the
assignment explicitly requires the sequential class. This checkpoint does not
change dependency versions or implement later routing modes. Notebook behavior
is covered only by the import-guard test, not a full notebook session. The
provided ten-scenario harness remains a broad smoke test, supplemented by
explicit lifecycle, database-effect, context, and failure-injection checks.

## 6. Report generation failed on Windows text encoding

The comparison report included Unicode arrows. An ad hoc Windows Python report
update used Path.write_text without an encoding, selecting the locale's cp1252.
It raised UnicodeEncodeError and had already truncated the working results file.
This was documentation tooling failure, not a model/server failure.

The tracked report was restored from the checkpoint commit, all verification
updates reapplied, and report text written explicitly as UTF-8. Test logs, saved
scenario transcripts, and metrics remained intact and did not need rerunning.
The final report files were decoded as UTF-8 and checked before commit.

## Public API audit

A source audit reviewed 23 public functions in the implemented agent, toolset,
factory, and launcher modules. Every reviewed function has a docstring and
return annotation. AgentServerConfig is a TypedDict tying each ADK BaseAgent
to its AgentCard and listening port. A2A compatibility import ordering and ADK
Web root-agent entry points are preserved.

## Baseline comparison outcome

Both ten-scenario runs used the same configured model, queries, seed data, and
basic Host. Each scenario called both specialists once in both runs. Aggregate
MCP calls were 30 → 29, traced specialist model requests 41 → 40, and summed
scenario durations 297.68 → 287.87 seconds. Single runs do not establish a
performance improvement.

The urgency answer replaced the unsupported specific hold-release estimate with
issuer-dependent timing and distinguished a tracking ticket from an external
refund/contact action. Statistics remained correct (12/6/7, 25 total).

A residual inefficiency remains: the statistics scenario repeated
get_ticket_stats in Part 3 (two calls vs. one in Part 2), with four rather than
three model requests. The final answer was correct, but upstream context reuse
is still nondeterministic. This limitation is recorded rather than masked by
the aggregate call-count decrease or the 10/10 smoke-test result.
