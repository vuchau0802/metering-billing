from datetime import datetime, timezone
from math import ceil
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import (
    TenantAuthenticationError,
    require_tenant_access,
)
from app.db import get_db
from app.schemas import (
    ApiCallRequest,
    BillingRedirectResponse,
    CheckoutRequest,
    CheckoutResponse,
    GenerateRequest,
    GenerateResponse,
    InvoiceDetailResponse,
    InvoiceSummaryResponse,
    UsageResponse,
    WebhookResponse,
)
from app.services.metering import (
    IdempotencyConflictError,
    PaymentRequiredError,
    TenantNotFoundError,
    get_usage_report,
    record_api_call,
    record_generate,
)
from app.services.billing import (
    AlreadySubscribedError,
    BillingConfigurationError,
    CheckoutCreationError,
    create_checkout_session,
)
from app.services.webhooks import (
    InvalidWebhookPayloadError,
    InvalidWebhookSignatureError,
    process_webhook,
)
from app.services.quotas import QuotaExceededError
from app.services.invoices import (
    InvoiceNotFoundError,
    get_monthly_invoice,
    list_monthly_invoices,
)

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
        pattern=r".*\S.*",
    ),
]
TenantApiKey = Annotated[
    str | None,
    Header(
        alias="X-Tenant-Key",
        max_length=255,
    ),
]

app = FastAPI(
    title="Usage Metering and Billing Engine",
    version="0.1.0",
)


async def read_raw_request_body(request: Request) -> bytes:
    return await request.body()


RawRequestBody = Annotated[
    bytes,
    Depends(read_raw_request_body),
]


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "invalid_request",
                "message": "The request body or headers are invalid.",
            }
        },
    )


@app.exception_handler(TenantNotFoundError)
async def handle_tenant_not_found(
    request: Request,
    error: TenantNotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "tenant_not_found",
                "message": f"Tenant {error.tenant_id} was not found.",
            }
        },
    )


@app.exception_handler(TenantAuthenticationError)
async def handle_tenant_authentication_error(
    request: Request,
    error: TenantAuthenticationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "code": "unauthorized",
                "message": str(error),
            }
        },
    )


@app.exception_handler(InvoiceNotFoundError)
async def handle_invoice_not_found(
    request: Request,
    error: InvoiceNotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "invoice_not_found",
                "message": str(error),
            }
        },
    )


@app.exception_handler(PaymentRequiredError)
async def handle_payment_required(
    request: Request,
    error: PaymentRequiredError,
) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "error": {
                "code": "payment_required",
                "message": (
                    "The tenant is not entitled to perform this action."
                ),
                "tenant_status": error.status.value,
            }
        },
    )


@app.exception_handler(IdempotencyConflictError)
async def handle_idempotency_conflict(
    request: Request,
    error: IdempotencyConflictError,
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "idempotency_conflict",
                "message": str(error),
            }
        },
    )


@app.exception_handler(QuotaExceededError)
async def handle_quota_exceeded(
    request: Request,
    error: QuotaExceededError,
) -> JSONResponse:
    retry_after = max(
        0,
        ceil(
            (
                error.resets_at
                - datetime.now(timezone.utc)
            ).total_seconds()
        ),
    )

    remaining = max(0, error.limit - error.used)

    return JSONResponse(
        status_code=429,
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(error.limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(
                int(error.resets_at.timestamp())
            ),
        },
        content={
            "error": {
                "code": "quota_exceeded",
                "message": (
                    f"{error.usage_type.value.replace('_', ' ')} "
                    "quota exceeded for the current UTC month."
                ),
                "usage_type": error.usage_type.value,
                "used": error.used,
                "limit": error.limit,
                "requested": error.requested,
                "resets_at": (
                    error.resets_at
                    .isoformat()
                    .replace("+00:00", "Z")
                ),
            }
        },
    )

@app.exception_handler(AlreadySubscribedError)
async def handle_already_subscribed(
    request: Request,
    error: AlreadySubscribedError,
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "already_subscribed",
                "message": str(error),
            }
        },
    )


@app.exception_handler(BillingConfigurationError)
async def handle_billing_configuration(
    request: Request,
    error: BillingConfigurationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "billing_not_configured",
                "message": str(error),
            }
        },
    )


@app.exception_handler(CheckoutCreationError)
async def handle_checkout_creation(
    request: Request,
    error: CheckoutCreationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "code": "checkout_creation_failed",
                "message": str(error),
            }
        },
    )

@app.exception_handler(InvalidWebhookSignatureError)
async def handle_invalid_webhook_signature(
    request: Request,
    error: InvalidWebhookSignatureError,
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "invalid_webhook_signature",
                "message": str(error),
            }
        },
    )

