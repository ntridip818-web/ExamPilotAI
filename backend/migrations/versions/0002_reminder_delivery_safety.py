"""Deduplicate reminders, enforce reminder identity, and add push retry metadata."""
from alembic import op
import sqlalchemy as sa


revision = "0002_reminder_delivery_safety"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reminders", sa.Column("push_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("reminders", sa.Column("push_next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reminders", sa.Column("push_last_error", sa.Text(), nullable=True))

    # Preserve delivery state on the lowest-ID row, then remove exact duplicates.
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, user_id, exam_id, reminder_type, remind_at, is_sent, push_sent "
        "FROM reminders ORDER BY id"
    )).mappings().all()
    canonical = {}
    duplicates = []
    for row in rows:
        key = (row["user_id"], row["exam_id"], row["reminder_type"], row["remind_at"])
        if key not in canonical:
            canonical[key] = dict(row)
        else:
            keep = canonical[key]
            keep["is_sent"] = bool(keep["is_sent"]) or bool(row["is_sent"])
            keep["push_sent"] = bool(keep["push_sent"]) or bool(row["push_sent"])
            duplicates.append(row["id"])

    for key, keep in canonical.items():
        bind.execute(
            sa.text("UPDATE reminders SET is_sent=:is_sent, push_sent=:push_sent WHERE id=:id"),
            {"is_sent": keep["is_sent"], "push_sent": keep["push_sent"], "id": keep["id"]},
        )
    if duplicates:
        bind.execute(
            sa.text("DELETE FROM reminders WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": duplicates},
        )

    op.create_index(
        "uq_reminder_identity",
        "reminders",
        ["user_id", "exam_id", "reminder_type", "remind_at"],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_reminder_identity", table_name="reminders")
    op.drop_column("reminders", "push_last_error")
    op.drop_column("reminders", "push_next_attempt_at")
    op.drop_column("reminders", "push_attempts")
