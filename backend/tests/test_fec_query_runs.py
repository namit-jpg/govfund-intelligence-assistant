from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base
from backend.models import FECQueryRun, SourceAuditLog
from backend.routers.ingestion import _cleanup_stale_fec_runs


def make_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_stale_fec_running_rows_are_marked_failed():
    db = make_session()
    try:
        old_started_at = datetime.utcnow() - timedelta(hours=2)
        audit = SourceAuditLog(
            source_system="FEC",
            operation_type="openfec_schedule_a_ingest",
            query_json="{}",
            status="running",
            started_at=old_started_at,
        )
        db.add(audit)
        db.flush()
        run = FECQueryRun(
            audit_log_id=audit.id,
            query_json="{}",
            status="running",
            started_at=old_started_at,
        )
        db.add(run)
        db.commit()

        assert _cleanup_stale_fec_runs(db) == 2
        db.refresh(audit)
        db.refresh(run)
        assert audit.status == "failed"
        assert run.status == "failed"
        assert "stale" in run.error_message.lower()
    finally:
        db.close()
