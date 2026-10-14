import pytest
from sqlalchemy import delete

from app.auth import (
    TenantAuthenticationError,
    hash_tenant_api_key,
    require_tenant_access,
)
from app.db import SessionLocal
from app.jobs import manage_tenant_api_key
from app.models import Plan, PlanName, Tenant, TenantStatus
from app.services.api_keys import (
    ApiKeyAlreadyProvisionedError,
    ApiKeyProvisionResult,
    provision_tenant_api_key,
)


TENANT_ID = 960_001
ORIGINAL_KEY = "tenant_original_key_with_enough_entropy_123"
NEW_KEY = "tenant_replacement_key_with_enough_entropy_456"


@pytest.fixture(autouse=True)
def tenant():
    with SessionLocal() as db:
        db.execute(delete(Tenant).where(Tenant.id == TENANT_ID))

        if db.get(Plan, PlanName.FREE) is None:
            db.add(
                Plan(
                    name=PlanName.FREE,
                    api_calls_limit=1_000,
                    ai_tokens_limit=100_000,
                    overage_enabled=False,
                    stripe_price_id=None,
                )
            )
            db.flush()

        db.add(
            Tenant(
                id=TENANT_ID,
                email="api-key-test@example.com",
                plan=PlanName.FREE,
                status=TenantStatus.ACTIVE,
            )
        )
        db.commit()

    yield

    with SessionLocal() as db:
        db.execute(delete(Tenant).where(Tenant.id == TENANT_ID))
        db.commit()


def test_provision_stores_only_hash_and_authenticates() -> None:
    with SessionLocal() as db:
        result = provision_tenant_api_key(
            db,
            tenant_id=TENANT_ID,
            key_generator=lambda: ORIGINAL_KEY,
        )

    assert result.api_key == ORIGINAL_KEY
    assert result.rotated is False

    with SessionLocal() as db:
        stored = db.get(Tenant, TENANT_ID)
        authenticated = require_tenant_access(
            db,
            tenant_id=TENANT_ID,
            api_key=ORIGINAL_KEY,
        )

        assert stored is not None
        assert stored.api_key_hash == hash_tenant_api_key(ORIGINAL_KEY)
        assert stored.api_key_hash != ORIGINAL_KEY
        assert authenticated.id == TENANT_ID


def test_existing_key_requires_explicit_rotation() -> None:
    with SessionLocal() as db:
        tenant = db.get(Tenant, TENANT_ID)
        assert tenant is not None
        tenant.api_key_hash = hash_tenant_api_key(ORIGINAL_KEY)
        db.commit()

        with pytest.raises(
            ApiKeyAlreadyProvisionedError,
            match="use --rotate",
        ):
            provision_tenant_api_key(
                db,
                tenant_id=TENANT_ID,
                key_generator=lambda: NEW_KEY,
            )

    with SessionLocal() as db:
        tenant = db.get(Tenant, TENANT_ID)
        assert tenant is not None
        assert tenant.api_key_hash == hash_tenant_api_key(ORIGINAL_KEY)


def test_rotation_revokes_old_key() -> None:
    with SessionLocal() as db:
        tenant = db.get(Tenant, TENANT_ID)
        assert tenant is not None
        tenant.api_key_hash = hash_tenant_api_key(ORIGINAL_KEY)
        db.commit()

        result = provision_tenant_api_key(
            db,
            tenant_id=TENANT_ID,
            rotate=True,
            key_generator=lambda: NEW_KEY,
        )

    assert result.rotated is True

    with SessionLocal() as db:
        with pytest.raises(TenantAuthenticationError):
            require_tenant_access(
                db,
                tenant_id=TENANT_ID,
                api_key=ORIGINAL_KEY,
            )

        authenticated = require_tenant_access(
            db,
            tenant_id=TENANT_ID,
            api_key=NEW_KEY,
        )

    assert authenticated.id == TENANT_ID


def test_command_prints_plaintext_key_once(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeSession:
        def __enter__(self) -> "FakeSession":
            return self

        def __exit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(
        manage_tenant_api_key,
        "SessionLocal",
        FakeSession,
    )
    monkeypatch.setattr(
        manage_tenant_api_key,
        "provision_tenant_api_key",
        lambda db, tenant_id, rotate: ApiKeyProvisionResult(
            tenant_id=tenant_id,
            api_key=NEW_KEY,
            rotated=rotate,
        ),
    )

    exit_code = manage_tenant_api_key.main(
        [str(TENANT_ID), "--rotate"]
    )
    output = capsys.readouterr()

    assert exit_code == 0
    assert output.out.count(NEW_KEY) == 1
    assert output.err == ""
