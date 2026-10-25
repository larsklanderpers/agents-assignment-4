# Part 1 live verification

Run date: 2026-10-25 (Australia/Sydney).
Environment: WSL, Python 3.14, installed Google ADK/MCP packages.
Model: `gemini-3.8-flash`, read from `.env` via `GEMINI_MODEL`.

## Implementation covered

1. MCP toolset configuration: explicit 15-tool customer-data filter and 10-tool
   support-safe filter, using SSE connection parameters.
2. Customer Data Agent: configured Gemini model and customer-data MCP toolset.
3. Agent instruction: role, capabilities, tool schemas, customer identification,
   requested writes, factual JSON responses, and handling of missing information.
4. Error handling: standard MCP/ADK handling plus instructions to explain tool
   failures, report limitations, and never invent records or successful actions.

## Results

| Check | Observed result |
| --- | --- |
| Supplied toolset structure harness | 4/4 checks passed |
| Supplied Customer Data Agent structure harness | 5/5 checks passed |
| Live customer-data SSE discovery | Exactly 15 tools |
| Live support SSE discovery | Exactly 10 tools |
| Direct customer lookup, ID 5 | Expected synthetic customer returned |
| Direct ticket filter, open + high | Exactly ticket 1; excluded resolved/high and open/low fixtures |
| Direct missing customer, ID 999999 | `null`, no protocol error |
| Direct malformed customer ID | MCP validation error with `isError=true` |
| Gemini customer lookup | Called `get_customer(5)` and `list_tickets(customer_id=5)`; final answer matched fixture |
| Gemini open/high ticket lookup | Called `list_tickets(status='open', priority='high')`; returned only ticket 1 |
| Gemini missing customer | Called `get_customer(999999)`; reported record not found, without inventing a customer |
| Gemini unspecified customer | Made no tool calls; requested customer identity |
| Gemini database error | MCP returned `no such table: customers`; final answer explained database failure with no completed actions |
| Gemini MCP unavailable | After server shutdown, final answer explained unavailable tools and suggested checking connection/retrying; no fabricated data |

The six Gemini conversation results were manually assessed against tool events
and known fixture records. These are observed results from one run, not a
promise that model wording or choices are deterministic. No write tools were
called in these conversations.

## Reproduction

From the assignment root, with the dependencies installed and a working API key:

```bash
python -m tests.test_mcp_toolset
python -c "from tests.test_agents import check_customer_data_agent; assert all(check_customer_data_agent())"
python tests/manual_part1.py
# Repeat only SSE discovery and direct-tool assertions, without Gemini calls:
python tests/manual_part1.py --tools-only
```

`manual_part1.py` creates one synthetic customer and three tickets in a temporary
SQLite database, starts the supplied MCP server on port 18080, and drives the
Customer Data Agent directly through ADK Runner. It prints actual tool calls,
results, and final answers for inspection. It intentionally renames the temporary
customer table to provoke a database error, then shuts down its server to test
unavailability. Its process and database are cleaned up afterward. Port 18080
must be free. The user's existing database/server is not used or changed.

## Observations and limits

- The configured model returned HTTP 200 responses; no model change was needed.
- ADK emitted experimental-feature and missing-ADC/mTLS warnings. Gemini API-key
  calls and local SSE connections still succeeded.
- During server unavailability, ADK logged connection-error stack traces and ran
  without the toolset. The model attempted an unavailable tool, received an ADK
  error, then produced an accurate failure response. This is graceful final-answer
  behavior, not silent recovery or proof of connectivity restoration.
- JSON answers were commonly wrapped in Markdown fences and field names varied.
  A strict machine-readable schema is not enforced in Part 1.
- Customer Data was executed in-process through ADK Runner against the real MCP
  server. A2A servers, Support Agent, Host Agent, and advanced routing are later
  checkpoints. Full-system tests remain expected to fail until those are built.
- Original GitHub `main` and both original starting commits are preserved.
