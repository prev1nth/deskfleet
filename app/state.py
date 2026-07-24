from typing import TypedDict

class TicketState(TypedDict):
    ticket: str
    order_id: str | None
    product_id: str | None
    category: str
    facts: str
    draft: str
    decision: str
    escalation_reason: str
    tool_calls: list[dict]
    iterations: int
    max_iterations: int
    trace_url: str | None
    _ticket_id: int | None
    _input_tokens: int
    _output_tokens: int
    _cached_tokens: int
