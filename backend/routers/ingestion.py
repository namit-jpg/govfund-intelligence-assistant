from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, defer
import pandas as pd
from io import BytesIO

from backend.db import get_db
from backend.models import DataQualityFlag, FECQueryRun, NormalizedTransaction, SourceAuditLog
from backend.schemas import FECIngestRequest
from backend.services.fec_client import FECValidationError, fetch_fec_transactions, redact_query, sanitize_fec_error, build_fec_request_params
from backend.services.repository import insert_records, serialize_model, to_json
from backend.services.source_config import get_source_config
from backend.services.tec_parser import parse_tec_file, preview_tec_file

router = APIRouter(prefix="/ingestion")
STALE_RUN_MINUTES = 30
COMPACT_FEC_RECORD_LIMIT = 500


@router.get("/config")
def ingestion_config():
    return get_source_config()


def _create_audit(db: Session, source_system: str, operation_type: str, query: dict) -> SourceAuditLog:
    audit = SourceAuditLog(
        source_system=source_system,
        operation_type=operation_type,
        query_json=to_json(query),
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


def _finish_audit(
    db: Session,
    audit: SourceAuditLog,
    status: str,
    pages_processed: int,
    raw_records_fetched: int,
    inserted_count: int,
    duplicate_count: int,
    error_message: str | None = None,
) -> None:
    audit.status = status
    audit.completed_at = datetime.utcnow()
    audit.pages_processed = pages_processed
    audit.raw_records_fetched = raw_records_fetched
    audit.inserted_count = inserted_count
    audit.duplicate_count = duplicate_count
    audit.error_message = sanitize_fec_error(error_message) if error_message else None
    db.add(audit)
    db.commit()


def _cleanup_stale_fec_runs(db: Session) -> int:
    cutoff = datetime.utcnow() - timedelta(minutes=STALE_RUN_MINUTES)
    stale_audits = (
        db.query(SourceAuditLog)
        .filter(
            SourceAuditLog.source_system == "FEC",
            SourceAuditLog.status == "running",
            SourceAuditLog.started_at < cutoff,
        )
        .all()
    )
    stale_runs = (
        db.query(FECQueryRun)
        .filter(FECQueryRun.status == "running", FECQueryRun.started_at < cutoff)
        .all()
    )
    message = "Marked stale after an interrupted or timed-out FEC query run."
    for audit in stale_audits:
        audit.status = "failed"
        audit.completed_at = datetime.utcnow()
        audit.error_message = message
    for run in stale_runs:
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        run.error_message = message
    db.commit()
    return len(stale_audits) + len(stale_runs)


def _is_broad_fec_query(body: dict) -> bool:
    specific_fields = [
        "contributor_name",
        "contributor_employer",
        "contributor_state",
        "contributor_city",
        "committee_id",
        "candidate_id",
    ]
    return not any(body.get(field) for field in specific_fields)


@router.post("/fec")
def ingest_fec(body: FECIngestRequest, db: Session = Depends(get_db)):
    _cleanup_stale_fec_runs(db)
    query = body.model_dump(exclude_none=True)
    audit = _create_audit(db, "FEC", "openfec_schedule_a_ingest", query)
    run = FECQueryRun(
        audit_log_id=audit.id,
        query_json=to_json(query),
        request_metadata_json=to_json({"endpoint": "schedule_a", "request_params": redact_query(build_fec_request_params(query))}),
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if not os.getenv("FEC_API_KEY"):
        message = "FEC_API_KEY is missing. Add it to .env before running OpenFEC ingestion."
        _finish_audit(db, audit, "failed", 0, 0, 0, 0, message)
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        run.error_message = message
        db.add(run)
        db.commit()
        raise HTTPException(status_code=400, detail=message)

    try:
        fetched = fetch_fec_transactions(query)
        inserted = insert_records(db, "FEC", fetched.records, source_url="https://api.open.fec.gov/v1/schedules/schedule_a/")
        errors = [sanitize_fec_error(error) for error in (fetched.errors + inserted.get("errors", []))]
        status = "completed" if not errors else "partial"

        if _is_broad_fec_query(query) and fetched.raw_records_fetched < min(int(query.get("per_page", 100)), 30):
            db.add(
                DataQualityFlag(
                    transaction_id=None,
                    flag_type="broad_query_low_record_count",
                    severity="warning",
                    message=(
                        "Broad FEC query returned fewer rows than expected. Review filters, OpenFEC availability, "
                        "and pagination metadata."
                    ),
                )
            )
            db.commit()

        _finish_audit(
            db,
            audit,
            status,
            fetched.pages_processed,
            fetched.raw_records_fetched,
            inserted["inserted_count"],
            inserted["duplicate_count"],
            "; ".join(errors[:5]) if errors else None,
        )
        result_payload = {
            "query": query,
            "records": fetched.records,
            "audit": {
                "audit_log_id": audit.id,
                "pages_processed": fetched.pages_processed,
                "raw_records_fetched": fetched.raw_records_fetched,
                "inserted_count": inserted["inserted_count"],
                "duplicate_count": inserted["duplicate_count"],
            },
            "errors": [sanitize_fec_error(error) for error in errors[:10]],
        }
        run.status = status
        run.completed_at = datetime.utcnow()
        run.pages_processed = fetched.pages_processed
        run.raw_records_fetched = fetched.raw_records_fetched
        run.inserted_count = inserted["inserted_count"]
        run.duplicate_count = inserted["duplicate_count"]
        run.error_message = "; ".join(result_payload["errors"][:5]) if errors else None
        run.result_json = to_json(result_payload)
        run.normalized_transaction_ids_json = to_json(inserted.get("transaction_ids", []))
        run.request_metadata_json = to_json({"endpoint": "schedule_a", "request_params": fetched.query})
        db.add(run)
        db.commit()
        return {
            "fec_query_run_id": run.id,
            "source_system": "FEC",
            "status": status,
            "pages_processed": fetched.pages_processed,
            "raw_records_fetched": fetched.raw_records_fetched,
            "inserted_count": inserted["inserted_count"],
            "duplicate_count": inserted["duplicate_count"],
            "errors": errors[:10],
            "audit_log_id": audit.id,
        }
    except FECValidationError as exc:
        message = sanitize_fec_error(exc)
        _finish_audit(db, audit, "failed", 0, 0, 0, 0, message)
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        run.error_message = message
        run.result_json = to_json({"query": query, "records": [], "errors": [message]})
        db.add(run)
        db.commit()
        raise HTTPException(status_code=400, detail=message) from exc
    except Exception as exc:
        message = sanitize_fec_error(exc)
        _finish_audit(db, audit, "failed", 0, 0, 0, 0, message)
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        run.error_message = message
        run.result_json = to_json({"query": query, "records": [], "errors": [message]})
        db.add(run)
        db.commit()
        raise HTTPException(status_code=502, detail=f"FEC ingestion failed: {message}") from exc


@router.get("/fec-runs")
def fec_runs(limit: int = 25, db: Session = Depends(get_db)):
    _cleanup_stale_fec_runs(db)
    rows = (
        db.query(FECQueryRun)
        .options(defer(FECQueryRun.result_json), defer(FECQueryRun.normalized_transaction_ids_json))
        .order_by(FECQueryRun.started_at.desc())
        .limit(min(max(1, limit), 50))
        .all()
    )
    return [_fec_run_summary(row) for row in rows]


def _fec_run_summary(run: FECQueryRun) -> dict:
    query = {}
    if run.query_json:
        try:
            query = json.loads(run.query_json)
        except json.JSONDecodeError:
            query = {}
    summary_parts = []
    for field, label in [
        ("contributor_name", "contributor"),
        ("contributor_employer", "employer"),
        ("contributor_state", "state"),
        ("contributor_city", "city"),
        ("committee_id", "committee"),
        ("candidate_id", "candidate"),
        ("two_year_transaction_period", "cycle"),
    ]:
        if query.get(field):
            summary_parts.append(f"{label}: {query[field]}")
    return {
        "id": run.id,
        "audit_log_id": run.audit_log_id,
        "status": run.status,
        "pages_processed": run.pages_processed,
        "raw_records_fetched": run.raw_records_fetched,
        "inserted_count": run.inserted_count,
        "duplicate_count": run.duplicate_count,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "query_summary": " | ".join(summary_parts) if summary_parts else "Broad FEC query",
    }


def _compact_fec_record(row: NormalizedTransaction) -> dict:
    return {
        "id": row.id,
        "source_system": row.source_system,
        "source_record_id": row.source_record_id,
        "transaction_id": row.transaction_id,
        "transaction_type": row.transaction_type,
        "transaction_date": row.transaction_date.isoformat() if row.transaction_date else None,
        "amount": row.amount,
        "contributor_name": row.contributor_name,
        "contributor_employer": row.contributor_employer,
        "contributor_city": row.contributor_city,
        "contributor_state": row.contributor_state,
        "recipient_name": row.recipient_name,
        "committee_name": row.committee_name,
        "candidate_name": row.candidate_name,
        "party": row.party,
        "office": row.office,
        "district": row.district,
        "cycle": row.cycle,
        "topic_tags_json": row.topic_tags_json,
    }


def _compact_run_records(db: Session, run: FECQueryRun, limit: int = COMPACT_FEC_RECORD_LIMIT) -> list[dict]:
    ids = []
    if run.normalized_transaction_ids_json:
        try:
            ids = [int(value) for value in json.loads(run.normalized_transaction_ids_json or "[]") if value]
        except (TypeError, ValueError, json.JSONDecodeError):
            ids = []
    if ids:
        rows = (
            db.query(NormalizedTransaction)
            .filter(NormalizedTransaction.id.in_(ids))
            .order_by(NormalizedTransaction.transaction_date.desc().nullslast(), NormalizedTransaction.id.desc())
            .limit(limit)
            .all()
        )
        return [_compact_fec_record(row) for row in rows]

    try:
        result = json.loads(run.result_json or "{}")
    except json.JSONDecodeError:
        return []
    fallback_records = result.get("records", [])[:limit]
    for record in fallback_records:
        record.pop("_raw_payload", None)
    return fallback_records


@router.get("/fec-runs/{run_id}")
def fec_run_detail(run_id: int, include_result: bool = False, db: Session = Depends(get_db)):
    query = db.query(FECQueryRun).filter(FECQueryRun.id == run_id)
    if not include_result:
        query = query.options(defer(FECQueryRun.result_json))
    run = query.one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="FEC query run not found.")
    payload = _fec_run_summary(run)
    for field in ["query_json", "request_metadata_json", "normalized_transaction_ids_json"]:
        value = getattr(run, field, None)
        if value:
            try:
                payload[field.replace("_json", "")] = json.loads(value)
            except json.JSONDecodeError:
                payload[field.replace("_json", "")] = value
    payload["records"] = _compact_run_records(db, run)
    payload["records_limited_to"] = COMPACT_FEC_RECORD_LIMIT
    if include_result:
        try:
            payload["result"] = json.loads(run.result_json or "{}")
        except json.JSONDecodeError:
            payload["result"] = {}
    return payload


@router.get("/fec-runs/{run_id}/json")
def fec_run_json(run_id: int, db: Session = Depends(get_db)):
    run = db.query(FECQueryRun).filter(FECQueryRun.id == run_id).one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="FEC query run not found.")
    try:
        return json.loads(run.result_json or "{}")
    except json.JSONDecodeError:
        return {"query_run_id": run.id, "records": [], "errors": ["Stored JSON could not be decoded."]}


