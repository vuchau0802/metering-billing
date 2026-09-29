from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import UsageType


StrictPositiveInt = Annotated[int, Field(strict=True, gt=0)]
StrictNonNegativeInt = Annotated[int, Field(strict=True, ge=0)]


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: StrictPositiveInt
    input_tokens: StrictNonNegativeInt
    cached_input_tokens: StrictNonNegativeInt
    output_tokens: StrictNonNegativeInt
    reasoning_tokens: StrictNonNegativeInt

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


class GenerateResponse(BaseModel):
    usage_event_id: StrictPositiveInt
    idempotency_key: str
    quantity: StrictNonNegativeInt
    cost_microusd: StrictNonNegativeInt
    usage: QuotaUsage


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