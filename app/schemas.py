from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import UsageType


StrictPositiveInt = Annotated[int, Field(strict=True, gt=0)]
StrictNonNegativeInt = Annotated[int, Field(strict=True, ge=0)]

class ApiCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: StrictPositiveInt

class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: StrictPositiveInt
    input_tokens: StrictNonNegativeInt
    cached_input_tokens: StrictNonNegativeInt
    output_tokens: StrictNonNegativeInt
    reasoning_tokens: StrictNonNegativeInt

    @model_validator(mode="after")
    def require_nonzero_usage(self) -> "GenerateRequest":
        if self.quantity == 0:
            raise ValueError(
                "At least one token count must be greater than zero."
            )

        return self

    @property
    def quantity(self) -> int:
        return (
            self.input_tokens
            + self.cached_input_tokens
            + self.output_tokens
            + self.reasoning_tokens
        )

    @property
    def token_breakdown(self) -> dict[str, int]:
        return {
            "input": self.input_tokens,
            "cached_input": self.cached_input_tokens,
            "output": self.output_tokens,
            "reasoning": self.reasoning_tokens,
        }


class QuotaUsage(BaseModel):
    used: StrictNonNegativeInt
    limit: StrictNonNegativeInt
    remaining: StrictNonNegativeInt
    overage: StrictNonNegativeInt

class GenerateResponse(BaseModel):
    usage_event_id: StrictPositiveInt
    idempotency_key: str
    quantity: StrictNonNegativeInt
    cost_microusd: StrictNonNegativeInt
    usage: QuotaUsage
    overage_quantity: StrictNonNegativeInt
    overage_cost_microusd: StrictNonNegativeInt
    projected_cost_microusd: StrictNonNegativeInt


class UsageWindow(BaseModel):
    start: datetime
    end: datetime


class UsageByType(BaseModel):
    api_calls: QuotaUsage
    ai_tokens: QuotaUsage


class UsageResponse(BaseModel):
    tenant_id: StrictPositiveInt
    window: UsageWindow
    usage: UsageByType
    cost_microusd: StrictNonNegativeInt
    overage_enabled: bool
    overage_cost_microusd: StrictNonNegativeInt
    projected_cost_microusd: StrictNonNegativeInt

class ErrorDetail(BaseModel):
    code: str
    message: str
    usage_type: UsageType | None = None
    used: int | None = None
    limit: int | None = None
    requested: int | None = None
    resets_at: datetime | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["ok"]

class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: StrictPositiveInt


class CheckoutResponse(BaseModel):
    session_id: str
    checkout_url: str

class WebhookResponse(BaseModel):
    received: bool
    duplicate: bool
    event_type: str

class BillingRedirectResponse(BaseModel):
    status: Literal["success", "canceled"]
    message: str
    session_id: str | None = None


class InvoiceLineResponse(BaseModel):
    usage_type: UsageType
    description: str
    event_count: StrictNonNegativeInt
    quantity: StrictNonNegativeInt
    overage_quantity: StrictNonNegativeInt
    subtotal_microusd: StrictNonNegativeInt
    overage_cost_microusd: StrictNonNegativeInt
    total_microusd: StrictNonNegativeInt


class InvoiceSummaryResponse(BaseModel):
    id: StrictPositiveInt
    tenant_id: StrictPositiveInt
    period_start: datetime
    period_end: datetime
    status: Literal["finalized"]
    currency: Literal["usd"]
    subtotal_microusd: StrictNonNegativeInt
    overage_cost_microusd: StrictNonNegativeInt
    total_microusd: StrictNonNegativeInt
    generated_at: datetime


class InvoiceDetailResponse(InvoiceSummaryResponse):
    lines: list[InvoiceLineResponse]
