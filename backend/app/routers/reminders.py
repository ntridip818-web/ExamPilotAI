from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.models.models import Reminder
from app.schemas.schemas import ReminderCreate, ReminderOut

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.post("/", response_model=ReminderOut)
def create_reminder(reminder: ReminderCreate, db: Session = Depends(get_db)):
    db_reminder = Reminder(**reminder.model_dump())
    db.add(db_reminder)
    db.commit()
    db.refresh(db_reminder)
    return db_reminder


@router.get("/user/{user_id}", response_model=List[ReminderOut])
def list_user_reminders(user_id: int, db: Session = Depends(get_db)):
    return db.query(Reminder).filter(Reminder.user_id == user_id).all()


@router.delete("/{reminder_id}")
def delete_reminder(reminder_id: int, db: Session = Depends(get_db)):
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(reminder)
    db.commit()
    return {"status": "deleted"}
