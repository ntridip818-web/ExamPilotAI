from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Enum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class ReminderType(str, enum.Enum):
    APPLICATION_DEADLINE = "application_deadline"
    ADMIT_CARD = "admit_card"
    EXAM_DAY = "exam_day"
    RESULT = "result"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    state = Column(String, nullable=True)
    education_level = Column(String, nullable=True)
    category = Column(String, nullable=True)
    firebase_uid = Column(String, unique=True, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    saved_exams = relationship("SavedExam", back_populates="user")
    reminders = relationship("Reminder", back_populates="user")


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    organization = Column(String, nullable=False)
    state = Column(String, nullable=True)
    category = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    application_start_date = Column(DateTime(timezone=True), nullable=True)
    application_end_date = Column(DateTime(timezone=True), nullable=True)
    exam_date = Column(DateTime(timezone=True), nullable=True)
    official_pdf_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    saved_by = relationship("SavedExam", back_populates="exam")
    reminders = relationship("Reminder", back_populates="exam")


class SavedExam(Base):
    __tablename__ = "saved_exams"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    saved_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="saved_exams")
    exam = relationship("Exam", back_populates="saved_by")


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    reminder_type = Column(Enum(ReminderType), nullable=False)
    remind_at = Column(DateTime(timezone=True), nullable=False)
    is_sent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="reminders")
    exam = relationship("Exam", back_populates="reminders")
