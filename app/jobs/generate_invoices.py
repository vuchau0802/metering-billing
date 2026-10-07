import logging
from dataclasses import dataclass
from datetime import datetime

from app.db import SessionLocal
from app.repositories import tenants as tenants_repository
from app.services.invoices import (
    generate_monthly_invoice,
    previous_utc_month,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvoiceJobResult:
    checked: int
    created: int
    existing: int
    failed: int


def run_invoice_generation(
    *,
    now: datetime | None = None,
) -> InvoiceJobResult:
    period = previous_utc_month(now)

    with SessionLocal() as db:
        tenant_ids = tenants_repository.list_tenant_ids(db)

    created = 0
    existing = 0
    failed = 0

    for tenant_id in tenant_ids:
        try:
            with SessionLocal() as db:
                result = generate_monthly_invoice(
                    db,
                    tenant_id=tenant_id,
                    year=period.start.year,
                    month=period.start.month,
                    now=now,
                )

            if result.created:
                created += 1
            else:
                existing += 1
        except Exception:
            failed += 1
            logger.exception(
                "Invoice generation failed: tenant_id=%s "
                "period=%s",
                tenant_id,
                period.start.date(),
            )

    return InvoiceJobResult(
        checked=len(tenant_ids),
        created=created,
        existing=existing,
        failed=failed,
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s "
            "%(name)s %(message)s"
        ),
    )

    result = run_invoice_generation()
    logger.info(
        "Invoice generation complete: checked=%s "
        "created=%s existing=%s failed=%s",
        result.checked,
        result.created,
        result.existing,
        result.failed,
    )

    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
