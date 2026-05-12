from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import DataQualityFlag, NormalizedTransaction, RawRecord, SourceAuditLog
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

router = APIRouter(prefix="/exports")


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
