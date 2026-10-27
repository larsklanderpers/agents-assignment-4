"""Real HTTP outage regression, with deterministic agents and no Gemini/MCP calls."""
import asyncio
import socket
import unittest
from typing import Any
from unittest.mock import patch
from tests.test_parallel import parallel
from run_agents import A2AClient, _create_uvicorn_server
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from sse_starlette.sse import AppStatus


class HttpSpecialist(BaseAgent):
    """Delay the healthy peer so an outage overlaps a real HTTP response."""
    completed: Any

    async def _run_async_impl(self, ctx):
        await asyncio.sleep(0.1)
        self.completed.append(self.name)
        yield Event(author=self.name, invocation_id=ctx.invocation_id,
            content=types.Content(role='model', parts=[types.Part(text=self.name + ' CURRENT')]))


class TestParallelHttp(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # These three fixtures share one loop. SSE's automatic drain watches a
        # process-wide Uvicorn signal handler; stopping one fixture must not
        # drain the Host's unrelated response. Production uses separate processes.
        self.enterContext(patch.object(AppStatus, 'enable_automatic_graceful_drain', False))

    async def test_cached_and_uncached_outages_return_failed_tasks(self):
        for failed_index in (0, 1):
            for warm in (False, True):
                with self.subTest(failed_index=failed_index, warm=warm):
                    servers, tasks, sockets = [], [], []
                    completed, summaries = [], []
                    async def start(agent):
                        sock = socket.socket()
                        sock.bind(('127.0.0.1', 0))
                        sock.listen()
                        sock.setblocking(False)
                        sockets.append(sock)
                        port = sock.getsockname()[1]
                        card = AgentCard(name=agent.name, description='HTTP regression fixture',
                            url=f'http://127.0.0.1:{port}', version='1.0',
                            capabilities=AgentCapabilities(streaming=True),
                            default_input_modes=['text/plain'], default_output_modes=['text/plain'],
                            skills=[AgentSkill(id='fixture', name='fixture', description='fixture', tags=['test'])])
                        server = _create_uvicorn_server(agent, card, port)
                        servers.append(server)
                        tasks.append(asyncio.create_task(server.serve(sockets=[sock])))
                        for _ in range(100):
                            if server.started:
                                return card.url
                            await asyncio.sleep(0.01)
                        raise TimeoutError('Fixture server did not start')
                    try:
                        urls = [await start(HttpSpecialist(name=name, completed=completed))
                                for name in ('data_fixture', 'support_fixture')]
                        with patch.object(parallel, 'CUSTOMER_DATA_AGENT_URL', urls[0]), patch.object(parallel, 'SUPPORT_AGENT_URL', urls[1]):
                            host = parallel.create_agent()
                        def summary(callback_context, llm_request):
                            summaries.append(parallel.create_summary_instruction(callback_context))
                            return LlmResponse(content=types.Content(role='model', parts=[types.Part(text='BOTH COMPLETE')]))
                        host.sub_agents[1].before_model_callback = summary
                        url = await start(host)
                        client = A2AClient(default_timeout=5)
                        if warm:
                            self.assertEqual(await asyncio.wait_for(client.send_message(url, 'healthy'), 5), 'BOTH COMPLETE')
                        servers[failed_index].should_exit = True
                        await tasks[failed_index]
                        before = len(summaries)
                        completed.clear()
                        failed_name = ('customer_data', 'support_specialist')[failed_index]
                        with self.assertRaisesRegex(RuntimeError, 'A2A task failed:.*' + failed_name + ' failed:'):
                            await asyncio.wait_for(client.send_message(url, 'outage'), 5)
                        self.assertEqual(len(summaries), before, 'Outage produced a successful summary')
                        self.assertEqual(completed, [('support_fixture', 'data_fixture')[failed_index]])
                    finally:
                        for server in servers:
                            server.should_exit = True
                        await asyncio.gather(*tasks, return_exceptions=True)
                        for sock in sockets:
                            sock.close()


if __name__ == '__main__':
    unittest.main()
