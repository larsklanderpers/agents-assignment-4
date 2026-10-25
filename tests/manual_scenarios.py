"""Run the supplied ten scenarios against repeatable synthetic sample data.

Usage: python tests/manual_scenarios.py --output docs/scenario_runs/part2.txt
Requires API access and free ports 18081, 10020, 10021, and 10022.
"""
import argparse
import asyncio
from contextlib import redirect_stdout
import importlib.util
import json
import re
import time
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from manual_part2 import ROOT, wait_ready
import test_scenarios


class BoundedScenarioClient(test_scenarios.A2AClient):
    """Add an overall scenario deadline without modifying supplied queries."""

    async def send_message(self, agent_url, message):
        """Fail the test after four minutes regardless of stream activity."""
        return await asyncio.wait_for(super().send_message(agent_url, message), timeout=240)


async def run_scenarios(processes):
    """Run the unchanged provided harness after actual card readiness checks."""
    await wait_ready(processes)
    test_scenarios.A2AClient = BoundedScenarioClient
    return await test_scenarios.main()


def main():
    """Start fixtures and save a comparable transcript for this checkpoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-mode', choices=['basic', 'advanced', 'parallel'], default='basic')
    args = parser.parse_args()
    for port in (18081, 10020, 10021, 10022):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', port))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='scenario-baseline-') as tmp:
        db = Path(tmp) / 'support.db'
        spec = importlib.util.spec_from_file_location('sample_setup', ROOT / 'database/database_setup.py')
        setup_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup_module)
        setup = setup_module.DatabaseSetup(str(db))
        setup.connect()
        setup.create_tables()
        setup.create_triggers()
        setup.insert_sample_data()
        setup.conn.close()
        env = dict(os.environ, HOST_AGENT_MODE=args.host_mode, SCENARIO_HOST_MODE=args.host_mode, PORT='18081', HOST='127.0.0.1', DB_PATH=str(db), PART2_TRACE=str(Path(tmp) / 'trace.jsonl'))
        processes, logs = [], []
        try:
            commands = [[sys.executable, str(ROOT / 'mcp_server/app.py')]] + [[sys.executable, str(ROOT / 'tests/manual_part2.py'), '--serve', name] for name in ('customer_data','support','host')]
            for index, command in enumerate(commands):
                log = (Path(tmp) / f'server-{index}.log').open('w')
                logs.append(log)
                processes.append(subprocess.Popen(command, env=env, stdout=log, stderr=log))
            metrics = []
            original_scenario = test_scenarios.test_scenario

            async def measured_scenario(*positional, **keyword):
                paths = list(Path(tmp).glob('server-*.log'))
                before = {path: len(path.read_text()) for path in paths}
                trace = Path(tmp) / 'trace.jsonl'
                trace_offset = len(trace.read_text()) if trace.exists() else 0
                started = time.perf_counter()
                passed = await original_scenario(*positional, **keyword)
                new_logs = {path.name: path.read_text()[offset:] for path, offset in before.items()}
                inputs = [json.loads(line) for line in trace.read_text()[trace_offset:].splitlines()] if trace.exists() else []
                row = {
                    'scenario': keyword.get('scenario_name', positional[0] if positional else ''),
                    'passed': passed,
                    'seconds': round(time.perf_counter() - started, 2),
                    'mcp_tool_calls': re.findall(r'\[TOOL\] ([^(]+)', new_logs.get('server-0.log', '')),
                    'customer_data_requests': new_logs.get('server-1.log', '').count('[Customer Data Agent] Received request'),
                    'support_requests': new_logs.get('server-2.log', '').count('[Support Agent] Received request'),
                    'model_requests': sum(r['agent'] in ('customer_data_agent', 'support_agent') for r in inputs),
                    'router_model_requests': sum(r['agent'] == 'query_router' for r in inputs),
                    'summary_model_requests': sum(r['agent'] == 'parallel_summary' for r in inputs),
                    'total_model_requests': len(inputs),
                    'routing_decisions': [json.loads(raw) for raw in re.findall(r'Routing decision: (\{[^\n]+\})', new_logs.get('server-3.log', ''))],
                }
                if args.host_mode == 'advanced':
                    pure_data = {
                        'Simple Query - Single Agent',
                        'Multi-Step Coordination - Complex Data Query',
                        'Data Aggregation - Statistical Analysis',
                    }
                    mode = 'data_only' if row['scenario'] in pure_data else 'sequential'
                    expected = (1, 0) if mode == 'data_only' else (1, 1)
                    observed = (row['customer_data_requests'], row['support_requests'])
                    decisions = row['routing_decisions']
                    route_ok = (observed == expected and row['router_model_requests'] == 1
                        and len(decisions) == 1 and decisions[0]['execution_mode'] == mode)
                    row['smoke_passed'] = passed
                    row['routing_contract_passed'] = route_ok
                    passed = passed and route_ok
                    row['passed'] = passed
                    print(f"Routing contract: {'PASS' if route_ok else 'FAIL'}; expected {mode} {expected}, observed {observed}")
                if args.host_mode == 'parallel':
                    execution_ok = (row['customer_data_requests'] == 1 and row['support_requests'] == 1
                        and row['summary_model_requests'] == 1)
                    row['smoke_passed'] = passed
                    row['parallel_contract_passed'] = execution_ok
                    passed = passed and execution_ok
                    row['passed'] = passed
                    print(f"Parallel execution contract: {execution_ok}")
                metrics.append(row)
                print('OBSERVED EXECUTION: ' + json.dumps(row), flush=True)
                return passed

            test_scenarios.test_scenario = measured_scenario
            with args.output.open('w', encoding='utf-8') as transcript:
                print('Checkpoint commit: ' + subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), file=transcript)
                print('Configured model: ' + os.environ.get('GEMINI_MODEL', '(default)'), file=transcript)
                print('Host mode: ' + args.host_mode, file=transcript)
                print('Fixture: original 15 sample customers and 25 tickets, newly seeded.', file=transcript)
                with redirect_stdout(transcript):
                    passed = asyncio.run(run_scenarios(processes))
            args.output.with_suffix('.metrics.json').write_text(json.dumps(metrics, indent=2) + '\n', encoding='utf-8')
            print(f'Scenario transcript: {args.output}; harness passed: {passed}', flush=True)
            return passed
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
            for log in logs:
                log.close()


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
