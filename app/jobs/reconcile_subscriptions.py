import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from stripe import StripeClient

from app.config import get_settings
from app.db import SessionLocal
from app.repositories import subscriptions
from app.services.billing import BillingConfigurationError
from app.services.webhooks import synchronize_subscription


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationResult:
    checked: int
    succeeded: int
    failed: int


def _reconcile_one(
    client: StripeClient,
    stripe_subscription_id: str,
    *,
    max_attempts: int,
    base_delay_seconds: float,
    sleep: Callable[[float], None],
) -> bool:
    for attempt in range(1, max_attempts + 1):
        try:
            stripe_subscription = (
                client.v1.subscriptions.retrieve(
                    stripe_subscription_id
                )
            )

            with SessionLocal() as db:
                synchronize_subscription(
                    db,
                    stripe_subscription.to_dict(),
                )
                db.commit()

            logger.info(
                "Reconciled Stripe subscription %s",
                stripe_subscription_id,
            )
            return True
        except Exception:
            if attempt == max_attempts:
                logger.exception(
                    "RECONCILIATION_FAILED subscription=%s "
                    "attempts=%s",
                    stripe_subscription_id,
                    max_attempts,
                )
                return False

            delay = base_delay_seconds * (
                2 ** (attempt - 1)
            )

            logger.warning(
                "Reconciliation attempt %s/%s failed for %s; "
                "retrying in %.1f seconds",
                attempt,
                max_attempts,
                stripe_subscription_id,
                delay,
            )
            sleep(delay)

    return False


def run_reconciliation(
    *,
    client: StripeClient | None = None,
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> ReconciliationResult:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    if base_delay_seconds < 0:
        raise ValueError(
            "base_delay_seconds cannot be negative"
        )

    settings = get_settings()

    if client is None:
        if not settings.stripe_secret_key:
            raise BillingConfigurationError(
                "STRIPE_SECRET_KEY is not configured"
            )

        client = StripeClient(
            settings.stripe_secret_key
        )

    with SessionLocal() as db:
        subscription_ids = (
            subscriptions.list_reconcilable_ids(db)
        )

    succeeded = 0
    failed = 0

    for stripe_subscription_id in subscription_ids:
        reconciled = _reconcile_one(
            client,
            stripe_subscription_id,
            max_attempts=max_attempts,
            base_delay_seconds=base_delay_seconds,
            sleep=sleep,
        )

        if reconciled:
            succeeded += 1
        else:
            failed += 1

    return ReconciliationResult(
        checked=len(subscription_ids),
        succeeded=succeeded,
        failed=failed,
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s "
            "%(name)s %(message)s"
        ),
    )

    try:
        result = run_reconciliation()
    except Exception:
        logger.exception(
            "RECONCILIATION_JOB_FAILED before completion"
        )
        return 1

    logger.info(
        "Reconciliation complete: checked=%s "
        "succeeded=%s failed=%s",
        result.checked,
        result.succeeded,
        result.failed,
    )

    if result.failed:
        logger.critical(
            "RECONCILIATION_ALERT: %s subscription(s) "
            "could not be reconciled",
            result.failed,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())