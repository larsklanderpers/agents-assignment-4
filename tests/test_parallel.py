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
        with patch.object(parallel, 'ParallelRemoteA2aAgent', side_effect=lambda **kw: Worker(shared=shared, **kw)):
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

    async def test_remote_failure_drains_both_workers_before_terminal_failure(self):
        # Exercise real RemoteA2aAgent lifecycle, ParallelAgent merger and Runner.
        # The failed remote yields cleanup events after the error, as ADK does.
        for failed_name in ('customer_data', 'support_specialist'):
            with self.subTest(failed_name=failed_name):
                finished = set()
                completed = set()
                failure_seen = asyncio.Event()
                fail = True
                async def remote_events(worker, ctx):
                    try:
                        if fail and worker.name == failed_name:
                            yield Event(author=worker.name, invocation_id=ctx.invocation_id,
                                content=types.Content(parts=[types.Part(text='PARTIAL')]))
                            failure_seen.set()
                            yield Event(author=worker.name, invocation_id=ctx.invocation_id,
                                error_message='connection refused')
                            yield Event(author=worker.name, invocation_id=ctx.invocation_id)
                        else:
                            if fail:
                                await failure_seen.wait()
                                await asyncio.sleep(0.05)
                            yield Event(author=worker.name, invocation_id=ctx.invocation_id,
                                content=types.Content(role='model', parts=[types.Part(text=worker.name + ' CURRENT')]))
                        completed.add(worker.name)
                    finally:
                        finished.add(worker.name)
                agent = parallel.create_agent()
                summaries = []
                def summary(callback_context, llm_request):
                    summaries.append(parallel.create_summary_instruction(callback_context))
                    return LlmResponse(content=types.Content(role='model', parts=[types.Part(text='RECOVERED')]))
                agent.sub_agents[1].before_model_callback = summary
                service = InMemorySessionService()
                await service.create_session(app_name='outage', user_id='u', session_id='s')
                runner = Runner(app_name='outage', agent=agent, session_service=service)
                async def invoke():
                    return [e async for e in runner.run_async(user_id='u', session_id='s',
                        new_message=types.Content(role='user', parts=[types.Part(text='request')]))]
                with patch.object(parallel.RemoteA2aAgent, '_run_async_impl', remote_events):
                    async with runner:
                        with self.assertRaisesRegex(RuntimeError, failed_name + ' failed: connection refused'):
                            await asyncio.wait_for(invoke(), 2)
                        self.assertEqual(finished, {'customer_data', 'support_specialist'})
                        self.assertEqual(completed, finished, 'A remote stream was aborted during failure handling')
                        self.assertFalse(summaries, 'Partial response was synthesized after a failure')
                        fail = False
                        events = await asyncio.wait_for(invoke(), 2)
                        self.assertEqual(events[-1].content.parts[0].text, 'RECOVERED')
                        self.assertEqual(len(summaries), 1, 'Previous failure poisoned the next turn')

    async def test_unexpected_remote_exception_is_deferred(self):
        async def remote_events(worker, ctx):
            raise ValueError('remote decode failed')
            yield
        worker = parallel.ParallelRemoteA2aAgent(name='customer_data', agent_card='http://example.test/card')
        ctx = SimpleNamespace(invocation_id='current', branch=None)
        with patch.object(parallel.RemoteA2aAgent, '_run_async_impl', remote_events):
            events = [e async for e in worker._run_async_impl(ctx)]
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0].error_message)
        self.assertIn('remote decode failed', events[0].actions.state_delta['customer_data_error'])

    async def test_cancellation_is_not_converted_to_an_error_event(self):
        async def remote_events(worker, ctx):
            raise asyncio.CancelledError()
            yield
        worker = parallel.ParallelRemoteA2aAgent(name='customer_data', agent_card='http://example.test/card')
        with patch.object(parallel.RemoteA2aAgent, '_run_async_impl', remote_events):
            with self.assertRaises(asyncio.CancelledError):
                _ = [e async for e in worker._run_async_impl(None)]

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
        parallel.capture_output(ctx)
        self.assertIn('without a current', ctx.state[ctx.agent_name + '_error'])
        with self.assertRaisesRegex(RuntimeError, 'without a current'):
            parallel.finish_parallel(ctx)

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
