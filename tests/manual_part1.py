"""Run opt-in Part 1 live checks against an isolated synthetic MCP database."""
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
sys.path.insert(0, str(ROOT / 'agents'))
sys.path.insert(0, str(ROOT / 'mcp_server'))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
os.environ['MCP_SERVER_URL'] = 'http://127.0.0.1:18080'
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from customer_data_agent.agent import create_agent
from customer_data_agent.response_schema import parse_customer_data_response
from shared.mcp_toolset import create_customer_data_toolset, create_support_toolset
from database import DatabaseManager
from mcp import ClientSession
from mcp.client.sse import sse_client

async def check_agent(label, prompt):
    """Collect actual tool calls and final responses for one fresh conversation."""
    agent = create_agent()
    sessions = InMemorySessionService()
    runner = Runner(app_name='part1_check', agent=agent, session_service=sessions)
    await sessions.create_session(app_name='part1_check', user_id='tester', session_id=label)
    calls, results, final = [], [], []
    try:
        async with runner:
            async for event in runner.run_async(
                user_id='tester', session_id=label,
                new_message=types.Content(role='user', parts=[types.Part(text=prompt)]),
            ):
                for part in event.content.parts if event.content else []:
                    if part.function_call:
                        calls.append({'name': part.function_call.name, 'args': part.function_call.args})
                    if part.function_response:
                        results.append({'name': part.function_response.name, 'response': part.function_response.response})
                    if part.text and event.is_final_response():
                        final.append(part.text)
        return {'case': label, 'calls': calls, 'tool_results': results, 'final': '\n'.join(final)}
    except Exception as exc:
        return {'case': label, 'error_type': type(exc).__name__, 'error_code': getattr(exc, 'code', None), 'detail': str(exc)}

def assert_schema_result(result, expected_status):
    """Require a complete typed response, not merely plausible model prose."""
    if result.get('error_type'):
        raise RuntimeError(f"{result['case']}: {result['error_type']}: {result.get('detail')}")
    parsed = parse_customer_data_response(result['final'])
    assert parsed.status == expected_status, (result['case'], parsed.status, expected_status)
    print(json.dumps({'schema_case': result['case'], 'status': parsed.status, 'passed': True}), flush=True)
    return parsed


async def main(server, db, tools_only=False):
    """Exercise SSE discovery, direct tools, and the Gemini-backed agent."""
    for factory, expected in [(create_customer_data_toolset, 15), (create_support_toolset, 10)]:
        toolset = factory()
        try:
            tools = await toolset.get_tools()
            assert len(tools) == expected, [t.name for t in tools]
            print(json.dumps({'discovery': factory.__name__, 'count': len(tools), 'passed': True}), flush=True)
        finally:
            await toolset.close()
    async with sse_client('http://127.0.0.1:18080/sse') as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            for name, args in [('get_customer', {'customer_id': 5}), ('list_tickets', {'status': 'open', 'priority': 'high'}), ('get_customer', {'customer_id': 999999}), ('get_customer', {'customer_id': 'invalid'})]:
                result = await session.call_tool(name, args)
                if args.get('customer_id') == 5:
                    assert not result.isError
                    assert json.loads(result.content[0].text)['name'] == 'Synthetic Customer Five'
                elif name == 'list_tickets':
                    rows = json.loads(result.content[0].text)
                    assert len(rows) == 1 and rows[0]['id'] == 1
                elif args.get('customer_id') == 999999:
                    assert not result.isError and json.loads(result.content[0].text) is None
                else:
                    assert result.isError
                print(json.dumps({'direct_tool': name, 'args': args, 'is_error': result.isError, 'content': [getattr(c, 'text', '') for c in result.content]}), flush=True)
    if tools_only:
        return
    for label, prompt in [
        ('customer_lookup', 'Get customer 5 information. Do not change any records.'),
        ('ticket_lookup', 'Show all open high-priority tickets. Do not change any records.'),
        ('missing_customer', 'Get customer 999999 information. If not found, clearly explain that. Do not change any records.'),
        ('ambiguous_customer', 'Look up my account details. Do not change any records.'),
        ('ticket_statistics', 'Get ticket statistics by status and priority. Do not change records.'),
        ('ticket_creation', 'For customer 5 create exactly one high-priority ticket for Schema fixture export failure XYZ99. Do not create duplicates.'),
    ]:
        result = await asyncio.wait_for(check_agent(label, prompt), timeout=120)
        print(json.dumps(result, default=str), flush=True)
        expected = {'missing_customer':'not_found', 'ambiguous_customer':'needs_clarification'}.get(label,'success')
        parsed = assert_schema_result(result, expected)
        with sqlite3.connect(db) as conn:
            count = conn.execute('SELECT count(*) FROM tickets').fetchone()[0]
            assert count == (4 if label == 'ticket_creation' else 3), 'Unexpected/duplicate write'
            if label == 'ticket_creation':
                row=conn.execute("SELECT id,priority FROM tickets WHERE issue LIKE '%XYZ99%'").fetchall()
                assert len(row)==1 and row[0][1]=='high', row
                assert any(a.tool=='create_ticket' and a.record_id==row[0][0] for a in parsed.completed_actions)
        if label == 'ticket_statistics':
            assert parsed.ticket_statistics.total_tickets==3 and parsed.ticket_statistics.open==2

    # Deliberately break only the disposable test database to exercise a tool error.
    with sqlite3.connect(db) as conn:
        conn.execute('ALTER TABLE customers RENAME TO unavailable_customers')
    result=await asyncio.wait_for(check_agent('database_error', 'Get customer 5 information. Do not change any records.'), timeout=120)
    print(json.dumps(result,default=str),flush=True)
    assert_schema_result(result,'error')
    server.terminate()
    server.wait(timeout=10)
    result=await asyncio.wait_for(check_agent('mcp_unavailable', 'Get customer 5 information. Do not change any records.'), timeout=90)
    print(json.dumps(result,default=str),flush=True)
    assert_schema_result(result,'error')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools-only', action='store_true', help='Run SSE/tool checks without calling Gemini')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='part1-check-') as tmp:
        db = Path(tmp) / 'support.db'
        manager = DatabaseManager(str(db))
        with sqlite3.connect(db) as conn:
            conn.execute("INSERT INTO customers(id,name,email,status) VALUES (5,'Synthetic Customer Five','five@example.test','active')")
            conn.executemany('INSERT INTO tickets(customer_id,issue,status,priority) VALUES (?,?,?,?)', [(5,'Synthetic login issue','open','high'),(5,'Synthetic resolved issue','resolved','high'),(5,'Synthetic minor issue','open','low')])
        env = dict(os.environ, PORT='18080', HOST='127.0.0.1', DB_PATH=str(db))
        with (Path(tmp) / 'mcp.log').open('w') as log:
            server = subprocess.Popen([sys.executable, str(ROOT / 'mcp_server/app.py')], env=env, stdout=log, stderr=log)
            try:
                for attempt in range(100):
                    if server.poll() is not None:
                        raise RuntimeError('Verification MCP server exited before startup')
                    try:
                        with socket.create_connection(('127.0.0.1', 18080), timeout=0.2):
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise TimeoutError('Verification MCP server did not start')
                asyncio.run(main(server, db, args.tools_only))
            finally:
                if server.poll() is None:
                    server.terminate()
                    server.wait(timeout=10)
