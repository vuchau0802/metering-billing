from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app import db as database
from app.config import Settings


def test_database_engine_uses_configured_pool_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        database_url=(
            "postgresql+psycopg://postgres:postgres"
            "@127.0.0.1:5432/metering"
        ),
        database_pool_size=7,
        database_max_overflow=12,
        database_pool_timeout_seconds=15,
        database_pool_recycle_seconds=900,
    )
    expected_engine = MagicMock()
    create_engine = MagicMock(return_value=expected_engine)

    monkeypatch.setattr(
        database,
        "create_engine",
        create_engine,
    )

    result = database.create_database_engine(settings)

    assert result is expected_engine
    create_engine.assert_called_once_with(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=7,
        max_overflow=12,
        pool_timeout=15,
        pool_recycle=900,
    )


@pytest.mark.parametrize(
    ("setting_name", "invalid_value"),
    [
        ("database_pool_size", 0),
        ("database_max_overflow", -1),
        ("database_pool_timeout_seconds", 0),
        ("database_pool_recycle_seconds", 0),
    ],
)
def test_database_pool_settings_reject_invalid_values(
    setting_name: str,
    invalid_value: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            **{setting_name: invalid_value},
        )