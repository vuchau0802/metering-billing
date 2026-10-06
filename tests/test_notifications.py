from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.models import UsageAlert, UsageType
from app.services.notifications import (
    LoggingUsageAlertNotifier,
    NotificationConfigurationError,
    SmtpUsageAlertNotifier,
    build_usage_alert_notifier,
)


def make_settings(**overrides) -> Settings:
    values = {
        "usage_alert_transport": "smtp",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "mailer",
        "smtp_password": "secret",
        "smtp_from_email": "billing@example.com",
        "smtp_use_starttls": True,
    }
    values.update(overrides)

    return Settings(_env_file=None, **values)


def make_alert() -> UsageAlert:
    return UsageAlert(
        id=42,
        tenant_id=7,
        usage_type=UsageType.AI_TOKENS,
        window_start=datetime(2026, 10, 1, tzinfo=UTC),
        window_end=datetime(2026, 11, 1, tzinfo=UTC),
        threshold_percent=80,
        used=80_000,
        limit=100_000,
        status="pending",
        attempts=0,
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"smtp_host": None},
            "SMTP_HOST is not configured",
        ),
        (
            {"smtp_from_email": None},
            "SMTP_FROM_EMAIL is not configured",
        ),
    ],
)
def test_smtp_notifier_requires_configuration(
    overrides: dict,
    message: str,
) -> None:
    with pytest.raises(
        NotificationConfigurationError,
        match=message,
    ):
        SmtpUsageAlertNotifier(
            make_settings(**overrides)
        )


def test_smtp_credentials_must_be_configured_together() -> None:
    with pytest.raises(
        NotificationConfigurationError,
        match=(
            "SMTP_USERNAME and SMTP_PASSWORD "
            "must be configured together"
        ),
    ):
        SmtpUsageAlertNotifier(
            make_settings(smtp_password=None)
        )


def test_smtp_notifier_sends_email() -> None:
    settings = make_settings()
    alert = make_alert()
    smtp_client = MagicMock()

    with patch(
        "app.services.notifications.smtplib.SMTP"
    ) as smtp_class:
        smtp_class.return_value.__enter__.return_value = (
            smtp_client
        )

        notifier = SmtpUsageAlertNotifier(settings)
        notifier.send(
            recipient="customer@example.com",
            alert=alert,
        )

    smtp_class.assert_called_once_with(
        "smtp.example.com",
        587,
        timeout=10,
    )
    smtp_client.starttls.assert_called_once()
    smtp_client.login.assert_called_once_with(
        "mailer",
        "secret",
    )
    smtp_client.send_message.assert_called_once()

    message = smtp_client.send_message.call_args.args[0]

    assert message["From"] == "billing@example.com"
    assert message["To"] == "customer@example.com"
    assert "80% of ai tokens quota used" in message["Subject"]
    assert "Usage: 80,000 of 100,000" in message.get_content()


def test_factory_uses_logging_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(
        usage_alert_transport="logging"
    )
    monkeypatch.setattr(
        "app.services.notifications.get_settings",
        lambda: settings,
    )

    notifier = build_usage_alert_notifier()

    assert isinstance(notifier, LoggingUsageAlertNotifier)


def test_factory_builds_smtp_notifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings()
    monkeypatch.setattr(
        "app.services.notifications.get_settings",
        lambda: settings,
    )

    notifier = build_usage_alert_notifier()

    assert isinstance(notifier, SmtpUsageAlertNotifier)