from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ProcessedWebhookEvent


def claim_event(
    db: Session,
    *,
    stripe_event_id: str,
    event_type: str,
) -> bool:
    existing = db.scalar(
        select(ProcessedWebhookEvent).where(
            ProcessedWebhookEvent.stripe_event_id
            == stripe_event_id
        )
    )

    if existing is not None:
        return False

    db.add(
        ProcessedWebhookEvent(
            stripe_event_id=stripe_event_id,
            event_type=event_type,
        )
    )

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False

    return True