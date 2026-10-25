# Part 2 failures and verification

Development date: 2026-10-25 (Australia/Sydney).
Environment: WSL, Python 3.14, configured `gemini-3.8-flash` model, local MCP SSE
server, and three real A2A JSON-RPC HTTP servers.

Failure reporting follows `development_review_policy.md`. The cases below are
separated into unexpected defects and deliberately injected failures so they can
be used directly in consultation and reflection.

## Unexpected failure 1: unconditional nest_asyncio patch

**Trigger and expectation:** Import the supplied launcher/client and start the
live A2A test in normal CLI execution. HTTPX should retrieve the agent cards.

**Observed failure:** The first attempt failed before a card request completed:
`sniffio.AsyncLibraryNotFoundError: unknown async library, or not in async context`.
The traceback passed through HTTPX/httpcore async synchronization and the
`nest_asyncio`-patched event loop.

**Cause and fix:** Importing `run_agents.py` unconditionally called
`nest_asyncio.apply()`. Under this Python 3.14 environment, patching ordinary CLI
execution interfered with async-library detection. We wrapped the patch in a
running-loop check: `asyncio.get_running_loop()` is attempted, and the patch is
applied only if an event loop is already running. Normal CLI execution keeps
its standard event loop; notebook callers retain the existing nested-loop path.

**Verification:** After this change, HTTP discovery succeeded for all three
agent cards and live JSON-RPC requests executed through Gemini and MCP.

**Limit:** This identifies an event-loop compatibility problem. There is no
observed evidence that an unsecured environment caused it. The notebook path
was not separately exercised, and the exact compatibility behavior may differ
on the assignment's recommended Python 3.11/3.12 environments.

## Unexpected failure 2: partial answer after downstream Support stopped

**Trigger and expectation:** Stop only the Support A2A server, leaving Customer
Data and Host running, then request combined account lookup and login help.
The client must make the unsuccessful end-to-end result visible.

**Observed failure:** The first run returned the Customer Data JSON artifact as
if it were the successful final answer, without delivering Support guidance.
The live test raised `AssertionError: Downstream failure unexpectedly reported
as success`. Earlier artifacts survived even though the downstream step failed.

**First diagnosis and fix:** `A2AClient.send_message()` checked whether a task had
artifacts before checking its final task status. We now return artifact text only when
`task.status.state == TaskState.completed`. An unsuccessful task raises a
`RuntimeError` with its final status and available status message even when
partial artifacts exist. Card-fetch responses also call `raise_for_status()`
before parsing their body.

**Regression checks:** Two controlled client tests verify that a failed task
with a partial artifact raises, and a completed task still returns its answer.
Both passed, but the next live outage rerun still returned a partial answer.
This exposed why the first fix was insufficient: the installed RemoteA2aAgent
emitted an ADK `Event(error_message=...)` instead of raising. The default executor
conversion path allowed the outer task to end as completed despite that event.
The client status check could not detect this falsely completed task.

**Second fix:** `convert_agent_event()` wraps the configured executor event
converter. It raises on a remote error event, letting the executor's existing
exception path publish a failed outer A2A task. Ordinary events still delegate
to the standard converter. The client status guard remains a second layer.
Two additional regression tests cover error-event propagation and normal-event
delegation. All four controlled tests pass. The targeted live rerun warms the
Host/Support connection before stopping Support, reproducing the cached-card
path that exposed the defect. Its final result is recorded below.

**Limit:** This exposes downstream failure accurately; it does not synthesize a
friendly fallback response or restart the unavailable specialist. Partial data
is not returned as a completed support answer.

## Unexpected failure 3: immediate test restart rejected closed sockets

**Trigger and expectation:** Restart the isolated fixture suite immediately
after the previous test's servers shut down.

**Observed failure:** The preflight bind probe raised
`OSError: [Errno 98] Address already in use`. Inspection showed no assignment
server processes or listening sockets remained.

**Diagnosis and fix:** With no listeners left, the behavior was consistent with
recently closed sockets in TIME_WAIT; the exact socket state was not captured.
The probe now sets `SO_REUSEADDR` before binding, as the server does. An active listener
still prevents the probe from binding; the test does not stop existing services.

**Verification:** The restarted full suite and the focused outage rerun both
passed preflight/startup after this change.

## Verification results

- Toolset structure: 4/4 checks passed.
- Agent structure: 14/14 checks passed.
- A2A cards/factory/integration structure: 17/17 checks passed.
- Client/executor error-propagation regression tests: 4/4 passed.
- Six normal live scenarios passed in the full run. Its seventh request exposed
  the downstream-stop defect described above.
- After both error-propagation fixes, a focused live rerun passed a normal Host
  request (including context assertions) and the cached-connection Support-stop
  scenario. It exited successfully and returned an explicit failed-task error:
  `A2A task failed ... support_specialist failed: A2A request failed: HTTP Error
  503: Network communication error: All connection attempts failed`.
- The entire seven-request suite was not repeated after the final converter
  change; its normal delegation path and failure path were exercised by the
  focused two-request rerun, alongside the four regression tests.

The initial live run verified customer lookup, standalone password guidance,
Host data-to-support handoff, missing-identity clarification, exactly one
high-priority ticket creation, and missing-customer handling before exposing
the downstream-stop defect. Test-only request traces showed Support receiving
the original query and Customer Data output. Database assertions confirmed no
ticket creation in lookup/clarification cases and exactly one requested ticket.

## Reproduction and boundaries

```bash
python -m tests.test_mcp_toolset
python -m tests.test_agents
python -m tests.test_a2a
python -m unittest tests.test_client_results -v
python tests/manual_part2.py
# Focused warm-context + downstream-stop reproduction:
python tests/manual_part2.py --outage-only
```

The live suite starts the supplied MCP server on port 18081 and three A2A
servers on 10020, 10021, and 10022 with a temporary synthetic database. It checks
actual HTTP card readiness, inspects test-only model-input traces, and validates
database effects. It terminates only its own processes and removes its fixture
files. It requires a working API key/model and free listening ports.

The suite covers seven live requests, including the deliberately stopped
Support server. Responses are manually assessed for troubleshooting quality;
context delivery and database effects have explicit assertions. The separate
10-scenario `test_scenarios.py` harness was not run as part of this fixture suite.
Advanced/parallel routing remains a later checkpoint. No PR is automatically
merged, and the original GitHub `main` remains the starting point.

## Remaining observations

The configured model produced useful troubleshooting, but wording is not fully
deterministic. One export response used future escalation wording ("will be
escalated") despite no external engineering escalation integration existing.
The actual database/tool traces show ticket creation and lookup only. Treat
escalation suggestions as guidance; this wording remains a prompt-quality
review point rather than an executed external action.
