from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.models import Reminder, Exam, User
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
