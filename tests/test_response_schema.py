"""Strict response parsing and real ADK tool/write boundary regressions."""
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
from customer_data_agent.agent import create_agent
from customer_data_agent.response_schema import (CustomerDataResponse, parse_customer_data_response,
    validate_model_response, validate_completed_response)
from google.adk.agents import BaseAgent, SequentialAgent
from google.adk.events import Event
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types


def envelope():
    """A minimal valid response, including every required nullable/list field."""
    return dict(schema_version='1.0', status='success', summary='Lookup completed',
        customer_context=None, customers=[], relevant_tickets=[], ticket_statistics=None,
        customer_statistics=None, completed_actions=[], errors=[])


class TestResponseSchema(unittest.TestCase):
    """Reject malformed structure without silently repairing model output."""

    def test_valid_success_and_error_envelopes(self):
        self.assertEqual(parse_customer_data_response(json.dumps(envelope())).schema_version, '1.0')
        for status, code in [('not_found','not_found'),('needs_clarification','missing_identity'),('error','tool_error')]:
            obj=envelope();obj.update(status=status, errors=[dict(code=code,message='Explanation')])
            self.assertEqual(parse_customer_data_response(json.dumps(obj)).status,status)

    def test_missing_extra_wrong_types_fences_and_invalid_nested_fields(self):
        cases=[]
        for key in envelope():
            obj=envelope();del obj[key];cases.append(json.dumps(obj))
        for update in [dict(schema_version='2.0'),dict(extra=True),dict(customers=None),dict(summary=7),
            dict(status='error'),dict(relevant_tickets=[dict(id='2',customer_id=5,issue='x',status='open',priority='high',created_at=None)]),
            dict(relevant_tickets=[dict(id=True,customer_id=5,issue='x',status='open',priority='high',created_at=None)]),
            dict(relevant_tickets=[dict(id=2,customer_id=5,issue='x',status='closed',priority='high',created_at=None)]),
            dict(completed_actions=[dict(tool='create_ticket',description='Created',record_id=None)]),
            dict(completed_actions=[dict(tool='refund',description='Refunded',record_id=1)]),
            dict(ticket_statistics=dict(total_tickets=3,open=1,in_progress=1,resolved=0,high=1,medium=1,low=1))]:
            obj=envelope();obj.update(update);cases.append(json.dumps(obj))
        cases += ['not json', '```json\n'+json.dumps(envelope())+'\n```']
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaisesRegex(RuntimeError,'failed schema validation'):
                    parse_customer_data_response(text)

    def test_nested_extras_rejected_and_created_id_preserved(self):
        obj=envelope();obj['completed_actions']=[dict(tool='create_ticket',description='Created ticket',record_id=2)]
        self.assertEqual(parse_customer_data_response(json.dumps(obj)).completed_actions[0].record_id,2)
        obj['completed_actions'][0]['unsupported']='extra'
        with self.assertRaises(RuntimeError):parse_customer_data_response(json.dumps(obj))

    def test_tool_calls_and_stream_fragments_not_mistaken_for_final_json(self):
        tool=LlmResponse(content=types.Content(parts=[types.Part(text='Looking up'),types.Part(function_call=types.FunctionCall(name='get_customer',args={'customer_id':5}))]))
        self.assertIsNone(validate_model_response(None,tool))
        self.assertIsNone(validate_model_response(None,LlmResponse(partial=True,content=types.Content(parts=[types.Part(text='{')]))))
        for response in [LlmResponse(content=types.Content(parts=[types.Part(text='invalid')])),LlmResponse(interrupted=True),LlmResponse(error_code='503')]:
            with self.assertRaises(RuntimeError):validate_model_response(None,response)

    def test_sdk_fallback_preserves_required_nulls_and_rejects_bad_or_mixed_args(self):
        def response(args, mixed=False):
            parts=[types.Part(function_call=types.FunctionCall(name='set_model_response',args=args))]
            if mixed:parts.append(types.Part(function_call=types.FunctionCall(name='create_ticket',args={})))
            return LlmResponse(content=types.Content(role='model',parts=parts))
        result=validate_model_response(None,response(envelope()))
        parsed=json.loads(result.content.parts[0].text)
        self.assertIn('customer_context',parsed)
        self.assertIsNone(parsed['customer_context'])
        with self.assertRaisesRegex(RuntimeError,'failed schema'):
            validate_model_response(None,response({'summary':'missing fields'}))
        with self.assertRaisesRegex(RuntimeError,'mixed'):
            validate_model_response(None,response(envelope(),mixed=True))

    def test_completion_gate_rejects_old_turn_and_malformed_final(self):
        ctx=SimpleNamespace(invocation_id='now',agent_name='customer_data_agent',session=SimpleNamespace(events=[]))
        ctx.session.events=[Event(author=ctx.agent_name,invocation_id='old',content=types.Content(parts=[types.Part(text=json.dumps(envelope()))]))]
        with self.assertRaisesRegex(RuntimeError,'without a current'):validate_completed_response(ctx)
        ctx.session.events.append(Event(author=ctx.agent_name,invocation_id='now',content=types.Content(parts=[types.Part(text='bad')])) )
        with self.assertRaisesRegex(RuntimeError,'failed schema'):validate_completed_response(ctx)


