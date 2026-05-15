from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import DataQualityFlag, NormalizedTransaction, RawRecord, SourceAuditLog, Watchlist
from backend.services.analytics_service import (
    apply_filters,
    build_monthly_executive_report,
    get_kpis,
    get_monthly_trend,
    get_source_split,
    get_top_employers,
    get_top_recipients,
)
from backend.services.export_service import build_csv_export, build_excel_export
from backend.services.repository import serialize_model
from backend.services.tracker_service import linked_watchlist_transactions, matched_transaction_payload, serialize_watchlist

router = APIRouter(prefix="/exports")


def _tracker_aggregates(rows: list[NormalizedTransaction]) -> tuple[dict, list[dict], list[dict], list[dict], list[dict]]:
    monthly = {}
    recipients = {}
    employers = {}
    source_split = {}
    for row in rows:
        amount = row.amount or 0
        if row.transaction_date:
            month = row.transaction_date.strftime("%Y-%m")
            monthly.setdefault(month, {"month": month, "source_system": row.source_system, "total_amount": 0.0, "transaction_count": 0})
            monthly[month]["total_amount"] += amount
            monthly[month]["transaction_count"] += 1
        if row.recipient_name:
            recipients.setdefault(row.recipient_name, {"recipient_name": row.recipient_name, "total_amount": 0.0, "transaction_count": 0})
            recipients[row.recipient_name]["total_amount"] += amount
            recipients[row.recipient_name]["transaction_count"] += 1
        employer = row.contributor_employer or row.contributor_entity_name
        if employer:
            employers.setdefault(employer, {"employer_company_signal": employer, "contributor_employer": employer, "total_amount": 0.0, "transaction_count": 0})
            employers[employer]["total_amount"] += amount
            employers[employer]["transaction_count"] += 1
        source_split.setdefault(row.source_system, {"source_system": row.source_system, "total_amount": 0.0, "transaction_count": 0})
        source_split[row.source_system]["total_amount"] += amount
        source_split[row.source_system]["transaction_count"] += 1
    kpis = {
        "total_records": len(rows),
        "total_contribution_amount": round(sum(row.amount or 0 for row in rows), 2),
        "unique_recipients": len({row.recipient_name for row in rows if row.recipient_name}),
        "unique_employer_company_signals": len({row.contributor_employer or row.contributor_entity_name for row in rows if row.contributor_employer or row.contributor_entity_name}),
        "fec_records": sum(1 for row in rows if row.source_system == "FEC"),
        "tec_records": sum(1 for row in rows if row.source_system == "TEC"),
    }
    sort_amount = lambda values: sorted(values, key=lambda item: item["total_amount"], reverse=True)
    return (
        kpis,
        sorted(monthly.values(), key=lambda item: item["month"]),
        sort_amount(list(recipients.values()))[:25],
        sort_amount(list(employers.values()))[:25],
        sort_amount(list(source_split.values())),
    )


def _filtered_transactions(db: Session, filters: dict):
    rows = (
        apply_filters(db.query(NormalizedTransaction), filters)
        .order_by(NormalizedTransaction.transaction_date.desc().nullslast(), NormalizedTransaction.id.desc())
        .limit(10000)
        .all()
    )
    return [serialize_model(row) for row in rows]


