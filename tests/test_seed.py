from typing import Any

from app.auth import hash_tenant_api_key
from app.models import PlanName, Tenant, TenantStatus
from seed import seed_tenants


class FakeSession:
    def __init__(self, tenants: dict[int, Tenant]) -> None:
        self.tenants = tenants
        self.added: list[Tenant] = []

    def get(self, model: Any, tenant_id: int) -> Tenant | None:
        assert model is Tenant
        return self.tenants.get(tenant_id)

    def add(self, tenant: Tenant) -> None:
        self.added.append(tenant)


def test_seed_tenants_preserves_existing_billing_state() -> None:
    existing_api_key_hash = hash_tenant_api_key("existing-key")
    existing = Tenant(
        id=1,
        email="customer@example.com",
        plan=PlanName.PRO,
        status=TenantStatus.PAST_DUE,
        stripe_customer_id="cus_existing",
        api_key_hash=existing_api_key_hash,
    )
    db = FakeSession({existing.id: existing})

    seed_tenants(db)  # type: ignore[arg-type]

    assert existing.email == "alice@example.com"
    assert existing.plan == PlanName.PRO
    assert existing.status == TenantStatus.PAST_DUE
    assert existing.stripe_customer_id == "cus_existing"
    assert existing.api_key_hash == existing_api_key_hash
    assert {tenant.id for tenant in db.added} == {2, 3, 4}
