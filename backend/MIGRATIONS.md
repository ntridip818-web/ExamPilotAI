# Database migration rollout (Phase 1)

## Fresh database

From the repository root:

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
```

The baseline migration creates the pre-Phase-1 schema. The next migration adds
push retry metadata, consolidates exact duplicate reminders while preserving
sent flags, and enforces a unique reminder identity.

## Existing database — manual preflight required

Do not run `alembic upgrade head` against an existing deployment until its
schema has been inspected and backed up.

The existing database must match revision `0001_baseline`. In particular,
verify the `users`, `exams`, `saved_exams`, `reminders`, and
`push_subscriptions` tables and the `reminders.push_sent` column. Compare
column types, nullability, foreign keys, indexes, and enum values with
`migrations/versions/0001_baseline.py`.

Only after a verified backup and schema comparison, mark the existing schema
as baseline (this records migration history; it does not execute DDL):

```bash
cd backend
alembic stamp 0001_baseline
alembic upgrade head
```

If the schema differs, stop and prepare a deployment-specific reconciliation
migration. Do not stamp a database merely to bypass migration errors.

## Operational notes

- The second migration keeps the lowest reminder ID for each
  (user, exam, type, scheduled time) key and OR-preserves `is_sent` and
  `push_sent` before deleting duplicates.
- PostgreSQL is required for effective `FOR UPDATE SKIP LOCKED` concurrency
  protection. SQLite is used only for CI migration and unit tests.
- Back up the database before migration and verify reminder counts afterward.
- This repository change does not run a migration against any live database.
