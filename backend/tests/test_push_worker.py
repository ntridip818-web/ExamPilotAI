from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
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
    setup_session = TestingSession()
    monkeypatch.setattr(push_worker, "SessionLocal", TestingSession)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-key")
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:test@example.com")

    user = User(email="test@example.com")
    exam = Exam(title="Test Exam", organization="Test Org")
    setup_session.add_all([user, exam])
    setup_session.commit()
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
    setup_session.add_all([reminder, subscription])
    setup_session.commit()
    reminder_id = reminder.id
    subscription_id = subscription.id
    user_id = user.id
    setup_session.close()

    yield TestingSession, reminder_id, subscription_id, user_id
    cleanup = TestingSession()
    cleanup.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_successful_push_marks_push_only(db_session):
    SessionFactory, reminder_id, _, _ = db_session
    with patch.object(push_worker, "webpush") as send:
        result = push_worker.process_due_push_notifications()

    assert send.call_count == 1
    assert result["sent"] == 1
    session = SessionFactory()
    try:
        reminder = session.get(Reminder, reminder_id)
        assert reminder.push_sent is True
        # Push success must not imply email/overall delivery completion.
        assert reminder.is_sent is False
    finally:
        session.close()


def test_transient_push_failure_remains_retryable(db_session):
    SessionFactory, reminder_id, _, _ = db_session
    with patch.object(
        push_worker,
        "webpush",
        side_effect=RuntimeError("temporary network failure"),
    ):
        result = push_worker.process_due_push_notifications()

    assert result["sent"] == 0
    assert result["errors"]
    session = SessionFactory()
    try:
        reminder = session.get(Reminder, reminder_id)
        assert reminder.push_sent is False
    finally:
        session.close()


def test_expired_subscription_is_removed(db_session):
    SessionFactory, reminder_id, subscription_id, _ = db_session

    class Response:
        status_code = 410

    with patch.object(
        push_worker,
        "webpush",
        side_effect=push_worker.WebPushException("expired", response=Response()),
    ):
        result = push_worker.process_due_push_notifications()

    assert result["sent"] == 0
    session = SessionFactory()
    try:
        assert session.get(PushSubscription, subscription_id) is None
        reminder = session.get(Reminder, reminder_id)
        assert reminder.push_sent is False
    finally:
        session.close()
