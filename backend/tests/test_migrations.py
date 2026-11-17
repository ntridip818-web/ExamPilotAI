from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_upgrade_deduplicates_existing_reminders_and_preserves_delivery_state(tmp_path):
    database_path = tmp_path / "legacy-reminders.db"
    database_url = f"sqlite:///{database_path}"
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    # Simulate a database at the previous schema revision, before the safety
    # migration and its unique identity index.
    command.upgrade(config, "0001_baseline")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO users (id, email) VALUES (1, 'migration@example.test')"
            ))
            connection.execute(text(
                "INSERT INTO exams (id, title, organization) VALUES (1, 'Migration Exam', 'ExamPilotAI')"
            ))
            connection.execute(text("""
                INSERT INTO reminders
                    (id, user_id, exam_id, reminder_type, remind_at, is_sent, push_sent)
                VALUES
                    (1, 1, 1, 'APPLICATION_DEADLINE', '2030-01-01 09:00:00', 0, 0),
                    (2, 1, 1, 'APPLICATION_DEADLINE', '2030-01-01 09:00:00', 1, 1)
            """))

        command.upgrade(config, "head")

        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT id, is_sent, push_sent, push_attempts "
                "FROM reminders"
            )).mappings().all()
            assert len(rows) == 1
            assert rows[0]["id"] == 1
            assert rows[0]["is_sent"] in (1, True)
            assert rows[0]["push_sent"] in (1, True)
            assert rows[0]["push_attempts"] == 0

            indexes = inspect(connection).get_indexes("reminders")
            unique_identity = next(
                index for index in indexes if index["name"] == "uq_reminder_identity"
            )
            assert unique_identity["unique"] is True
            assert unique_identity["column_names"] == [
                "user_id", "exam_id", "reminder_type", "remind_at"
            ]

            # A second migration invocation must be a no-op.
            command.upgrade(config, "head")
    finally:
        engine.dispose()
