from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.services import analytics_service as analytics

router = APIRouter(prefix="/analytics")


@router.get("/kpis")
def kpis(
    source_system: str | None = None,
    min_amount: float | None = None,
    db: Session = Depends(get_db),
):
    return analytics.get_kpis(db, {"source_system": source_system, "min_amount": min_amount})


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    return analytics.build_overview(db)


@router.get("/monthly-trend")
def monthly(source_system: str | None = None, db: Session = Depends(get_db)):
    return analytics.get_monthly_trend(db, {"source_system": source_system})


@router.get("/top-recipients")
def top_recipients(db: Session = Depends(get_db)):
    return analytics.get_top_recipients(db, {}, 25)


@router.get("/top-employers")
def top_employers(db: Session = Depends(get_db)):
    return analytics.get_top_employers(db, {}, 25)


@router.get("/source-split")
def source_split(db: Session = Depends(get_db)):
    return analytics.get_source_split(db, {})


@router.get("/party-distribution")
def party_distribution(db: Session = Depends(get_db)):
    return analytics.get_party_distribution(db, {})


@router.get("/topic-distribution")
def topic_distribution(db: Session = Depends(get_db)):
    return analytics.get_topic_distribution(db, {})


@router.get("/geo-distribution")
def geo_distribution(db: Session = Depends(get_db)):
    return analytics.get_geo_distribution(db, {})


@router.get("/recent-high-value")
def recent_high_value(db: Session = Depends(get_db)):
    return analytics.get_recent_high_value_records(db, {}, 25)


@router.get("/reporting-months")
def reporting_months(db: Session = Depends(get_db)):
    return analytics.get_available_report_months(db)


@router.get("/executive-report")
def executive_report(
    report_month: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return analytics.build_monthly_executive_report(db, report_month)


@router.get("/company-dossier")
def company_dossier(employer: str, db: Session = Depends(get_db)):
    return analytics.company_dossier(db, employer)


@router.get("/recipient-dossier")
def recipient_dossier(recipient: str, db: Session = Depends(get_db)):
    return analytics.recipient_dossier(db, recipient)


@router.get("/network")
def network(
    source_system: str | None = None,
    min_amount: float | None = None,
    topic_tag: str | None = None,
    contributor_employer: str | None = None,
    recipient: str | None = None,
    max_nodes: int = 40,
    db: Session = Depends(get_db),
):
    return analytics.network_data(
        db,
        {
            "source_system": source_system,
            "min_amount": min_amount,
            "topic_tag": topic_tag,
            "contributor_employer": contributor_employer,
            "recipient": recipient,
        },
        max_nodes=max_nodes,
    )


@router.post("/compare-competitors")
def compare(payload: dict):
    return {"competitors": payload.get("competitor_names", [])}
