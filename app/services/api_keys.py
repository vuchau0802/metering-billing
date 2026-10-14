from collections.abc import Callable
from dataclasses import dataclass
from secrets import token_urlsafe

from sqlalchemy.orm import Session

from app.auth import hash_tenant_api_key
from app.repositories import tenants as tenants_repository


class ApiKeyTenantNotFoundError(Exception):
    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        super().__init__(f"Tenant {tenant_id} was not found")


class ApiKeyAlreadyProvisionedError(Exception):
    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        super().__init__(
            f"Tenant {tenant_id} already has an API key; "
            "use --rotate to replace it"
        )


@dataclass(frozen=True)
class ApiKeyProvisionResult:
    tenant_id: int
    api_key: str
    rotated: bool


def generate_tenant_api_key() -> str:
    return f"tenant_{token_urlsafe(32)}"


def provision_tenant_api_key(
    db: Session,
    *,
    tenant_id: int,
    rotate: bool = False,
    key_generator: Callable[[], str] = generate_tenant_api_key,
) -> ApiKeyProvisionResult:
    tenant = tenants_repository.get_tenant_for_update(
        db,
        tenant_id,
    )

    if tenant is None:
        raise ApiKeyTenantNotFoundError(tenant_id)

    had_key = tenant.api_key_hash is not None

    if had_key and not rotate:
        raise ApiKeyAlreadyProvisionedError(tenant_id)

    api_key = key_generator()

    if len(api_key) < 32:
        raise ValueError(
            "Generated tenant API keys must be at least 32 characters"
        )

    tenant.api_key_hash = hash_tenant_api_key(api_key)
    db.commit()

    return ApiKeyProvisionResult(
        tenant_id=tenant.id,
        api_key=api_key,
        rotated=had_key,
    )
