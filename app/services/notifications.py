import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

from app.config import Settings, get_settings
from app.models import UsageAlert


logger = logging.getLogger(__name__)


class NotificationConfigurationError(RuntimeError):
    pass


class UsageAlertNotifier(Protocol):
    def send(
        self,
        *,
        recipient: str,
        alert: UsageAlert,
    ) -> None:
        ...


class LoggingUsageAlertNotifier:
    def send(
        self,
        *,
        recipient: str,
        alert: UsageAlert,
    ) -> None:
        logger.info(
            "USAGE_ALERT recipient=%s tenant=%s "
            "usage_type=%s threshold=%s%% used=%s limit=%s",
            recipient,
            alert.tenant_id,
            alert.usage_type.value,
            alert.threshold_percent,
            alert.used,
            alert.limit,
        )


class SmtpUsageAlertNotifier:
    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_host:
            raise NotificationConfigurationError(
                "SMTP_HOST is not configured"
            )

        if not settings.smtp_from_email:
            raise NotificationConfigurationError(
                "SMTP_FROM_EMAIL is not configured"
            )

        if bool(settings.smtp_username) != bool(
            settings.smtp_password
        ):
            raise NotificationConfigurationError(
                "SMTP_USERNAME and SMTP_PASSWORD "
                "must be configured together"
            )

        self.settings = settings

    def send(
        self,
        *,
        recipient: str,
        alert: UsageAlert,
    ) -> None:
        usage_name = alert.usage_type.value.replace(
            "_",
            " ",
        )

        message = EmailMessage()
        message["Subject"] = (
            f"Usage alert: {alert.threshold_percent}% "
            f"of {usage_name} quota used"
        )
        message["From"] = self.settings.smtp_from_email
        message["To"] = recipient
        message.set_content(
            "\n".join(
                [
                    f"Tenant: {alert.tenant_id}",
                    f"Usage type: {usage_name}",
                    (
                        f"Usage: {alert.used:,} "
                        f"of {alert.limit:,}"
                    ),
                    (
                        "Threshold: "
                        f"{alert.threshold_percent}%"
                    ),
                    (
                        "Billing window: "
                        f"{alert.window_start.isoformat()} "
                        f"to {alert.window_end.isoformat()}"
                    ),
                ]
            )
        )

        with smtplib.SMTP(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=10,
        ) as client:
            client.ehlo()

            if self.settings.smtp_use_starttls:
                client.starttls(
                    context=ssl.create_default_context()
                )
                client.ehlo()

            if self.settings.smtp_username:
                client.login(
                    self.settings.smtp_username,
                    self.settings.smtp_password,
                )

            client.send_message(message)


def build_usage_alert_notifier() -> UsageAlertNotifier:
    settings = get_settings()

    if settings.usage_alert_transport == "smtp":
        return SmtpUsageAlertNotifier(settings)

    return LoggingUsageAlertNotifier()
