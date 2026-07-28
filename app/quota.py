import os
from app.storage import get_all_metrics

SPEND_CAP_USD = float(os.environ.get("SPEND_CAP_USD", "2.0"))


def get_total_spend() -> float:
    metrics = get_all_metrics()
    input_cost = metrics.get("input_cost", 0)
    output_cost = metrics.get("output_cost", 0)
    cached_cost = metrics.get("cached_cost", 0)
    return input_cost + output_cost + cached_cost


def is_over_quota() -> bool:
    return get_total_spend() >= SPEND_CAP_USD


def quota_exceeded_response() -> dict:
    current = get_total_spend()
    return {
        "error": "quota_exceeded",
        "message": (
            f"OpenAI spend cap of ${SPEND_CAP_USD:.2f} has been reached "
            f"(current: ${current:.4f}). "
            "Contact an admin to reset the quota."
        ),
        "current_spend_usd": round(current, 4),
        "cap_usd": SPEND_CAP_USD,
    }
