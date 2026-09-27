import pytest
from pydantic import ValidationError

from app.schemas import GenerateRequest


VALID_REQUEST = {
    "tenant_id": 1,
    "input_tokens": 100,
    "cached_input_tokens": 25,
    "output_tokens": 40,
    "reasoning_tokens": 10,
}


def test_generate_request_calculates_quantity() -> None:
    request = GenerateRequest(**VALID_REQUEST)

    assert request.quantity == 175
    assert request.token_breakdown == {
        "input": 100,
        "cached_input": 25,
        "output": 40,
        "reasoning": 10,
    }


@pytest.mark.parametrize(
    "field",
    [
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
    ],
)
def test_generate_request_rejects_negative_tokens(field: str) -> None:
    data = {**VALID_REQUEST, field: -1}

    with pytest.raises(ValidationError):
        GenerateRequest(**data)


def test_generate_request_rejects_string_integer() -> None:
    data = {**VALID_REQUEST, "input_tokens": "100"}

    with pytest.raises(ValidationError):
        GenerateRequest(**data)


def test_generate_request_rejects_boolean() -> None:
    data = {**VALID_REQUEST, "output_tokens": True}

    with pytest.raises(ValidationError):
        GenerateRequest(**data)


def test_generate_request_rejects_unknown_fields() -> None:
    data = {**VALID_REQUEST, "unknown_field": 123}

    with pytest.raises(ValidationError):
        GenerateRequest(**data)


def test_generate_request_requires_positive_tenant_id() -> None:
    data = {**VALID_REQUEST, "tenant_id": 0}

    with pytest.raises(ValidationError):
        GenerateRequest(**data)