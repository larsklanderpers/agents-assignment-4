"""Strict Customer Data response contract and final-answer validation."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.genai import types


class StrictRecord(BaseModel):
    """Reject unknown fields and type coercion at every nested boundary."""
    model_config = ConfigDict(extra='forbid', strict=True)


class CustomerRecord(StrictRecord):
    """Customer fields exposed by the supplied database."""
    id: int = Field(gt=0)
    name: str
    email: str
    phone: str | None
    status: Literal['active', 'disabled']
    created_at: str | None
    updated_at: str | None


class TicketRecord(StrictRecord):
    """Ticket identity, issue, and exact database status/priority values."""
    id: int = Field(gt=0)
    customer_id: int = Field(gt=0)
    issue: str
    status: Literal['open', 'in_progress', 'resolved']
    priority: Literal['low', 'medium', 'high']
    created_at: str | None


class TicketStatistics(StrictRecord):
    """Explicit count fields; absent database groups must be represented by zero."""
    total_tickets: int = Field(ge=0)
    open: int = Field(ge=0)
    in_progress: int = Field(ge=0)
    resolved: int = Field(ge=0)
    high: int = Field(ge=0)
    medium: int = Field(ge=0)
    low: int = Field(ge=0)

    @model_validator(mode='after')
    def check_totals(self) -> 'TicketStatistics':
        """Reject internally contradictory status or priority totals."""
        if self.open + self.in_progress + self.resolved != self.total_tickets or self.high + self.medium + self.low != self.total_tickets:
            raise ValueError('Ticket statistics groups must sum to total_tickets')
        return self


class CustomerStatistics(StrictRecord):
    """Counts of all supplied account status values."""
    total_customers: int = Field(ge=0)
    active: int = Field(ge=0)
    disabled: int = Field(ge=0)

    @model_validator(mode='after')
    def check_totals(self) -> 'CustomerStatistics':
        """Reject internally contradictory account totals."""
        if self.active + self.disabled != self.total_customers:
            raise ValueError('Customer statistics groups must sum to total_customers')
        return self


class CompletedAction(StrictRecord):
    """A reported successful tool operation, with write IDs where applicable."""
    tool: Literal['get_customer', 'list_customers', 'add_customer', 'update_customer',
        'disable_customer', 'activate_customer', 'get_ticket', 'list_tickets',
        'create_ticket', 'update_ticket_status', 'update_ticket_priority',
        'delete_ticket', 'get_ticket_stats', 'get_customer_stats', 'search_tickets']
    description: str = Field(min_length=1)
    record_id: int | None

    @model_validator(mode='after')
    def require_write_id(self) -> 'CompletedAction':
        """Require a positive record ID for all reported write operations."""
        reads = {'get_customer','list_customers','get_ticket','list_tickets','get_ticket_stats','get_customer_stats','search_tickets'}
        if self.tool not in reads and (self.record_id is None or self.record_id <= 0):
            raise ValueError('Completed writes require a positive record_id')
        return self


class ResponseIssue(StrictRecord):
    """An explicit missing-information, absent-record, or tool-failure detail."""
    code: Literal['not_found', 'missing_identity', 'tool_error', 'unavailable', 'other']
    message: str = Field(min_length=1)


class CustomerDataResponse(StrictRecord):
    """Versioned final envelope; every field is required, even when empty/null."""
    schema_version: Literal['1.0']
    status: Literal['success', 'not_found', 'needs_clarification', 'error']
    summary: str = Field(min_length=1)
    customer_context: CustomerRecord | None
    customers: list[CustomerRecord]
    relevant_tickets: list[TicketRecord]
    ticket_statistics: TicketStatistics | None
    customer_statistics: CustomerStatistics | None
    completed_actions: list[CompletedAction]
    errors: list[ResponseIssue]

    @model_validator(mode='after')
    def require_issue_detail(self) -> 'CustomerDataResponse':
        """Require an explanation for non-success outcomes."""
        if self.status != 'success' and not self.errors:
            raise ValueError('Non-success responses require errors with explanatory details')
        return self


def parse_customer_data_response(text: str) -> CustomerDataResponse:
    """Parse raw JSON only; reject fences, missing fields, extras, and wrong types."""
    try:
        return CustomerDataResponse.model_validate_json(text, strict=True)
    except ValidationError as exc:
        raise RuntimeError('Customer Data response failed schema validation; no tools were retried. Earlier writes, if any, may already have committed.') from exc


def validate_model_response(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
    """Validate final text before emission while allowing intermediate tool calls."""
    if llm_response.error_code or llm_response.interrupted:
        raise RuntimeError('Customer Data generation failed or was interrupted; no tools were retried')
    if llm_response.partial:
        return None  # Streaming fragments are provisional, not complete answers.
    content = llm_response.content
    parts = content.parts or [] if content else []
    calls = [p.function_call for p in parts if p.function_call]
    final_calls = [call for call in calls if call.name == 'set_model_response']
    if final_calls:
        # The installed ADK fallback drops None fields after validating its args.
        # Convert its validated final declaration to text before tool dispatch;
        # no real tool is executed and no generation/workflow retry occurs.
        if len(calls) != 1 or len(final_calls) != 1:
            raise RuntimeError('Structured final response must not be mixed with tool operations')
        try:
            parsed = CustomerDataResponse.model_validate(final_calls[0].args, strict=True)
        except ValidationError as exc:
            raise RuntimeError('Customer Data response failed schema validation; no tools were retried. Earlier writes, if any, may already have committed.') from exc
        llm_response.content = types.Content(role='model', parts=[types.Part(text=parsed.model_dump_json())])
        return llm_response
    if calls or any(p.function_response for p in parts):
        return None
    text = ''.join(p.text or '' for p in parts if not p.thought)
    parsed = parse_customer_data_response(text)
    llm_response.content = types.Content(role='model', parts=[types.Part(text=parsed.model_dump_json())])
    return llm_response


def validate_completed_response(callback_context: CallbackContext) -> None:
    """Gate agent completion, including SDK-generated structured-output events."""
    for event in reversed(callback_context.session.events):
        if event.invocation_id != callback_context.invocation_id or event.author != callback_context.agent_name:
            continue
        if event.error_message:
            raise RuntimeError('Customer Data returned an error event')
        if event.is_final_response() and event.content:
            text = ''.join(p.text or '' for p in event.content.parts or [] if not p.thought)
            if text.strip():
                parse_customer_data_response(text)
                return
    raise RuntimeError('Customer Data completed without a current validated answer')
