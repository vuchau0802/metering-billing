from datetime import datetime, timezone

from app.config import (
    AI_TOKEN_OVERAGE_PRICE_PER_1K,
    API_CALL_OVERAGE_PRICE_PER_1K,
    API_CALL_PRICE_PER_1K,
    CACHED_INPUT_PRICE_PER_1K,
    INPUT_PRICE_PER_1K,
    OUTPUT_PRICE_PER_1K,
    UNITS_PER_PRICE_BLOCK,
)
from app.models import UsageType

def _validate_quantities(**quantities: int) -> None:
    for name, value in quantities.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")

        if value < 0:
            raise ValueError(f"{name} must be non-negative")


def calculate_api_call_cost(quantity: int) -> int:
    _validate_quantities(quantity=quantity)

    return quantity * API_CALL_PRICE_PER_1K // UNITS_PER_PRICE_BLOCK

def calculate_overage_cost(
    usage_type: UsageType,
    quantity: int,
) -> int:
    _validate_quantities(quantity=quantity)

    if usage_type == UsageType.API_CALL:
        price_per_1k = API_CALL_OVERAGE_PRICE_PER_1K
    elif usage_type == UsageType.AI_TOKENS:
        price_per_1k = AI_TOKEN_OVERAGE_PRICE_PER_1K
    else:
        raise ValueError(f"Unsupported usage type: {usage_type}")

    return (
        quantity
        * price_per_1k
        // UNITS_PER_PRICE_BLOCK
    )


def calculate_ai_token_cost(
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
) -> int:
    _validate_quantities(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    )

    input_cost = (
        input_tokens
        * INPUT_PRICE_PER_1K
        // UNITS_PER_PRICE_BLOCK
    )
    cached_input_cost = (
        cached_input_tokens
        * CACHED_INPUT_PRICE_PER_1K
        // UNITS_PER_PRICE_BLOCK
    )
    output_cost = (
        (output_tokens + reasoning_tokens)
        * OUTPUT_PRICE_PER_1K
        // UNITS_PER_PRICE_BLOCK
    )

    return input_cost + cached_input_cost + output_cost

def calculate_projected_monthly_cost(
    cost_microusd: int,
    *,
    window_start: datetime,
    window_end: datetime,
    now: datetime | None = None,
) -> int:
    _validate_quantities(cost_microusd=cost_microusd)

    current = now or datetime.now(timezone.utc)

    if (
        current.tzinfo is None
        or window_start.tzinfo is None
        or window_end.tzinfo is None
    ):
        raise ValueError("projection datetimes must include timezone information")

    current = current.astimezone(timezone.utc)
    start = window_start.astimezone(timezone.utc)
    end = window_end.astimezone(timezone.utc)

    if end <= start:
        raise ValueError("window_end must be after window_start")

    elapsed_end = min(max(current, start), end)
    elapsed_seconds = max(
        1,
        int((elapsed_end - start).total_seconds()),
    )
    window_seconds = int((end - start).total_seconds())

    projected = (
        cost_microusd
        * window_seconds
        // elapsed_seconds
    )

    return max(cost_microusd, projected)
