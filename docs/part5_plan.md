# Part 5: parallel execution checkpoint

Branch/PR: parts/part-5-parallel-execution, stacked on Part 4.

Rubric: remote outputs stored with after-agent callbacks (3), ParallelAgent (2),
dynamic summary instruction reading state (3), full sequential orchestrator (2).

Architecture: parallel Customer Data and Support remote workers, then tool-free
Gemini synthesis with include_contents='none'. Both workers receive the original
request independently. Support does not wait for Customer Data. In parallel mode
its toolset excludes all writes; Customer Data owns requested changes. This mode
also makes a directly served Support agent read-only. Basic/advanced retain their
existing toolsets. All servers must use the same HOST_AGENT_MODE configuration.

Clear outputs per invocation and capture only matching worker/current invocation
final text. Synthesis requires both outputs and prioritizes Customer Data for
record facts and actions while preserving Support guidance and uncertainty.

Validation: actual ADK barrier proves concurrent start; repeated turns, readonly
instruction, stale/missing output, worker failure, and tool filters are checked.
Then run inherited regressions/structural checks, real MCP/A2A fixture with one
requested write and outage, and unchanged ten scenarios on original sample data.
Compare Parts 2–5 calls, model overhead, MCP duplication, output, and durations.
Document observed failures separately from preventive checks and expected injected
failures. Preserve earlier snapshots and do not infer cost/speed guarantees.
