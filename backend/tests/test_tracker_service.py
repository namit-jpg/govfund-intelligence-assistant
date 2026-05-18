from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base
from backend.models import FECQueryRun, SourceAuditLog, Watchlist, WatchlistRun, WatchlistRunTransaction
from backend.schemas import WatchlistCreateRequest
from backend.services.tracker_service import create_watchlist_from_payload, linked_watchlist_transactions, run_watchlist


def make_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_watchlist_run_fetches_fec_and_links_matching_transactions(monkeypatch):
    db = make_session()
    monkeypatch.setenv("FEC_API_KEY", "test-key")

    def fake_fetch(filters):
        assert filters["contributor_employer"] == "AECOM"
        return SimpleNamespace(
            records=[
                {
                    "source_record_id": "FEC-AECOM-1",
                    "transaction_id": "T1",
                    "transaction_type": "INDIVIDUAL_CONTRIBUTION",
                    "transaction_date": "2026-03-01",
                    "amount": 500.0,
                    "contributor_name": "Jane Public",
                    "contributor_employer": "AECOM",
                    "recipient_name": "Infrastructure Leadership PAC",
                    "committee_name": "Infrastructure Leadership PAC",
                    "cycle": "2026",
                    "_raw_payload": {"sub_id": "FEC-AECOM-1"},
                }
            ],
            errors=[],
            pages_processed=1,
            raw_records_fetched=1,
            query={"contributor_employer": "AECOM"},
        )

    monkeypatch.setattr("backend.services.tracker_service.fetch_fec_transactions", fake_fetch)
    try:
        watchlist = create_watchlist_from_payload(
            db,
            WatchlistCreateRequest(
                name="Infrastructure tracker",
                watchlist_type="donation_monitor",
                entities=[{"entity_name": "AECOM", "entity_type": "EMPLOYER_SIGNAL"}],
                filters={"cycle": "2026", "max_records": 50},
                cadence="daily",
                max_records=50,
            ),
        )

        result = run_watchlist(db, watchlist.id, run_type="manual", live=True)

        assert result["status"] == "completed"
        assert result["raw_records_fetched"] == 1
        assert result["inserted_count"] == 1
        assert result["matched_count"] == 1
        assert db.query(WatchlistRun).count() == 1
        assert db.query(WatchlistRunTransaction).count() == 1
        assert db.query(SourceAuditLog).filter(SourceAuditLog.operation_type == "watchlist_fec_ingest").count() == 1
        assert db.query(FECQueryRun).count() == 1
        assert len(linked_watchlist_transactions(db, watchlist.id)) == 1
    finally:
        db.close()


def test_monthly_watchlist_run_sets_next_run_about_30_days(monkeypatch):
    db = make_session()
    monkeypatch.delenv("FEC_API_KEY", raising=False)
    try:
        watchlist = create_watchlist_from_payload(
            db,
            WatchlistCreateRequest(
                name="Monthly tracker",
                watchlist_type="donation_monitor",
                entities=[{"entity_name": "Pape-Dawson Engineers", "entity_type": "EMPLOYER_SIGNAL"}],
                filters={"cycle": "2026", "max_records": 50, "cadence": "monthly"},
                cadence="monthly",
                max_records=50,
            ),
        )

        result = run_watchlist(db, watchlist.id, run_type="manual", live=True)
        updated = db.query(Watchlist).filter(Watchlist.id == watchlist.id).one()

        assert result["status"] == "partial"
        assert updated.cadence == "monthly"
        assert updated.last_run_at is not None
        assert updated.next_run_at is not None
        assert 29 <= (updated.next_run_at - updated.last_run_at).days <= 30
    finally:
        db.close()
