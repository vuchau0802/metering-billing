from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLine
from app.repositories import invoices as invoices_repository
from app.repositories import tenants as tenants_repository
from app.services.quotas import QuotaWindow, current_utc_month


class InvoicePeriodError(ValueError):
    pass


class InvoiceTenantNotFoundError(Exception):
    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        super().__init__(f"Tenant {tenant_id} was not found")


class InvoiceNotFoundError(Exception):
    def __init__(self, invoice_id: int) -> None:
        self.invoice_id = invoice_id
        super().__init__(f"Invoice {invoice_id} was not found")


@dataclass(frozen=True)
class InvoiceGenerationResult:
    invoice: Invoice
    created: bool


def utc_month(year: int, month: int) -> QuotaWindow:
    try:
        start = datetime(
            year,
            month,
            1,
            tzinfo=timezone.utc,
        )
    except ValueError as error:
        raise InvoicePeriodError(
            "year and month must identify a valid UTC month"
        ) from error

    if month == 12:
        end = datetime(
            year + 1,
            1,
            1,
            tzinfo=timezone.utc,
        )
    else:
        end = datetime(
            year,
            month + 1,
            1,
            tzinfo=timezone.utc,
        )

    return QuotaWindow(start=start, end=end)


def previous_utc_month(
    now: datetime | None = None,
) -> QuotaWindow:
    current = current_utc_month(now)

    if current.start.month == 1:
        return utc_month(current.start.year - 1, 12)

    return utc_month(
        current.start.year,
        current.start.month - 1,
    )


def generate_monthly_invoice(
    db: Session,
    *,
    tenant_id: int,
    year: int,
    month: int,
    now: datetime | None = None,
) -> InvoiceGenerationResult:
    period = utc_month(year, month)
    current = current_utc_month(now)

    if period.end > current.start:
        raise InvoicePeriodError(
            "only completed UTC months can be invoiced"
        )

    tenant = tenants_repository.get_tenant_for_update(
        db,
        tenant_id,
    )

    if tenant is None:
        raise InvoiceTenantNotFoundError(tenant_id)

    existing = invoices_repository.get_for_period(
        db,
        tenant_id=tenant_id,
        period_start=period.start,
        period_end=period.end,
    )

    if existing is not None:
        db.commit()
        return InvoiceGenerationResult(
            invoice=existing,
            created=False,
        )

    aggregates = invoices_repository.aggregate_usage_lines(
        db,
        tenant_id=tenant_id,
        period_start=period.start,
        period_end=period.end,
    )
    invoice = invoices_repository.create_finalized_invoice(
        db,
        tenant_id=tenant_id,
        period_start=period.start,
        period_end=period.end,
        aggregates=aggregates,
    )
    db.commit()

    return InvoiceGenerationResult(
        invoice=invoice,
        created=True,
    )


def list_monthly_invoices(
    db: Session,
    tenant_id: int,
) -> list[Invoice]:
    return invoices_repository.list_for_tenant(db, tenant_id)


def get_monthly_invoice(
    db: Session,
    *,
    tenant_id: int,
    invoice_id: int,
) -> tuple[Invoice, list[InvoiceLine]]:
    invoice = invoices_repository.get_for_tenant(
        db,
        invoice_id=invoice_id,
        tenant_id=tenant_id,
    )

    if invoice is None:
        raise InvoiceNotFoundError(invoice_id)

    lines = invoices_repository.list_lines(db, invoice.id)

    return invoice, lines
