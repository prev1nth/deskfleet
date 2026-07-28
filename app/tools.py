import httpx
import time

FAKESTORE_BASE = "https://fakestoreapi.com"

TOOL_REGISTRY = {
    "get_order_status": {
        "description": "Get the status of an order by order ID",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order ID to look up"}
            },
            "required": ["order_id"],
        },
    },
    "get_product": {
        "description": "Get product details by product ID",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "The product ID"}
            },
            "required": ["product_id"],
        },
    },
    "search_products": {
        "description": "Search products by query string",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"],
        },
    },
}

async def get_order_status(order_id: str) -> dict:
    url = f"{FAKESTORE_BASE}/carts/{order_id}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "_url": url,
                    "_method": "GET",
                    "_status_code": resp.status_code,
                    "order_id": order_id,
                    "status": "shipped",
                    "date": data.get("date", "unknown"),
                    "user_id": data.get("userId"),
                    "products": [
                        {"product_id": p.get("productId"), "quantity": p.get("quantity")}
                        for p in data.get("products", [])
                    ],
                }
            return {"_url": url, "_method": "GET", 
                    "_status_code": resp.status_code, "order_id": order_id, 
                    "status": "not_found", "error": "Order not found"}
    except Exception as e:
        return {"_url": url, "_method": "GET", "order_id": order_id, "status": "error", "error": str(e)}


async def get_product(product_id: int):
    url = f"{FAKESTORE_BASE}/products/{product_id}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200 :
                data = resp.json()
                return {
                    "_url": url,
                    "_method": "GET",
                    "_status_code": resp.status_code,
                    "product_id": product_id,
                    "title": data.get("title"),
                    "price": data.get("price"),
                    "category": data.get("category"),
                    "description": data.get("description"),
                    "rating": data.get("rating", {}).get("rate"),
                }
            return {"_url": url, "_method": "GET", "_status_code": resp.status_code, "product_id": product_id, "error": "Product not found"}
    except Exception as e:
        return {"_url": url, "_method": "GET", "product_id": product_id, "error": str(e)}


async def search_products(query: str) -> dict:
    url = f"{FAKESTORE_BASE}/products"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                products = resp.json()
                matches = [
                    p for p in products if query.lower() in p.get("title", "").lower()
                    or query.lower() in p.get("category", "").lower()
                ]
                return {
                    "_url": url,
                    "_method": "GET",
                    "_status_code": resp.status_code,
                    "query": query,
                    "count": len(matches),
                    "results": [
                        {"id": p.get("id"), "title": p.get("title"), "price": p.get("price")}
                        for p in matches[:5]
                    ],
                }
            return {"_url": url, "_method": "GET", "_status_code": resp.status_code, "query": query, "count": 0, "results": []}
    except Exception as e:
        return {"_url": url, "_method": "GET", "query": query, "count": 0, "error": str(e)}


async def search_products_with_orders(query: str) -> list[dict]:
    """Search products and return which orders contain them."""
    products_url = f"{FAKESTORE_BASE}/products"
    carts_url = f"{FAKESTORE_BASE}/carts"
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Get all products
            products_resp = await client.get(products_url)
            carts_resp = await client.get(carts_url)
            
            if products_resp.status_code != 200 or carts_resp.status_code != 200:
                return []
            
            products = products_resp.json()
            carts = carts_resp.json()
            
            # Find matching products
            matching_products = [
                p for p in products if query.lower() in p.get("title", "").lower()
                or query.lower() in p.get("category", "").lower()
            ]
            
            # For each matching product, find which orders contain it
            results = []
            for product in matching_products[:5]:  # Limit to 5 products
                product_id = product.get("id")
                orders_containing = []
                
                for cart in carts:
                    for cart_product in cart.get("products", []):
                        if cart_product.get("productId") == product_id:
                            orders_containing.append({
                                "order_id": str(cart.get("id")),
                                "quantity": cart_product.get("quantity"),
                                "order_date": cart.get("date"),
                            })
                
                results.append({
                    "product_id": product_id,
                    "title": product.get("title"),
                    "price": product.get("price"),
                    "category": product.get("category"),
                    "orders": orders_containing,
                })
            
            return results
    except Exception as e:
        return []


async def get_orders(limit: int = 100) -> list[dict]:
    url = f"{FAKESTORE_BASE}/carts"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                carts = resp.json()
                orders = []
                for cart in carts[:limit]:
                    orders.append({
                        "order_id": str(cart.get("id")),
                        "user_id": cart.get("userId"),
                        "date": cart.get("date", "unknown"),
                        "product_count": len(cart.get("products", [])),
                        "products": [
                            {"product_id": p.get("productId"), "quantity": p.get("quantity")}
                            for p in cart.get("products", [])[:3]
                        ],
                    })
                return orders
            return []
    except Exception as e:
        return []


TOOL_FUNCTIONS = {
    "get_order_status": get_order_status,
    "get_product": get_product,
    "search_products": search_products,
}


def is_tool_allowed(tool_name: str) -> bool:
    return tool_name in TOOL_REGISTRY


async def execute_tool(tool_name: str, ticket_id: int = None, **kwargs) -> dict :
    from app.storage import save_trace

    if not is_tool_allowed(tool_name):
        return {"error": f"Tool '{tool_name}' not in allowlist", "allowed_tools": list(TOOL_REGISTRY.keys())}

    func = TOOL_FUNCTIONS.get(tool_name)
    start = time.time()
    result = await func(**kwargs)
    duration_ms = (time.time() - start) * 1000

    if ticket_id:
        actual_url = result.get("_url", f"{FAKESTORE_BASE}/{tool_name.replace('_', '/')}")
        save_trace(
            ticket_id=ticket_id,
            step_type="api_call",
            step_name=tool_name,
            request={"url": actual_url, "method": "GET", "params": kwargs},
            response={k: v for k, v in result.items() if not k.startswith('_')},
            metadata={
                "url": actual_url,
                "method": "GET",
                "status_code": result.get("_status_code"),
                "duration_ms": duration_ms,
            },
            duration_ms=duration_ms,
        )

    return result
