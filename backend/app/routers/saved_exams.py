from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.models.models import SavedExam, Exam
from app.schemas.schemas import SavedExamCreate, SavedExamOut

router = APIRouter(prefix="/saved-exams", tags=["saved-exams"])


@router.post("/", response_model=SavedExamOut)
def save_exam(saved: SavedExamCreate, db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.id == saved.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    existing = db.query(SavedExam).filter(
        SavedExam.user_id == saved.user_id,
        SavedExam.exam_id == saved.exam_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Exam already saved")

    db_saved = SavedExam(**saved.model_dump())
    db.add(db_saved)
    db.commit()
    db.refresh(db_saved)
    return db_saved


@router.get("/user/{user_id}", response_model=List[SavedExamOut])
def list_saved_exams(user_id: int, db: Session = Depends(get_db)):
    return db.query(SavedExam).filter(SavedExam.user_id == user_id).all()


@router.delete("/{saved_exam_id}")
def unsave_exam(saved_exam_id: int, db: Session = Depends(get_db)):
    saved = db.query(SavedExam).filter(SavedExam.id == saved_exam_id).first()
    if not saved:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(saved)
    db.commit()
    return {"status": "removed"}
