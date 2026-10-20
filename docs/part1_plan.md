# Part 1 breakpoint

## Scope and implementation order

1. Configure the Customer Data MCP toolset with all 15 server tools.
2. Configure the Support MCP toolset with the 10 support-safe tools. Exclude
   `disable_customer`, `activate_customer`, `delete_ticket`, `add_customer`, and
   `update_customer`.
3. Implement the Customer Data Agent using the configured Gemini model and its
   MCP toolset. Give it instructions for data lookup, requested writes, missing
   identifiers, factual responses, and graceful tool-error reporting.
4. Verify the toolsets and Customer Data Agent structure before proceeding to
   Part 2.

## Verification

From the assignment root, in the Python environment with dependencies installed:

```bash
python -m tests.test_mcp_toolset
python -c "from tests.test_agents import check_customer_data_agent; assert all(check_customer_data_agent())"
```

For a manual functional check, leave the MCP server running in one terminal:

```bash
cd mcp_server
python app.py
```

Then open the Customer Data Agent in another terminal:

```bash
cd agents
adk web
```

Select `customer_data_agent` in the UI. With a valid API key and available model,
try `Get customer 5's information` and `Show open high-priority tickets`.
Check responses against the database. These model-backed checks are separate
from the structural checks and have not yet been verified.

## Stop here

The Support Agent, Host Agent, agent cards, and `create_all_agents()` remain
unimplemented for Part 2. Consequently, full agent/A2A checks and
`python run_agents.py --mode start` are expected to fail at this breakpoint.
The launcher's misleading startup-success message also remains unchanged.

The initial commit captures the starter stubs. Part 1 changes should form a
separate checkpoint commit after verification.
