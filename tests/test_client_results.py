"""Regression checks for A2A client handling of partial artifacts."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from a2a.types import TaskState
from run_agents import A2AClient, convert_agent_event
from create_agents import create_host_agent_card


class TestA2AClientResults(unittest.IsolatedAsyncioTestCase):
    """A failed task must not look successful merely because it has data."""

    async def send_task(self, state):
        """Use real client setup with mocked HTTP and a controlled A2A task."""
        task = SimpleNamespace(
            status=SimpleNamespace(state=state, message=None),
            artifacts=[SimpleNamespace(parts=[SimpleNamespace(root=SimpleNamespace(text='partial data'))])],
        )

        class FakeA2AClient:
            async def send_message(self, message):
                yield task, None

        card = create_host_agent_card().model_dump(mode='json', by_alias=True)
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=card))
        original_client = httpx.AsyncClient
        with patch('run_agents.httpx.AsyncClient', side_effect=lambda **kw: original_client(transport=transport, **kw)):
            with patch('run_agents.ClientFactory') as factory:
                factory.return_value.create.return_value = FakeA2AClient()
                return await A2AClient().send_message('http://example.test', 'test request')

    async def test_failed_task_with_partial_artifact_raises(self):
        """Preserve failure status even after an earlier agent produced data."""
        with self.assertRaisesRegex(RuntimeError, 'failed'):
            await self.send_task(TaskState.failed)

    async def test_completed_task_with_artifact_returns_text(self):
        """Completed tasks still return their normal answer."""
        self.assertEqual(await self.send_task(TaskState.completed), 'partial data')


class TestAgentErrorConversion(unittest.TestCase):
    """Remote error events must interrupt the executor's success path."""

    def test_remote_error_is_raised(self):
        event = SimpleNamespace(author='support_specialist', error_message='Connection failed')
        with self.assertRaisesRegex(RuntimeError, 'support_specialist failed: Connection failed'):
            convert_agent_event(event)

    def test_normal_events_use_standard_converter(self):
        event = SimpleNamespace(error_message=None)
        with patch('run_agents._DEFAULT_EVENT_CONVERTER', return_value=['normal']) as converter:
            self.assertEqual(convert_agent_event(event, 'context'), ['normal'])
            converter.assert_called_once_with(event, 'context')


if __name__ == '__main__':
    unittest.main()
