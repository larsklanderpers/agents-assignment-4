"""Parallel ADK execution, state isolation, and failure contracts without APIs."""
import asyncio
import os
from types import SimpleNamespace, MappingProxyType
from unittest.mock import patch
from typing import Any
import unittest
from tests.test_routing import context
from host_agent import parallel_router_agent as parallel
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types


class Worker(BaseAgent):
    """Barrier requires both workers to start; sequential execution times out."""
    agent_card: str = ''
    shared: Any

    async def _run_async_impl(self, ctx):
        self.shared['started'].add(self.name)
        if len(self.shared['started']) == 2:
            self.shared['barrier'].set()
        await asyncio.wait_for(self.shared['barrier'].wait(), 2)
        if self.shared.get('fail') and self.name == 'support_specialist':
            raise RuntimeError('deliberate worker failure')
        yield Event(author=self.name, invocation_id=ctx.invocation_id,
            content=types.Content(role='model', parts=[types.Part(text=self.name + ' CURRENT')]))


class TestParallel(unittest.IsolatedAsyncioTestCase):
    """Exercise actual ParallelAgent callbacks and summary sequencing."""

    async def test_concurrency_repeated_turns_and_worker_failure(self):
        shared = {'started': set(), 'barrier': asyncio.Event()}
        with patch.object(parallel, 'RemoteA2aAgent', side_effect=lambda **kw: Worker(shared=shared, **kw)):
            agent = parallel.create_agent()
        summaries = []
        def summary(callback_context, llm_request):
            instruction = parallel.create_summary_instruction(callback_context)
            self.assertIn('customer_data CURRENT', instruction)
            self.assertIn('support_specialist CURRENT', instruction)
            summaries.append(instruction)
            return LlmResponse(content=types.Content(role='model', parts=[types.Part(text='FINAL SYNTHESIS')]))
        agent.sub_agents[1].before_model_callback = summary
        service = InMemorySessionService()
        await service.create_session(app_name='parallel_test', user_id='u', session_id='s')
        runner = Runner(app_name='parallel_test', agent=agent, session_service=service)
        async def invoke():
            return [event async for event in runner.run_async(user_id='u', session_id='s',
                new_message=types.Content(role='user', parts=[types.Part(text='current request')]))]
        async with runner:
            for _ in range(2):
                shared.update(started=set(), barrier=asyncio.Event())
                events = await invoke()
                self.assertEqual(shared['started'], {'customer_data','support_specialist'})
                self.assertEqual(events[-1].content.parts[0].text, 'FINAL SYNTHESIS')
            shared.update(started=set(), barrier=asyncio.Event(), fail=True)
            with self.assertRaisesRegex(RuntimeError, 'deliberate worker failure'):
                await invoke()
            self.assertEqual(len(summaries), 2, 'Summary ran after failed worker')

    def test_missing_stale_outputs_and_readonly_instruction(self):
        ctx = context()
        parallel.prepare_parallel(ctx)
        with self.assertRaisesRegex(RuntimeError, 'both current'):
            parallel.create_summary_instruction(ctx)
        ctx.state.update(customer_data_output='DATA', support_specialist_output='SUPPORT')
        ctx.state = MappingProxyType(ctx.state)
        self.assertIn('DATA', parallel.create_summary_instruction(ctx))
        ctx.invocation_id = 'next'
        with self.assertRaisesRegex(RuntimeError, 'different invocation'):
            parallel.create_summary_instruction(ctx)

    def test_capture_rejects_previous_turn(self):
        ctx = context()
        ctx.session.events = [Event(author='customer_data', invocation_id='old',
            content=types.Content(parts=[types.Part(text='STALE')]))]
        with self.assertRaisesRegex(RuntimeError, 'without a current'):
            parallel.capture_output(ctx)

    def test_parallel_support_cannot_write(self):
        from support_agent.agent import create_agent
        with patch.dict(os.environ, HOST_AGENT_MODE='parallel'):
            agent = create_agent()
        self.assertFalse(set(agent.tools[0].tool_filter) & {'create_ticket','update_ticket_status','update_ticket_priority'})
        self.assertIn('read-only', agent.instruction)
        with patch.dict(os.environ, HOST_AGENT_MODE='basic'):
            self.assertIn('create_ticket', create_agent().tools[0].tool_filter)


if __name__ == '__main__':
    unittest.main()
