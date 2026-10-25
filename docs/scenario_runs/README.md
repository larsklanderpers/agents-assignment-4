# Scenario output comparison across checkpoints

Run the unchanged supplied ten-scenario harness against a fresh copy of its
original 15-customer / 25-ticket sample dataset for each checkpoint:

| Checkpoint | Host mode | Transcript |
| --- | --- | --- |
| Part 2: basic A2A | basic | `part2.txt` |
| Part 3: code quality | basic | `part3.txt` |
| Part 4: advanced routing | advanced | `part4.txt` (planned) |
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

Each run saves complete printed scenario answers plus a `.metrics.json` file
with per-scenario duration, MCP tool names, specialist request counts, and specialist model
request counts. The current model-input trace covers the two specialists; add
Host classifier/synthesis tracing when those later modes are implemented. The transcript records the checkpoint commit and configured
model. Use the same model/configuration when comparing; timestamps and model
wording naturally vary. Single-run durations are observations, not performance
benchmarks or proof of concurrent execution.

Review correctness, missing context, duplicated work, unsupported action claims,
error handling, and whether execution matches the requested routing mode. The
provided harness automatically checks only response length and relevant words.
Its printed expected-capability lists are not assertions. In particular, its
single-agent/parallel labels do not prove conditional or parallel execution.

Keep the seven-request suite as a separate regression check: it explicitly
checks context handoff, database effects, and a stopped downstream service,
which the ten-scenario harness does not cover.

Part 2 versus Part 3 observations and residual issues: `../part3_comparison.md`.
