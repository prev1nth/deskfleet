from pydantic import BaseModel

class ResolveRequest(BaseModel) :
    ticket: str
    order_id: str | None = None
    product_id: str | None = None

class ResolveResponse(BaseModel) :
    decision: str
    reply: str
    category: str

class SearchRequest(BaseModel):
    query: str


class ProductRequest(BaseModel):
    product_id: int    