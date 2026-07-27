import os
import time
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from app.guardrails import scan_resolve_request
from app.model import ResolveRequest, ResolveResponse

from app.graph import compiled_graph



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
    if scan["injection_detected"] :
        resp = ResolveResponse(
            decision = "REFUSE",
            reply = "This ticket has been flagged and cannot be processed.",
            category = "refused"

        )

        return resp

    cleaned_ticket = scan["cleaned"]
    ticket_id += 1
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
    # async for chunk in compiled_graph.astream(initial_state, stream_mode= "messages"):

    # output = result.get("draft", "")
    latency = time.time() - start 
    return ResolveResponse(
        decision= "Researched",
        category= str(result.get("tool_calls")),
        reply=(f"input tokens:{result.get("_input_tokens")}, "
            f"output tokens : {result.get("_output_tokens")}")
    )

@app.get("/metrics/raw")
async def metrics_raw():
    return {}

app.mount("/", StaticFiles(directory="static", html=True), name = "static")