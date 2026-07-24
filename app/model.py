from pydantic import BaseModel

class ResolveRequest(BaseModel) :
    ticket: str
    order_id: str | None = None
    product_id: str | None = None

class ResolveResponse(BaseModel) :
    decision: str
    reply: str
    category: str