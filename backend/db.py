from __future__ import annotations

import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

_PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_DIR / ".env")
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./govfund_actual.db"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _ensure_sqlite_columns() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns or column.primary_key:
                    continue
                column_type = column.type.compile(dialect=engine.dialect)
                statement = f"ALTER TABLE {_quote(table.name)} ADD COLUMN {_quote(column.name)} {column_type}"
                logger.info("Adding missing SQLite column %s.%s", table.name, column.name)
                conn.execute(text(statement))


def _ensure_sqlite_indexes() -> None:
    statements = [
        (
            "uq_raw_records_source_record",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_records_source_record "
            "ON raw_records (source_system, source_record_id)",
        ),
        (
            "uq_normalized_transactions_source_record",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_normalized_transactions_source_record "
            "ON normalized_transactions (source_system, source_record_id)",
        ),
        (
            "ix_normalized_transactions_date_id",
            "CREATE INDEX IF NOT EXISTS ix_normalized_transactions_date_id "
            "ON normalized_transactions (transaction_date DESC, id DESC)",
        ),
        (
            "ix_normalized_transactions_source_date",
            "CREATE INDEX IF NOT EXISTS ix_normalized_transactions_source_date "
            "ON normalized_transactions (source_system, transaction_date DESC)",
        ),
        (
            "ix_normalized_transactions_amount",
            "CREATE INDEX IF NOT EXISTS ix_normalized_transactions_amount "
            "ON normalized_transactions (amount DESC)",
        ),
        (
            "ix_normalized_transactions_employer",
            "CREATE INDEX IF NOT EXISTS ix_normalized_transactions_employer "
            "ON normalized_transactions (contributor_employer)",
        ),
        (
            "ix_normalized_transactions_recipient",
            "CREATE INDEX IF NOT EXISTS ix_normalized_transactions_recipient "
            "ON normalized_transactions (recipient_name)",
        ),
        (
            "ix_normalized_transactions_state_city",
            "CREATE INDEX IF NOT EXISTS ix_normalized_transactions_state_city "
            "ON normalized_transactions (contributor_state, contributor_city)",
        ),
        (
            "ix_normalized_transactions_cycle",
            "CREATE INDEX IF NOT EXISTS ix_normalized_transactions_cycle "
            "ON normalized_transactions (cycle)",
        ),
        (
            "ix_raw_records_ingested_id",
            "CREATE INDEX IF NOT EXISTS ix_raw_records_ingested_id "
            "ON raw_records (ingested_at DESC, id DESC)",
        ),
        (
            "ix_fec_query_runs_started",
            "CREATE INDEX IF NOT EXISTS ix_fec_query_runs_started "
            "ON fec_query_runs (started_at DESC)",
        ),
        (
            "ix_source_audit_logs_started",
            "CREATE INDEX IF NOT EXISTS ix_source_audit_logs_started "
            "ON source_audit_logs (started_at DESC)",
        ),
        (
            "ix_source_audit_logs_completed_status",
            "CREATE INDEX IF NOT EXISTS ix_source_audit_logs_completed_status "
            "ON source_audit_logs (status, completed_at DESC)",
        ),
    ]
    with engine.begin() as conn:
        for name, statement in statements:
            try:
                conn.execute(text(statement))
            except SQLAlchemyError as exc:
                logger.warning("Could not create index %s: %s", name, exc)


def _configure_sqlite_runtime() -> None:
    with engine.begin() as conn:
        for statement in [
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA temp_store=MEMORY",
            "PRAGMA cache_size=-64000",
        ]:
            try:
                conn.execute(text(statement))
            except SQLAlchemyError as exc:
                logger.debug("Could not apply SQLite pragma %s: %s", statement, exc)


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        _configure_sqlite_runtime()
        _ensure_sqlite_columns()
        _ensure_sqlite_indexes()
