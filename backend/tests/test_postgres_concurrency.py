import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.models import Exam, PushSubscription, Reminder, ReminderType, User
from app.services import push_worker


@pytest.fixture
def postgres_schema():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL is required for PostgreSQL integration tests")

    admin_engine = create_engine(url, pool_pre_ping=True)
    schema = "ep_test_" + uuid.uuid4().hex[:12]
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_engine(
        url,
        pool_size=12,
        max_overflow=4,
        pool_pre_ping=True,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    try:
        yield factory
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def seed_due_reminder(factory):
    session = factory()
    try:
        user = User(email=f"{uuid.uuid4().hex}@example.test")
        exam = Exam(title="Concurrent Test Exam", organization="ExamPilotAI")
        session.add_all([user, exam])
        session.flush()
        reminder = Reminder(
            user_id=user.id,
            exam_id=exam.id,
            reminder_type=ReminderType.APPLICATION_DEADLINE,
            remind_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        )
        subscription = PushSubscription(
            user_id=user.id,
            endpoint=f"https://push.example.test/{uuid.uuid4().hex}",
            subscription={"endpoint": "https://push.example.test", "keys": {"p256dh": "x", "auth": "y"}},
        )
        session.add_all([reminder, subscription])
        session.commit()
        return reminder.id, user.id, exam.id
    finally:
        session.close()


def test_ten_concurrent_inserts_create_only_one_reminder(postgres_schema):
    factory = postgres_schema
    _, user_id, exam_id = seed_due_reminder(factory)
    remind_at = datetime.now(timezone.utc) + timedelta(days=1)

    def insert_same_reminder(_):
        session = factory()
        try:
            session.add(Reminder(
                user_id=user_id,
                exam_id=exam_id,
                reminder_type=ReminderType.EXAM_DAY,
                remind_at=remind_at,
            ))
            session.commit()
            return "created"
        except IntegrityError:
            session.rollback()
            return "duplicate"
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(insert_same_reminder, range(10)))

    assert results.count("created") == 1
    assert results.count("duplicate") == 9
    session = factory()
    try:
        count = session.query(Reminder).filter(
            Reminder.user_id == user_id,
            Reminder.exam_id == exam_id,
            Reminder.reminder_type == ReminderType.EXAM_DAY,
            Reminder.remind_at == remind_at,
        ).count()
        assert count == 1
    finally:
        session.close()


def test_two_workers_skip_a_reminder_locked_by_the_first_worker(postgres_schema, monkeypatch):
    factory = postgres_schema
    reminder_id, _, _ = seed_due_reminder(factory)
    monkeypatch.setattr(push_worker, "SessionLocal", factory)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-key")
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:test@example.test")

    first_send_started = threading.Event()
    release_first_send = threading.Event()
    first_result = {}

    def blocking_success(**kwargs):
        first_send_started.set()
        assert release_first_send.wait(timeout=10), "test timed out waiting to release worker 1"

    def run_first_worker():
        first_result.update(push_worker.process_due_push_notifications())

    with patch.object(push_worker, "webpush", side_effect=blocking_success):
        thread = threading.Thread(target=run_first_worker)
        thread.start()
        assert first_send_started.wait(timeout=10), "worker 1 did not claim and start sending"

        # The first worker is holding the row lock during delivery. The second
        # worker must skip it rather than sending the same reminder.
        second_result = push_worker.process_due_push_notifications()
        release_first_send.set()
        thread.join(timeout=10)

    assert not thread.is_alive()
    assert first_result["processed"] == 1
    assert first_result["sent"] == 1
    assert second_result["processed"] == 0
    session = factory()
    try:
        assert session.get(Reminder, reminder_id).push_sent is True
    finally:
        session.close()



def test_two_email_workers_skip_a_reminder_locked_by_the_first_worker(postgres_schema, monkeypatch):
    from app import reminder_worker

    factory = postgres_schema
    reminder_id, _, _ = seed_due_reminder(factory)
    # This reminder is due for email delivery as well.
    monkeypatch.setattr(reminder_worker, "send_email", lambda *args, **kwargs: None)

    first_send_started = threading.Event()
    release_first_send = threading.Event()
    first_result = {}

    def blocking_send(*args, **kwargs):
        first_send_started.set()
        assert release_first_send.wait(timeout=10), "test timed out waiting to release email worker 1"

    def run_first_worker():
        session = factory()
        try:
            first_result["sent"] = reminder_worker.process_reminders(session)
        finally:
            session.close()

    with patch.object(reminder_worker, "send_email", side_effect=blocking_send):
        thread = threading.Thread(target=run_first_worker)
        thread.start()
        assert first_send_started.wait(timeout=10), "email worker 1 did not claim and start sending"

        second_session = factory()
        try:
            second_result = reminder_worker.process_reminders(second_session)
        finally:
            second_session.close()

        release_first_send.set()
        thread.join(timeout=10)

    assert not thread.is_alive()
    assert first_result["sent"] == 1
    assert second_result == 0
    session = factory()
    try:
        assert session.get(Reminder, reminder_id).is_sent is True
    finally:
        session.close()
