from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from app.models.models import ReminderType


class UserCreate(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    state: Optional[str] = None
    education_level: Optional[str] = None
    category: Optional[str] = None


class UserOut(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    state: Optional[str]
    education_level: Optional[str]
    category: Optional[str]

    class Config:
        from_attributes = True


class ExamOut(BaseModel):
    id: int
    title: str
    organization: str
    state: Optional[str]
    category: Optional[str]
    description: Optional[str]
    application_start_date: Optional[datetime]
    application_end_date: Optional[datetime]
    exam_date: Optional[datetime]
    official_pdf_url: Optional[str]

    class Config:
        from_attributes = True


class ExamCreate(BaseModel):
    title: str
    organization: str
    state: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    application_start_date: Optional[datetime] = None
    application_end_date: Optional[datetime] = None
    exam_date: Optional[datetime] = None
    official_pdf_url: Optional[str] = None


class SavedExamCreate(BaseModel):
    user_id: int
    exam_id: int


class SavedExamOut(BaseModel):
    id: int
    exam: ExamOut
    saved_at: datetime

    class Config:
        from_attributes = True


class ReminderCreate(BaseModel):
    user_id: int
    exam_id: int
    reminder_type: ReminderType
    remind_at: datetime


class ReminderOut(BaseModel):
    id: int
    exam_id: int
    reminder_type: ReminderType
    remind_at: datetime
    is_sent: bool

    class Config:
        from_attributes = True
