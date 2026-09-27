from app.config import (
    API_CALL_PRICE_PER_1K,
    CACHED_INPUT_PRICE_PER_1K,
    INPUT_PRICE_PER_1K,
    OUTPUT_PRICE_PER_1K,
    UNITS_PER_PRICE_BLOCK,
)


def _validate_quantities(**quantities: int) -> None:
    for name, value in quantities.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")

        if value < 0:
            raise ValueError(f"{name} must be non-negative")


def calculate_api_call_cost(quantity: int) -> int:
    _validate_quantities(quantity=quantity)

    return quantity * API_CALL_PRICE_PER_1K // UNITS_PER_PRICE_BLOCK


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