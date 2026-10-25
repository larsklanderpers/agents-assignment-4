"""Opt-in live A2A checkpoint checks: python tests/manual_part2.py."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'agents'))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
os.environ['MCP_SERVER_URL'] = 'http://127.0.0.1:18081'
from run_agents import A2AClient, configure_logging, create_all_agents, run_agent_server
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
import httpx


def record_request(callback_context, llm_request):
    """Record actual model input in the test-only trace to check A2A handoff."""
    with open(os.environ['PART2_TRACE'], 'a') as trace:
        trace.write(json.dumps({'agent': callback_context.agent_name,
            'contents': [c.model_dump(mode='json', exclude_none=True) for c in llm_request.contents]}) + '\n')


async def serve(name):
    """Serve one real agent with test-only request tracing."""
    config = create_all_agents()[name]
    if name == 'host' and os.environ.get('SCENARIO_HOST_MODE'):
        from host_agent import root_agent
        if root_agent is None:
            raise RuntimeError('Requested scenario Host mode is not implemented')
        config['agent'] = root_agent
    from google.adk.agents import Agent

    def trace_models(agent):
        """Trace all local LLM stages, including the advanced router."""
        if isinstance(agent, Agent):
            agent.before_model_callback = record_request
        for child in agent.sub_agents:
            trace_models(child)

    trace_models(config['agent'])
    await run_agent_server(config['agent'], config['card'], config['port'])


async def wait_ready(processes):
    """Wait for real HTTP agent cards rather than a fixed startup delay."""
    async with httpx.AsyncClient() as client:
        for port in (10020, 10021, 10022):
            for _ in range(200):
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError('A verification server exited during startup')
                try:
                    response = await client.get(f'http://127.0.0.1:{port}{AGENT_CARD_WELL_KNOWN_PATH}')
                    response.raise_for_status()
                    card = response.json()
                    assert card['skills'] and card['url'].endswith(str(port))
                    break
                except httpx.HTTPError:
                    await asyncio.sleep(0.2)
            else:
                raise TimeoutError(f'A2A server {port} did not become ready')
    print('PASS: all three HTTP agent cards available', flush=True)


async def send_with_deadline(client, url, prompt):
    """Bound whole test requests even when transport stream activity continues."""
    return await asyncio.wait_for(client.send_message(url, prompt), timeout=180)


async def check_cases(processes, db, trace, outage_only=False, host_mode="basic"):
    """Exercise real A2A HTTP calls and verify context plus database effects."""
    await wait_ready(processes)
    client = A2AClient(default_timeout=180)
    cases = [
        ('data_lookup', 10020, 'Get customer 5 information. Do not change any records.'),
        ('support_password', 10021, 'How do I reset my password? Give general guidance; do not change records.'),
        ('host_context', 10022, 'I am customer 5. Show my open tickets and help with my login issue. Do not change any records.'),
        ('missing_identity', 10022, 'Look up my account and help me with login. Do not change any records.'),
        ('ticket_creation', 10022, 'For customer 6 create one high-priority ticket for Fixture export failure ABC42, which blocks all exports, and help me troubleshoot. Do not create duplicates.'),
        ('missing_record', 10022, 'Check customer 999999 and help with login. Do not change any records.'),
    ]
    if host_mode == 'advanced' and not outage_only:
        cases += [
            ('host_data_only', 10022, 'Get customer 5 information. Do not provide support. Do not change records.'),
            ('host_support_only', 10022, 'How do I reset my password? Give general guidance; do not change records.'),
        ]
    if outage_only:
        cases = [case for case in cases if case[0] == 'host_context']
    for label, port, prompt in cases:
        offset = len(trace.read_text(encoding='utf-8')) if trace.exists() else 0
        logs = [trace.parent / 'server-1.log', trace.parent / 'server-2.log']
        log_offsets = [len(path.read_text(encoding='utf-8')) for path in logs]
        answer = await send_with_deadline(client, f'http://localhost:{port}', prompt)
        assert answer and len(answer) > 40, label
        print(json.dumps({'case': label, 'answer': answer}), flush=True)
        if host_mode == 'advanced' and port == 10022:
            assert 'ROUTING_PLAN:' not in answer, 'Internal routing plan leaked into final answer'
            counts = tuple(path.read_text(encoding='utf-8')[offset:].count('Received request') for path, offset in zip(logs, log_offsets))
            expected_calls = {'host_data_only': (1, 0), 'host_support_only': (0, 1)}.get(label, (1, 1))
            assert counts == expected_calls, (label, counts, expected_calls)
            print('PASS: actual specialist HTTP requests match the selected route', flush=True)
        if label == 'data_lookup':
            assert 'A2A Fixture Five' in answer
        if label in ('host_data_only', 'host_support_only'):
            records = [json.loads(line) for line in trace.read_text(encoding='utf-8')[offset:].splitlines()]
            names = {r['agent'] for r in records}
            expected = 'customer_data_agent' if label == 'host_data_only' else 'support_agent'
            excluded = 'support_agent' if label == 'host_data_only' else 'customer_data_agent'
            assert expected in names and excluded not in names, names
            assert 'query_router' in names, names
            if label == 'host_data_only':
                assert 'A2A Fixture Five' in answer, 'Skip callback lost the useful data answer'
            print('PASS: requested route ran only its selected specialist', flush=True)
        if label == 'host_context' and host_mode != 'parallel':
            records = [json.loads(line) for line in trace.read_text()[offset:].splitlines()]
            support_inputs = [json.dumps(r['contents']) for r in records if r['agent'] == 'support_agent']
            assert support_inputs, 'Support never received a model request'
            assert any(prompt in content and 'A2A Fixture Five' in content and 'Fixture existing login issue' in content for content in support_inputs), 'Original query or data result missing from Support context'
            print('PASS: Support model input includes original query and Customer Data output', flush=True)
        if host_mode == 'parallel' and port == 10022:
            records = [json.loads(line) for line in trace.read_text(encoding='utf-8')[offset:].splitlines()]
            summaries = [json.dumps(r['contents']) for r in records if r['agent'] == 'parallel_summary']
            assert len(summaries) == 1, 'Expected exactly one final synthesis'
            counts = tuple(path.read_text(encoding='utf-8')[start:].count('Received request') for path, start in zip(logs, log_offsets))
            assert counts == (1, 1), counts
            if label == 'host_context':
                assert 'Fixture existing login issue' in summaries[0], 'Data ticket context missing from synthesis input'
                assert 'Fixture existing login issue' in answer and 'five@example.test' in answer, 'Summary lost relevant account/ticket evidence'
            if label == 'ticket_creation':
                assert 'ticket' in answer.lower() and '2' in answer, 'Summary lost the created ticket ID'
            print('PASS: both remote workers and one current synthesis', flush=True)
        with sqlite3.connect(db) as conn:
            count = conn.execute('SELECT count(*) FROM tickets').fetchone()[0]
            if label in ('data_lookup', 'support_password', 'host_context', 'missing_identity'):
                assert count == 1, 'Unexpected ticket write during a lookup'
            if label in ('missing_record', 'host_data_only', 'host_support_only'):
                assert count == 2, 'Unexpected write after the requested ticket was created'
            if label == 'ticket_creation':
                rows = conn.execute('SELECT customer_id, issue, priority FROM tickets WHERE customer_id=6').fetchall()
                assert len(rows) == 1 and rows[0][2] == 'high' and 'ABC42' in rows[0][1], rows
                print('PASS: exactly one requested high-priority ticket created for customer 6', flush=True)
    # The Support server is separate, so test a real downstream A2A failure.
    processes[2].terminate()
    processes[2].wait(timeout=10)
    if host_mode == 'advanced':
        offset = len(trace.read_text(encoding='utf-8'))
        answer = await send_with_deadline(client, 'http://localhost:10022', 'Get customer 5 information. Do not provide support. Do not change records.')
        assert 'A2A Fixture Five' in answer
        records = [json.loads(line) for line in trace.read_text(encoding='utf-8')[offset:].splitlines()]
        assert not any(r['agent'] == 'support_agent' for r in records)
        print(json.dumps({'case': 'skipped_support_unavailable', 'answer': answer}), flush=True)
    try:
        answer = await send_with_deadline(client, 'http://localhost:10022', 'Check customer 5 and help with login. Do not change records.')
    except RuntimeError as exc:
        assert 'failed' in str(exc).lower(), str(exc)
        print(json.dumps({'case': 'support_unavailable', 'error_type': type(exc).__name__, 'detail': str(exc)}), flush=True)
    else:
        raise AssertionError(f'Downstream failure unexpectedly reported as success: {answer}')


if __name__ == '__main__':
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', choices=['customer_data', 'support', 'host'])
    parser.add_argument('--host-mode', choices=['basic', 'advanced', 'parallel'], default='basic')
    parser.add_argument('--outage-only', action='store_true', help='Warm the Host context and test a stopped Support server')
    args = parser.parse_args()
    if args.serve:
        asyncio.run(serve(args.serve))
    else:
        # Fail before launching if one of the fixed assignment ports is already used.
        for port in (18081, 10020, 10021, 10022):
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(('127.0.0.1', port))
        with tempfile.TemporaryDirectory(prefix='part2-a2a-') as tmp:
            db = Path(tmp) / 'support.db'
            trace = Path(tmp) / 'trace.jsonl'
            # Use the supplied database manager without colliding with package names.
            import importlib.util
            spec = importlib.util.spec_from_file_location('fixture_database', ROOT / 'mcp_server/database.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.DatabaseManager(str(db))
            with sqlite3.connect(db) as conn:
                conn.executemany('INSERT INTO customers(id,name,email,status) VALUES (?,?,?,?)', [(5,'A2A Fixture Five','five@example.test','active'),(6,'A2A Fixture Six','six@example.test','active')])
                conn.execute("INSERT INTO tickets(customer_id,issue,status,priority) VALUES (5,'Fixture existing login issue','open','high')")
            env = dict(os.environ, HOST_AGENT_MODE=args.host_mode, SCENARIO_HOST_MODE=args.host_mode, PORT='18081', HOST='127.0.0.1', DB_PATH=str(db), PART2_TRACE=str(trace))
            processes, logs = [], []
            try:
                commands = [[sys.executable, str(ROOT / 'mcp_server/app.py')]] + [[sys.executable, __file__, '--serve', name] for name in ('customer_data','support','host')]
                for index, command in enumerate(commands):
                    log = (Path(tmp) / f'server-{index}.log').open('w')
                    logs.append(log)
                    processes.append(subprocess.Popen(command, env=env, stdout=log, stderr=log))
                asyncio.run(check_cases(processes, db, trace, args.outage_only, args.host_mode))
            except BaseException:
                for log in logs:
                    log.flush()
                for path in Path(tmp).glob('server-*.log'):
                    print(f'--- {path.name}: last 35 lines ---', flush=True)
                    print('\n'.join(path.read_text().splitlines()[-35:]), flush=True)
                raise
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
                for log in logs:
                    log.close()
