# Assignment 4: Reflection

## Student Name: Lars Klander

The five checkpoints cover the 100-point core assignment and the 25-point routing bonus. I have broken it up into sections for review because the exercise was time-consuming. I have checked in a PR for each part, and have merged all of them at this point, as per our discussion. 

# Part 1: MCP Tools \+ Customer Data Agent

## Toolset Design Decisions

I configured Customer Data with all 15 supplied MCP tools. Support normally receives 10 tools, excluding customer creation/update, account activation/disablement, and ticket deletion. Both factories use McpToolset with SSE connection parameters and explicit tool filters; the tool schemas are discovered from the server rather than reimplemented as manual wrappers. In Part 5, Support loses its three ticket-write tools as well, leaving seven read-only tools so Customer Data owns concurrent writes.That became necessary because of the concurrency challenges.

Live discovery confirmed 15 and 10 tools in the original configuration. The filter controls which tools an agent can call, but it does not guarantee accurate prose about what happened. That distinction became important in later checkpoints.

## Data Agent Instruction

The agent uses GEMINI\_MODEL from configuration; the recorded runs used gemini-3.8-flash. Its instruction covers customer and ticket lookup, searches, statistics, requested changes, schema-driven arguments, missing identity, and reporting only actions supported by successful tool results. It asks for identity instead of assuming a customer ID and distinguishes existing records from actions completed during the current workflow. The instructions to the agent were in fact very specific about the need to do it that way rather than assuming an identity \[a very simple attempt to mitigate hallucinations\].

The failure tests were as useful as the successful lookups were (though, honestly, that might be more a function of how I debug and problem solve). A missing customer returned no record, an invalid ID produced an MCP validation error, a deliberately renamed fixture table produced a database error, and stopping the fixture MCP server tested unavailability. In six live Gemini conversations, final answers either matched the fixture or explained the limitation. These were deliberate fault injections, not unexpected defects in the supplied database. During the outage, ADK logged errors and rejected an unavailable-tool attempt before the model explained the failure; there was no demonstrated automatic recovery.

One limitation remains: requesting JSON in an instruction does not enforce a JSON schema. Even when I started doing work, (which I ultimately added to the solution after Part 5), it was clear that worrying about JSON was probably minor in the long run: a valid schema guarantees structure, not truth. A perfectly formatted response could still invent a ticket. We must continue checking claimed actions against actual tool results. 

Responses used varying field names and Markdown fences. The Part 1 PR also intentionally stopped before full-system startup; unimplemented later stages were expected scaffold failures at that checkpoint. 

# Part 2: Multi-Agent A2A System

## Support Agent Design

Support's knowledge base covers login, password resets, billing, performance, exports, and feature requests. It combines general troubleshooting with retrieved records, asks for missing identifiers, and distinguishes recommendations from completed actions. In the basic workflow it should reuse Customer Data's preceding results rather than repeat every lookup.

Live tests revealed that correct database behavior was insufficient. Customer Data created exactly one requested ticket, but Support later said that no ticket had been created. It had described only its own actions rather than the entire workflow. Other answers offered future escalation without a contact tool or gave an unsupported 1–3 business-day estimate. These findings became explicit Part 3 instruction changes.

## Host Agent Orchestration

The basic Host is a SequentialAgent containing two RemoteA2aAgents: Customer Data, then Support. Test-only traces confirmed Support received both the original request and the preceding data answer. This order is appropriate when guidance depends on account or ticket context and when writes should be understood before the next agent responds.

The most serious failure appeared when Support was stopped. The client returned Customer Data's partial JSON as if the entire request had succeeded. The first fix required a completed A2A task before returning artifacts. Controlled client tests passed, but the next live outage still returned a partial answer: RemoteA2aAgent had emitted an error event while the outer task was marked completed. A second fix wrapped the executor's event converter and raised on error events, causing the outer task to fail. The final complete seven-request rerun returned an explicit failed-task error. This is why I keep testing despite multiple successful attempts, because I keep finding combinatory errors that are different than the initial run errors are.

## A2A Protocol Insights

Each AgentCard advertises a configured URL, description, version, capabilities, input/output modes, and skills with examples. RemoteA2aAgent discovers the remote service through .well-known/agent-card.json; calls cross real HTTP JSON-RPC boundaries rather than directly invoking a Python function. That separation makes transport failures, task status, partial artifacts, and service readiness part of the application contract.

