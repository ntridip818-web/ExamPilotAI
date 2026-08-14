from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.orm import Session

from app.core.database import Base, engine, get_db
from app.models.models import Exam, SavedExam, Reminder
from app.routers import exams, users, saved_exams, reminders

import os
import secrets


# Create database tables
Base.metadata.create_all(bind=engine)


# FastAPI application
app = FastAPI(
    title="ExamPilotAI API",
    description="Backend for the ExamPilotAI government exam tracking platform",
    version="0.1.0",
)


# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API routers
app.include_router(users.router)
app.include_router(exams.router)
app.include_router(saved_exams.router)
app.include_router(reminders.router)


# Health check
@app.get("/")
def root():
    return {
        "status": "ExamPilotAI API is running"
    }


# Temporary protected endpoint
# Used once to remove duplicate exams from the database.
@app.post("/admin/cleanup-duplicate-exams")
def cleanup_duplicate_exams(
    x_cleanup_token: str = Header(...),
    db: Session = Depends(get_db),
):
    cleanup_token = os.getenv("CLEANUP_TOKEN")

    # Security check
    if not cleanup_token or not secrets.compare_digest(
        x_cleanup_token,
        cleanup_token,
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid cleanup token",
        )

    # Get all exams ordered by ID
    exams = (
        db.query(Exam)
        .order_by(
            Exam.title,
            Exam.organization,
            Exam.id.asc(),
        )
        .all()
    )

    groups = {}

    # Group exams by normalized title + organization
    for exam in exams:
        key = (
            exam.title.strip().lower(),
            exam.organization.strip().lower(),
        )

        groups.setdefault(key, []).append(exam)

    deleted = 0

    # Process duplicate groups
    for key, duplicate_group in groups.items():

        if len(duplicate_group) <= 1:
            continue

        # Keep the oldest exam
        keep = duplicate_group[0]

        # Remove duplicates
        for duplicate in duplicate_group[1:]:

            # Move saved exams
            saved_exams = (
                db.query(SavedExam)
                .filter(
                    SavedExam.exam_id == duplicate.id
                )
                .all()
            )

            for saved in saved_exams:

                existing_saved = (
                    db.query(SavedExam)
                    .filter(
                        SavedExam.user_id == saved.user_id,
                        SavedExam.exam_id == keep.id,
                    )
                    .first()
                )

                if existing_saved:
                    # User already saved the kept exam
                    db.delete(saved)
                else:
                    # Move saved exam to kept exam
                    saved.exam_id = keep.id

            # Move reminders
            reminders = (
                db.query(Reminder)
                .filter(
                    Reminder.exam_id == duplicate.id
                )
                .all()
            )

            for reminder in reminders:
                reminder.exam_id = keep.id

            # Delete duplicate exam
            db.delete(duplicate)

            deleted += 1

    # Save changes
    db.commit()

    return {
        "status": "cleanup_complete",
        "deleted_duplicates": deleted,
    }
