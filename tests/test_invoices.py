from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.auth import hash_tenant_api_key
from app.db import SessionLocal
from app.jobs.generate_invoices import (
    InvoiceJobResult,
    run_invoice_generation,
)
from app.main import app
from app.models import (
    Invoice,
    InvoiceLine,
    Plan,
    PlanName,
    Tenant,
    TenantStatus,
    UsageEvent,
    UsageType,
)
from app.services.invoices import (
    InvoicePeriodError,
    generate_monthly_invoice,
    previous_utc_month,
)


TENANT_ID = 930_001
TENANT_KEY = "invoice-test-key"
SEPTEMBER_START = datetime(2026, 9, 1, tzinfo=UTC)
OCTOBER_START = datetime(2026, 10, 1, tzinfo=UTC)
NOVEMBER_START = datetime(2026, 11, 1, tzinfo=UTC)
NOW = datetime(2026, 10, 5, 12, tzinfo=UTC)


def clean_invoice_test_data() -> None:
    with SessionLocal() as db:
        invoice_ids = select(Invoice.id).where(
            Invoice.tenant_id == TENANT_ID
        )
        db.execute(
            delete(InvoiceLine).where(
                InvoiceLine.invoice_id.in_(invoice_ids)
            )
        )
        db.execute(
            delete(Invoice).where(
                Invoice.tenant_id == TENANT_ID
            )
        )
        db.execute(
            delete(UsageEvent).where(
                UsageEvent.tenant_id == TENANT_ID
            )
        )
        db.execute(
            delete(Tenant).where(Tenant.id == TENANT_ID)
        )
        db.commit()


@pytest.fixture(autouse=True)
def invoice_test_data():
    clean_invoice_test_data()

    with SessionLocal() as db:
        plan = db.get(Plan, PlanName.PRO)

        if plan is None:
            db.add(
                Plan(
                    name=PlanName.PRO,
                    api_calls_limit=50_000,
                    ai_tokens_limit=5_000_000,
                    overage_enabled=True,
                    stripe_price_id=None,
                )
            )
            db.flush()

        db.add(
            Tenant(
                id=TENANT_ID,
                email="invoice@example.com",
                plan=PlanName.PRO,
                status=TenantStatus.ACTIVE,
                api_key_hash=hash_tenant_api_key(TENANT_KEY),
            )
        )
        db.commit()

    yield
    clean_invoice_test_data()


def add_usage_event(
    *,
    idempotency_key: str,
    usage_type: UsageType,
    quantity: int,
    subtotal_microusd: int,
    created_at: datetime,
    overage_quantity: int = 0,
    overage_cost_microusd: int = 0,
) -> None:
    with SessionLocal() as db:
        db.add(
            UsageEvent(
                tenant_id=TENANT_ID,
                idempotency_key=idempotency_key,
                usage_type=usage_type,
                quantity=quantity,
                token_breakdown=None,
                overage_quantity=overage_quantity,
                overage_cost_microusd=(
                    overage_cost_microusd
                ),
                cost_microusd=(
                    subtotal_microusd
                    + overage_cost_microusd
                ),
                response_snapshot={},
                created_at=created_at,
            )
        )
        db.commit()


def generate_september_invoice() -> int:
    with SessionLocal() as db:
        result = generate_monthly_invoice(
            db,
            tenant_id=TENANT_ID,
            year=2026,
            month=9,
            now=NOW,
        )

    return result.invoice.id


def test_previous_utc_month_crosses_year_boundary() -> None:
    period = previous_utc_month(
        datetime(2026, 1, 15, tzinfo=UTC)
    )

    assert period.start == datetime(2025, 12, 1, tzinfo=UTC)
    assert period.end == datetime(2026, 1, 1, tzinfo=UTC)


def test_current_month_cannot_be_invoiced() -> None:
    with SessionLocal() as db:
        with pytest.raises(
            InvoicePeriodError,
            match="only completed UTC months",
        ):
            generate_monthly_invoice(
                db,
                tenant_id=TENANT_ID,
                year=2026,
                month=10,
                now=NOW,
            )


