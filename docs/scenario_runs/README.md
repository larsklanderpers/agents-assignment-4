# Scenario output comparison across checkpoints

Run the unchanged supplied ten-scenario harness against a fresh copy of its
original 15-customer / 25-ticket sample dataset for each checkpoint:

| Checkpoint | Host mode | Transcript |
| --- | --- | --- |
| Part 2: basic A2A | basic | `part2.txt` |
| Part 3: code quality | basic | `part3.txt` |
| Part 4: advanced routing | advanced | `part4.txt` |
| Part 5: parallel routing | parallel | `part5.txt` (planned) |

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
explicit synthesis counters when Part 5 is implemented.

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
