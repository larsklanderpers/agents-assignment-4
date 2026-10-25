# Parallel outage timeout follow-up

Date: 26 October 2026 (Australia/Sydney). Branch: `fixes/parallel-outage-timeout`.
Based on `fixes/customer-data-response-schema` (PR #6), preserving all five checkpoint histories. Implementation: `0a90ef4`.

## Failure evidence and limits of the diagnosis

The previous follow-up preserved a real 180-second client timeout after Support stopped, under both Python 3.14 and the required Python 3.11. Customer Data completed, but the Host did not deliver a terminal failure. These remain in `scenario_runs/schema-parallel-py311-timeout.txt` and the corresponding Python 3.14/cleanup-attempt logs. Changing Python versions alone did not fix it.

Two diagnostic Python 3.11 runs of the unchanged implementation completed successfully this time (`parallel-outage-fix-before-pass-1.txt` and `before-pass-2.txt`). The original hang is intermittent; this session did not reproduce the same 180-second stall. We should not describe every old request as failing, or claim task traces conclusively isolated every cause of the historical stall.

A stronger deterministic regression did expose the unsafe failure boundary. Using the real ADK Runner, RemoteA2aAgent lifecycle and ParallelAgent merger, a mocked remote yields partial content, an error, and cleanup events while its healthy sibling is still working. Substituting the old raise-inside-worker method fails for either specialist: both streams are aborted before normal completion (`parallel-outage-fix-old-boundary.txt`). The earlier single-error-event unit test checked the exception alone and missed this cleanup/cancellation behavior.

The earlier PR #6 attempt drained remote cleanup but still raised inside the parallel worker; it did not eliminate the live timeout. This fix moves the exception outside the parallel merger altogether.

## Change

Each worker drains its SDK stream, suppresses error and post-error output, and records its failure in invocation state. The per-worker completion callback records missing final output through the same mechanism. The ParallelAgent's completion callback raises only after both worker lifecycles and the merger have finished. The existing A2A executor then publishes a failed task and the client rejects any partial artifacts. Synthesis never runs after a recorded worker failure. Preparation clears both outputs and errors on every invocation; a failed turn cannot poison a later successful one.

The workers still run concurrently. A healthy sibling is allowed to finish; no automatic retry or duplicate-write attempt is introduced. Cancellation remains cancellation rather than being converted into a remote error.

## Additional failures during verification

1. The first HTTP regression tried to assign `worker.agent_card` after construction. In this ADK version it is a constructor argument, not a mutable Pydantic field; four subcases failed with `ValueError`. The fixture now supplies endpoint URLs before construction. This was a test defect, not an application outage (`parallel-outage-fix-fixture-configuration-failure.txt`).
2. A later combined regression run failed one HTTP subcase with an incomplete chunked response; Uvicorn logged “ASGI callable returned without completing response.” The fixture ran three servers in one loop. SSE's automatic graceful-drain watcher follows a process-wide Uvicorn shutdown signal, so stopping one fixture could drain the unrelated Host stream. The test now scopes automatic drain off while its shared-loop servers run and restores the flag afterward; its own shutdown still closes all servers. Production code is unchanged for this fixture issue. The failed run is retained in `parallel-outage-fix-http-fixture-failure.txt`.

## Verification under Python 3.11.17

ADK 2.12.0; a2a-sdk 0.3.26; MCP 1.30.0; Pydantic 2.14.1; sse-starlette 3.5.0.

- 40 regression methods passed, including concurrency, schema, routing, quality, client status, cleanup, cancellation and error-state recovery. The HTTP method covers four real-network subcases: either specialist stopped, before and after warming/caching its card. Each must return a failed task within a five-second outer test deadline, with no synthesis and with the healthy peer finishing.
- All 35 supplied structural checks passed: agents 14/14, A2A 17/17, MCP 4/4. These are structural checks, not substitutes for live tests.
- The full live parallel suite passed all seven requests: six normal cases plus stopped Support. It checked schema parsing, original request/context, useful synthesis, missing identity/record, and exactly one requested high-priority ticket. The outage returned `A2A task failed: support_specialist failed: ... All connection attempts failed`, rather than a successful partial answer or the 180-second test timeout. Transcript: `parallel-outage-fix-a2a.txt`. A further healthy-context/outage repeat returned the failed task in **15.1 seconds** and explicitly asserted no summary model ran after the outage (`parallel-outage-fix-outage-repeat.txt`).

Commands (from the repository, with the Python 3.11 environment activated):

```sh
python -m unittest tests.test_response_schema tests.test_parallel tests.test_parallel_http tests.test_routing tests.test_quality tests.test_client_results -v
python tests/test_agents.py
python tests/test_a2a.py
python tests/test_mcp_toolset.py
python tests/manual_part2.py --host-mode parallel
python tests/manual_part2.py --host-mode parallel --outage-only
python tests/manual_scenarios.py --host-mode parallel --output docs/scenario_runs/parallel-outage-fix.txt
```

## Ten-scenario comparison

The unchanged ten queries used a fresh copy of the original 15-customer/25-ticket fixture. The new parallel run passed all ten smoke checks and all ten execution contracts (one request to each specialist and one summary per scenario). Its transcript records the starting HEAD and the actual implementation provenance, `0a90ef4`; the code was tested from the working tree before that commit was made.

| Snapshot | Host mode | Passed | Specialist HTTP | Total model requests | MCP calls | Summed seconds |
| --- | --- | --- | --- | --- | --- | --- |
| Part 2 | basic sequential | 10/10 | 20 | 41 | 30 | 297.68 |
| Part 3 | basic sequential | 10/10 | 20 | 40 | 29 | 287.87 |
| Part 4 | advanced | 10/10 | 17 | 43 | 23 | 277.92 |
| Part 5 | parallel | 10/10 | 20 | 56 | 39 | 222.80 |
| PR #6 schema follow-up | advanced | 10/10 | 17 | 46 | 26 | 353.33 |
| This fix, with schema | parallel | 10/10 | 20 | 57 | 41 | 269.58 |

The new run made 47 specialist model requests plus 10 summaries. Both workers still receive every query, including pure data queries; there is no adaptive routing saving in parallel mode. Compared with Part 5, this run made one extra model request and two extra MCP calls, and took longer in aggregate. Those snapshots also differ in schema enforcement, runtime and nondeterministic model execution, so the difference cannot be attributed to this failure-handling change. Part 4 and the schema follow-up selected fewer specialists for pure data queries. Output wording/tool selection varied while the smoke and execution contracts remained satisfied. This is a reliability follow-up, not evidence of better answer quality or performance. All earlier transcripts remain unchanged.

## Remaining issues

This is a graceful failure after both workers settle, not fail-fast cancellation or a transaction. Database work can already be committed when a sibling fails; inspect records before retrying a write. The other worker's network/model timeout can still delay the final failure. The five-second deterministic HTTP deadline and 180-second live harness deadline are test safeguards; they do not establish a universal production request deadline.

The original intermittent 180-second stall was not reproduced in the two pre-change diagnostic runs. The deterministic old/new cleanup regression and post-change live results support the changed boundary, but do not prove all possible SDK/transport cancellation failures have been eliminated. ADK's A2A integration remains experimental; its current version also deprecates ParallelAgent/SequentialAgent in favor of Workflow. Migration is separate work.

Scenario smoke checks measure response length and keywords, plus observed parallel execution; they do not prove every answer is factually correct. Model choices/tool calls and timings vary, and each historical snapshot is a single run. No latency or cost improvement should be inferred from this reliability fix alone.
