import time
import json

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from app.state import TicketState
from app.consts import MAX_ITERS
from app.llm_consts import SYSTEM_MESSAGE_CLASSIFIER

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

def classifier_node(state: TicketState) -> dict:
    ticket_id = state.get("_ticket_id")

    content = (
        f"Ticket: {state['ticket']}\n"
        f"Order_Id: {state.get('order_id', 'none')}\n"
        f"Product_ID: {state.get('product_id', 'none')}"
    )
    messages = [
        SystemMessage(SYSTEM_MESSAGE_CLASSIFIER),
        HumanMessage(content)
    ]

    start = time.time()
    response = llm.invoke(messages)
    duration_ms = (time.time() - start ) * 1000

    category = response.content.strip().lower()
    if category not in ("order", "product", "refund", "other") :
        category = "other"

    usage = getattr(response, "usage_metadata", {}) or {}
    # input_details = usage.get("input_token_details", {}) or {}
    return {
        "category": category,
        "duration": duration_ms,
        "_input_tokens": usage.get("input_tokens", 0),
        "_output_tokens": usage.get("output_tokens", 0),
        "_cached_tokens": usage.get("cache_read", 0)
    }


def build_graph():
    graph = StateGraph(TicketState)

    graph.add_node("classifier", classifier_node)

    graph.set_entry_point("classifier")

    return graph.compile()

compiled_graph = build_graph()