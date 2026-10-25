# Parts 2, 3, and 4: the same ten scenarios

The configured gemini-3.8-flash model, ten provided queries, and freshly seeded
15-customer/25-ticket database are unchanged. Parts 2/3 use the basic Host;
Part 4 uses the advanced conditional Host. Earlier snapshots are preserved.

## Observed totals

| Measure | Part 2 | Part 3 | Part 4 |
| --- | ---: | ---: | ---: |
| Original smoke checks | 10/10 | 10/10 | 10/10 |
| Specialist A2A requests | 20 | 20 | 17 |
| Specialist model requests | 41 | 40 | 33 |
| Router model requests | 0 | 0 | 10 |
| Total traced model requests | 41 | 40 | 43 |
| MCP calls | 30 | 29 | 23 |
| Summed scenario seconds | 297.68 | 287.87 | 277.92 |

Part 4 also passed 10/10 explicit routing contracts: expected actual specialist
HTTP call counts, one current route decision, and one router model request per
query. These execution checks supplement the original length/keyword checks.

## Per-scenario execution

Counts separated by slashes are Part 2 / Part 3 / Part 4. Model counts include
router overhead in Part 4; the basic Hosts have no router LLM.

| Scenario | Part 4 route | Specialist HTTP | Total model requests | MCP calls |
| --- | --- | ---: | ---: | ---: |
| Simple Query - Single Agent | data_only | 2 / 2 / 1 | 3 / 3 / 3 | 2 / 2 / 2 |
| Task Allocation - Customer Tier Recognition | sequential | 2 / 2 / 2 | 4 / 3 / 4 | 4 / 2 / 2 |
| Coordinated Query - Multi-Agent Collaboration | sequential | 2 / 2 / 2 | 3 / 3 / 4 | 2 / 2 / 2 |
| Multi-Step Coordination - Complex Data Query | data_only | 2 / 2 / 1 | 3 / 4 / 3 | 1 / 2 / 1 |
| Negotiation/Escalation - Multiple Intents | sequential | 2 / 2 / 2 | 4 / 4 / 4 | 3 / 3 / 2 |
| Urgency Detection - Immediate Escalation | sequential | 2 / 2 / 2 | 5 / 5 / 5 | 4 / 5 / 3 |
| Multi-Intent - Parallel Task Execution | sequential | 2 / 2 / 2 | 3 / 3 / 4 | 2 / 2 / 2 |
| Cross-Agent Dependency - Context Passing | sequential | 2 / 2 / 2 | 4 / 3 / 4 | 4 / 2 / 2 |
| Data Aggregation - Statistical Analysis | data_only | 2 / 2 / 1 | 3 / 4 / 3 | 1 / 2 / 1 |
| Customer Search - Ticket Resolution Flow | sequential | 2 / 2 / 2 | 9 / 8 / 9 | 7 / 7 / 6 |

## Useful differences and remaining issues

- The simple customer lookup, complex record lookup, and statistics query now
  skip Support. The other seven scenarios require both specialists and retain
  data → guidance order. The scenario labelled parallel still runs sequentially;
  parallel execution is Part 5, not an inference from that scenario name.
- Pure-data results are now the Customer Data JSON-style answer, rather than a
  Support restatement. The answer survives the skip callback and contains no
  ROUTING_PLAN marker. Presentation therefore varies between data-only and
  guidance routes; JSON fences/field names remain model-generated, not a strict
  schema guarantee.
- Statistics remain correct: 12 open, 6 in-progress, and 7 resolved tickets,
  total 25. Part 3 repeated get_ticket_stats twice; Part 4 makes one call because
  Support is skipped. This removes that observed duplicate in this run, not all
  possible duplication on combined routes.
- The ten scenarios do not exercise a pure general-support-only Host request.
  The separate advanced fixture verifies that missing path with zero Customer
  Data HTTP calls, as well as mixed context handoff and one requested write.
- The dedicated outage checks show that data-only still succeeds with Support
  stopped, while a combined request fails explicitly. No partial-answer success
  regression or routing-diagnostic replacement was observed.
- Specialist calls decrease, but the planner adds ten paid model requests:
  total model requests are 43, compared with 41/40 previously. Token usage and
  billed cost were not measured. Fewer remote agents is not proof of lower cost.
- Summed duration decreased in this single run, despite extra model requests.
  Provider latency/tool choices vary; these are observations, not a benchmark
  or evidence that the routing change caused a speed improvement.
- Control uses bounded rules. The planning LLM does not override decisions.
  Complex paraphrases/negation can still over-route or misclassify. The first
  false-positive rule and Pydantic test-counter failure are documented in
  part4_test_results.md, including their corrections and reruns.

Full transcripts and per-scenario measurements are in scenario_runs/part2.*,
scenario_runs/part3.*, and scenario_runs/part4.*. No earlier output was replaced.
