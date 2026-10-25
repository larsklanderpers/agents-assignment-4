"""Quality regressions for startup truthfulness, failures, and import side effects."""
import asyncio
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run_agents
import httpx


class FakeServer:
    """A controlled server lifecycle; no sockets or external services required."""

    def __init__(self, delay=None, bind_failure=False):
        self.started = False
        self.should_exit = False
        self.delay = delay
        self.bind_failure = bind_failure
        self.config = SimpleNamespace(port=12345)
        self.closed = False

    async def serve(self):
        if self.bind_failure:
            raise SystemExit(1)
        if self.delay is not None:
            await asyncio.sleep(self.delay)
            self.started = True
        try:
            while not self.should_exit:
                await asyncio.sleep(0.005)
        finally:
            self.closed = True


class TestSupervisor(unittest.IsolatedAsyncioTestCase):
    """Readiness must reflect server state, and every failure cleans up peers."""

    def fixtures(self, servers):
        configs = {str(i): {'agent': None, 'card': None, 'port': i} for i in range(len(servers))}
        return patch.multiple(run_agents, create_all_agents=lambda: configs, print_agent_card=lambda *a: None), patch.object(run_agents, '_create_uvicorn_server', side_effect=servers)

    async def test_readiness_waits_for_all_servers(self):
        servers = [FakeServer(0), FakeServer(0.1)]
        ready, stop = asyncio.Event(), asyncio.Event()
        config_patch, factory_patch = self.fixtures(servers)
        with config_patch, factory_patch:
            task = asyncio.create_task(run_agents.start_all_servers(ready, stop))
            await asyncio.sleep(0.02)
            self.assertFalse(ready.is_set())
            await asyncio.wait_for(ready.wait(), 1)
            self.assertTrue(all(s.started for s in servers))
            stop.set()
            await task
        self.assertTrue(all(s.closed for s in servers))

    async def test_startup_timeout_does_not_report_ready(self):
        server, ready = FakeServer(), asyncio.Event()
        config_patch, factory_patch = self.fixtures([server])
        with config_patch, factory_patch:
            with self.assertRaises(TimeoutError):
                await run_agents.start_all_servers(ready=ready, startup_timeout=0.02)
        self.assertFalse(ready.is_set())
        self.assertTrue(server.closed)

    async def test_bind_exit_propagates_and_stops_sibling(self):
        servers, ready = [FakeServer(0), FakeServer(bind_failure=True)], asyncio.Event()
        config_patch, factory_patch = self.fixtures(servers)
        with config_patch, factory_patch:
            with self.assertRaisesRegex(RuntimeError, 'bind port'):
                await run_agents.start_all_servers(ready=ready)
        self.assertFalse(ready.is_set())
        self.assertTrue(servers[0].closed)

    async def test_real_servers_ready_and_stop_cleanly(self):
        """Exercise supervised A2A listeners without making model requests."""
        configs = run_agents.create_all_agents()
        for config in configs.values():
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                config['port'] = probe.getsockname()[1]
        ready, stop = asyncio.Event(), asyncio.Event()
        with patch.object(run_agents, 'create_all_agents', return_value=configs):
            with patch.object(run_agents, 'print_agent_card'):
                task = asyncio.create_task(run_agents.start_all_servers(ready, stop))
                try:
                    await asyncio.wait_for(ready.wait(), 5)
                    async with httpx.AsyncClient() as client:
                        for config in configs.values():
                            response = await client.get(f"http://127.0.0.1:{config['port']}{run_agents.AGENT_CARD_WELL_KNOWN_PATH}")
                            self.assertEqual(response.status_code, 200)
                            self.assertEqual(response.json()['name'], config['card'].name)
                finally:
                    stop.set()
                    await task

    async def test_real_occupied_port_fails_without_readiness(self):
        """Use Uvicorn's actual bind path, not a simulated SystemExit."""
        async def app(scope, receive, send):
            return

        with socket.socket() as occupied:
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            server = run_agents.uvicorn.Server(run_agents.uvicorn.Config(
                app, host='127.0.0.1', port=occupied.getsockname()[1],
                lifespan='off', log_level='critical',
            ))
            ready = asyncio.Event()
            config_patch, factory_patch = self.fixtures([server])
            with config_patch, factory_patch:
                with self.assertRaisesRegex(RuntimeError, 'bind port'):
                    await run_agents.start_all_servers(ready=ready)
            self.assertFalse(ready.is_set())

    async def test_mixed_smoke_test_failure_returns_false(self):
        with patch.object(run_agents.A2AClient, 'send_message', AsyncMock(side_effect=['answer', RuntimeError('offline'), 'answer'])):
            with redirect_stdout(io.StringIO()):
                self.assertFalse(await run_agents.test_agents())


class TestCLIAndResponses(unittest.TestCase):
    """CLI failures and empty responses must not appear successful."""

    def test_factory_failure_returns_nonzero_without_readiness(self):
        with patch.object(run_agents, 'create_all_agents', side_effect=RuntimeError('factory failed')):
            with self.assertLogs(run_agents.logger, level='INFO') as captured:
                self.assertEqual(run_agents.main(['--mode', 'start']), 1)
        self.assertFalse(any('servers are ready' in line for line in captured.output))

    def test_test_mode_failure_returns_nonzero(self):
        with patch.object(run_agents, '_run_test_mode', AsyncMock(return_value=False)):
            self.assertEqual(run_agents.main(['--mode', 'test']), 1)

    def test_empty_stream_and_empty_completed_task_raise(self):
        empty_task = SimpleNamespace(status=SimpleNamespace(state=run_agents.TaskState.completed), artifacts=[])
        for response in (None, (empty_task, None)):
            with self.subTest(response=response), self.assertRaises(RuntimeError):
                run_agents.extract_response_text(response)

    def test_direct_message_and_all_artifacts_return_text(self):
        message = run_agents.create_text_message_object(content='direct answer')
        self.assertEqual(run_agents.extract_response_text(message), 'direct answer')
        task = SimpleNamespace(status=SimpleNamespace(state=run_agents.TaskState.completed), artifacts=[SimpleNamespace(parts=message.parts), SimpleNamespace(parts=message.parts)])
        self.assertEqual(run_agents.extract_response_text((task, None)), 'direct answerdirect answer')

    def test_import_preserves_root_logging_and_cli_loop(self):
        code = """import logging
from unittest.mock import patch
import nest_asyncio
handlers = list(logging.getLogger().handlers)
with patch.object(nest_asyncio, 'apply') as apply:
    import run_agents
    apply.assert_not_called()
assert logging.getLogger().handlers == handlers
"""
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_running_loop_import_uses_nested_loop_guard(self):
        code = """import asyncio
from unittest.mock import patch
import nest_asyncio
async def check():
    with patch.object(nest_asyncio, 'apply') as apply:
        import run_agents
        apply.assert_called_once_with()
asyncio.run(check())
"""
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
