"""Supervised A2A server CLI and client with explicit readiness/failure contracts."""

import asyncio
from collections.abc import AsyncIterator
import logging
import os
import sys
from typing import Any

# Add agents directory to Python path
agents_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agents')
sys.path.insert(0, agents_dir)

# Load .env BEFORE importing agent modules: shared/agents_config.py reads
# GEMINI_MODEL and MCP_SERVER_URL at import time.
from dotenv import load_dotenv
project_root = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(project_root, '.env'))

# IMPORTANT: Apply A2A compatibility patch BEFORE any A2A imports
from shared import a2a_compat  # noqa: F401

import httpx
import nest_asyncio
import uvicorn

from a2a.client import ClientConfig, ClientFactory, create_text_message_object
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, Message, TaskState, TransportProtocol
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH

from google.adk.a2a.executor.a2a_agent_executor import (
    A2aAgentExecutor,
    A2aAgentExecutorConfig,
)
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from create_agents import create_all_agents

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure CLI logging; imported agent modules leave root handlers alone."""
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(name)s] %(levelname)s - %(message)s',
        datefmt='%H:%M:%S',
    )


def print_agent_card(agent_card: AgentCard, port: int) -> None:
    """Print agent card in a nice formatted way."""
    print("\n" + "="*80)
    print(f"AGENT: {agent_card.name}")
    print("="*80)
    print(f"URL: http://127.0.0.1:{port}")
    print(f"Description: {agent_card.description}")
    print(f"Protocol: {agent_card.protocol_version}")
    print(f"Transport: {agent_card.preferred_transport}")
    print(f"\nSkills:")
    for skill in agent_card.skills:
        print(f"  - {skill.name}: {skill.description}")
        print(f"    Examples:")
        examples = skill.examples if hasattr(skill, 'examples') else []
        for example in examples[:3]:  # Show first 3 examples
            print(f"      * {example}")
    print("="*80 + "\n")

# Only notebook callers with an already-running loop need nested-loop support.
# Patching plain CLI execution can break async-library detection on Python 3.14.
try:
    asyncio.get_running_loop()
except RuntimeError:
    pass
else:
    nest_asyncio.apply()


_DEFAULT_EVENT_CONVERTER = A2aAgentExecutorConfig().event_converter


def convert_agent_event(event: Event, *args: Any) -> list[Any]:
    """Propagate remote ADK errors so partial artifacts cannot complete a task."""
    if event.error_message:
        raise RuntimeError(f"{event.author} failed: {event.error_message}")
    return _DEFAULT_EVENT_CONVERTER(event, *args)


def create_agent_a2a_server(agent: BaseAgent, agent_card: AgentCard) -> A2AStarletteApplication:
    """
    Create an A2A server for an ADK agent with logging.

    Args:
        agent: The ADK agent instance
        agent_card: The agent card with metadata

    Returns:
        A2AStarletteApplication instance
    """
    runner = Runner(
        app_name=agent.name,
        agent=agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )

    config = A2aAgentExecutorConfig(event_converter=convert_agent_event)
    executor = A2aAgentExecutor(runner=runner, config=config)

    # Create custom request handler with logging. DefaultRequestHandler has no
    # handle_request(); A2A message/send and message/stream requests arrive at
    # on_message_send() and on_message_send_stream().
    class LoggingRequestHandler(DefaultRequestHandler):
        """Add request diagnostics while preserving standard A2A behavior."""
        def _log_request(self, params: Any) -> None:
            agent_name = agent_card.name
            logger.info(f"[{agent_name}] Received request")

            # Log request details
            if hasattr(params, 'message') and params.message:
                msg_text = ""
                if hasattr(params.message, 'parts') and params.message.parts:
                    for part in params.message.parts:
                        if hasattr(part, 'root') and hasattr(part.root, 'text'):
                            msg_text += part.root.text
                if msg_text:
                    logger.info(f"[{agent_name}] Message: {msg_text[:100]}...")

        async def on_message_send(self, params: Any, context: Any = None) -> Any:
            """Log and delegate a non-streaming A2A request."""
            self._log_request(params)
            response = await super().on_message_send(params, context)
            logger.info(f"[{agent_card.name}] Sending response")
            return response

        async def on_message_send_stream(self, params: Any, context: Any = None) -> AsyncIterator[Any]:
            """Log and yield the standard streaming A2A response events."""
            self._log_request(params)
            async for event in super().on_message_send_stream(params, context):
                yield event
            logger.info(f"[{agent_card.name}] Sending response")

    request_handler = LoggingRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )

    return A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )


def _create_uvicorn_server(agent: BaseAgent, card: AgentCard, port: int) -> uvicorn.Server:
    """Construct a server without binding a socket until serve() is awaited."""
    app = create_agent_a2a_server(agent, card)
    return uvicorn.Server(uvicorn.Config(
        app.build(), host='127.0.0.1', port=port, log_level='warning', loop='none',
    ))


async def _serve(server: uvicorn.Server) -> None:
    """Translate Uvicorn bind exits into exceptions the supervisor can handle."""
    try:
        await server.serve()
    except SystemExit as exc:
        raise RuntimeError(f'Agent server could not bind port {server.config.port}') from exc


async def run_agent_server(agent: BaseAgent, agent_card: AgentCard, port: int) -> None:
    """Serve one A2A endpoint until shutdown; raise if its startup fails."""
    await _serve(_create_uvicorn_server(agent, agent_card, port))


async def start_all_servers(
    ready: asyncio.Event | None = None,
    stop: asyncio.Event | None = None,
    startup_timeout: float = 15.0,
) -> None:
    """Serve all agents, reporting readiness only after every listener starts.

    Optional events coordinate test-mode readiness and shutdown. Factory, bind,
    timeout, and runtime failures propagate to the caller. Every exit shuts down
    this invocation's servers, including siblings of a failed server.
    """
    configs = create_all_agents()
    servers = [_create_uvicorn_server(c['agent'], c['card'], c['port']) for c in configs.values()]
    tasks = [asyncio.create_task(_serve(server)) for server in servers]
    stop_task = None
    try:
        deadline = asyncio.get_running_loop().time() + startup_timeout
        while not all(server.started for server in servers):
            for task in tasks:
                if task.done():
                    task.result()
                    raise RuntimeError('An agent server exited before readiness')
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError('Agent servers did not become ready before the startup deadline')
            await asyncio.sleep(0.05)
        for task in tasks:
            if task.done():
                task.result()
                raise RuntimeError('An agent server exited before readiness')
        logger.info('All %d agent servers are ready. Press Ctrl+C to stop.', len(servers))
        for config in configs.values():
            print_agent_card(config['card'], config['port'])
        if ready is not None:
            ready.set()
        waiting = list(tasks)
        if stop is not None:
            stop_task = asyncio.create_task(stop.wait())
            waiting.append(stop_task)
        finished, _ = await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
        for task in finished:
            task.result()
    finally:
        if stop_task is not None:
            stop_task.cancel()
            await asyncio.gather(stop_task, return_exceptions=True)
        for server in servers:
            server.should_exit = True
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)
        except TimeoutError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def run_servers_in_background() -> None:
    """Run the supervised servers synchronously, usable as a thread target."""
    asyncio.run(start_all_servers())


def extract_response_text(response: Any) -> str:
    """Return nonempty completed A2A text, or raise for failed/empty responses.

    Accept a direct A2A Message or a client (Task, update) tuple. A partial
    artifact never overrides a failed task status. All text artifacts in a
    completed task are included; non-text/empty results are explicit failures.
    """
    if isinstance(response, Message):
        parts = response.parts
    elif isinstance(response, tuple) and response and hasattr(response[0], 'status'):
        task = response[0]
        if task.status.state != TaskState.completed:
            message = task.status.message
            detail = ' '.join(getattr(p.root, 'text', '') for p in message.parts) if message else ''
            state = getattr(task.status.state, 'value', str(task.status.state))
            raise RuntimeError(f'A2A task {state}: {detail or "no status message; check server logs"}')
        parts = [part for artifact in (task.artifacts or []) for part in artifact.parts]
    else:
        raise RuntimeError('A2A stream ended without a supported final response')
    text = ''.join(getattr(part.root, 'text', '') for part in parts)
    if not text.strip():
        raise RuntimeError('A2A response contained no text answer')
    return text


class A2AClient:
    """Simple A2A client for testing agents."""

    def __init__(self, default_timeout: float = 240.0) -> None:
        """Set request timeout and initialize the agent-card cache."""
        self._agent_info_cache: dict[str, dict[str, Any] | None] = {}
        self.default_timeout = default_timeout

    async def send_message(self, agent_url: str, message: str) -> str:
        """
        Send a message to an A2A agent.

        Args:
            agent_url: The agent's base URL
            message: The message to send

        Returns:
            Nonempty text from a completed task or direct message.

        Raises:
            RuntimeError: The task failed, needs input, or has no text answer.
            httpx.HTTPError: Discovery or transport failed.
        """
        timeout_config = httpx.Timeout(
            timeout=self.default_timeout,
            connect=10.0,
            read=self.default_timeout,
            write=10.0,
            pool=5.0,
        )

        async with httpx.AsyncClient(timeout=timeout_config) as httpx_client:
            # Check cache for agent card
            if agent_url in self._agent_info_cache and self._agent_info_cache[agent_url] is not None:
                agent_card_data = self._agent_info_cache[agent_url]
            else:
                # Fetch agent card
                agent_card_response = await httpx_client.get(
                    f'{agent_url}{AGENT_CARD_WELL_KNOWN_PATH}'
                )
                agent_card_response.raise_for_status()
                agent_card_data = self._agent_info_cache[agent_url] = agent_card_response.json()

            # Create AgentCard from data
            from a2a.types import AgentCard
            agent_card = AgentCard(**agent_card_data)

            # Create A2A client
            config = ClientConfig(
                httpx_client=httpx_client,
                supported_transports=[
                    TransportProtocol.jsonrpc,
                    TransportProtocol.http_json,
                ],
                use_client_preference=True,
            )

            factory = ClientFactory(config)
            client = factory.create(agent_card)

            # Create and send message
            message_obj = create_text_message_object(content=message)

            # Keep only the latest snapshot rather than retaining the full stream.
            last_response = None
            async for response in client.send_message(message_obj):
                last_response = response
            return extract_response_text(last_response)


async def test_agents() -> bool:
    """Smoke-test each endpoint and return False if any request fails."""
    client = A2AClient()

    print("\n" + "="*80)
    print("TESTING CUSTOMER SUPPORT A2A AGENTS")
    print("="*80 + "\n")

    checks = [
        ("1. Testing Customer Data Agent", "http://localhost:10020",
         "Show me all open tickets with high priority"),
        ("2. Testing Support Agent", "http://localhost:10021",
         "I can't login to my account, what should I do?"),
        ("3. Testing Host Agent (Orchestrator)", "http://localhost:10022",
         "I'm having login issues, can you check my account and help me resolve this?"),
    ]
    passed = 0
    for title, url, query in checks:
        print(title)
        print("-"*80)
        try:
            response = await client.send_message(url, query)
            print(f"Response: {response}\n")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {e}\n")

    print("="*80)
    print(f"Agent requests passed: {passed}/{len(checks)}")
    print("="*80 + "\n")

    return passed == len(checks)


async def _run_test_mode() -> bool:
    """Wait for verified startup, run smoke tests, and stop owned servers."""
    ready, stop = asyncio.Event(), asyncio.Event()
    servers = asyncio.create_task(start_all_servers(ready=ready, stop=stop))
    readiness = asyncio.create_task(ready.wait())
    try:
        finished, _ = await asyncio.wait([servers, readiness], return_when=asyncio.FIRST_COMPLETED)
        if servers in finished:
            await servers
            raise RuntimeError('Agent servers stopped before tests could start')
        return await test_agents()
    finally:
        readiness.cancel()
        await asyncio.gather(readiness, return_exceptions=True)
        stop.set()
        await servers


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; return 1 on failures and 130 on keyboard interruption."""
    import argparse

    parser = argparse.ArgumentParser(description='Run the Customer Support A2A system')
    parser.add_argument('--mode', choices=['start', 'test'], default='start')
    args = parser.parse_args(argv)
    configure_logging()
    try:
        if args.mode == 'start':
            asyncio.run(start_all_servers())
            return 0
        return 0 if asyncio.run(_run_test_mode()) else 1
    except KeyboardInterrupt:
        logger.info('Shutting down agent servers')
        return 130
    except Exception:
        logger.exception('Agent system failed')
        return 1


if __name__ == '__main__':
    sys.exit(main())
