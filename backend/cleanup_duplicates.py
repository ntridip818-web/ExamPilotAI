from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.models import Exam, SavedExam, Reminder

import os


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

db = SessionLocal()

try:
    # Find duplicate exams by title + organization
    exams = (
        db.query(Exam)
        .order_by(Exam.title, Exam.organization, Exam.id.asc())
        .all()
    )

    groups = {}

    for exam in exams:
        key = (
            exam.title.strip().lower(),
            exam.organization.strip().lower(),
        )
        groups.setdefault(key, []).append(exam)

    deleted = 0

    for key, duplicate_group in groups.items():

        if len(duplicate_group) <= 1:
            continue

        # Keep the oldest exam (smallest ID)
        keep = duplicate_group[0]
        duplicates = duplicate_group[1:]

        print(
            f"Keeping Exam ID {keep.id}: "
            f"{keep.title} / {keep.organization}"
        )

        for duplicate in duplicates:

            print(f"Removing duplicate Exam ID {duplicate.id}")

            # Move saved exams to the kept exam
            saved_exams = (
                db.query(SavedExam)
                .filter(SavedExam.exam_id == duplicate.id)
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
                    db.delete(saved)
                else:
                    saved.exam_id = keep.id

            # Move reminders to the kept exam
            reminders = (
                db.query(Reminder)
                .filter(Reminder.exam_id == duplicate.id)
                .all()
            )

            for reminder in reminders:
                reminder.exam_id = keep.id

            # Delete duplicate exam
            db.delete(duplicate)
            deleted += 1

    db.commit()

    print(f"Cleanup complete. Deleted {deleted} duplicate exams.")

finally:
    db.close()
