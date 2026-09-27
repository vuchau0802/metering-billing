from datetime import datetime, timezone
from math import ceil
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    GenerateRequest,
    GenerateResponse,
    UsageResponse,
)
from app.services.metering import (
    IdempotencyConflictError,
    PaymentRequiredError,
    TenantNotFoundError,
    get_usage_report,
    record_generate,
)
from app.services.quotas import QuotaExceededError


app = FastAPI(
    title="Usage Metering and Billing Engine",
    version="0.1.0",
)


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
                    "AI token quota exceeded for the current UTC month."
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get(
    "/usage/{tenant_id}",
    response_model=UsageResponse,
)
def usage(
    tenant_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_usage_report(db, tenant_id)

@app.post(
    "/generate",
    response_model=GenerateResponse,
)
def generate(
    payload: GenerateRequest,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=255,
            pattern=r".*\S.*",
        ),
    ],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    result = record_generate(
        db,
        request=payload,
        idempotency_key=idempotency_key,
    )

    if result.replayed:
        response.headers["Idempotent-Replay"] = "true"

    return result.response