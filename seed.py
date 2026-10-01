from app.config import get_settings
from sqlalchemy.orm import Session

from app.auth import hash_tenant_api_key
from app.db import SessionLocal
from app.models import Plan, PlanName, Tenant, TenantStatus

def seed_plans(db: Session) -> None:
    settings = get_settings()

    plans = [
        {
            "name": PlanName.FREE,
            "api_calls_limit": 1_000,
            "ai_tokens_limit": 100_000,
            "stripe_price_id": None,
        },
        {
            "name": PlanName.PRO,
            "api_calls_limit": 50_000,
            "ai_tokens_limit": 5_000_000,
            "stripe_price_id": settings.stripe_pro_price_id,
        },
    ]

    for data in plans:
        plan = db.get(Plan, data["name"])

        if plan is None:
            db.add(Plan(**data))
        else:
            plan.api_calls_limit = data["api_calls_limit"]
            plan.ai_tokens_limit = data["ai_tokens_limit"]
            plan.stripe_price_id = data["stripe_price_id"]

    db.flush()


def seed_tenants(db: Session) -> None:
    tenants = [
        {
            "id": 1,
            "email": "alice@example.com",
            "plan": PlanName.FREE,
            "status": TenantStatus.ACTIVE,
            "api_key_hash": hash_tenant_api_key("dev-tenant-1-key"),
        },
        {
            "id": 2,
            "email": "bob@example.com",
            "plan": PlanName.FREE,
            "status": TenantStatus.ACTIVE,
            "api_key_hash": hash_tenant_api_key("dev-tenant-2-key"),
        },
        {
            "id": 3,
            "email": "pro@example.com",
            "plan": PlanName.PRO,
            "status": TenantStatus.ACTIVE,
            "api_key_hash": hash_tenant_api_key("dev-tenant-3-key"),
        },
        {
            "id": 4,
            "email": "past-due@example.com",
            "plan": PlanName.PRO,
            "status": TenantStatus.PAST_DUE,
            "api_key_hash": hash_tenant_api_key("dev-tenant-4-key"),
        },
    ]

    for data in tenants:
        tenant = db.get(Tenant, data["id"])

        if tenant is None:
            db.add(Tenant(**data))
        else:
            tenant.email = data["email"]
            if tenant.api_key_hash is None:
                tenant.api_key_hash = data["api_key_hash"]


def main() -> None:
    with SessionLocal() as db:
        seed_plans(db)
        seed_tenants(db)
        db.commit()

    print("Seed complete.")


if __name__ == "__main__":
    main()
