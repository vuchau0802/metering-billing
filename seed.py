from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Plan, PlanName, Tenant, TenantStatus


def seed_plans(db: Session) -> None:
    plans = [
        {
            "name": PlanName.FREE,
            "api_calls_limit": 1_000,
            "ai_tokens_limit": 100_000,
        },
        {
            "name": PlanName.PRO,
            "api_calls_limit": 50_000,
            "ai_tokens_limit": 5_000_000,
        },
    ]

    for data in plans:
        plan = db.get(Plan, data["name"])

        if plan is None:
            db.add(Plan(**data))
        else:
            plan.api_calls_limit = data["api_calls_limit"]
            plan.ai_tokens_limit = data["ai_tokens_limit"]

    db.flush()


def seed_tenants(db: Session) -> None:
    tenants = [
        {
            "id": 1,
            "email": "alice@example.com",
            "plan": PlanName.FREE,
            "status": TenantStatus.ACTIVE,
        },
        {
            "id": 2,
            "email": "bob@example.com",
            "plan": PlanName.FREE,
            "status": TenantStatus.ACTIVE,
        },
        {
            "id": 3,
            "email": "pro@example.com",
            "plan": PlanName.PRO,
            "status": TenantStatus.ACTIVE,
        },
        {
            "id": 4,
            "email": "past-due@example.com",
            "plan": PlanName.PRO,
            "status": TenantStatus.PAST_DUE,
        },
    ]

    for data in tenants:
        tenant = db.get(Tenant, data["id"])

        if tenant is None:
            db.add(Tenant(**data))
        else:
            tenant.email = data["email"]
            tenant.plan = data["plan"]
            tenant.status = data["status"]


def main() -> None:
    with SessionLocal() as db:
        seed_plans(db)
        seed_tenants(db)
        db.commit()

    print("Seed complete.")


if __name__ == "__main__":
    main()