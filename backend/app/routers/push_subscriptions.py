from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.models import PushSubscription, User
from app.schemas.schemas import PushSubscriptionCreate, PushSubscriptionOut

router = APIRouter(prefix="/push-subscriptions", tags=["push-subscriptions"])


@router.get("/public-key")
def get_public_key():
    import os
    key = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="Push notifications are not configured")
    return {"public_key": key}


@router.post("/", response_model=PushSubscriptionOut)
def save_push_subscription(
    payload: PushSubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(PushSubscription).filter(
        PushSubscription.endpoint == payload.endpoint
    ).first()

    if existing:
        if existing.user_id != current_user.id:
            existing.user_id = current_user.id
        existing.subscription = payload.subscription
        db.commit()
        db.refresh(existing)
        return existing

    record = PushSubscription(
        user_id=current_user.id,
        endpoint=payload.endpoint,
        subscription=payload.subscription,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/")
def delete_push_subscription(
    endpoint: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.query(PushSubscription).filter(
        PushSubscription.endpoint == endpoint,
        PushSubscription.user_id == current_user.id,
    ).first()
    if record:
        db.delete(record)
        db.commit()
    return {"status": "deleted"}
