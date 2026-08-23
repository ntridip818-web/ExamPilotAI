from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.core.database import Base, engine, get_db
from app.models.models import Exam, SavedExam, Reminder
from app.routers import exams, users, saved_exams, reminders

import os
import secrets


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ExamPilotAI API",
    description="Backend for the ExamPilotAI government exam tracking platform",
    version="0.1.0",
)


cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


app.include_router(users.router)
app.include_router(exams.router)
app.include_router(saved_exams.router)
app.include_router(reminders.router)


@app.get("/")
def root():
    return {"status": "ExamPilotAI API is running"}


@app.post("/admin/cleanup-duplicate-exams")
def cleanup_duplicate_exams(
    x_cleanup_token: str = Header(...),
    db: Session = Depends(get_db),
):
    cleanup_token = os.getenv("CLEANUP_TOKEN")

    if not cleanup_token or not secrets.compare_digest(x_cleanup_token, cleanup_token):
        raise HTTPException(status_code=403, detail="Invalid cleanup token")

    exams = (
        db.query(Exam)
        .order_by(Exam.title, Exam.organization, Exam.id.asc())
        .all()
    )

    groups = {}
    for exam in exams:
        key = (exam.title.strip().lower(), exam.organization.strip().lower())
        groups.setdefault(key, []).append(exam)

    deleted = 0

    for duplicate_group in groups.values():
        if len(duplicate_group) <= 1:
            continue

        keep = duplicate_group[0]

        for duplicate in duplicate_group[1:]:
            saved_exams = db.query(SavedExam).filter(SavedExam.exam_id == duplicate.id).all()
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
                    db.delete(saved)
                else:
                    saved.exam_id = keep.id

            reminders = db.query(Reminder).filter(Reminder.exam_id == duplicate.id).all()
            for reminder in reminders:
                reminder.exam_id = keep.id

            db.delete(duplicate)
            deleted += 1

    db.commit()

    return {
        "status": "cleanup_complete",
        "deleted_duplicates": deleted,
    }
