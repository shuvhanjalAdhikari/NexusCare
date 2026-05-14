# NexusCare — Database Migration Guide

Alembic manages schema migrations for NexusCare. Read this file before touching
the database schema.

---

## ⚠️  Database Objects NOT Managed by Alembic

**This is the most important section. Read it first.**

The following objects are defined in `backend/sql/01_schema.sql` and are invisible
to Alembic autogenerate. If you create or modify them, Alembic will never detect
the change — you must handle them manually.

### Triggers

| Trigger function         | Attached to                  | Effect                        |
|--------------------------|------------------------------|-------------------------------|
| `set_updated_at()`       | Every table with `updated_at`| Sets `updated_at = now()` on UPDATE |
| `attach_updated_at(tbl)` | Called per table at DDL time | Creates the per-table trigger |

### Custom SQL Functions

| Function              | Purpose                                            |
|-----------------------|----------------------------------------------------|
| `set_updated_at()`    | Trigger body — sets `updated_at`                  |
| `attach_updated_at()` | Helper that creates the trigger for a named table |

### Partial Indexes

These indexes have a `WHERE` clause that Alembic cannot reproduce via autogenerate:

| Index name                  | Table                  | Condition                  |
|-----------------------------|------------------------|----------------------------|
| `idx_users_deleted`         | `users`                | `WHERE deleted_at IS NULL` |
| `idx_patients_deleted`      | `patients`             | `WHERE deleted_at IS NULL` |
| `idx_appointments_deleted`  | `appointments`         | `WHERE deleted_at IS NULL` |
| `idx_visits_deleted`        | `visits`               | `WHERE deleted_at IS NULL` |
| `idx_invoices_deleted`      | `invoices`             | `WHERE deleted_at IS NULL` |
| `idx_memberships_deleted`   | `hospital_memberships` | `WHERE deleted_at IS NULL` |

### How to Add New Triggers, Functions, or Partial Indexes

1. Add the DDL to `backend/sql/01_schema.sql` (keeps it as the authoritative schema).
2. Write an Alembic migration using `op.execute()` for the raw SQL. Example:

```python
def upgrade() -> None:
    # Add soft-delete index to new_table
    op.execute("""
        CREATE INDEX idx_new_table_deleted
        ON new_table(deleted_at)
        WHERE deleted_at IS NULL
    """)
    # Attach updated_at trigger
    op.execute("SELECT attach_updated_at('new_table')")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_new_table_deleted")
    op.execute("DROP TRIGGER IF EXISTS trg_new_table_updated_at ON new_table")
```

Never rely on autogenerate to create these — always write them by hand.

---

## Day-to-Day Workflow

All commands run from `backend/` with the virtual environment activated:

```bash
cd backend
source venv/bin/activate      # Linux/macOS
# or: venv\Scripts\activate   # Windows
```

### 1. Make a schema change

Edit the SQLAlchemy model in `app/models/`. Then generate a migration:

```bash
alembic revision --autogenerate -m "short description of change"
```

**Always review the generated file** in `alembic/versions/` before applying it.
Autogenerate is not perfect — it will miss triggers, partial indexes, and CHECK
constraints. Add those manually using `op.execute()` if needed.

### 2. Apply migrations

```bash
alembic upgrade head        # apply all pending migrations
alembic upgrade +1          # apply exactly one migration
```

### 3. Roll back

```bash
alembic downgrade -1        # undo the last migration
alembic downgrade <rev>     # downgrade to a specific revision ID
```

### 4. Check current state

```bash
alembic current             # which revision the DB is at
alembic history --verbose   # full migration history
alembic check               # diff models vs DB (may show noise for partial indexes)
```

---

## Fresh Database Setup

Use this when starting from scratch (new developer machine, CI, staging reset).

```bash
# 1. Start PostgreSQL (schema is applied automatically on first boot)
docker compose up -d

# The docker-compose.yml mounts backend/sql/ into postgres's
# docker-entrypoint-initdb.d/ directory. On first container start,
# postgres runs 01_schema.sql automatically — triggers, indexes, and all.

# 2. Wait for postgres to be ready (~5 seconds), then stamp Alembic baseline
cd backend
alembic stamp head

# 3. Apply any migrations that exist on top of the baseline
alembic upgrade head
```

> If the DB is not fresh (already has tables from a previous run), skip step 1
> and go straight to `alembic stamp head` followed by `alembic upgrade head`.

---

## Applying Migrations to an Existing Database

If you're running migrations against a database that was set up from `01_schema.sql`
but has never had Alembic run against it:

```bash
# Mark the DB as being at the baseline revision (no DDL is executed)
alembic stamp head

# Then apply any migrations written after the baseline
alembic upgrade head
```

---

## Generating a SQL Script (offline mode)

To produce raw SQL for review or manual application (e.g., production deployments
where you don't want to run Alembic against prod directly):

```bash
alembic upgrade head --sql > migration.sql
```

Review `migration.sql` before applying it manually via psql or pgAdmin.

---

## File Layout

```
backend/
├── alembic.ini                  # Alembic configuration (URL set in env.py)
├── alembic/
│   ├── env.py                   # Engine setup, model imports, URL normalisation
│   ├── script.py.mako           # Template for generated migration files
│   └── versions/
│       └── 20260513_1848_9ae5293c81a8_baseline.py   # Empty baseline
└── sql/
    └── 01_schema.sql            # Source-of-truth DDL (triggers, functions, indexes)
```

Migration filenames follow the pattern `YYYYMMDD_HHMM_<revid>_<slug>.py`.

---

## Environment Variables

Alembic reads `DATABASE_URL` from `../.env` (one level above `backend/`) via
`app.config.Settings`. The URL may be `postgresql://` or `postgresql+asyncpg://` —
`alembic/env.py` normalises the scheme automatically.

Do not set `sqlalchemy.url` in `alembic.ini`. It is intentionally blank.
