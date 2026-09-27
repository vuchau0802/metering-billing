import pytest

from app.services.costs import (
    calculate_ai_token_cost,
    calculate_api_call_cost,
)


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [
        (0, 0),
        (1, 2),
        (1_000, 2_000),
        (1_500, 3_000),
    ],
)
def test_calculate_api_call_cost(
    quantity: int,
    expected: int,
) -> None:
    assert calculate_api_call_cost(quantity) == expected


def test_calculate_ai_token_cost() -> None:
    cost = calculate_ai_token_cost(
        input_tokens=1_000,
        cached_input_tokens=1_000,
        output_tokens=1_000,
        reasoning_tokens=1_000,
    )

    assert cost == 1_425_000


def test_reasoning_tokens_use_output_rate() -> None:
    output_cost = calculate_ai_token_cost(
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=1_000,
        reasoning_tokens=0,
    )
    reasoning_cost = calculate_ai_token_cost(
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_tokens=1_000,
    )

    assert reasoning_cost == output_cost
    assert reasoning_cost == 600_000


@pytest.mark.parametrize(
    "invalid_quantity",
    [-1, -100],
)
def test_api_call_cost_rejects_negative_quantity(
    invalid_quantity: int,
) -> None:
    with pytest.raises(ValueError, match="must be non-negative"):
        calculate_api_call_cost(invalid_quantity)


def test_ai_token_cost_rejects_negative_component() -> None:
    with pytest.raises(ValueError, match="output_tokens"):
        calculate_ai_token_cost(
            input_tokens=100,
            cached_input_tokens=50,
            output_tokens=-1,
            reasoning_tokens=10,
        )


def test_cost_rejects_boolean_as_integer() -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        calculate_api_call_cost(True)