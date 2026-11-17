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
from app.routers.push_subscriptions import router as push_subscriptions_router
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
    app.include_router(push_subscriptions_router)
    active_user = {"value": user}
    app.dependency_overrides[get_current_user] = lambda: active_user["value"]

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    yield client, db, user, exam, TestingSession, engine, active_user
    client.close()
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_create_then_list_reminder_persists_after_reload(test_app):
    client, db, user, exam, _, _, _ = test_app
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
    client, _, user, exam, _, _, _ = test_app
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
    client, _, user, exam, _, _, _ = test_app
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



def test_automatic_reminder_endpoints_are_idempotent_sequentially(test_app):
    client, db, user, exam, _, _, _ = test_app
    future = datetime.now(timezone.utc) + timedelta(days=40)
    exam.application_end_date = future
    exam.exam_date = future + timedelta(days=10)
    db.commit()

    first = client.post(f"/reminders/automatic/{exam.id}")
    assert first.status_code == 200, first.text
    assert len(first.json()["created"]) == 3
    second = client.post(f"/reminders/automatic/{exam.id}")
    assert second.status_code == 200, second.text
    assert second.json()["created"] == []

    first = client.post(f"/reminders/automatic-exam/{exam.id}")
    assert first.status_code == 200, first.text
    assert len(first.json()["created"]) == 2
    second = client.post(f"/reminders/automatic-exam/{exam.id}")
    assert second.status_code == 200, second.text
    assert second.json()["created"] == []

    assert db.query(Reminder).filter(
        Reminder.user_id == user.id, Reminder.exam_id == exam.id,
        Reminder.reminder_type == ReminderType.APPLICATION_DEADLINE,
    ).count() == 3
    assert db.query(Reminder).filter(
        Reminder.user_id == user.id, Reminder.exam_id == exam.id,
        Reminder.reminder_type == ReminderType.EXAM_DAY,
    ).count() == 2



def test_push_endpoint_cannot_be_reassigned_to_another_user(test_app):
    client, db, user, _, _, _, active_user = test_app
    endpoint = "https://push.example.test/shared-endpoint"
    original_subscription = {
        "endpoint": endpoint,
        "keys": {"p256dh": "original-key", "auth": "original-auth"},
    }
    created = client.post(
        "/push-subscriptions/",
        json={"endpoint": endpoint, "subscription": original_subscription},
    )
    assert created.status_code == 200, created.text

    other_user = User(email="other-account@example.com")
    db.add(other_user)
    db.commit()
    db.refresh(other_user)
    active_user["value"] = other_user

    hijack = client.post(
        "/push-subscriptions/",
        json={
            "endpoint": endpoint,
            "subscription": {
                "endpoint": endpoint,
                "keys": {"p256dh": "attacker-key", "auth": "attacker-auth"},
            },
        },
    )
    assert hijack.status_code == 409

    record = db.query(PushSubscription).filter(
        PushSubscription.endpoint == endpoint
    ).one()
    assert record.user_id == user.id
    assert record.subscription == original_subscription


def test_push_endpoint_can_be_updated_by_its_owner(test_app):
    client, db, user, _, _, _, _ = test_app
    endpoint = "https://push.example.test/owned-endpoint"
    first = {"endpoint": endpoint, "keys": {"p256dh": "old", "auth": "old"}}
    second = {"endpoint": endpoint, "keys": {"p256dh": "new", "auth": "new"}}

    created = client.post(
        "/push-subscriptions/",
        json={"endpoint": endpoint, "subscription": first},
    )
    assert created.status_code == 200, created.text

    updated = client.post(
        "/push-subscriptions/",
        json={"endpoint": endpoint, "subscription": second},
    )
    assert updated.status_code == 200, updated.text
    record = db.query(PushSubscription).filter(
        PushSubscription.endpoint == endpoint
    ).one()
    assert record.user_id == user.id
    assert record.subscription == second