class FixtureModel(BaseLlm):
    """Emit one write request, then a controlled final answer without API access."""
    calls: int = 0
    final_text: str
    use_fallback: bool = False

    async def generate_content_async(self,llm_request,stream=False):
        self.calls += 1
        if self.calls == 1:
            yield LlmResponse(content=types.Content(role='model',parts=[types.Part(function_call=types.FunctionCall(name='create_ticket',args={'customer_id':5,'issue':'Fixture write'}))]))
        else:
            part=types.Part(function_call=types.FunctionCall(name='set_model_response',args=json.loads(self.final_text))) if self.use_fallback else types.Part(text=self.final_text)
            yield LlmResponse(content=types.Content(role='model',parts=[part]))


class NextAgent(BaseAgent):
    """Observe whether downstream execution starts after validation."""
    calls: Any

    async def _run_async_impl(self,ctx):
        self.calls.append('downstream')
        yield Event(author=self.name,invocation_id=ctx.invocation_id,content=types.Content(parts=[types.Part(text='Support reached')]))


class TestADKValidation(unittest.IsolatedAsyncioTestCase):
    """Use actual ADK tool execution and SQLite, not only direct parser calls."""

    async def run_case(self,valid,fallback=False):
        conn=sqlite3.connect(':memory:');conn.execute('CREATE TABLE tickets(id INTEGER PRIMARY KEY,customer_id INTEGER,issue TEXT)')
        def create_ticket(customer_id:int,issue:str)->dict:
            """Create a fixture row once; never call a real service."""
            cur=conn.execute('INSERT INTO tickets(customer_id,issue) VALUES (?,?)',(customer_id,issue));conn.commit()
            return dict(id=cur.lastrowid,customer_id=customer_id,issue=issue)
        obj=envelope();obj['completed_actions']=[dict(tool='create_ticket',description='Created ticket',record_id=1)]
        data=create_agent();data.tools=[FunctionTool(create_ticket)]
        model=FixtureModel(model='gemini-3.8-flash',final_text=json.dumps(obj) if valid else '{"ticket_id":"one"}',use_fallback=fallback)
        data.model=model
        downstream=[]
        root=SequentialAgent(name='schema_test',sub_agents=[data,NextAgent(name='next_agent',calls=downstream)])
        sessions=InMemorySessionService();await sessions.create_session(app_name='schema_test',user_id='u',session_id='s')
        runner=Runner(app_name='schema_test',agent=root,session_service=sessions)
        async def invoke():
            return [event async for event in runner.run_async(user_id='u',session_id='s',new_message=types.Content(role='user',parts=[types.Part(text='Create one ticket')]))]
        try:
            async with runner:
                if valid:
                    events=await invoke()
                    text=next(''.join(p.text or '' for p in e.content.parts) for e in events if e.author=='customer_data_agent' and e.is_final_response() and e.content)
                    self.assertEqual(parse_customer_data_response(text).completed_actions[0].record_id,1)
                    self.assertEqual(downstream,['downstream'])
                else:
                    with self.assertRaisesRegex(RuntimeError,'failed schema validation'):await invoke()
                    self.assertEqual(downstream,[])
            self.assertEqual(conn.execute('SELECT count(*) FROM tickets').fetchone()[0],1)
            self.assertEqual(model.calls,2,'Validation restarted the model/tool workflow')
        finally:conn.close()

    async def test_invalid_final_after_write_fails_without_retry_or_handoff(self):
        await self.run_case(False)

    async def test_valid_final_after_write_preserves_id_and_allows_handoff(self):
        await self.run_case(True)


    async def test_sdk_fallback_after_write_valid_and_invalid(self):
        await self.run_case(True,True)
        await self.run_case(False,True)


if __name__=='__main__':unittest.main()
