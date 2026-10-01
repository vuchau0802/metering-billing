from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import TenantStatus, UsageEvent, UsageType
from app.repositories import tenants as tenants_repository
from app.repositories import usage_events as usage_events_repository
from app.schemas import (
    ApiCallRequest,
    GenerateRequest,
    GenerateResponse,
    QuotaUsage,
    UsageByType,
    UsageResponse,
    UsageWindow,
)
from app.services.costs import (
    calculate_ai_token_cost,
    calculate_api_call_cost,
)
from app.services.quotas import check_quota, current_utc_month


class TenantNotFoundError(Exception):
    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        super().__init__(f"Tenant {tenant_id} was not found")


class PaymentRequiredError(Exception):
    def __init__(
        self,
        tenant_id: int,
        status: TenantStatus,
    ) -> None:
        self.tenant_id = tenant_id
        self.status = status

        super().__init__(
            f"Tenant {tenant_id} is not entitled to perform this action"
        )


class IdempotencyConflictError(Exception):
    def __init__(self, idempotency_key: str) -> None:
        self.idempotency_key = idempotency_key

        super().__init__(
            "The idempotency key was already used for a different request"
        )


@dataclass(frozen=True)
class MeteringResult:
    response: dict[str, Any]
    replayed: bool


def _event_matches_request(
    event: UsageEvent,
    *,
    tenant_id: int,
    usage_type: UsageType,
    quantity: int,
    token_breakdown: dict[str, int] | None,
) -> bool:
    return (
        event.tenant_id == tenant_id
        and event.usage_type == usage_type
        and event.quantity == quantity
        and event.token_breakdown == token_breakdown
    )


def _replay_existing_event(
    event: UsageEvent,
    *,
    tenant_id: int,
    usage_type: UsageType,
    quantity: int,
    token_breakdown: dict[str, int] | None,
) -> MeteringResult:
    if not _event_matches_request(
        event,
        tenant_id=tenant_id,
        usage_type=usage_type,
        quantity=quantity,
        token_breakdown=token_breakdown,
    ):
        raise IdempotencyConflictError(
            event.idempotency_key
        )

    return MeteringResult(
        response=dict(event.response_snapshot),
        replayed=True,
    )


def _record_usage(
    db: Session,
    *,
    tenant_id: int,
    usage_type: UsageType,
    quantity: int,
    token_breakdown: dict[str, int] | None,
    cost_microusd: int,
    idempotency_key: str,
) -> MeteringResult:
    existing = usage_events_repository.get_by_idempotency_key(
        db,
        idempotency_key,
    )

    if existing is not None:
        return _replay_existing_event(
            existing,
            tenant_id=tenant_id,
            usage_type=usage_type,
            quantity=quantity,
            token_breakdown=token_breakdown,
        )

    tenant_record = (
        tenants_repository.get_tenant_with_plan_for_update(
            db,
            tenant_id,
        )
    )

    if tenant_record is None:
        raise TenantNotFoundError(tenant_id)

    tenant, plan = tenant_record

    # Recheck after acquiring the tenant lock because another
    # request may have completed while this request waited.
    existing = usage_events_repository.get_by_idempotency_key(
        db,
        idempotency_key,
    )

    if existing is not None:
        return _replay_existing_event(
            existing,
            tenant_id=tenant_id,
            usage_type=usage_type,
            quantity=quantity,
            token_breakdown=token_breakdown,
        )

    if tenant.status != TenantStatus.ACTIVE:
        raise PaymentRequiredError(
            tenant_id=tenant.id,
            status=tenant.status,
        )

    quota = check_quota(
        db,
        tenant_id=tenant.id,
        plan=plan,
        usage_type=usage_type,
        requested=quantity,
    )

    try:
        event = usage_events_repository.create_usage_event(
            db,
            tenant_id=tenant.id,
            idempotency_key=idempotency_key,
            usage_type=usage_type,
            quantity=quantity,
            token_breakdown=token_breakdown,
            cost_microusd=cost_microusd,
            response_snapshot={},
        )

        response = GenerateResponse(
            usage_event_id=event.id,
            idempotency_key=idempotency_key,
            quantity=quantity,
            cost_microusd=cost_microusd,
            usage=QuotaUsage(
                used=quota.used,
                limit=quota.limit,
                remaining=quota.remaining,
            ),
        ).model_dump(mode="json")

        event.response_snapshot = response
        db.commit()

        return MeteringResult(
            response=response,
            replayed=False,
        )
    except IntegrityError:
        db.rollback()

        existing = (
            usage_events_repository
            .get_by_idempotency_key(
                db,
                idempotency_key,
            )
        )

        if existing is None:
            raise

        return _replay_existing_event(
            existing,
            tenant_id=tenant_id,
            usage_type=usage_type,
            quantity=quantity,
            token_breakdown=token_breakdown,
        )


def record_generate(
    db: Session,
    *,
    request: GenerateRequest,
    idempotency_key: str,
) -> MeteringResult:
    cost_microusd = calculate_ai_token_cost(
        input_tokens=request.input_tokens,
        cached_input_tokens=request.cached_input_tokens,
        output_tokens=request.output_tokens,
        reasoning_tokens=request.reasoning_tokens,
    )

    return _record_usage(
        db,
        tenant_id=request.tenant_id,
        usage_type=UsageType.AI_TOKENS,
        quantity=request.quantity,
        token_breakdown=request.token_breakdown,
        cost_microusd=cost_microusd,
        idempotency_key=idempotency_key,
    )


def record_api_call(
    db: Session,
    *,
    request: ApiCallRequest,
    idempotency_key: str,
) -> MeteringResult:
    quantity = 1

    return _record_usage(
        db,
        tenant_id=request.tenant_id,
        usage_type=UsageType.API_CALL,
        quantity=quantity,
        token_breakdown=None,
        cost_microusd=calculate_api_call_cost(quantity),
        idempotency_key=idempotency_key,
    )

def get_usage_report(
    db: Session,
    tenant_id: int,
) -> dict[str, Any]:
    tenant_record = tenants_repository.get_tenant_with_plan(
        db,
        tenant_id,
    )

    if tenant_record is None:
        raise TenantNotFoundError(tenant_id)

    tenant, plan = tenant_record
    window = current_utc_month()

    totals, total_cost = usage_events_repository.get_usage_rollup(
        db,
        tenant_id=tenant.id,
        window_start=window.start,
        window_end=window.end,
    )

    api_calls_used = totals[UsageType.API_CALL]
    ai_tokens_used = totals[UsageType.AI_TOKENS]

    report = UsageResponse(
        tenant_id=tenant.id,
        window=UsageWindow(
            start=window.start,
            end=window.end,
        ),
        usage=UsageByType(
            api_calls=QuotaUsage(
                used=api_calls_used,
                limit=plan.api_calls_limit,
                remaining=max(
                    0,
                    plan.api_calls_limit - api_calls_used,
                ),
            ),
            ai_tokens=QuotaUsage(
                used=ai_tokens_used,
                limit=plan.ai_tokens_limit,
                remaining=max(
                    0,
                    plan.ai_tokens_limit - ai_tokens_used,
                ),
            ),
        ),
        cost_microusd=total_cost,
    )

    return report.model_dump(mode="json")