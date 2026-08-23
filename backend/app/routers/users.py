from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, verify_bearer_token
from app.core.database import get_db
from app.models.models import User
from app.schemas.schemas import UserCreate, UserOut, UserProfileUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserOut)
def create_user(
    user: UserCreate,
    token: dict = Depends(verify_bearer_token),
    db: Session = Depends(get_db),
):
    uid = token.get("uid")
    token_email = (token.get("email") or "").strip().lower()
    email = str(user.email).strip().lower()

    if not uid or not token_email or token_email != email:
        raise HTTPException(status_code=403, detail="Authenticated email does not match request")

    existing = db.query(User).filter(User.firebase_uid == uid).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    existing_by_email = db.query(User).filter(User.email == email).first()
    if existing_by_email:
        if existing_by_email.firebase_uid and existing_by_email.firebase_uid != uid:
            raise HTTPException(status_code=409, detail="Email is already linked to another account")
        existing_by_email.firebase_uid = uid
        for field, value in user.model_dump(exclude={"email"}).items():
            setattr(existing_by_email, field, value)
        db.commit()
        db.refresh(existing_by_email)
        return existing_by_email

    db_user = User(**user.model_dump(), firebase_uid=uid)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this profile")
    return current_user


@router.put("/{user_id}", response_model=UserOut)
def update_user_profile(
    user_id: int,
    profile: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this profile")

    update_data = profile.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)
    return current_user
