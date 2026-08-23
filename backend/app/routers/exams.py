from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional

from app.core.auth import require_admin
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
    query = db.query(Exam).filter(Exam.is_active.is_(True))

    if state:
        query = query.filter(Exam.state == state)

    if category:
        query = query.filter(Exam.category == category)

    return query.order_by(Exam.application_end_date.asc()).all()


@router.get("/{exam_id}", response_model=ExamOut)
def get_exam(
    exam_id: int,
    db: Session = Depends(get_db),
):
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.is_active.is_(True)).first()

    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    return exam


@router.post("/", response_model=ExamOut, status_code=201)
def create_exam(
    exam: ExamCreate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    title = exam.title.strip()
    organization = exam.organization.strip()

    if not title:
        raise HTTPException(status_code=422, detail="Exam title cannot be empty")

    if not organization:
        raise HTTPException(status_code=422, detail="Organization cannot be empty")

    existing = (
        db.query(Exam)
        .filter(
            func.lower(func.trim(Exam.title)) == title.lower(),
            func.lower(func.trim(Exam.organization)) == organization.lower(),
        )
        .first()
    )

    if existing:
        raise HTTPException(status_code=409, detail="Exam already exists")

    exam_data = exam.model_dump()
    exam_data["title"] = title
    exam_data["organization"] = organization

    for field in ["state", "category", "description", "official_pdf_url"]:
        if exam_data.get(field):
            exam_data[field] = exam_data[field].strip()

    db_exam = Exam(**exam_data)
    db.add(db_exam)
    db.commit()
    db.refresh(db_exam)
    return db_exam
