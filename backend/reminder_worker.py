import os
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.models import Reminder, User, Exam

RESEND_API_URL = "https://api.resend.com/emails"


def send_email(to_email: str, subject: str, html: str) -> None:
    api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("REMINDER_FROM_EMAIL")
    if not api_key or not from_email:
        raise RuntimeError("RESEND_API_KEY and REMINDER_FROM_EMAIL must be configured")

    response = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"from": from_email, "to": [to_email], "subject": subject, "html": html},
        timeout=20,
    )
    response.raise_for_status()


def process_reminders(db: Session) -> int:
    now = datetime.now(timezone.utc)
    reminders = (
        db.query(Reminder, User, Exam)
        .join(User, Reminder.user_id == User.id)
        .join(Exam, Reminder.exam_id == Exam.id)
        .filter(Reminder.is_sent.is_(False), Reminder.remind_at <= now)
        .all()
    )

    sent = 0
    for reminder, user, exam in reminders:
        subject = f"ExamPilotAI reminder: {exam.title}"
        html = (
            f"<p>This is your ExamPilotAI reminder.</p>"
            f"<p><strong>{exam.title}</strong></p>"
            f"<p>Reminder type: {reminder.reminder_type.value}</p>"
            f"<p>Scheduled time: {reminder.remind_at.isoformat()}</p>"
        )
        send_email(user.email, subject, html)
        reminder.is_sent = True
        sent += 1

    if sent:
        db.commit()
    return sent


def main() -> None:
    db = SessionLocal()
    try:
        sent = process_reminders(db)
        print(f"Processed reminders: {sent}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
