from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Plan, Tenant


def get_tenant_with_plan_for_update(
    db: Session,
    tenant_id: int,
) -> tuple[Tenant, Plan] | None:
    statement = (
        select(Tenant, Plan)
        .join(Plan, Plan.name == Tenant.plan)
        .where(Tenant.id == tenant_id)
        .with_for_update(of=Tenant)
    )

    row = db.execute(statement).one_or_none()

    if row is None:
        return None

    return row[0], row[1]

def get_tenant_with_plan(
    db: Session,
    tenant_id: int,
) -> tuple[Tenant, Plan] | None:
    statement = (
        select(Tenant, Plan)
        .join(Plan, Plan.name == Tenant.plan)
        .where(Tenant.id == tenant_id)
    )

    row = db.execute(statement).one_or_none()

    if row is None:
        return None

    return row[0], row[1]