import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.models import Exam, PushSubscription, Reminder, ReminderType, User
from app.services import push_worker


@pytest.fixture
def db_session(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    monkeypatch.setattr(push_worker, "SessionLocal", lambda: session)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-key")
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:test@example.com")

    user = User(email="test@example.com")
    exam = Exam(title="Test Exam", organization="Test Org")
    session.add_all([user, exam])
    session.commit()
    reminder = Reminder(
        user_id=user.id,
        exam_id=exam.id,
        reminder_type=ReminderType.APPLICATION_DEADLINE,
        remind_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    subscription = PushSubscription(
        user_id=user.id,
        endpoint="https://push.example.test/endpoint",
        subscription={"endpoint": "https://push.example.test/endpoint", "keys": {"p256dh": "x", "auth": "y"}},
    )
    session.add_all([reminder, subscription])
    session.commit()
    yield session, reminder, subscription
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_successful_push_marks_push_only(db_session):
    session, reminder, _ = db_session
    with patch.object(push_worker, "webpush") as send:
        result = push_worker.process_due_push_notifications()

    assert send.call_count == 1
    assert result["sent"] == 1
    session.refresh(reminder)
    assert reminder.push_sent is True
    # Push success must not imply email/overall delivery completion.
    assert reminder.is_sent is False


def test_transient_push_failure_remains_retryable(db_session):
    session, reminder, _ = db_session
    with patch.object(
        push_worker,
        "webpush",
        side_effect=RuntimeError("temporary network failure"),
    ):
        result = push_worker.process_due_push_notifications()

    assert result["sent"] == 0
    assert result["errors"]
    session.refresh(reminder)
    assert reminder.push_sent is False


def test_expired_subscription_is_removed(db_session):
    session, reminder, subscription = db_session

    class Response:
        status_code = 410

    class ExpiredPushError(Exception):
        response = Response()

    with patch.object(push_worker, "webpush", side_effect=push_worker.WebPushException("expired", response=Response())):
        result = push_worker.process_due_push_notifications()

    assert result["sent"] == 0
    assert session.get(PushSubscription, subscription.id) is None
    session.refresh(reminder)
    assert reminder.push_sent is False
