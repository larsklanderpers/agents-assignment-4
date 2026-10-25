"""Conditional A2A orchestration with explicit, per-request routing decisions."""
import json
import logging
import os
import re
import sys
from typing import Literal, TypedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import a2a_compat  # noqa: F401 - before RemoteA2aAgent
from google.adk.agents import Agent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.genai import types
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from shared.agents_config import CUSTOMER_DATA_AGENT_URL, SUPPORT_AGENT_URL, GEMINI_MODEL

logger = logging.getLogger(__name__)


class RoutingDecision(TypedDict):
    """A routing contract enforced by callbacks, not by free-form model output."""

    needs_data: bool
    needs_support: bool
    urgency: Literal['low', 'medium', 'high']
    execution_mode: Literal['sequential', 'data_only', 'support_only']
    reason: str


def analyze_query_intent(query: str) -> RoutingDecision:
    """Choose specialists using bounded phrases; uncertain requests run both.

    Pure record queries do not become support requests merely because a ticket
    description mentions an issue/password. Limited explicit negation is handled;
    this is a transparent rule-based analyzer, not unrestricted language parsing.
    Urgency is descriptive and never authorizes writes or external escalation.
    """
    text = ' '.join(query.casefold().split())
    not_urgent = bool(re.search(r"\b(?:not urgent|no rush|low priority|whenever you can)\b", text))
    urgency_text = re.sub(r'\bnot urgent\b', '', text)
    urgency: Literal['low', 'medium', 'high'] = 'high' if re.search(r'\b(?:urgent|urgently|immediately|asap|critical|immediate)\b', urgency_text) else ('low' if not_urgent else 'medium')
    # Remove explicit negation of a support request, not arbitrary surrounding text.
    active = re.sub(r"\b(?:do not|don't|without|no)\s+(?:(?:need|provide|give|any|want|for)\s+)*(?:support|help|troubleshooting|guidance|advice)(?:\s+(?:guidance|assistance))?\b", '', text)
    support_text = active
    if re.search(r'^(?:please\s+)?(?:get|show|list|find|search|retrieve)\b', active):
        support_text = re.sub(r'"[^"]*"|(?<!\w)\'[^\']*\'(?!\w)', '', active)
    support_text = re.sub(r'\bsupport(?=\s+tickets?\b)', '', support_text)
    support = bool(re.search(r'\b(?:support|help|assist|assistance|troubleshoot|troubleshooting|guidance|solutions?|advice|fix|solve|explain)\b', support_text))
    reported_problem = bool(re.search(r"\b(?:cannot|can't|unable|failing|failed|charged|cancel)\b", support_text))
    support |= bool(re.search(r'\bhow\b.*\b(?:reset|login|log in|password|payment|export)\b|\b(?:reset|change) my password\b', support_text))
    records = bool(re.search(r'\b(?:customers?|accounts?|tickets?|statistics|stats)\b', active))
    lookup = bool(re.search(r'\b(?:get|show|list|find|search|retrieve|check|lookup|look up|statistics|stats|history|status|details|information|how many)\b', active))
    writes = bool(re.search(r'\b(?:create|open|update|close|delete|disable|activate|add)\b', active))
    descriptive_lookup = records and lookup and bool(re.search(
        r'^(?:please\s+)?(?:get|show|list|find|search|retrieve)\b', active))
    personal_problem = bool(re.search(r"\b(?:i|we)\s+(?:cannot|can't|am unable|are unable)\b", active))
    support |= reported_problem and (not descriptive_lookup or personal_problem)
    identity = bool(re.search(r'\b(?:customer|account|user|ticket|id)\s*(?:id\s*)?[:#]?\s*\d+\b|[\w.+-]+@[\w.-]+\.[a-z]+', active))
    data = (records and (lookup or writes)) or identity
    # Personal account problems need lookup/clarification; general how-to does not.
    data |= support and bool(re.search(r'\b(?:my|our) account\b', active)) and not bool(re.search(r'\bhow\b', active))
    if not data and not support:
        data = support = True
        reason = 'Ambiguous intent; retain both specialists for lookup clarification and guidance.'
    elif data and support:
        reason = 'Account/record context and support guidance are both requested.'
    elif data:
        reason = 'Record lookup or management only; support guidance is not requested.'
    else:
        reason = 'General support guidance without a record lookup requirement.'
    return RoutingDecision(needs_data=bool(data), needs_support=bool(support), urgency=urgency,
        execution_mode='sequential' if data and support else ('data_only' if data else 'support_only'), reason=reason)