@app.exception_handler(InvalidWebhookPayloadError)
async def handle_invalid_webhook_payload(
    request: Request,
    error: InvalidWebhookPayloadError,
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "invalid_webhook_payload",
                "message": str(error),
            }
        },
    )

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get(
    "/usage/{tenant_id}",
    response_model=UsageResponse,
)
def usage(
    tenant_id: int,
    tenant_api_key: TenantApiKey = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_tenant_access(
        db,
        tenant_id=tenant_id,
        api_key=tenant_api_key,
    )
    return get_usage_report(db, tenant_id)


@app.get(
    "/invoices/{tenant_id}",
    response_model=list[InvoiceSummaryResponse],
)
def list_invoices(
    tenant_id: int,
    tenant_api_key: TenantApiKey = None,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    require_tenant_access(
        db,
        tenant_id=tenant_id,
        api_key=tenant_api_key,
    )

    return [
        {
            "id": invoice.id,
            "tenant_id": invoice.tenant_id,
            "period_start": invoice.period_start,
            "period_end": invoice.period_end,
            "status": invoice.status,
            "currency": invoice.currency,
            "subtotal_microusd": invoice.subtotal_microusd,
            "overage_cost_microusd": (
                invoice.overage_cost_microusd
            ),
            "total_microusd": invoice.total_microusd,
            "generated_at": invoice.generated_at,
        }
        for invoice in list_monthly_invoices(db, tenant_id)
    ]


@app.get(
    "/invoices/{tenant_id}/{invoice_id}",
    response_model=InvoiceDetailResponse,
)
def invoice_detail(
    tenant_id: int,
    invoice_id: int,
    tenant_api_key: TenantApiKey = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_tenant_access(
        db,
        tenant_id=tenant_id,
        api_key=tenant_api_key,
    )
    invoice, lines, adjustments = get_monthly_invoice(
        db,
        tenant_id=tenant_id,
        invoice_id=invoice_id,
    )

    return {
        "id": invoice.id,
        "tenant_id": invoice.tenant_id,
        "period_start": invoice.period_start,
        "period_end": invoice.period_end,
        "status": invoice.status,
        "currency": invoice.currency,
        "subtotal_microusd": invoice.subtotal_microusd,
        "overage_cost_microusd": (
            invoice.overage_cost_microusd
        ),
        "total_microusd": invoice.total_microusd,
        "generated_at": invoice.generated_at,
        "adjustment_microusd": sum(
            adjustment.amount_microusd
            for adjustment in adjustments
        ),
        "lines": [
            {
                "usage_type": line.usage_type,
                "description": line.description,
                "event_count": line.event_count,
                "quantity": line.quantity,
                "overage_quantity": line.overage_quantity,
                "subtotal_microusd": line.subtotal_microusd,
                "overage_cost_microusd": (
                    line.overage_cost_microusd
                ),
                "total_microusd": line.total_microusd,
            }
            for line in lines
        ],
        "adjustments": [
            {
                "id": adjustment.id,
                "source_event_id": adjustment.source_event_id,
                "old_plan": adjustment.old_plan,
                "new_plan": adjustment.new_plan,
                "period_start": adjustment.period_start,
                "period_end": adjustment.period_end,
                "effective_at": adjustment.effective_at,
                "old_monthly_price_microusd": (
                    adjustment.old_monthly_price_microusd
                ),
                "new_monthly_price_microusd": (
                    adjustment.new_monthly_price_microusd
                ),
                "amount_microusd": adjustment.amount_microusd,
                "currency": adjustment.currency,
            }
            for adjustment in adjustments
        ],
    }

@app.post(
    "/generate",
    response_model=GenerateResponse,
)
def generate(
    payload: GenerateRequest,
    response: Response,
    idempotency_key: IdempotencyKey,
    tenant_api_key: TenantApiKey = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_tenant_access(
        db,
        tenant_id=payload.tenant_id,
        api_key=tenant_api_key,
    )
    result = record_generate(
        db,
        request=payload,
        idempotency_key=idempotency_key,
    )

    if result.replayed:
        response.headers["Idempotent-Replay"] = "true"

    return result.response


@app.post(
    "/api-call",
    response_model=GenerateResponse,
)
def api_call(
    payload: ApiCallRequest,
    response: Response,
    idempotency_key: IdempotencyKey,
    tenant_api_key: TenantApiKey = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_tenant_access(
        db,
        tenant_id=payload.tenant_id,
        api_key=tenant_api_key,
    )
    result = record_api_call(
        db,
        request=payload,
        idempotency_key=idempotency_key,
    )

    if result.replayed:
        response.headers["Idempotent-Replay"] = "true"

    return result.response

@app.post(
    "/billing/checkout",
    response_model=CheckoutResponse,
)
def billing_checkout(
    payload: CheckoutRequest,
    tenant_api_key: TenantApiKey = None,
    db: Session = Depends(get_db),
) -> CheckoutResponse:
    require_tenant_access(
        db,
        tenant_id=payload.tenant_id,
        api_key=tenant_api_key,
    )
    return create_checkout_session(
        db,
        payload.tenant_id,
    )

@app.post(
    "/webhooks/stripe",
    response_model=WebhookResponse,
)
def stripe_webhook(
    payload: RawRequestBody,
    stripe_signature: Annotated[
        str,
        Header(alias="Stripe-Signature"),
    ],
    db: Session = Depends(get_db),
) -> WebhookResponse:
    result = process_webhook(
        db,
        payload=payload,
        signature=stripe_signature,
    )

    return WebhookResponse(
        received=True,
        duplicate=result.duplicate,
        event_type=result.event_type,
    )

@app.get(
    "/billing/success",
    response_model=BillingRedirectResponse,
)
def billing_success(
    session_id: str,
) -> BillingRedirectResponse:
    return BillingRedirectResponse(
        status="success",
        message="Checkout completed successfully.",
        session_id=session_id,
    )


@app.get(
    "/billing/cancel",
    response_model=BillingRedirectResponse,
)
def billing_cancel() -> BillingRedirectResponse:
    return BillingRedirectResponse(
        status="canceled",
        message="Checkout was canceled.",
    )
