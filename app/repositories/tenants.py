from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Plan, PlanName, Tenant


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

def get_tenant_for_update(
    db: Session,
    tenant_id: int,
) -> Tenant | None:
    statement = (
        select(Tenant)
        .where(Tenant.id == tenant_id)
        .with_for_update()
    )

    return db.scalar(statement)


def get_tenant_by_customer_for_update(
    db: Session,
    stripe_customer_id: str,
) -> Tenant | None:
    statement = (
        select(Tenant)
        .where(
            Tenant.stripe_customer_id
            == stripe_customer_id
        )
        .with_for_update()
    )

    return db.scalar(statement)

def get_plan(
    db: Session,
    plan_name: PlanName,
) -> Plan | None:
    return db.get(Plan, plan_name)


def list_tenant_ids(db: Session) -> list[int]:
    statement = select(Tenant.id).order_by(Tenant.id)

    return list(db.scalars(statement))