The first live A2A attempt failed with sniffio.AsyncLibraryNotFoundError before card retrieval completed. The launcher had unconditionally applied nest\_asyncio. Under the tested Python 3.14 environment, this interfered with async-library detection. Applying the patch only when an event loop is already running restored ordinary CLI execution. The evidence supports an event-loop compatibility diagnosis; a full notebook workflow was not tested. An immediate fixture restart also failed its port probe after listeners had closed. SO\_REUSEADDR corrected the probe; TIME\_WAIT was a plausible explanation, not a captured socket-state diagnosis.

# Part 3: Challenges and Solutions

## Technical Challenges

The original launcher printed “Servers are running” after its server thread had already failed. Part 3 replaced fixed-delay readiness with an async supervisor: readiness follows actual listener startup, failures propagate to a nonzero exit, and owned servers are shut down on exit. Tests covered real listeners, an occupied port, factory failure, and startup deadlines. Audited empty-result paths now raise instead of returning an apparently successful placeholder, and all text artifacts are considered. Logging configuration moved to entry points so unrelated activity no longer inherited a Customer Data label.

Instructions were strengthened to report actions across the whole workflow and avoid unsupported external-action promises or precise provider policies. The live write case then correctly attributed ticket \#2 to the preceding Customer Data step, with SQLite confirming exactly one creation. That is observed improvement, not a guarantee for every future model answer.

Development tooling also failed. An overbroad edit inserted an import into embedded subprocess snippets and broke two tests. Narrowing the edit and exposing captured stderr fixed those tests. A Windows report write omitted UTF-8, raised UnicodeEncodeError, and truncated a working report. Restoring the tracked report and writing UTF-8 recovered it without losing test evidence. These were test-edit and documentation failures, distinct from application failures.

## Architecture Decisions

Sequential execution preserves a useful dependency: Support sees the data result before responding. A2A adds discovery and deployment separation, along with network and lifecycle complexity. Direct calls would remove some transport handling, but would not exercise the distributed architecture required by the assignment.

The final review found docstrings and return annotations on all 34 public functions in the reviewed implementation modules. The current 35 structural checks and 28 regressions passed again during this review. Some inherited module headers still use older part/point labels; the README rubric is the reference used here.

# Bonus: Routing Modes

## Advanced Router — Part 4

Bounded rules identify data-only, support-only, or combined requests. A before-agent callback saves a fresh decision and invocation ID; the dynamic router instruction reads that state. The Gemini router plans tasks, while callbacks enforce the route. It is not an unrestricted model-based intent classifier. Ambiguous requests retain both specialists, and urgency does not authorize writes.

The first intent matrix misrouted “List failed payment tickets” because “failed” was interpreted as a request for troubleshooting rather than a record description. The rules were revised and tested against descriptive queries, quoted literals, common negation, and explicit guidance requests. Another test initially reported no calls because Pydantic copied a typed list counter; that was a fixture defect, corrected by retaining the shared counter.

Skipping Support also creates an output hazard: a skip event can replace the useful data answer. The implementation caches and replays the current data answer and rejects stale or missing state. Those were preventive checks, not claimed live failures. The final advanced fixture passed ten requests, including all three routes and successful data-only execution while Support was unavailable.

## Parallel Router — Part 5

A ParallelAgent runs both remote specialists from the original request. Each worker's after-agent callback stores its current final text. A tool-free Gemini summary reads both outputs from state with include\_contents='none'. Because Support cannot wait for Customer Data's result, it has read-only tools in this mode; Customer Data owns requested writes. The live fixture verified one ticket creation and correct final attribution. A real ADK barrier test established concurrent scheduling without inferring concurrency from a faster answer.

Parallel execution reintroduced answer-quality failures. The first ten-scenario attempt passed every automated check while the summary offered to forward to billing, invented a reset-link expiry, and conflated open with in-progress status. An intermediate answer also inferred an unlocked account from active status. Explicit summary instructions addressed these cases; the final reviewed examples improved, but a global search still says “for your account” without requester identity. That unsupported personalization remains unresolved.

A provider call also stalled for more than four minutes. The cause was not established; test-only overall deadlines now bound verification requests. Later, a stopped-Support test logged an error but hung until the 180-second deadline. Raising the error in the outer converter could interrupt the parallel event merger while sibling workers were suspended. A RemoteA2aAgent subclass now raises error events inside the worker. A regression covers that event shape, and the final seven-request live suite returned a terminal failed-task RuntimeError. No installed SDK files were changed. Another rerun rejected a valid answer because the fixture required a full customer name; the assertion was corrected to check relevant account/ticket evidence rather than unnecessary wording.

