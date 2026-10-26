# Part 2: Multi-agent A2A checkpoint

Branch and PR: `parts/part-2-multi-agent-a2a-system`.
This checkpoint builds on Part 1. Its PR targets the Part 1 branch while that PR
remains open, so reviewers see only Part 2 changes. Neither PR is merged here.

## Scope

1. **Support Agent:** configured Gemini model, existing support-safe MCP toolset,
   and the approved instruction covering login, password resets, billing,
   performance, feature requests, exports, ticket handling, and failures.
2. **Host:** a basic `SequentialAgent` runs Customer Data and then Support using
   two `RemoteA2aAgent` instances and well-known discovery URLs.
3. **Discovery cards:** all three agents advertise version, capabilities, input
   and output modes, JSON-RPC transport, skills, examples, and configured URLs.
4. **Integration:** `create_all_agents()` supplies agents, cards, and ports to the
   existing A2A server launcher. The compatibility import remains before remote
   agent imports.

## Verification

```bash
python -m tests.test_mcp_toolset
python -m tests.test_agents
python -m tests.test_a2a
python tests/manual_part2.py
# Focused downstream-stop regression:
python tests/manual_part2.py --outage-only
# Provided ten-scenario baseline on fresh original sample data:
python tests/manual_scenarios.py --host-mode basic --output docs/scenario_runs/part2.txt
```

The opt-in live script starts the supplied MCP server and three real HTTP A2A
servers with a temporary synthetic database. It uses port 18081 for MCP and the
assignment ports 10020, 10021, and 10022; these must be free. It reads the model
and API key from the local environment / `.env`.

Test-only model-input tracing verifies that Support receives the original
request and Customer Data output. Database assertions check that lookup requests
do not create tickets and that the requested ticket is created exactly once.
All temporary server processes and fixture files are cleaned up afterward.
See `part2_test_results.md` for observed results, failure analysis, and remaining
limitations. `development_review_policy.md` defines the failure-first convention
for this and future checkpoint PRs.

## Runtime compatibility

The initial live attempt exposed `sniffio.AsyncLibraryNotFoundError` under
Python 3.14 because importing `run_agents.py` unconditionally applied
`nest_asyncio`. The launcher now applies that patch only when imported inside an
already-running event loop. Plain CLI execution retains the normal event loop.

## Later checkpoints

Dynamic routing, parallel execution/synthesis, and a broader code-quality review
remain outside Part 2. The basic Host always calls both specialists in order.
The existing launcher's fixed-delay readiness message is unchanged; the live
verification script checks actual HTTP card readiness instead.
