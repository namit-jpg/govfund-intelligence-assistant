from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base
from backend.models import NormalizedTransaction
from backend.services.analytics_service import build_monthly_executive_report, get_monthly_trend, get_top_employers, get_top_recipients


def make_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def seed_transactions(db):
    db.add_all(
        [
            NormalizedTransaction(
                source_system="FEC",
                source_record_id="1",
                transaction_date=date(2026, 3, 14),
                amount=2500,
                contributor_employer="ABC Construction LLC",
                recipient_name="Texans for Infrastructure Growth",
            ),
            NormalizedTransaction(
                source_system="TEC",
                source_record_id="2",
                transaction_date=date(2026, 3, 20),
                amount=1800,
                contributor_employer="Frontier Infrastructure Group",
                recipient_name="Friends of Daniel Mercer",
            ),
        ]
    )
    db.commit()


def test_analytics_aggregations_group_by_explicit_columns():
    db = make_session()
    try:
        seed_transactions(db)

        monthly = get_monthly_trend(db, {})
        recipients = get_top_recipients(db, {})
        employers = get_top_employers(db, {})

        assert monthly == [
            {"month": "2026-03", "source_system": "FEC", "total_amount": 2500.0, "transaction_count": 1},
            {"month": "2026-03", "source_system": "TEC", "total_amount": 1800.0, "transaction_count": 1},
        ]
        assert recipients[0]["recipient_name"] == "Texans for Infrastructure Growth"
        assert employers[0]["contributor_employer"] == "ABC Construction LLC"
        assert build_monthly_executive_report(db, "2026-03")["report_month"] == "2026-03"
    finally:
        db.close()
