import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    yield


app = FastAPI(title="DeskFleet", version="0.1.0", lifespan=lifespan)

class ResolveRequest(BaseModel) :
    ticket: str
    order_id: str | None = None
    product_id: str | None = None

class ResolveResponse(BaseModel) :
    decision: str
    reply: str
    category: str


@app.get("/health")
async def health():
    return {"status":"ok"}

@app.post("/resolve", response_model=ResolveResponse)
async def resolve_ticket(req: ResolveRequest):
    return {"decision":req.ticket, "reply":req.order_id, "category": "dummy"}

app.mount("/", StaticFiles(directory="static", html=True), name = "static")