def prepare_routing(callback_context: CallbackContext) -> None:
    """Replace routing state and clear cached data for every invocation."""
    content = callback_context.user_content
    query = ' '.join(part.text for part in (content.parts or []) if part.text) if content else ''
    decision = analyze_query_intent(query)
    callback_context.state['routing_decision'] = decision
    callback_context.state['routing_invocation_id'] = callback_context.invocation_id
    callback_context.state['temp:customer_data_response'] = None
    logger.info('Routing decision: %s', json.dumps(decision, sort_keys=True))


def _current_decision(context: ReadonlyContext) -> dict:
    """Reject stale or malformed decisions; an empty decision runs both agents."""
    decision = context.state.get('routing_decision')
    if context.state.get('routing_invocation_id') != context.invocation_id or not isinstance(decision, dict):
        return {}
    data, support = decision.get('needs_data'), decision.get('needs_support')
    if type(data) is not bool or type(support) is not bool or not (data or support):
        return {}
    mode = 'sequential' if data and support else ('data_only' if data else 'support_only')
    if decision.get('urgency') not in ('low', 'medium', 'high') or not isinstance(decision.get('reason'), str):
        return {}
    if decision.get('execution_mode') != mode:
        return {}
    return decision


def should_run_customer_data_agent(callback_context: CallbackContext) -> types.Content | None:
    """Run unless a valid current decision explicitly excludes data access."""
    if _current_decision(callback_context).get('needs_data') is False:
        return types.Content(role='model', parts=[])
    return None


def remember_customer_data(callback_context: CallbackContext) -> None:
    """Preserve the current remote data answer for a later Support skip."""
    for event in reversed(callback_context.session.events):
        if event.invocation_id == callback_context.invocation_id and event.author == callback_context.agent_name:
            if event.error_message:
                raise RuntimeError(event.error_message)
            if event.content and any(part.text for part in event.content.parts or []):
                callback_context.state['temp:customer_data_response'] = event.content.model_dump(mode='json', exclude_none=True)
                return
    if _current_decision(callback_context).get('needs_data') is not False:
        raise RuntimeError('Customer Data completed without a text answer')


def should_run_support_agent(callback_context: CallbackContext) -> types.Content | None:
    """Skip Support on data-only routes while preserving the useful data answer."""
    if _current_decision(callback_context).get('needs_support') is False:
        response = callback_context.state.get('temp:customer_data_response')
        if not response:
            raise RuntimeError('Data-only routing has no current Customer Data answer')
        return types.Content.model_validate(response)
    return None


def create_router_instruction(readonly_context: ReadonlyContext) -> str:
    """Read the decision persisted by prepare_routing; never mutate readonly state."""
    decision = _current_decision(readonly_context)
    return (
        'You are an internal task planner. The callbacks enforce this routing decision: '
        + json.dumps(decision, sort_keys=True)
        + '. Return one short internal sentence describing the tasks for the selected specialists. '
        'Prefix that sentence with ROUTING_PLAN:. '
        'Do not answer the customer, invent records, change the route, perform actions, '
        'or promise escalation. The specialists provide the final answer. Urgency is '
        'context for guidance, not authorization for writes. No tools are available to you.'
    )


def create_agent() -> SequentialAgent:
    """Build Router → conditional Customer Data → conditional Support over A2A."""
    router = Agent(name='query_router', model=GEMINI_MODEL,
        instruction=create_router_instruction, before_agent_callback=prepare_routing)
    customer_data = RemoteA2aAgent(name='customer_data',
        description='Retrieve/manage customer and ticket records',
        agent_card=f'{CUSTOMER_DATA_AGENT_URL}{AGENT_CARD_WELL_KNOWN_PATH}',
        before_agent_callback=should_run_customer_data_agent,
        after_agent_callback=remember_customer_data)
    support = RemoteA2aAgent(name='support_specialist',
        description='Provide customer support and troubleshooting',
        agent_card=f'{SUPPORT_AGENT_URL}{AGENT_CARD_WELL_KNOWN_PATH}',
        before_agent_callback=should_run_support_agent)
    return SequentialAgent(name='advanced_customer_support_host', sub_agents=[router,
        SequentialAgent(name='conditional_execution', sub_agents=[customer_data, support])])
