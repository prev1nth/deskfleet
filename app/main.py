import os
import time
import json
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from app.guardrails import scan_resolve_request, scan_input, scan_output
from app.model import ResolveRequest, ResolveResponse, SearchRequest, ProductRequest

from app.graph import compiled_graph
from app.metrics import record_ticket, calculate_cost
from app.storage import save_ticket, save_trace, get_tickets, get_ticket, get_ticket_traces, get_ticket_tool_calls, get_stats
from app.tools import search_products, get_product, get_orders, search_products_with_orders
from app.quota import is_over_quota, quota_exceeded_response


from prometheus_client import generate_latest


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    yield


app = FastAPI(title="DeskFleet", version="0.1.0", lifespan=lifespan)

ticket_id = 0


@app.get("/health")
async def health():
    return {"status":"ok"}

@app.post("/resolve", response_model=ResolveResponse)
async def resolve_ticket(req: ResolveRequest):
    global ticket_id
    start = time.time()

    #1. scan for prompt injection
    scan = scan_resolve_request(req)
    if scan["injection_detected"]:
        latency = time.time() - start
        record_ticket("REFUSE", latency)

        # Save ticket with trace
        ticket_id = save_ticket(
            body=req.ticket,
            category="refused",
            decision="REFUSE",
            reply="This ticket has been flagged and cannot be processed.",
            escalation_reason="Prompt injection detected",
            tool_calls=[],
        )
        save_trace(
            ticket_id=ticket_id,
            step_type="validation",
            step_name="injection_detection",
            request={"input": req.ticket},
            response={"injection_detected": True, "cleaned": scan["cleaned"]},
            metadata={"patterns_matched": True},
        )

        return ResolveResponse(
            decision="REFUSE",
            reply="This ticket has been flagged and cannot be processed.",
            tool_calls=[],
            trace_url=None,
            category="refused",
            escalation_reason="Prompt injection detected",
        )

    cleaned_ticket = scan["cleaned"]

    # Check OpenAI spend cap
    if is_over_quota():
        quota = quota_exceeded_response()
        latency = time.time() - start
        record_ticket("QUOTA_EXCEEDED", latency)
        return JSONResponse(status_code=429, content=quota)

    # Save initial ticket to get ID
    ticket_id = save_ticket(
        body=cleaned_ticket,
        category="",
        decision="PENDING",
        reply="",
        escalation_reason="",
        tool_calls=[],
    )

    # Log input validation trace
    save_trace(
        ticket_id=ticket_id,
        step_type="validation",
        step_name="input_scan",
        request={"input": req.ticket},
        response={"injection_detected": False, "cleaned": cleaned_ticket},
        metadata={"pii_redacted": req.ticket != cleaned_ticket},
    )

    initial_state = {
        "ticket": cleaned_ticket,
        "order_id": req.order_id,
        "product_id": req.product_id,
        "category": "",
        "facts": "",
        "draft": "",
        "decision": "",
        "escalation_reason": "",
        "tool_calls": [],
        "iterations": 0,
        "max_iterations": 3,
        "trace_url": None,
        "_ticket_id": ticket_id,
        "_input_tokens": 0,
        "_output_tokens": 0,
        "_cached_tokens": 0,
    }

    result = await compiled_graph.ainvoke(initial_state)

    # redact any PII that slipped into the reply
    original_draft = result.get("draft", "")
    result["draft"] = scan_output(original_draft)

    # Log output validation trace
    save_trace(
        ticket_id=ticket_id,
        step_type="validation",
        step_name="output_scan",
        request={"draft": original_draft},
        response={"redacted_draft": result["draft"]},
        metadata={"pii_redacted": original_draft != result["draft"]},
    )

    latency = time.time() - start
    input_tokens = result.get("_input_tokens", 0)
    output_tokens = result.get("_output_tokens", 0)
    cached_tokens = result.get("_cached_tokens", 0)

    decision = result.get("decision", "ERROR")
    record_ticket(decision, latency, input_tokens, output_tokens, cached_tokens=cached_tokens)

    # Update ticket with final result
    from app.storage import get_conn
    conn = get_conn()
    conn.execute(
        """UPDATE tickets SET category=?, decision=?, reply=?, escalation_reason=?, tool_calls=?
            WHERE id=?""",
        (
            result.get("category", ""),
            decision,
            result.get("draft", ""),
            result.get("escalation_reason", ""),
            str(result.get("tool_calls", [])),
            ticket_id,
        ),
    )
    
    # Save tool_calls to separate table
    tool_calls = result.get("tool_calls", [])
    for tc in tool_calls:
        conn.execute(
            """INSERT INTO tool_calls (ticket_id, tool_name, arguments, result)
                VALUES (?, ?, ?, ?)""",
            (ticket_id, tc.get("tool"), json.dumps(tc.get("args", {})), json.dumps(tc.get("result", {}))),
        )
    
    conn.commit()
    conn.close()

    return ResolveResponse(
        decision=decision,
        reply=result.get("draft", ""),
        tool_calls=result.get("tool_calls", []),
        trace_url=result.get("trace_url"),
        category=result.get("category", ""),
        escalation_reason=result.get("escalation_reason") or None,
    )


@app.get("/metrics")
async def metrics():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/metrics.html")


@app.get("/metrics/prometheus")
async def metrics_prometheus():
    from app.metrics import DESKFLEET_REGISTRY
    from prometheus_client import generate_latest
    return PlainTextResponse(generate_latest(DESKFLEET_REGISTRY).decode(), media_type="text/plain")


