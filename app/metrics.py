from prometheus_client import Counter, Histogram, CollectorRegistry

# Use a custom registry so we can control what gets exposed
DESKFLEET_REGISTRY = CollectorRegistry()

TICKET_COUNTER = Counter(
    "deskfleet_tickets_total",
    "Total tickets processed",
    ["decision"],
    registry=DESKFLEET_REGISTRY,
)

TICKET_LATENCY = Histogram(
    "deskfleet_ticket_latency_seconds",
    "Per-ticket processing latency",
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
    registry=DESKFLEET_REGISTRY,
)

INPUT_TOKENS = Counter(
    "deskfleet_input_tokens_total",
    "Total input tokens consumed",
    ["model", "decision"],
    registry=DESKFLEET_REGISTRY,
)

OUTPUT_TOKENS = Counter(
    "deskfleet_output_tokens_total",
    "Total output tokens consumed",
    ["model", "decision"],
    registry=DESKFLEET_REGISTRY,
)

CACHED_TOKENS = Counter(
    "deskfleet_cached_tokens_total",
    "Total cached input tokens",
    ["model", "decision"],
    registry=DESKFLEET_REGISTRY,
)

INPUT_COST = Counter(
    "deskfleet_input_cost_usd_total",
    "Cost of input tokens in USD",
    ["model", "decision"],
    registry=DESKFLEET_REGISTRY,
)

OUTPUT_COST = Counter(
    "deskfleet_output_cost_usd_total",
    "Cost of output tokens in USD",
    ["model", "decision"],
    registry=DESKFLEET_REGISTRY,
)

CACHED_COST = Counter(
    "deskfleet_cached_cost_usd_total",
    "Cost of cached input tokens in USD",
    ["model", "decision"],
    registry=DESKFLEET_REGISTRY,
)

TOOL_CALL_COUNTER = Counter(
    "deskfleet_tool_calls_total",
    "Total tool calls made",
    ["tool_name"],
    registry=DESKFLEET_REGISTRY,
)


def calculate_cost(input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> dict:
    regular_input_tokens = input_tokens - cached_input_tokens

    input_cost = regular_input_tokens / 1_000_000 * 0.15
    cached_cost = cached_input_tokens / 1_000_000 * 0.075
    output_cost = output_tokens / 1_000_000 * 0.60

    return {
        "input_cost": input_cost,
        "cached_cost": cached_cost,
        "output_cost": output_cost,
        "total_cost": input_cost + cached_cost + output_cost,
        "regular_input_tokens": regular_input_tokens,
    }


def record_ticket(
    decision: str,
    latency: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    model: str = "gpt-4o-mini",
):
    from app.storage import save_metric

    TICKET_COUNTER.labels(decision=decision).inc()
    TICKET_LATENCY.observe(latency)

    costs = calculate_cost(input_tokens, output_tokens, cached_tokens)

    INPUT_TOKENS.labels(model=model, decision=decision).inc(input_tokens)
    OUTPUT_TOKENS.labels(model=model, decision=decision).inc(output_tokens)
    CACHED_TOKENS.labels(model=model, decision=decision).inc(cached_tokens)

    INPUT_COST.labels(model=model, decision=decision).inc(costs["input_cost"])
    OUTPUT_COST.labels(model=model, decision=decision).inc(costs["output_cost"])
    CACHED_COST.labels(model=model, decision=decision).inc(costs["cached_cost"])

    # Persist to database
    save_metric("input_tokens", input_tokens)
    save_metric("output_tokens", output_tokens)
    save_metric("cached_tokens", cached_tokens)
    save_metric("input_cost", costs["input_cost"])
    save_metric("output_cost", costs["output_cost"])
    save_metric("cached_cost", costs["cached_cost"])
    save_metric("tickets", 1)


def record_tool_call(tool_name: str):
    from app.storage import save_metric
    TOOL_CALL_COUNTER.labels(tool_name=tool_name).inc()
    save_metric("tool_calls", 1)
