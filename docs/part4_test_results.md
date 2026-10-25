# Part 4 failures and verification

Date: 2026-10-25, Australia/Sydney. WSL/Python 3.14 and the same configured
Gemini model as the earlier checkpoints. This checkpoint adds conditional
specialist selection while keeping remote A2A calls sequential when both run.

## 1. A ticket-description word caused false Support routing

The first routing matrix failed for "List failed payment tickets": expected
data_only, observed sequential. The initial analyzer treated "failed" as a
request for troubleshooting even though it described records to retrieve.

The rule now distinguishes a descriptive record lookup from a personal problem
report, while explicit requests for help/solutions still select Support. The
matrix also covers quoted search literals, "support tickets" as a record noun,
explicit support requests, common negated guidance phrases, word boundaries,
and urgency versus filtering high-priority records. This is bounded pattern
handling, not a general natural-language understanding guarantee.

## 2. Pydantic copied the test's call counter

The first ADK sequencing test expected a Customer Data call but observed an empty
external list. The stub's list[str] field was validated/copied by Pydantic;
appending to it did not update the external list used by the assertion. This
was a test-fixture observation error, not evidence that the route never ran.

The test counter field now retains the shared object. The actual ADK callback
path then passed data-only, support-only, and combined requests in one session,
with the expected final answer each time. Current-invocation state is refreshed,
and stale/malformed decisions conservatively run both specialists.

## Answer preservation and state hazards covered before live testing

A before-agent Content return skips a stage but also emits an event. Returning
"Support skipped" at the end of a data-only route could replace the useful data
answer. The implementation instead caches the current data answer in an after-
agent callback and returns that content when Support is skipped. It raises if
the expected current answer is absent, rather than returning a router plan or
an earlier turn's answer. Tests verify exact useful final output and state
refresh across turns. These are preventive checks, not claimed live defects.

## Verification status

- Routing contracts: seven test methods, including a multi-case intent matrix
  and three same-session ADK turns, passed before live testing.
- Routing plus inherited quality/client regressions: 23/23 in the initial
  combined run; final capture pending.
- Basic structural harnesses: 35/35 passed.
- Advanced live fixture (ten requests): pending.
- Provided ten-scenario advanced run and Part 2/3 comparison: pending.

## Remaining limitations

Route control is deterministic rule-based analysis; the extra router LLM plans
tasks using that decision but cannot override it. Arbitrary paraphrases,
contradictions, or complex negation can still cause conservative extra calls or
misclassification. The analyzer does not use customer tiers, transactions, or
unavailable business data. Urgency is descriptive rather than permission.

The same ten provided scenarios do not contain a pure generic-support-only
Host request; the dedicated fixture supplies that missing route. Their built-in
length/keyword checks remain weak. Actual specialist calls and routing decisions
must be compared with the intended routes; a printed routing decision alone is
not execution evidence. Specialist model counters remain comparable with the
old snapshots; separate router and total counters expose the new overhead.

No dependency migration, parallel execution, or automatic recovery/restart of a
failed specialist is part of this checkpoint. Inherited failed-task handling and
truthful action summaries must remain intact. Single runs are not performance
benchmarks, and passing model examples do not guarantee every future response.
