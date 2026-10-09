from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.models import Reminder, ReminderType, Exam, User
from app.schemas.schemas import ReminderCreate, ReminderOut

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.post("/", response_model=ReminderOut)
def create_reminder(
    reminder: ReminderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if reminder.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot create a reminder for another user")

    exam = db.query(Exam).filter(Exam.id == reminder.exam_id, Exam.is_active.is_(True)).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    db_reminder = Reminder(
        user_id=current_user.id,
        exam_id=reminder.exam_id,
        reminder_type=reminder.reminder_type,
        remind_at=reminder.remind_at,
    )
    db.add(db_reminder)
    db.commit()
    db.refresh(db_reminder)
    return db_reminder


@router.post("/automatic/{exam_id}")
def create_automatic_deadline_reminders(
    exam_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create idempotent 7-, 3-, and 1-day deadline reminders at 9:00 AM IST."""
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.is_active.is_(True)).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    if not exam.application_end_date:
        raise HTTPException(
            status_code=400,
            detail="This exam has no verified application deadline yet.",
        )

    ist = ZoneInfo("Asia/Kolkata")
    deadline = exam.application_end_date
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=ist)
    else:
        deadline = deadline.astimezone(ist)

    now = datetime.now(timezone.utc)
    created = []
    skipped = []
    for days_before in (7, 3, 1):
        local_date = deadline.date() - timedelta(days=days_before)
        local_time = datetime.combine(local_date, time(hour=9), tzinfo=ist)
        remind_at = local_time.astimezone(timezone.utc)
        if remind_at <= now:
            skipped.append(days_before)
            continue

        existing = db.query(Reminder).filter(
            Reminder.user_id == current_user.id,
            Reminder.exam_id == exam_id,
            Reminder.reminder_type == ReminderType.APPLICATION_DEADLINE,
            Reminder.remind_at == remind_at,
        ).first()
        if existing:
            continue

        item = Reminder(
            user_id=current_user.id,
            exam_id=exam_id,
            reminder_type=ReminderType.APPLICATION_DEADLINE,
            remind_at=remind_at,
        )
        db.add(item)
        created.append({"days_before": days_before, "remind_at": remind_at.isoformat()})

    db.commit()
    return {
        "status": "ok",
        "created": created,
        "skipped_past_reminders": skipped,
        "message": "Automatic reminders created." if created else "No new future reminders were needed.",
    }


@router.post("/automatic-exam/{exam_id}")
def create_automatic_exam_day_reminders(
    exam_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create reminders at 9:00 AM IST the day before and 6:00 AM IST on exam day."""
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.is_active.is_(True)).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if not exam.exam_date:
        raise HTTPException(status_code=400, detail="This exam has no verified exam date yet.")

    ist = ZoneInfo("Asia/Kolkata")
    exam_date = exam.exam_date
    if exam_date.tzinfo is None:
        exam_date = exam_date.replace(tzinfo=ist)
    else:
        exam_date = exam_date.astimezone(ist)

    now = datetime.now(timezone.utc)
    created = []
    for days_before, hour in ((1, 9), (0, 6)):
        local_date = exam_date.date() - timedelta(days=days_before)
        local_time = datetime.combine(local_date, time(hour=hour), tzinfo=ist)
        remind_at = local_time.astimezone(timezone.utc)
        if remind_at <= now:
            continue

        existing = db.query(Reminder).filter(
            Reminder.user_id == current_user.id,
            Reminder.exam_id == exam_id,
            Reminder.reminder_type == ReminderType.EXAM_DAY,
            Reminder.remind_at == remind_at,
        ).first()
        if existing:
            continue

        db.add(Reminder(
            user_id=current_user.id,
            exam_id=exam_id,
            reminder_type=ReminderType.EXAM_DAY,
            remind_at=remind_at,
        ))
        created.append({"days_before": days_before, "remind_at": remind_at.isoformat()})

    db.commit()
    return {
        "status": "ok",
        "created": created,
        "message": "Exam-day reminders created." if created else "No new future exam-day reminders were needed.",
    }


@router.get("/user/{user_id}", response_model=List[ReminderOut])
def list_user_reminders(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access another user's reminders")
    return db.query(Reminder).filter(Reminder.user_id == current_user.id).all()


@router.delete("/{reminder_id}")
def delete_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Not found")
    if reminder.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot delete another user's reminder")

    db.delete(reminder)
    db.commit()
    return {"status": "deleted"}
