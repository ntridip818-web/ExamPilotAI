import json
import os
from datetime import datetime, timezone

from pywebpush import WebPushException, webpush
from sqlalchemy import exists
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
        # Exclude reminders without any registered device from the batch query.
        # Otherwise the oldest 50 such reminders could occupy every scheduler run
        # and prevent reminders later in the queue from being processed.
        has_subscription = exists().where(
            PushSubscription.user_id == Reminder.user_id
        )
        reminders = (
            db.query(Reminder)
            .filter(
                Reminder.push_sent.is_(False),
                Reminder.remind_at <= now,
                has_subscription,
            )
            .order_by(Reminder.remind_at.asc())
            .limit(50)
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
                        # Remove expired subscriptions so they don't get retried forever.
                        db.delete(subscription)
                    else:
                        errors.append(f"reminder {reminder.id}: {exc}")
                except Exception as exc:
                    errors.append(f"reminder {reminder.id}: {exc}")

            if delivered:
                # This flag tracks push delivery only. Do not set is_sent here:
                # that field may represent overall/email completion and email is
                # not sent by this worker.
                reminder.push_sent = True
                sent += 1

        db.commit()
        return {"processed": processed, "sent": sent, "errors": errors}
    finally:
        db.close()
