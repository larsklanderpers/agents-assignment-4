# Customer Data structured-response follow-up

Branch: fixes/customer-data-response-schema, based on Part 5. This follow-up
changes the producer contract shared by basic, advanced, and parallel modes.

## Failure: the SDK dropped required null values

The first 35 regression tests passed, including real ADK/SQLite cases for valid
and malformed final text after a write. The first live lookup nevertheless failed
with four missing-field errors: customer_context.phone, ticket_statistics,
customer_statistics, and a completed-action record_id. The model had supplied
nullable fields, but the installed ADK output_schema-with-tools fallback used
SetModelResponseTool serialized its validated model with model_dump(exclude_none=True).
Its final JSON omitted them.
This was a serialization-path gap that the first fixtures had not exercised.

The fix intercepts the installed fallback's set_model_response declaration in
the public after-model callback, validates its arguments strictly, and converts
it to canonical JSON text including null fields before dispatch. This is a final
response declaration, not a real database tool; other tool calls pass through.
A final declaration mixed with real tool operations is rejected rather than
silently swallowing a write. Invalid fallback arguments raise before the SDK can
return validation feedback and ask the model to try again. No SDK files changed.

Two added regression methods exercise fallback null preservation, invalid/mixed
arguments, and valid/invalid fallback finals after an actual SQLite fixture write.
The total is 37 regression methods, all passing. Plain-text and fallback failures
leave exactly one row, make two fixture model calls (write then final), and do not
run the downstream agent. No automatic workflow/formatting retry is implemented.

## Contract

CustomerDataResponse requires schema_version, status, summary, customer_context,
customers, relevant_tickets, ticket_statistics, customer_statistics,
completed_actions, and errors. Nullable fields must be present as null; unused
collections are empty lists. Nested customer/ticket records, exact status/priority
values, statistics, action tool names/IDs, and explanatory issue details are typed.
Unknown fields and coercion are rejected. Statistics must sum and completed writes
require positive record IDs. Non-success outcomes require explanatory errors.

Agent.output_schema constrains generation; after-model validation handles final
text and SDK fallback declarations, and an after-agent gate checks the current
invocation before downstream execution. Tool-call reasoning turns are allowed;
stream fragments are provisional and only complete output is accepted. Support
continues to return prose. Pydantic is an explicit dependency in both manifests.

## Database contract review: email can be null

The supplied database/API allows customer creation without email. An initial
non-nullable email field would have rejected a legitimate record. Before final
verification it was changed to required-but-nullable, matching phone/timestamps;
a regression covers a customer with all optional database values null. This was
a source-audit correction, not a live model failure.

## Python environment and remaining parallel outage failure

The assignment specifies Python 3.11. Earlier checkpoints and initial follow-up
runs used the base Python 3.14 environment. An existing a2a-agents environment was
found with Python 3.11.17. Final regressions and structural checks were repeated
there: 37/37 and 35/35 passed. The eight live MCP/schema cases also passed there.
Both environments use ADK 2.12.0, a2a-sdk 0.3.26 and MCP 1.30.0; Pydantic differs
(2.13.5 in base, 2.14.1 in a2a-agents), so this is not a pure Python-only A/B test.

Focused parallel live testing passed the healthy context/synthesis request but
then timed out after 180 seconds when Support was stopped. It reproduced on both
Python 3.14 and Python 3.11, even though the Part 5 final outage run had passed.
Consequently the existing worker wrapper is not a complete reliability solution,
and the result cannot be blamed solely on Python 3.14. Saved timeout logs are
schema-parallel-py314-timeout.txt and schema-parallel-py311-timeout.txt.

An attempted fix drained SDK task-control cleanup events before raising a worker
error. A more realistic cleanup-sequence unit test passed, but the live 3.11 outage
still timed out (schema-parallel-cleanup-attempt-timeout.txt). That hypothesis was
insufficient. The speculative production/test change was restored to the Part 5
version; commits retain the attempt and restoration. No SDK files were changed.
The final PR is scoped to Customer Data's schema and reports the parallel outage
as an unresolved integration issue, not a passing check. Its root cause is not
established by these observations. Basic and advanced outage checks did pass.

The original nest_asyncio incident occurred under Python 3.14 and its import guard
fixed the observed CLI failure. These new tests do not establish what an unguarded
3.11 run would have done; they do establish that the later parallel timeout also
occurs in the required environment.

## Verification

Final unit/regression run: 37/37. Supplied structural harnesses: 35/35.
Live MCP/Gemini: 8/8 typed cases passed, exit 0: customer/ticket lookup,
missing customer, missing identity, statistics, exactly one requested creation,
database failure, and stopped MCP. Discovery still returned 15/10 tools and all
four direct MCP checks passed. Initial/final evidence: schema-mcp-initial.json and
schema-mcp.json under scenario_runs/. The write case created ticket #4 once and
its ID matched completed_actions; all other normal cases left three original tickets.

Full basic A2A suite: 7/7 passed, exit 0. Direct Data output parsed strictly,
Support received data context, the requested high-priority ticket was created once,
and stopped Support produced an explicit failed task. Evidence: schema-basic.json.
Focused advanced A2A on Python 3.14: 3/3 passed, exit 0 (mixed context,
data-only while Support was stopped, and explicit failure when Support was required).
The replayed data-only answer retained required null fields. Evidence: schema-advanced.json.

Focused parallel A2A: healthy synthesis passed on both runtimes; outage timed out
on both. The full two-request fixture is FAILED, not 2/2 passed. An attempted
cleanup correction also failed live and was restored; see failure section above.

Final advanced ten-scenario run on Python 3.11: 10/10 smoke checks and 10/10
actual-routing contracts passed, exit 0, on commit 93132a4. Three data-only final
answers also passed strict parsing plus selected fixture facts: customer 5 is
Charlie Brown, the open/high query returns customers 1/7 and tickets 1/3, and
statistics are 12 open / 6 in-progress / 7 resolved, total 25.

Evidence: schema-followup.txt and schema-followup.metrics.json. Actual totals:
17 specialist HTTP requests, 46 total traced model requests (36 specialist + 10
router), 26 MCP calls, 353.33 summed scenario seconds. Part 4's earlier advanced
run had 17 / 43 / 23 / 277.92 respectively. These are separate single runs with
both contract and environment changes (Python/Pydantic), not a controlled cost
or speed comparison. No token/billed-cost claim is made. Original Parts 2–5
baselines are unchanged. Keyword/length smoke checks remain weak: the schema's
required field names alone can supply matching words. A valid envelope does not
establish task success, factual completeness, or correct action attribution.

## Remaining issues

Structure is not factual truth: a model can still fill a valid schema with wrong
records, omit requested facts using empty collections, or misattribute actions.
Positive write IDs and consistent totals do not prove those values came from tools.
The live database checks establish the tested examples, not universal grounding.
Support and the parallel summary can still introduce prose errors; the earlier
unsupported personalization finding remains outside this format-only correction.

Validation does not roll back a committed write. A failed request may have side
effects, and neither automatic retry nor workflow-wide idempotency is provided.
The application never restarts tool execution to repair invalid output. Models
can still choose additional real tool calls during normal reasoning, so this is
not an exactly-once execution guarantee. Provider/transport failures may terminate
the run without any valid envelope; missing data is distinct from runtime failure.

The fallback adapter depends on the installed ADK's set_model_response declaration;
SDK/model upgrades require these regressions and live checks. No full dependency
migration, production deadline policy, or notebook/UI verification is added.
