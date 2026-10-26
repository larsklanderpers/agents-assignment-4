# Scenario output comparison across checkpoints

Run the unchanged supplied ten-scenario harness against a fresh copy of its
original 15-customer / 25-ticket sample dataset for each checkpoint:

| Checkpoint | Host mode | Transcript |
| --- | --- | --- |
| Part 2: basic A2A | basic | `part2.txt` |
| Part 3: code quality | basic | `part3.txt` |
| Part 4: advanced routing | advanced | `part4.txt` |
| Part 5: parallel routing | parallel | `part5.txt` |

```bash
python tests/manual_scenarios.py --host-mode basic --output docs/scenario_runs/part2.txt
# At the corresponding later checkpoints:
python tests/manual_scenarios.py --host-mode basic --output docs/scenario_runs/part3.txt
python tests/manual_scenarios.py --host-mode advanced --output docs/scenario_runs/part4.txt
python tests/manual_scenarios.py --host-mode parallel --output docs/scenario_runs/part5.txt
```

Advanced and parallel modes must be implemented before their runs. The wrapper
selects the requested Host entry point rather than silently testing the basic
factory for every checkpoint.

Each run saves complete printed scenario answers plus a `.metrics.json` file.
`model_requests` retains the comparable specialist-model count. Part 4 also
records `router_model_requests`, `total_model_requests`, and `routing_decisions`.
Its original smoke result and added actual-routing contract are reported
separately. The test tracer walks local LLM stages, including the router; add
explicit synthesis counters for Part 5. Part 5 records `summary_model_requests`
and checks one actual request per specialist plus one synthesis request. Controlled
ADK barrier tests separately establish concurrent scheduling.

Transcripts record checkpoint commit, configured model, and Host mode. Use the
same queries, seed data, and model/configuration when comparing. Wording,
timestamps, tool choices, and timing vary; single-run durations are not benchmarks.

Review correctness, missing context, duplicated work, unsupported action claims,
error handling, and whether execution matches the requested routing mode. The
provided harness automatically checks only response length and relevant words.
Its printed expected-capability lists are not assertions. In particular, its
single-agent/parallel labels do not prove conditional or parallel execution.

Keep the seven-request suite as a separate regression check: it explicitly
checks context handoff, database effects, and a stopped downstream service,
which the ten-scenario harness does not cover.

Part 2 versus Part 3 observations and residual issues: `../part3_comparison.md`.

Parts 2/3/4 comparison, including router overhead: `../part4_comparison.md`.

Parts 2–5 comparison and parallel limitations: `../part5_comparison.md`.
Dedicated Part 5 live answers and expected outage: `part5-live.json`.

Part 5 preserves the first ten-scenario attempt as `part5-initial.*`, because
manual review found unsupported offers, reset timing, and a status-label error
despite passing smoke/execution assertions. `part5-live-initial.json` captures
the first dedicated run, and `part5-live-intermediate.json` records the later
partial run interrupted after a stalled provider response. Final results use
`part5.txt`, `part5.metrics.json`, and `part5-live.json`.
The live wrappers now have whole-request deadlines in addition to transport idle
timeouts (180 seconds dedicated fixture, 240 seconds per supplied scenario).

Additional Part 5 failure evidence: `part5-outage-timeout.txt` preserves the live
parallel error-event hang; `part5-fixture-assertion.txt` preserves the valid answer
rejected by an overly literal name assertion. The final live suite passed after
the worker error wrapper and fixture correction. See the failure chronology.
