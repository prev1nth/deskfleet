import time
import json

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from app.state import TicketState
from app.consts import MAX_ITERS
from app.llm_consts import SYSTEM_MESSAGE_CLASSIFIER
from app.tools import TOOL_REGISTRY, execute_tool, is_tool_allowed

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


async def researcher_node(state: TicketState) -> dict :
    ticket_id = state.get("_ticket_id")
    category = state["category"]
    ticket = state["ticket"]
    order_id = state.get("order_id")
    product_id = state.get("product_id")

    tool_schemas = [
        {"type": "function", "function": {"name": name, "description": info["description"], "parameters": info["parameters"]}}
        for name, info in TOOL_REGISTRY.items()
    ]

    # Build context message based on what we know
    context_parts = [f"Ticket: {ticket}"]
    if order_id:
        context_parts.append(f"Order ID: {order_id}")
    if product_id:
        context_parts.append(f"Product ID: {product_id}")

    messages = [
        SystemMessage(content=f"""You are a research agent. The ticket has been classified as: {category}.
Use the available tools to gather facts. You MUST call at least one tool.

IMPORTANT RULES:
- If order_id is provided, call get_order_status to get order details
- If product_id is provided, call get_product to get product details
- If BOTH order_id and product_id are provided:
  1. Call get_order_status to verify the order contains this product
  2. Call get_product to get full product details
- If the ticket asks about products in an order, you MUST:
  1. First call get_order_status to get the order details (including product IDs)
  2. Then call get_product for EACH product_id in the order to get full product details
- Gather ALL relevant information before responding

Available tools: {', '.join(TOOL_REGISTRY.keys())}"""),
        HumanMessage(content="\n".join(context_parts)),
    ]

    tool_calls_log = []
    all_facts = []
    total_input_tokens = 0
    total_output_tokens = 0
    total_cached_tokens = 0

    # max 3 rounds of tool calls before we just return what we have
    for _ in range(MAX_ITERS):
        start = time.time()
        response = llm.bind_tools(tool_schemas).invoke(messages)
        duration_ms = (time.time() - start) * 1000

        usage = getattr(response, "usage_metadata", {}) or {}

        input_details = usage.get("input_token_details", {}) or {}
        total_input_tokens += usage.get("input_tokens", 0)
        total_output_tokens += usage.get("output_tokens", 0)
        total_cached_tokens += input_details.get("cache_read", 0)

        messages.append(AIMessage(content=response.content or "", tool_calls=response.tool_calls))

        if not response.tool_calls:
            break

        for tc in response.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]

            if not is_tool_allowed(tool_name):
                # model tried to call something not in our allowlist
                tool_calls_log.append({"tool": tool_name, "args": tool_args, "result": {"error": "not in allowlist"}})
                messages.append(ToolMessage(content=json.dumps({"error": "Tool not allowed"}), tool_call_id=tc["id"]))
                continue

            
            result = await execute_tool(tool_name, ticket_id=ticket_id, **tool_args)
            tool_calls_log.append({"tool": tool_name, "args": tool_args, "result": result})
            all_facts.append(json.dumps(result))
            messages.append(ToolMessage(content=json.dumps(result), tool_call_id=tc["id"]))

    return {
        "facts": "\n".join(all_facts) if all_facts else "No facts gathered",
        "tool_calls": tool_calls_log,
        "_input_tokens": total_input_tokens,
        "_output_tokens": total_output_tokens,
        "_cached_tokens": total_cached_tokens,
    }

def build_graph():
    graph = StateGraph(TicketState)

    graph.add_node("classifier", classifier_node)
    graph.add_node("researcher", researcher_node)
    
    graph.set_entry_point("classifier")
    graph.add_edge("classifier", "researcher")
    
    return graph.compile()

compiled_graph = build_graph()