def test_generation_freezes_lines_and_is_idempotent() -> None:
    add_usage_event(
        idempotency_key="invoice-api-call",
        usage_type=UsageType.API_CALL,
        quantity=2,
        subtotal_microusd=4_000,
        created_at=SEPTEMBER_START,
    )
    add_usage_event(
        idempotency_key="invoice-ai-tokens",
        usage_type=UsageType.AI_TOKENS,
        quantity=120_000,
        subtotal_microusd=18_000_000,
        overage_quantity=20_000,
        overage_cost_microusd=15_000_000,
        created_at=datetime(2026, 9, 15, tzinfo=UTC),
    )
    add_usage_event(
        idempotency_key="invoice-current-month",
        usage_type=UsageType.AI_TOKENS,
        quantity=999,
        subtotal_microusd=999,
        created_at=OCTOBER_START,
    )

    with SessionLocal() as db:
        first = generate_monthly_invoice(
            db,
            tenant_id=TENANT_ID,
            year=2026,
            month=9,
            now=NOW,
        )
        second = generate_monthly_invoice(
            db,
            tenant_id=TENANT_ID,
            year=2026,
            month=9,
            now=NOW,
        )

        invoice_count = db.scalar(
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.tenant_id == TENANT_ID)
        )
        lines = list(
            db.scalars(
                select(InvoiceLine)
                .where(
                    InvoiceLine.invoice_id
                    == first.invoice.id
                )
                .order_by(InvoiceLine.usage_type)
            )
        )

    assert first.created is True
    assert second.created is False
    assert first.invoice.id == second.invoice.id
    assert invoice_count == 1
    assert first.invoice.period_start == SEPTEMBER_START
    assert first.invoice.period_end == OCTOBER_START
    assert first.invoice.subtotal_microusd == 18_004_000
    assert first.invoice.overage_cost_microusd == 15_000_000
    assert first.invoice.total_microusd == 33_004_000
    assert len(lines) == 2

    ai_line = next(
        line
        for line in lines
        if line.usage_type == UsageType.AI_TOKENS
    )
    assert ai_line.event_count == 1
    assert ai_line.quantity == 120_000
    assert ai_line.overage_quantity == 20_000
    assert ai_line.subtotal_microusd == 18_000_000
    assert ai_line.overage_cost_microusd == 15_000_000
    assert ai_line.total_microusd == 33_000_000


def test_empty_month_creates_zero_total_statement() -> None:
    invoice_id = generate_september_invoice()

    with SessionLocal() as db:
        invoice = db.get(Invoice, invoice_id)
        line_count = db.scalar(
            select(func.count())
            .select_from(InvoiceLine)
            .where(InvoiceLine.invoice_id == invoice_id)
        )

    assert invoice is not None
    assert invoice.total_microusd == 0
    assert line_count == 0


def test_authenticated_invoice_list_and_detail() -> None:
    add_usage_event(
        idempotency_key="invoice-api-response",
        usage_type=UsageType.API_CALL,
        quantity=1,
        subtotal_microusd=2_000,
        created_at=SEPTEMBER_START,
    )
    invoice_id = generate_september_invoice()
    client = TestClient(app)
    headers = {"X-Tenant-Key": TENANT_KEY}

    listing = client.get(
        f"/invoices/{TENANT_ID}",
        headers=headers,
    )
    detail = client.get(
        f"/invoices/{TENANT_ID}/{invoice_id}",
        headers=headers,
    )

    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["total_microusd"] == 2_000
    assert detail.status_code == 200
    assert detail.json()["id"] == invoice_id
    assert detail.json()["lines"] == [
        {
            "usage_type": "api_call",
            "description": "API calls",
            "event_count": 1,
            "quantity": 1,
            "overage_quantity": 0,
            "subtotal_microusd": 2_000,
            "overage_cost_microusd": 0,
            "total_microusd": 2_000,
        }
    ]


def test_monthly_job_is_safe_to_rerun(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.jobs.generate_invoices."
        "tenants_repository.list_tenant_ids",
        lambda db: [TENANT_ID],
    )

    first = run_invoice_generation(now=NOW)
    second = run_invoice_generation(now=NOW)

    assert first == InvoiceJobResult(
        checked=1,
        created=1,
        existing=0,
        failed=0,
    )
    assert second == InvoiceJobResult(
        checked=1,
        created=0,
        existing=1,
        failed=0,
    )
