from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.database import Base, get_db
from app.models.models import Exam, PushSubscription, Reminder, ReminderType, User
from app.routers.reminders import router as reminders_router
from app.services import push_worker


@pytest.fixture
def test_app():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSession()
    user = User(email="reminder-test@example.com")
    exam = Exam(title="Persistence Test Exam", organization="Test Org")
    db.add_all([user, exam])
    db.commit()
    db.refresh(user)
    db.refresh(exam)

    app = FastAPI()
    app.include_router(reminders_router)
    app.dependency_overrides[get_current_user] = lambda: user

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    yield client, db, user, exam, TestingSession, engine
    client.close()
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_create_then_list_reminder_persists_after_reload(test_app):
    client, db, user, exam, _, _ = test_app
    remind_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    response = client.post(
        "/reminders/",
        json={
            "user_id": user.id,
            "exam_id": exam.id,
            "reminder_type": "application_deadline",
            "remind_at": remind_at,
        },
    )
    assert response.status_code == 200, response.text
    created = response.json()

    # A separate GET request mirrors the frontend's post-refresh reload.
    response = client.get(f"/reminders/user/{user.id}")
    assert response.status_code == 200, response.text
    records = response.json()
    assert any(record["id"] == created["id"] for record in records)


def test_multiple_reminders_for_same_exam_are_preserved(test_app):
    client, _, user, exam, _, _ = test_app
    for days in (1, 2):
        response = client.post(
            "/reminders/",
            json={
                "user_id": user.id,
                "exam_id": exam.id,
                "reminder_type": "application_deadline",
                "remind_at": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
            },
        )
        assert response.status_code == 200, response.text

    response = client.get(f"/reminders/user/{user.id}")
    assert response.status_code == 200, response.text
    matching = [r for r in response.json() if r["exam_id"] == exam.id]
    assert len(matching) == 2


def test_reminder_endpoints_reject_other_users(test_app):
    client, _, user, exam, _, _ = test_app
    response = client.get(f"/reminders/user/{user.id + 999}")
    assert response.status_code == 403

    response = client.post(
        "/reminders/",
        json={
            "user_id": user.id + 999,
            "exam_id": exam.id,
            "reminder_type": "application_deadline",
            "remind_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 403
