# Part 4: Advanced conditional routing

Branch/PR: `parts/part-4-advanced-routing`, stacked on Part 3 while that PR is open.
Bonus rubric: query analysis (5), callbacks (4), dynamic instruction (3), assembled
orchestrator (3), total 15 bonus points.

## Implementation

`analyze_query_intent()` returns needs_data, needs_support, urgency,
execution_mode, and a diagnostic reason. It uses transparent bounded rules;
uncertain requests retain both specialists. General how-to uses Support only;
pure record requests use Customer Data only; mixed requests run both in order.
Urgency does not authorize writes, refunds, or external escalation.

The router's before-agent callback writes a fresh decision and invocation ID,
and clears the prior data answer. The dynamic instruction reads that state
without attempting to mutate ReadonlyContext. The router LLM produces a brief
task plan; callbacks enforce the computed decision, not free-form model output.

Architecture: Router LLM → conditional sequential executor → Customer Data A2A
and/or Support A2A. A skipped Customer Data stage emits no diagnostic answer. A
skipped Support stage re-emits the current data answer, so the last stage cannot
replace it with "skipped" text. Missing/stale/malformed state runs both stages.
The cached answer is limited to the current invocation.

## Running and testing

```bash
python -m unittest tests.test_routing tests.test_quality tests.test_client_results -v
python -m tests.test_agents
python -m tests.test_a2a
python -m tests.test_mcp_toolset
python tests/manual_part2.py --host-mode advanced
python tests/manual_scenarios.py --host-mode advanced --output docs/scenario_runs/part4.txt
```

The supplied CLI factory still serves basic routing. The test runners explicitly
select the advanced Host, and ADK Web selects it with HOST_AGENT_MODE=advanced.
A basic launcher run is not evidence of testing advanced routing.

The advanced live fixture includes the original seven requests plus Host-only
data and general-support requests and a data-only request while Support is down
(ten requests total). It asserts actual specialist HTTP request counts, context
handoff, database effects, useful final answers, and failed-task propagation when
an unavailable specialist is required. Unit tests exercise multiple turns in one
real ADK session with stubbed remotes/model to detect stale state.

The ten provided scenarios retain the same model, queries, and original sample
data used by Parts 2/3. Instrumentation now separates specialist model requests,
router model requests, total model requests, route decisions, and actual remote
requests. Router overhead is included rather than presenting skipped specialists
as an automatic cost/performance win. Preserve all earlier snapshots.

See part4_test_results.md and the eventual comparison report for evidence,
failures, and limitations. Parallel execution remains Part 5.