@router.get("/fec-runs/{run_id}/xlsx")
def fec_run_xlsx(run_id: int, db: Session = Depends(get_db)):
    run = db.query(FECQueryRun).filter(FECQueryRun.id == run_id).one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="FEC query run not found.")
    try:
        data = json.loads(run.result_json or "{}")
    except json.JSONDecodeError:
        data = {"records": []}
    
    records = data.get("records", [])
    out = BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as w:
        pd.DataFrame(records).to_excel(w, sheet_name='FEC Snapshot', index=False)
    out.seek(0)
    
    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=fec_snapshot_{run_id}.xlsx"}
    )


@router.post("/fec/cleanup-stale")
def cleanup_stale_fec_runs(db: Session = Depends(get_db)):
    return {"stale_runs_marked": _cleanup_stale_fec_runs(db)}


@router.post("/tec-preview")
def preview_tec_upload(file: UploadFile = File(...)):
    try:
        return preview_tec_file(file.file, filename=file.filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"TEC preview failed: {exc}") from exc


@router.post("/tec-file")
def ingest_tec_file(
    file: UploadFile = File(...),
    mapping_json: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    mapping = None
    if mapping_json:
        try:
            mapping = json.loads(mapping_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Manual TEC mapping was not valid JSON.") from exc

    audit = _create_audit(
        db,
        "TEC",
        "tec_file_import",
        {"filename": file.filename, "mapping": mapping or "auto"},
    )
    try:
        parsed = parse_tec_file(file.file, filename=file.filename, mapping=mapping)
        inserted = insert_records(db, "TEC", parsed.records, source_url=file.filename)

        for warning in parsed.warnings:
            db.add(
                DataQualityFlag(
                    transaction_id=None,
                    flag_type="unmapped_tec_column",
                    severity="info",
                    message=warning,
                )
            )
        db.commit()

        errors = inserted.get("errors", [])
        status = "completed" if not errors else "partial"
        _finish_audit(
            db,
            audit,
            status,
            1,
            len(parsed.records),
            inserted["inserted_count"],
            inserted["duplicate_count"],
            "; ".join(errors[:5]) if errors else None,
        )
        return {
            "source_system": "TEC",
            "status": status,
            "raw_records_fetched": len(parsed.records),
            "inserted_count": inserted["inserted_count"],
            "duplicate_count": inserted["duplicate_count"],
            "mapping": parsed.mapping,
            "mapping_confidence": parsed.confidence,
            "warnings": parsed.warnings,
            "errors": errors[:10],
            "audit_log_id": audit.id,
        }
    except Exception as exc:
        _finish_audit(db, audit, "failed", 1, 0, 0, 0, str(exc))
        raise HTTPException(status_code=400, detail=f"TEC import failed: {exc}") from exc


@router.get("/audit-logs")
def audit_logs(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(SourceAuditLog).order_by(SourceAuditLog.started_at.desc()).limit(limit).all()
    return [serialize_model(row) for row in rows]


@router.get("/data-quality-flags")
def data_quality_flags(limit: int = 250, db: Session = Depends(get_db)):
    rows = db.query(DataQualityFlag).order_by(DataQualityFlag.created_at.desc()).limit(limit).all()
    return [serialize_model(row) for row in rows]