## Mode Comparison

Each checkpoint repeated the same ten queries against freshly seeded original data (15 customers and 25 tickets), using the same configured model. The wrapper measured elapsed wall-clock time around each supplied scenario call with time.perf\_counter and recorded actual specialist requests, traced model requests, and MCP calls. Timings include request/discovery work, printing, and smoke checks; they exclude fixture startup and between-query sleeps. Each checkpoint has one final measured run, so this is not a controlled benchmark.

| Measure across ten queries | Part 2 | Part 3 | Part 4 | Part 5 |
| :---- | :---- | :---- | :---- | :---- |
| Specialist A2A requests | 20 | 20 | 17 | 20 |
| Specialist model requests | 41 | 40 | 33 | 46 |
| Router/summary model requests | 0 | 0 | 10 | 10 |
| Total model requests | 41 | 40 | 43 | 56 |
| MCP calls | 30 | 29 | 23 | 39 |
| Sum of request durations, seconds | 297.68 | 287.87 | 277.92 | 222.80 |

For a direct same-query comparison, the query was: “I'm customer 5 (Charlie Brown). Please show me my ticket history and also tell me how to reset my password.”

| Mode/checkpoint | Specialists called | Measured seconds | Context passing |
| :---- | :---- | :---- | :---- |
| Basic / Part 2 | Both, sequential | 63.13 | Data answer precedes Support |
| Basic / Part 3 | Both, sequential | 27.56 | Same dependency, stronger instructions |
| Advanced / Part 4 | Both, sequential | 23.50 | Combined route retains data-to-support order |
| Parallel / Part 5 | Both, concurrent | 19.25 | Independent workers; summary combines outputs |

The two basic runs alone show substantial timing variability. The faster parallel observation therefore does not establish a causal speed improvement. Token usage and billed cost were not measured. Part 4 reduced specialist calls and MCP work, but ten router requests increased total model requests to 43\. Part 5 added summary requests and duplicated reads, raising the total to 56 and MCP calls to 39\.

Statistics stayed correct at 12 open, 6 in progress, and 7 resolved tickets. The statistics lookup occurred once, twice, once, and twice across Parts 2–5: aggregate counts would have hidden that regression. All MCP calls in the final ten-scenario runs were reads; separate live fixtures verified requested writes. The supplied harness checks length and keywords, not all its printed expected capabilities. An urgency scenario could pass without creating the listed ticket; the request did not explicitly authorize a ticket. Actual routing assertions and manual answer review were necessary supplements.

# Key Learnings

1. Successful tools, accurate final prose, and successful end-to-end task status require separate evidence. A valid partial artifact cannot establish completion.  
2. Failure injection must cross real service boundaries. Client-only tests missed falsely completed tasks, and an exception-based worker test missed the live parallel error-event path. One successful outage run was insufficient.  
3. More agents can increase work and introduce new factual errors. Conditional execution reduced unnecessary specialist work; parallel synthesis duplicated reads and needed its own instruction and failure controls.

# Ideas for Improvement

* Add structured outputs and fact/action validation, including checks against unsupported personalization and exact status/count errors. Keep general advice distinct from verified account facts and capabilities.  
* Add production overall deadlines, explicit remote cancellation semantics, and idempotent write handling before automatic retries. Local cancellation does not guarantee a remote action stops, and a failed workflow does not roll back writes.  
* Evaluate more paraphrases and negation for routing, and use dependency-aware parallelism only where tasks are independent. Measure repeated runs, tokens, and cost before selecting a default mode for performance reasons.  
* Make discovery metadata reflect mode-specific capabilities. The Support card's generic ticket-management description currently remains when parallel Support is read-only. Customer Data's advertised JSON mode also does not enforce a schema.  
* Validate a full ADK Web/notebook workflow and the recommended Python environment. Experimental A2A/deprecated workflow warnings and compatibility code remain.

The final review reran the 35 supplied structural checks and 28 current regressions; all passed. Live evidence is from the saved checkpoint runs, not a new live run performed for this reflection. Full ADK Web interaction has not been established by the saved HTTP/Runner tests. All five PRs remain open and main remains the original starter; final submission/merging has not been performed by this review.

# Sources

