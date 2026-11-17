import json
import os
from datetime import datetime, timedelta, timezone

from pywebpush import WebPushException, webpush
from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.models import Reminder, PushSubscription


def process_due_push_notifications():
    private_key = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    subject = os.getenv("VAPID_SUBJECT", "").strip()

    if not private_key or not subject:
        return {"processed": 0, "sent": 0, "errors": ["Push notifications are not configured"]}

    db: Session = SessionLocal()
    processed = 0
    sent = 0
    errors = []

    try:
        now = datetime.now(timezone.utc)
        has_subscription = exists().where(
            PushSubscription.user_id == Reminder.user_id
        )
        # PostgreSQL workers claim disjoint rows. The row locks remain held
        # until this batch commits, preventing another API instance from
        # delivering the same reminder concurrently.
        reminders = (
            db.query(Reminder)
            .filter(
                Reminder.push_sent.is_(False),
                Reminder.remind_at <= now,
                or_(
                    Reminder.push_next_attempt_at.is_(None),
                    Reminder.push_next_attempt_at <= now,
                ),
                has_subscription,
            )
            .order_by(Reminder.remind_at.asc(), Reminder.id.asc())
            .limit(50)
            .with_for_update(skip_locked=True)
            .all()
        )

        for reminder in reminders:
            processed += 1
            subscriptions = (
                db.query(PushSubscription)
                .filter(PushSubscription.user_id == reminder.user_id)
                .all()
            )

            delivered = False
            failure_messages = []
            payload = json.dumps({
                "title": "ExamPilotAI Reminder",
                "body": f"{reminder.exam.title} — {reminder.reminder_type.value.replace('_', ' ').title()}",
                "url": "./",
                "reminder_id": reminder.id,
            })

            for subscription in subscriptions:
                try:
                    webpush(
                        subscription_info=subscription.subscription,
                        data=payload,
                        vapid_private_key=private_key,
                        vapid_claims={"sub": subject},
                    )
                    delivered = True
                except WebPushException as exc:
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status in (404, 410):
                        db.delete(subscription)
                    else:
                        failure_messages.append(str(exc))
                except Exception as exc:
                    failure_messages.append(str(exc))

            # Delivery policy: one successful device delivery completes this
            # reminder. Other devices that failed in the same batch are not
            # retried, avoiding duplicate notifications to already-successful
            # devices. Per-device delivery tracking would be a separate schema.
            if delivered:
                reminder.push_sent = True
                reminder.push_next_attempt_at = None
                reminder.push_last_error = None
                sent += 1
            elif failure_messages:
                reminder.push_attempts = (reminder.push_attempts or 0) + 1
                delay_minutes = min(60, 2 ** min(reminder.push_attempts - 1, 6))
                reminder.push_next_attempt_at = now + timedelta(minutes=delay_minutes)
                reminder.push_last_error = "; ".join(failure_messages)[:2000]
                errors.extend(
                    f"reminder {reminder.id}: {message}"
                    for message in failure_messages
                )

        db.commit()
        return {"processed": processed, "sent": sent, "errors": errors}
    finally:
        db.close()
