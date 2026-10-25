"""Routing contracts and real ADK sequencing without network/model calls."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace, MappingProxyType
import unittest
from unittest.mock import patch
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
from host_agent import advanced_router_agent as routing
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types


def context(query='', state=None, invocation='current', agent='customer_data'):
    """Supply only the documented callback properties used by these helpers."""
    return SimpleNamespace(user_content=types.Content(parts=[types.Part(text=query)]),
        state={} if state is None else state, invocation_id=invocation,
        agent_name=agent, session=SimpleNamespace(events=[]))


class TestRoutingRules(unittest.TestCase):
    """Differentiate requested actions from record descriptions and negations."""

    def test_intent_matrix(self):
        cases = [
            ('Get customer information for ID 5', 'data_only'),
            ('Show all customers with open high-priority tickets', 'data_only'),
            ('Find tickets about password reset issues', 'data_only'),
            ('List failed payment tickets', 'data_only'),
            ('List support tickets', 'data_only'),
            ('Customer 5 needs support', 'sequential'),
            ('General support please', 'support_only'),
            ("Find tickets containing 'help'", 'data_only'),
            ('Find tickets containing "reset my password"', 'data_only'),
            ('Give statistics on customer tickets', 'data_only'),
            ('How do I reset my password?', 'support_only'),
            ('Help me troubleshoot a slow browser', 'support_only'),
            ('Customer ID 5: help me with login', 'sequential'),
            ('Find tickets about password resets and explain common solutions', 'sequential'),
            ('Check my account and help with login', 'sequential'),
            ('Get customer 5. Do not provide support.', 'data_only'),
            ('Get customer 5 without troubleshooting', 'data_only'),
            ('Get customer 5. Do not provide troubleshooting guidance.', 'data_only'),
            ('The identifier was provided', 'sequential'),
            ('', 'sequential'),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                decision = routing.analyze_query_intent(query)
                self.assertEqual(decision['execution_mode'], expected)
                self.assertTrue(decision['needs_data'] or decision['needs_support'])

    def test_urgency_is_not_an_action(self):
        self.assertEqual(routing.analyze_query_intent('URGENT help me now')['urgency'], 'high')
        self.assertEqual(routing.analyze_query_intent('Not urgent, show customer 5')['urgency'], 'low')
        self.assertEqual(routing.analyze_query_intent('Show high priority tickets')['urgency'], 'medium')

    def test_preparation_refreshes_decision_and_clears_previous_answer(self):
        ctx = context('Get customer 5', {'temp:customer_data_response': {'old': True}})
        routing.prepare_routing(ctx)
        self.assertEqual(ctx.state['routing_decision']['execution_mode'], 'data_only')
        self.assertIsNone(ctx.state['temp:customer_data_response'])
        ctx.user_content = types.Content(parts=[types.Part(text='How do I reset'), types.Part(text='my password?')])
        ctx.invocation_id = 'next'
        routing.prepare_routing(ctx)
        self.assertEqual(ctx.state['routing_decision']['execution_mode'], 'support_only')
        self.assertEqual(ctx.state['routing_invocation_id'], 'next')

    def test_stale_missing_and_malformed_decisions_run_both(self):
        for state in [{}, {'routing_decision': 'bad'},
            {'routing_invocation_id': 'old', 'routing_decision': routing.analyze_query_intent('Get customer 5')},
            {'routing_invocation_id': 'current', 'routing_decision': {'needs_data': False, 'needs_support': False, 'execution_mode': 'data_only'}},
            {'routing_invocation_id': 'current', 'routing_decision': {'needs_data': 'false', 'needs_support': True, 'execution_mode': 'support_only'}}]:
            ctx = context(state=state)
            self.assertIsNone(routing.should_run_customer_data_agent(ctx))
            self.assertIsNone(routing.should_run_support_agent(ctx))

    def test_instruction_reads_readonly_state_without_writing(self):
        ctx = context('Get customer 5')
        routing.prepare_routing(ctx)
        before = json.dumps(ctx.state, sort_keys=True)
        ctx.state = MappingProxyType(ctx.state)
        self.assertIn('data_only', routing.create_router_instruction(ctx))
        self.assertEqual(json.dumps(dict(ctx.state), sort_keys=True), before)

    def test_skip_support_requires_current_data_answer(self):
        ctx = context('Get customer 5')
        routing.prepare_routing(ctx)
        with self.assertRaisesRegex(RuntimeError, 'no current'):
            routing.should_run_support_agent(ctx)


class StubRemote(BaseAgent):
    """Use BaseAgent's actual callbacks but emit a fixed remote answer."""
    agent_card: str = ''
    calls: Any

    async def _run_async_impl(self, ctx):
        self.calls.append(self.name)
        text = 'CUSTOMER DATA ANSWER' if self.name == 'customer_data' else 'SUPPORT ANSWER'
        yield Event(author=self.name, invocation_id=ctx.invocation_id,
            content=types.Content(role='model', parts=[types.Part(text=text)]))


class TestADKRouting(unittest.IsolatedAsyncioTestCase):
    """Exercise callbacks, state deltas, skip behavior, and same-session turns."""

    async def test_routes_and_preserves_final_answer_across_turns(self):
        calls = []
        def remote(**kwargs):
            return StubRemote(calls=calls, **kwargs)
        with patch.object(routing, 'RemoteA2aAgent', side_effect=remote):
            agent = routing.create_agent()
        def router_response(callback_context, llm_request):
            return LlmResponse(content=types.Content(role='model', parts=[types.Part(text='INTERNAL ROUTING PLAN')]))
        agent.sub_agents[0].before_model_callback = router_response
        sessions = InMemorySessionService()
        await sessions.create_session(app_name='routing_test', user_id='u', session_id='s')
        runner = Runner(app_name='routing_test', agent=agent, session_service=sessions)
        async with runner:
            for query, expected_calls, expected_answer in [
                ('Get customer 5', ['customer_data'], 'CUSTOMER DATA ANSWER'),
                ('How do I reset my password?', ['support_specialist'], 'SUPPORT ANSWER'),
                ('Check customer 5 and help with login', ['customer_data','support_specialist'], 'SUPPORT ANSWER'),
            ]:
                calls.clear()
                finals=[]
                async for event in runner.run_async(user_id='u', session_id='s', new_message=types.Content(role='user', parts=[types.Part(text=query)])):
                    if event.is_final_response() and event.content:
                        text=''.join(p.text or '' for p in event.content.parts or [])
                        if text: finals.append(text)
                self.assertEqual(calls, expected_calls, query)
                self.assertEqual(finals[-1], expected_answer, query)


if __name__ == '__main__':
    unittest.main()
