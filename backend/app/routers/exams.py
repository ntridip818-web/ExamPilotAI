from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.models.models import Exam
from app.schemas.schemas import ExamOut, ExamCreate

router = APIRouter(prefix="/exams", tags=["exams"])


@router.get("/", response_model=List[ExamOut])
def list_exams(
    state: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Exam).filter(Exam.is_active == True)
    if state:
        query = query.filter(Exam.state == state)
    if category:
        query = query.filter(Exam.category == category)
    return query.order_by(Exam.application_end_date.asc()).all()


@router.get("/{exam_id}", response_model=ExamOut)
def get_exam(exam_id: int, db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    return exam


@router.post("/", response_model=ExamOut)
def create_exam(exam: ExamCreate, db: Session = Depends(get_db)):
    db_exam = Exam(**exam.model_dump())
    db.add(db_exam)
    db.commit()
    db.refresh(db_exam)
    return db_exam