@router.get("/csv")
def export_csv(
    q: str | None = None,
    source_system: str | None = None,
    contributor_employer: str | None = None,
    recipient: str | None = None,
    topic_tag: str | None = None,
    cycle: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    rows = _filtered_transactions(
        db,
        {
            "q": q,
            "source_system": source_system,
            "contributor_employer": contributor_employer,
            "recipient": recipient,
            "topic_tag": topic_tag,
            "cycle": cycle,
            "state": state,
        },
    )
    bio = build_csv_export(rows)
    return StreamingResponse(
        bio,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=govfund_transactions.csv"},
    )


@router.get("/transactions.xlsx")
def export_transactions_xlsx(
    q: str | None = None,
    source_system: str | None = None,
    contributor_employer: str | None = None,
    recipient: str | None = None,
    topic_tag: str | None = None,
    cycle: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    filters = {
        "q": q,
        "source_system": source_system,
        "contributor_employer": contributor_employer,
        "recipient": recipient,
        "topic_tag": topic_tag,
        "cycle": cycle,
        "state": state,
    }
    rows = _filtered_transactions(db, filters)
    bio = build_excel_export(
        get_kpis(db, filters),
        get_monthly_trend(db, filters),
        get_top_recipients(db, filters, 25),
        get_top_employers(db, filters, 25),
        rows,
        get_source_split(db, filters),
        None,
        audit_logs=[],
        data_quality_flags=[],
        raw_records=[],
    )
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=govfund_filtered_transactions.xlsx"},
    )


@router.get("/watchlists/{watchlist_id}.xlsx")
def export_watchlist_xlsx(watchlist_id: int, db: Session = Depends(get_db)):
    watchlist = db.query(Watchlist).filter(Watchlist.id == watchlist_id).one_or_none()
    if not watchlist:
        rows = []
        tracker_summary = {"error": "Tracker was not found."}
    else:
        rows = linked_watchlist_transactions(db, watchlist_id)
        tracker_summary = serialize_watchlist(db, watchlist)
    kpis, monthly, top_rec, top_emp, source_split = _tracker_aggregates(rows)
    txns = matched_transaction_payload(db, watchlist, rows) if watchlist else []
    executive_report = {
        "headline": f"Tracker report: {tracker_summary.get('name', 'Unknown tracker')}",
        "summary": "This workbook contains records matched to the selected tracker only.",
        "compliance_note": "FEC employer fields are employer/company signals reported by individual contributors, not proof of direct corporate donations.",
        "highlights": [
            f"Matched records: {kpis['total_records']}",
            f"Total amount in matched records: ${kpis['total_contribution_amount']:,.0f}",
            f"Latest run: {tracker_summary.get('latest_run', {}).get('started_at') if tracker_summary.get('latest_run') else 'not run yet'}",
        ],
        "risks": ["Coverage depends on tracker filters, available OpenFEC fields, and records already fetched during tracker runs."],
        "recommended_actions": ["Review Source Record IDs before using findings in client-facing material."],
    }
    bio = build_excel_export(kpis, monthly, top_rec, top_emp, txns, source_split, executive_report, audit_logs=[], data_quality_flags=[], raw_records=[])
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=govfund_tracker_{watchlist_id}.xlsx"},
    )


@router.get("/excel")
def export_excel(db: Session = Depends(get_db)):
    tx = _filtered_transactions(db, {})
    audit_logs = [serialize_model(row) for row in db.query(SourceAuditLog).order_by(SourceAuditLog.started_at.desc()).limit(500).all()]
    flags = [serialize_model(row) for row in db.query(DataQualityFlag).order_by(DataQualityFlag.created_at.desc()).limit(1000).all()]
    raw = [serialize_model(row) for row in db.query(RawRecord).order_by(RawRecord.ingested_at.desc()).limit(1000).all()]
    bio = build_excel_export(
        get_kpis(db, {}),
        get_monthly_trend(db, {}),
        get_top_recipients(db, {}, 25),
        get_top_employers(db, {}, 25),
        tx,
        get_source_split(db, {}),
        build_monthly_executive_report(db),
        audit_logs=audit_logs,
        data_quality_flags=flags,
        raw_records=raw,
    )
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=govfund_export.xlsx"},
    )


@router.get("/audit-logs")
def export_audit_logs(db: Session = Depends(get_db)):
    rows = [serialize_model(row) for row in db.query(SourceAuditLog).order_by(SourceAuditLog.started_at.desc()).limit(5000).all()]
    return StreamingResponse(
        build_csv_export(rows),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=govfund_audit_logs.csv"},
    )


@router.get("/data-quality-flags")
def export_data_quality_flags(db: Session = Depends(get_db)):
    rows = [serialize_model(row) for row in db.query(DataQualityFlag).order_by(DataQualityFlag.created_at.desc()).limit(5000).all()]
    return StreamingResponse(
        build_csv_export(rows),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=govfund_data_quality_flags.csv"},
    )