* [Part 1 PR: MCP tools and Customer Data](https://github.com/larsklanderpers/agents-assignment-4/pull/1)  
* [Part 2 PR: multi-agent A2A](https://github.com/larsklanderpers/agents-assignment-4/pull/2)  
* [Part 3 PR: code quality](https://github.com/larsklanderpers/agents-assignment-4/pull/3)  
* [Part 4 PR: advanced routing](https://github.com/larsklanderpers/agents-assignment-4/pull/4)  
* [Part 5 PR: parallel execution](https://github.com/larsklanderpers/agents-assignment-4/pull/5)  
* Checkpoint failure reports: part1\_test\_results.md through part5\_test\_results.md.  
* Four-checkpoint comparison: part5\_comparison.md; full transcripts and metrics under scenario\_runs/. Initial, interrupted, and rejected Part 5 attempts are retained.

# Follow-up after Part 5: Customer Data Schema — PR \#6

The schema follow-up addresses the earlier instruction-only JSON limitation. Customer Data now declares a versioned Pydantic output schema and validates its final response before handoff. Records, statistics, completed actions and errors have required typed fields; unused nullable fields remain explicit nulls. Validation rejects missing/extra fields, wrong types, invalid status/priority values, inconsistent statistic totals and completed writes without positive IDs. Support continues to return readable prose.

The first live lookup failed even though 35 regression methods passed. ADK 2.12.0 used its set\_model\_response fallback, then removed required null fields during serialization. The correction validates that final declaration and emits canonical JSON before dispatch, preserving nulls; a second gate checks the completed response for the current invocation. Added regressions cover the actual fallback path. Source review also caught that email must be nullable because the supplied database permits customers without email.

Invalid final output fails explicitly instead of automatically repeating the workflow. In actual ADK/SQLite regressions, malformed output after one fixture write left exactly one row and did not reach the downstream agent. Both plain-text and fallback final declarations were exercised. The live write case also returned the ID of the single ticket confirmed in the fixture database. This does not establish a general exactly-once guarantee: models can choose additional tools during ordinary reasoning, and validation cannot undo committed writes.

The required a2a-agents environment is Python 3.11.17. Final checks there passed 37 regression methods and 35 structural checks, eight live MCP/schema cases, and all ten advanced-mode smoke/routing checks. Additional parsing confirmed the three data-only answers and selected fixture facts. Earlier follow-up tests on Python 3.14 passed eight MCP cases, the seven-request basic A2A suite and three focused advanced checks. The earlier checkpoint comparisons remain historical results from Python 3.14.

The new advanced run recorded 17 specialist HTTP calls, 46 total model requests (36 specialist and 10 router), 26 MCP calls and 353.33 summed scenario seconds. Part 4's earlier advanced run recorded 17/43/23/277.92. Both the contract and environment changed; Pydantic was 2.13.5 in base and 2.14.1 in a2a-agents, although ADK/A2A/MCP versions matched. These single runs cannot isolate a Python or schema effect, and tokens/billed cost were not measured.

One integration failure remains unresolved. Healthy parallel synthesis passed, but stopping Support timed out after 180 seconds on both Python 3.14 and Python 3.11. The earlier Part 5 passing outage run did not establish reliability. An attempted change drained SDK cleanup events before raising; its regression passed, but the live outage still timed out, so the speculative parallel change was restored to the Part 5 version. All failed attempts are retained in the PR evidence. The root cause is not established, and this schema PR does not claim to fix parallel cancellation.

The original nest\_asyncio failure occurred under Python 3.14 and the import guard fixed that observed CLI problem. We have not shown what an unguarded Python 3.11 run would do. Reproducing the later parallel timeout under 3.11 demonstrates why it should not simply be attributed to using 3.14.

A valid schema still does not prove factual truth, completeness or correct action attribution. It can contain invented records or empty collections that omit requested facts; Support or synthesis can still introduce prose errors. Required customer/ticket field names also make keyword-only smoke tests less informative. Production overall deadlines, remote cancellation, rollback and idempotency remain limitations. Full interactive ADK Web verification is separate from these automated HTTP/Runner checks.

Follow-up PR and preserved failure evidence: [https\://github.com/larsklanderpers/agents-assignment-4/pull/6](https://github.com/larsklanderpers/agents-assignment-4/pull/6)

# Parallel outage follow-up — PR \#7 (Python 3.11)

The schema follow-up preserved a 180-second parallel outage timeout under both Python 3.14 and the required Python 3.11. The earlier attempt to drain SDK cleanup events still raised inside a parallel worker and did not fix the live timeout. Two unchanged diagnostic runs succeeded in this follow-up, confirming that the historical stall is intermittent; the exact cause of every stalled request has not been conclusively isolated.

A stronger regression exposed an unsafe failure boundary: with partial content, a remote error, cleanup events and a slower sibling, the old handler aborted both streams before normal completion. That test failed for either specialist. The fix drains each worker, records invocation-local errors, and raises only after the ParallelAgent merger and both worker lifecycles finish. Synthesis is skipped after a failure, old error state is cleared for the next turn, and writes are never automatically retried. The workers still execute concurrently.

Verification also caught two fixture failures. Assigning an agent-card URL after construction raised Pydantic errors; the fixture now supplies URLs during construction. A combined HTTP test then lost a chunked response because three same-loop servers shared SSE's automatic shutdown watcher. The fixture isolates that signal and restores it afterward; production shutdown code was not changed for this test issue. Failed logs and the successful reruns are retained in the PR. A final whitespace check also caught formatting in captured model output, which was normalized without changing answer wording.

Under Python 3.11.17, all 40 regression methods and 35 structural checks passed. Four real-HTTP outage subcases cover either specialist stopped, with cached and uncached cards, and require a failed task within five seconds. The full seven-request live parallel suite passed, including exactly one requested ticket and a stopped Support server. A further healthy-context/outage repeat returned a failed task in 15.1 seconds and confirmed that no summary model ran after the outage. The same-session regression also verifies recovery after a failed turn.

All ten unchanged scenarios passed their smoke and parallel-execution checks. The new run recorded 20 specialist HTTP requests, 47 specialist model requests plus 10 summaries (57 total), 41 MCP calls and 269.58 summed seconds. Part 5 recorded 20/56/39/222.80; Part 4's advanced routing recorded 17/43/23/277.92. The new run made more calls and took longer than the earlier parallel snapshot. Runtime, schema enforcement and model variability differ, so these single runs cannot isolate the effect of this fix or establish better cost, latency or answer accuracy. Earlier snapshots remain intact.

Remaining tradeoffs: failure waits for the healthy worker to settle. A database action may already be committed when the overall request fails, so records must be checked before retrying a write. The test deadlines do not establish a universal production deadline, and a stalled surviving peer can still delay failure. The deterministic old/new cleanup regression and passing live results support the new boundary, but do not prove every SDK or transport cancellation failure has been eliminated. The A2A integration remains experimental, and current ADK also warns that ParallelAgent and SequentialAgent are deprecated.

Follow-up PR, failure evidence and scenario comparison: [https\://github.com/larsklanderpers/agents-assignment-4/pull/7](https://github.com/larsklanderpers/agents-assignment-4/pull/7)

I have merged PRs 1-5 but left 6 and 7 outstanding since they exceeded the direction. 

**Closing Thoughts**

Final thoughts on this project: I like the agent SDK for prototyping and quick solution of testing models, though I feel like the troubleshooting leaves a bit to be desired (but again, as I have noted before, maybe some of that is just because I know I am making a lot of mistakes at the beginning). 

I am still not completely comfortable with Python, and probably my first ten drafts of each agent had descriptions that weren’t quite comprehensive enough, in weird ways, and that feels like something that is likely to remain a problem (a personal issue, for sure) but I can certainly see the benefit in the sort of natural language instruction it supports; I just worry about the specificity not being there as I am often more comfortable with math and deterministic structures as the language of specificity than I am with English, but I think that’s probably just a mental training model.

If it’s not entirely clear from the writing, I did the entire unit in Python 3.14 inadvertently, and then went back and made sure it worked as expected in 3.11. I only really twigged to the version number being incorrect on the parallel outage which then drove me to go back and re-read the instructions and realize that a potential problem cause was the versioning, even though that ultimately turned out to be a red herring. 

I do have one open question: I feel like the structure of the agents we created here was very object oriented, particularly in constructing things in such a way that the host bot was able to work with both of the other two. When building properly complex systems, is this the way you would tend to do it? With a clear hierarchy of actions enunciated within each bot and then more general (orchestrator?) bots that are a bit smarter (stronger model?) that are responsible for directing the child bots on the receipt of a triggering action? That pattern makes sense to me I was just wondering if it became unsustainable at scale and there was a different pattern you would use.  
