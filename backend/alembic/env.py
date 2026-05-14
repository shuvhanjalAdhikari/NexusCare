# TODO (Phase 4.6 — Index/Constraint Naming Alignment):
# Autogenerate currently produces ~100 lines of spurious index/constraint diffs
# on every run because 01_schema.sql uses idx_*/*_key naming while the models
# emit ix_*/uq_* names. Until the alignment work lands, EVERY generated
# migration must be hand-pruned to strip these false-positive diffs. See
# MIGRATIONS.md → "Known Issue: Index/Constraint Naming Drift" for the rule and
# the affected object list. Disabling compare_indexes here is not a fix —
# it would silence legitimate index changes too. The right fix is to align the
# names; this comment exists to remind the next migrator why their autogen
# output looks alarming.

import asyncio
import sys
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ---------------------------------------------------------------------------
# Ensure the backend package root is on sys.path so `app.*` imports resolve
# when Alembic is invoked from any working directory.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# App imports — order matters:
#   1. Settings first (no DB side-effects)
#   2. database (creates Base; engine creation is acceptable here because the
#      venv has asyncpg installed and .env is present)
#   3. All models — side-effect import registers every table with Base.metadata
#      so autogenerate can diff the full schema
# ---------------------------------------------------------------------------
from app.config import settings
from app.database import Base
import app.models  # noqa: F401 — registers all ORM models with Base.metadata

# ---------------------------------------------------------------------------
# Alembic Config object — provides access to values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# Wire up Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# DATABASE URL — read from Settings, normalise to postgresql+asyncpg:// scheme.
# The .env file may store a plain postgresql:// URL; asyncpg requires the
# +asyncpg dialect specifier.
# ---------------------------------------------------------------------------
_raw_url: str = settings.database_url

if _raw_url.startswith("postgresql+asyncpg://"):
    _async_url = _raw_url
elif _raw_url.startswith("postgresql://"):
    _async_url = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _raw_url.startswith("postgres://"):
    # Heroku-style shorthand
    _async_url = _raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    raise ValueError(
        f"Unsupported DATABASE_URL scheme: {_raw_url!r}. "
        "Expected postgresql://, postgresql+asyncpg://, or postgres://"
    )

config.set_main_option("sqlalchemy.url", _async_url)

# ---------------------------------------------------------------------------
# Target metadata for autogenerate — must reference the same Base that all
# models inherit from. Every model imported above registers its table here.
# ---------------------------------------------------------------------------
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# OFFLINE MODE — emit SQL to stdout without a live DB connection.
# Useful for generating migration scripts to review before applying.
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection needed)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Suppress noise from server defaults (e.g. now(), gen_random_uuid())
        compare_server_default=False,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# ONLINE MODE — connect to DB and apply migrations.
# ---------------------------------------------------------------------------
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Detect column type changes (e.g. VARCHAR(100) → VARCHAR(200))
        compare_type=True,
        # Skip comparing server defaults — Alembic cannot reliably round-trip
        # PostgreSQL expressions like now() or gen_random_uuid()
        compare_server_default=False,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create async engine and run migrations inside a sync-bridge connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
