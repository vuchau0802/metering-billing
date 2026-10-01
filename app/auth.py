from hashlib import sha256
from hmac import compare_digest

from sqlalchemy.orm import Session

from app.models import Tenant


class TenantAuthenticationError(Exception):
    pass


def hash_tenant_api_key(api_key: str) -> str:
    return sha256(api_key.encode("utf-8")).hexdigest()


def require_tenant_access(
    db: Session,
    *,
    tenant_id: int,
    api_key: str | None,
) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    expected_hash = (
        tenant.api_key_hash
        if tenant is not None and tenant.api_key_hash is not None
        else "0" * 64
    )
    supplied_hash = hash_tenant_api_key(api_key or "")

    if not compare_digest(supplied_hash, expected_hash):
        raise TenantAuthenticationError(
            "The tenant API key is missing or invalid."
        )

    return tenant
