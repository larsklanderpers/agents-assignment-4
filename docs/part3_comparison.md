# Part 2 → Part 3 scenario comparison

Both runs use `gemini-3.8-flash`, the unchanged ten provided queries, a freshly
seeded 15-customer/25-ticket database, and the basic sequential Host.
Part 2 transcript: `scenario_runs/part2.txt`; Part 3: `scenario_runs/part3.txt`.
The matching `.metrics.json` files preserve the measured execution counters.

## Per-scenario observations

| Scenario | MCP calls P2 → P3 | Traced model requests P2 → P3 | Seconds P2 → P3 |
| --- | ---: | ---: | ---: |
| Simple Query - Single Agent | 2 → 2 | 3 → 3 | 38.28 → 46.30 |
| Task Allocation - Customer Tier Recognition | 4 → 2 | 4 → 3 | 22.86 → 23.01 |
| Coordinated Query - Multi-Agent Collaboration | 2 → 2 | 3 → 3 | 20.02 → 18.90 |
| Multi-Step Coordination - Complex Data Query | 1 → 2 | 3 → 4 | 17.13 → 22.42 |
| Negotiation/Escalation - Multiple Intents | 3 → 3 | 4 → 4 | 31.18 → 28.36 |
| Urgency Detection - Immediate Escalation | 4 → 5 | 5 → 5 | 31.36 → 41.01 |
| Multi-Intent - Parallel Task Execution | 2 → 2 | 3 → 3 | 63.13 → 27.56 |
| Cross-Agent Dependency - Context Passing | 4 → 2 | 4 → 3 | 23.35 → 22.10 |
| Data Aggregation - Statistical Analysis | 1 → 2 | 3 → 4 | 11.33 → 15.13 |
| Customer Search - Ticket Resolution Flow | 7 → 7 | 9 → 8 | 39.04 → 43.08 |

Both harness runs report 10/10. Each scenario invoked Customer Data once and
Support once in both runs: no routing architecture changed.

| Total observed | Part 2 | Part 3 |
| --- | ---: | ---: |
| MCP calls | 30 | 29 |
| Traced specialist model requests | 41 | 40 |
| Sum of scenario durations (seconds) | 297.68 | 287.87 |

These are single-run observations, not benchmark evidence or proof that code
quality caused a speed/call-count improvement. Provider latency and model tool
choices vary. Counters cover the two specialists; no Host LLM exists in basic mode.

## Answer quality and remaining failures

- **Unsupported timing:** Part 2 urgency guidance gave a specific "1–3 business
  days" estimate unsupported by tools or the supplied knowledge base. Part 3
  instead says exact timing depends on the issuer/financial institution.
- **External action promises:** Part 3 explicitly says refunds/account actions
  cannot be completed or scheduled through these tools and asks permission to
  create a tracking ticket. A ticket is not a contacted engineering/billing team.
- **Action attribution (separate seven-request fixture):** Part 2 said no new
  ticket was created after the upstream agent created one. Part 3 says "Ticket
  #2 was created earlier in this workflow; I reused it without creating a
  duplicate." SQLite confirms exactly one creation. This write case is covered
  by the seven-request suite, not by the read-only ten-scenario baseline.
- **Correctness retained:** Both statistics answers reported 12 open, 6
  in-progress, and 7 resolved tickets (25 total), matching the fixture.
- **Residual redundant read:** Part 3 called `get_ticket_stats` twice in the
  statistics scenario, versus once in Part 2, despite receiving upstream context.
  That scenario also used four model requests instead of three. The final
  answer was correct, but the reuse instruction does not deterministically
  prevent duplicated reads. This remains a routing/context-efficiency review
  point, not a failure hidden by the aggregate one-call reduction.
- **Test coverage limit:** The ten-scenario harness still checks only response
  length and keywords. Its expected-capability lists and single-agent/parallel
  labels are not assertions. Passing it is not proof of every intended behavior.

All observed MCP calls in both ten-scenario runs were reads. The seven-request
suite separately verifies writes, context delivery, and downstream failure.
The improved wording is evidence from these runs, not a guarantee of future
model outputs. No new routing mode or dependency upgrade is included.
