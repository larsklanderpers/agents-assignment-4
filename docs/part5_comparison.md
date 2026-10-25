# Parts 2–5: the same ten scenarios

The unchanged ten queries use a fresh original 15-customer/25-ticket fixture and
the same configured Gemini model. Parts 2/3 use basic sequential routing, Part 4
conditional sequential routing, and Part 5 parallel workers followed by synthesis.

## Measured totals

| Measure | Part 2 | Part 3 | Part 4 | Part 5 |
| --- | ---: | ---: | ---: | ---: |
| Smoke checks | 10/10 | 10/10 | 10/10 | 10/10 |
| Specialist A2A requests | 20 | 20 | 17 | 20 |
| Specialist model requests | 41 | 40 | 33 | 46 |
| Router model requests | 0 | 0 | 10 | 0 |
| Summary model requests | 0 | 0 | 0 | 10 |
| Total traced model requests | 41 | 40 | 43 | 56 |
| MCP calls | 30 | 29 | 23 | 39 |
| Summed scenario seconds | 297.68 | 287.87 | 277.92 | 222.8 |

Part 5 also checks one actual remote request per specialist and one summary
model request in each scenario. A separate actual-ADK barrier test proves concurrent
scheduling; HTTP counts and shorter duration alone do not prove concurrency.

## Per-scenario counts

Slash-separated counts are Parts 2 / 3 / 4 / 5. Total model counts include local
router or summary overhead where present.

| Scenario | Specialist HTTP | Total model requests | MCP calls |
| --- | ---: | ---: | ---: |
| Simple Query - Single Agent | 2 / 2 / 1 / 2 | 3 / 3 / 3 / 5 | 2 / 2 / 2 / 3 |
| Task Allocation - Customer Tier Recognition | 2 / 2 / 2 / 2 | 4 / 3 / 4 / 5 | 4 / 2 / 2 / 4 |
| Coordinated Query - Multi-Agent Collaboration | 2 / 2 / 2 / 2 | 3 / 3 / 4 / 5 | 2 / 2 / 2 / 4 |
| Multi-Step Coordination - Complex Data Query | 2 / 2 / 1 / 2 | 3 / 4 / 3 / 5 | 1 / 2 / 1 / 2 |
| Negotiation/Escalation - Multiple Intents | 2 / 2 / 2 / 2 | 4 / 4 / 4 / 5 | 3 / 3 / 2 / 4 |
| Urgency Detection - Immediate Escalation | 2 / 2 / 2 / 2 | 5 / 5 / 5 / 5 | 4 / 5 / 3 / 4 |
| Multi-Intent - Parallel Task Execution | 2 / 2 / 2 / 2 | 3 / 3 / 4 / 5 | 2 / 2 / 2 / 4 |
| Cross-Agent Dependency - Context Passing | 2 / 2 / 2 / 2 | 4 / 3 / 4 / 5 | 4 / 2 / 2 / 4 |
| Data Aggregation - Statistical Analysis | 2 / 2 / 1 / 2 | 3 / 4 / 3 / 5 | 1 / 2 / 1 / 2 |
| Customer Search - Ticket Resolution Flow | 2 / 2 / 2 / 2 | 9 / 8 / 9 / 11 | 7 / 7 / 6 / 8 |

## Part 5 tool calls

- `get_customer`: 14
- `get_ticket`: 2
- `get_ticket_stats`: 2
- `list_tickets`: 17
- `search_tickets`: 4

These are single-run observations, not benchmarks or causal evidence of a speed
improvement. Token usage and billed cost were not measured. Earlier snapshots
are preserved. The initial Part 5 attempt is retained separately; its automated
checks passed despite semantic failures described in part5_test_results.md.

## Answer review and remaining issues

- Final cancellation guidance states that the system cannot cancel subscriptions,
  process payments/refunds, or forward requests; it directs the customer to their
  provider. The initial offer to forward to billing and specific unverified portal
  did not recur in this answer.
- Final urgency guidance identifies the disabled account and existing ticket,
  states no new ticket was created, and says refunds/forwarding are unavailable.
  No transaction records exist; no refund or bank investigation is verified.
  The supplied expected-capability prose mentions creating an urgent ticket, but
  that is not an assertion or an explicit user request. The observed calls were
  all reads; automatic escalation/ticket creation is not claimed.
- The dependency answer now preserves ticket #1 as open and #6 as in_progress,
  instead of calling both open. It explicitly distinguishes active account status
  from unknown lockout state. The final dedicated live answer does the same.
- The search answer gives general troubleshooting rather than inventing historical
  resolution notes. The initial specific 15–60 minute expiry did not recur.
  It still says "for your account" even though the query is a global ticket search
  with no requester identity. That is an unsupported personalization and remains
  an answer-quality issue, not a failure caught by the smoke/execution checks.
  General administrator-reset advice is not evidence of an exposed admin capability.
- Statistics remain 12 open / 6 in progress / 7 resolved (25 total), with priority
  totals 5/8/12. Parallel workers both call get_ticket_stats: the duplicate eliminated
  by Part 4 returns in Part 5. The record-only scenarios again run both specialists.
- All 39 observed MCP calls in the final ten scenarios were reads. The separate
  final live fixture verifies exactly one requested creation and correct ticket #2
  attribution. There is no workflow-wide transaction or idempotency guarantee.
- The final run used 46 specialist and 10 summary model requests: 56 total, versus
  Part 4's 43. Both specialists independently look up context; synthesis adds a
  third stage. Summed scenario time was 222.80 seconds versus 277.92 in Part 4,
  but that single observation cannot establish speed or cost savings. A provider
  stall in an intermediate run is separate evidence of timing variability.
- Initial ten-scenario attempt: 10/10 smoke and execution checks, 54 model requests,
  38 MCP calls, 201.55 summed seconds, despite the semantic failures. The final
  corrected run replaces neither that evidence nor earlier checkpoint baselines.
- Live A2A error-event cancellation initially hung until the fixture deadline.
  Worker-local error propagation passed the final full live suite. Production
  overall deadlines, remote cancellation, rollback, and retries remain limitations;
  a local cancellation does not guarantee remote side effects stop.

The final automated result is 10/10 smoke and 10/10 execution contracts. It is not
a claim of ten semantically perfect answers. See part5_test_results.md for failure
chronology and preserved attempts; the original transcript wording is retained.
