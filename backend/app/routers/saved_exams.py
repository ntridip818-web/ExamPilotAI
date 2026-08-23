from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.models import SavedExam, Exam, User
from app.schemas.schemas import SavedExamCreate, SavedExamOut

router = APIRouter(prefix="/saved-exams", tags=["saved-exams"])


@router.post("/", response_model=SavedExamOut)
def save_exam(
    saved: SavedExamCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if saved.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot modify another user's saved exams")

    exam = db.query(Exam).filter(Exam.id == saved.exam_id, Exam.is_active.is_(True)).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    existing = db.query(SavedExam).filter(
        SavedExam.user_id == current_user.id,
        SavedExam.exam_id == saved.exam_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Exam already saved")

    db_saved = SavedExam(user_id=current_user.id, exam_id=saved.exam_id)
    db.add(db_saved)
    db.commit()
    db.refresh(db_saved)
    return db_saved


@router.get("/user/{user_id}", response_model=List[SavedExamOut])
def list_saved_exams(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access another user's saved exams")
    return db.query(SavedExam).filter(SavedExam.user_id == current_user.id).all()


@router.delete("/{saved_exam_id}")
def unsave_exam(
    saved_exam_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    saved = db.query(SavedExam).filter(SavedExam.id == saved_exam_id).first()
    if not saved:
        raise HTTPException(status_code=404, detail="Not found")
    if saved.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot delete another user's saved exam")

    db.delete(saved)
    db.commit()
    return {"status": "removed"}