@app.get("/metrics/raw")
async def metrics_raw():
    from app.metrics import DESKFLEET_REGISTRY
    from prometheus_client import generate_latest

    # Get database stats
    db_stats = get_stats()

    # Get persisted metrics from database (source of truth)
    from app.storage import get_all_metrics
    db_metrics = get_all_metrics()

    # Also get prometheus in-memory counters
    prom_text = generate_latest(DESKFLEET_REGISTRY).decode()
    metrics = {}
    for line in prom_text.splitlines():
        if line.startswith("# HELP"):
            parts = line.split(" ", 3)
            current_name = parts[2]
            metrics[current_name] = {"help": parts[3] if len(parts) > 3 else "", "type": "", "value": 0, "by_label": {}}
        elif line.startswith("# TYPE"):
            parts = line.split(" ")
            current_name = parts[2]
            if current_name not in metrics:
                metrics[current_name] = {"type": "", "value": 0, "by_label": {}}
            metrics[current_name]["type"] = parts[3]
        elif line and not line.startswith("#"):
            parts = line.split(" ", 1)
            full_name = parts[0]
            val = float(parts[1]) if len(parts) > 1 else 0
            if "{" in full_name:
                base_name = full_name.split("{")[0]
                label_str = full_name.split("{")[1].rstrip("}")
                labels = {}
                for pair in label_str.split(","):
                    k, v = pair.split("=", 1)
                    labels[k] = v.strip('"')
                if base_name not in metrics:
                    metrics[base_name] = {"type": "", "value": 0, "by_label": {}}
                label_key = ", ".join(f"{k}={v}" for k, v in sorted(labels.items()))
                metrics[base_name]["by_label"][label_key] = val
            else:
                if full_name not in metrics:
                    metrics[full_name] = {"type": "", "value": 0, "by_label": {}}
                metrics[full_name]["value"] = val

    # Compute latency stats from traces table
    from app.storage import get_conn
    conn = get_conn()
    latency_rows = conn.execute(
        "SELECT duration_ms FROM traces WHERE step_type = 'llm_call' AND duration_ms IS NOT NULL"
    ).fetchall()
    conn.close()
    latencies = [row[0] for row in latency_rows]
    avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0
    p50_latency_ms = sorted(latencies)[len(latencies) // 2] if latencies else 0
    p95_latency_ms = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0
    max_latency_ms = max(latencies) if latencies else 0

    # Use database values as source of truth (persists across restarts)
    def db_val(metric_name):
        return db_metrics.get(metric_name, 0)

    # Tool calls come from tool_calls table (has historical data)
    tool_calls_count = db_stats.get("tool_calls", {})
    tool_calls_total = sum(tool_calls_count.values())

    # Latency histogram
    latency_hist = {}
    bucket_data = metrics.get("deskfleet_ticket_latency_seconds_bucket", {})
    for label_key, val in bucket_data.get("by_label", {}).items():
        le = label_key.split("=", 1)[1] if "=" in label_key else "unknown"
        latency_hist[le] = val

    latency_sum = metrics.get("deskfleet_ticket_latency_seconds_sum", {}).get("value", 0)
    latency_count = metrics.get("deskfleet_ticket_latency_seconds_count", {}).get("value", 0)

    return {
        "database": db_stats,
        "prometheus": {
            "deskfleet_tickets_total": db_val("tickets"),
            "deskfleet_input_tokens_total": db_val("input_tokens"),
            "deskfleet_output_tokens_total": db_val("output_tokens"),
            "deskfleet_cached_tokens_total": db_val("cached_tokens"),
            "deskfleet_input_cost_usd_total": db_val("input_cost"),
            "deskfleet_output_cost_usd_total": db_val("output_cost"),
            "deskfleet_cached_cost_usd_total": db_val("cached_cost"),
            "deskfleet_tool_calls_total": tool_calls_total,
            "deskfleet_ticket_latency": {
                "histogram": latency_hist,
                "sum": latency_sum,
                "count": latency_count,
                "avg": latency_sum / latency_count if latency_count else 0,
            },
        },
        "latency_stats": {
            "avg_ms": round(avg_latency_ms, 1),
            "p50_ms": round(p50_latency_ms, 1),
            "p95_ms": round(p95_latency_ms, 1),
            "max_ms": round(max_latency_ms, 1),
            "total_llm_calls": len(latencies),
        },
    }
    
@app.post("/api/search-products")
async def api_search_products(req: SearchRequest):
    return await search_products(req.query)


@app.post("/api/search-products-with-orders")
async def api_search_products_with_orders(req: SearchRequest):
    return await search_products_with_orders(req.query)


@app.post("/api/get-product")
async def api_get_product(req: ProductRequest):
    return await get_product(req.product_id)


@app.get("/api/orders")
async def api_list_orders(limit: int = 100):
    return {"orders": await get_orders(limit)}


@app.get("/api/tickets")
async def api_list_tickets(limit: int = 50, offset: int = 0):
    return {"tickets": get_tickets(limit, offset), "stats": get_stats()}


@app.get("/api/tickets/{ticket_id}")
async def api_get_ticket(ticket_id: int):
    ticket = get_ticket(ticket_id)
    if not ticket:
        return {"error": "Ticket not found"}
    return {
        "ticket": ticket,
        "traces": get_ticket_traces(ticket_id),
        "tool_calls": get_ticket_tool_calls(ticket_id),
    }


@app.get("/admin")
async def admin_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin.html")

# Serve static files AFTER API routes
app.mount("/", StaticFiles(directory="static", html=True), name = "static")