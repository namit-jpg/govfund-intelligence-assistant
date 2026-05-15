from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models import (
    FECQueryRun,
    NormalizedTransaction,
    SourceAuditLog,
    Watchlist,
    WatchlistEntity,
    WatchlistRun,
    WatchlistRunTransaction,
)
from backend.services.analytics_service import apply_filters
from backend.services.entity_matcher import build_match_explanation, match_transaction_to_watchlist
from backend.services.fec_client import build_fec_request_params, fetch_fec_transactions, redact_query, sanitize_fec_error
from backend.services.normalizer import normalize_name
from backend.services.repository import insert_records, parse_date, serialize_model, to_json


def _parse_json(value, default):
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default


def _date_text(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _entity_notes(entity: WatchlistEntity) -> dict:
    return _parse_json(entity.notes, {})


def _watchlist_entities(db: Session, watchlist_id: int) -> list[WatchlistEntity]:
    return db.query(WatchlistEntity).filter(WatchlistEntity.watchlist_id == watchlist_id).all()


def watchlist_payload(db: Session, watchlist: Watchlist) -> dict:
    entities = _watchlist_entities(db, watchlist.id)
    return {
        "id": watchlist.id,
        "name": watchlist.name,
        "entities": [
            {
                "entity_name": entity.entity_name,
                "entity_type": entity.entity_type,
                **_entity_notes(entity),
            }
            for entity in entities
        ],
    }


def serialize_watchlist(db: Session, watchlist: Watchlist) -> dict:
    entities = _watchlist_entities(db, watchlist.id)
    latest_run = (
        db.query(WatchlistRun)
        .filter(WatchlistRun.watchlist_id == watchlist.id)
        .order_by(WatchlistRun.started_at.desc())
        .first()
    )
    filters = _parse_json(watchlist.filters_json, {})
    return {
        "id": watchlist.id,
        "name": watchlist.name,
        "description": watchlist.description,
        "watchlist_type": watchlist.watchlist_type,
        "status": watchlist.status or "active",
        "cadence": watchlist.cadence or "daily",
        "enabled": watchlist.enabled is not False,
        "date_from": _date_text(watchlist.date_from),
        "date_to": _date_text(watchlist.date_to),
        "cycle": watchlist.cycle or filters.get("cycle"),
        "min_amount": watchlist.min_amount,
        "max_records": watchlist.max_records,
        "last_run_at": _date_text(watchlist.last_run_at),
        "next_run_at": _date_text(watchlist.next_run_at),
        "entities": [
            {
                "id": entity.id,
                "entity_name": entity.entity_name,
                "entity_type": entity.entity_type,
                "notes": _entity_notes(entity),
            }
            for entity in entities
        ],
        "latest_run": serialize_model(latest_run) if latest_run else None,
    }


def create_watchlist_from_payload(db: Session, payload) -> Watchlist:
    filters = payload.filters or {}
    cadence = (filters.get("cadence") or payload.cadence or "daily").lower().replace(" ", "_")
    watchlist = Watchlist(
        name=payload.name,
        description=payload.description,
        watchlist_type=payload.watchlist_type,
        filters_json=json.dumps(filters),
        date_from=parse_date(filters.get("date_from")),
        date_to=parse_date(filters.get("date_to")),
        min_amount=float(filters["min_amount"]) if filters.get("min_amount") not in (None, "") else None,
        sources=filters.get("source_system") or "FEC",
        status="active",
        cadence=cadence,
        cycle=str(filters.get("cycle") or "") or None,
        max_records=int(filters.get("max_records") or payload.max_records or 250),
        enabled=bool(payload.enabled),
        next_run_at=datetime.utcnow() if cadence != "historical_only" else None,
    )
    db.add(watchlist)
    db.flush()
    for entity in payload.entities:
        name = (entity.get("entity_name") or "").strip()
        if not name:
            continue
        notes = {
            key: entity.get(key)
            for key in ("candidate_id", "committee_id")
            if entity.get(key)
        }
        db.add(
            WatchlistEntity(
                watchlist_id=watchlist.id,
                entity_type=(entity.get("entity_type") or "EMPLOYER_SIGNAL").upper(),
                entity_name=name,
                normalized_entity_name=normalize_name(name),
                notes=json.dumps(notes) if notes else None,
            )
        )
    db.commit()
    db.refresh(watchlist)
    return watchlist


def _base_watchlist_filters(watchlist: Watchlist) -> dict:
    filters = _parse_json(watchlist.filters_json, {})
    return {
        "source_system": "FEC",
        "min_date": _date_text(watchlist.date_from) or filters.get("date_from") or filters.get("min_date"),
        "max_date": _date_text(watchlist.date_to) or filters.get("date_to") or filters.get("max_date"),
        "min_amount": watchlist.min_amount if watchlist.min_amount is not None else filters.get("min_amount"),
        "cycle": watchlist.cycle or filters.get("cycle"),
        "state": filters.get("state") or filters.get("contributor_state"),
    }


def _fec_queries_for_watchlist(watchlist: Watchlist, entities: list[WatchlistEntity]) -> list[dict]:
    base = _base_watchlist_filters(watchlist)
    max_records = max(1, min(int(watchlist.max_records or 250), 5000))
    per_entity_limit = max(25, min(500, max_records // max(1, len(entities))))
    queries = []
    for entity in entities:
        notes = _entity_notes(entity)
        entity_type = (entity.entity_type or "").upper()
        query = {
            key: value
            for key, value in base.items()
            if value not in (None, "", "All")
        }
        query["max_records"] = per_entity_limit
        query["per_page"] = 100
        if base.get("cycle"):
            query["two_year_transaction_period"] = str(base["cycle"])
        if entity_type in {"EMPLOYER_SIGNAL", "COMPANY_SIGNAL", "BUSINESS"}:
            query["contributor_employer"] = entity.entity_name
        elif notes.get("committee_id") or entity.entity_name.upper().startswith("C"):
            query["committee_id"] = notes.get("committee_id") or entity.entity_name.strip()
        elif notes.get("candidate_id") or entity.entity_name[:1].isalpha() and entity.entity_name[1:].isdigit():
            query["candidate_id"] = notes.get("candidate_id") or entity.entity_name.strip()
        else:
            continue
        queries.append(query)
    return queries


def _create_audit(db: Session, watchlist: Watchlist, query: dict) -> SourceAuditLog:
    audit = SourceAuditLog(
        source_system="FEC",
        operation_type="watchlist_fec_ingest",
        query_json=to_json({"watchlist_id": watchlist.id, **query}),
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


def _finish_audit(db: Session, audit: SourceAuditLog, status: str, fetched=None, inserted=None, error: str | None = None) -> None:
    audit.status = status
    audit.completed_at = datetime.utcnow()
    audit.pages_processed = getattr(fetched, "pages_processed", 0) if fetched else 0
    audit.raw_records_fetched = getattr(fetched, "raw_records_fetched", 0) if fetched else 0
    audit.inserted_count = (inserted or {}).get("inserted_count", 0)
    audit.duplicate_count = (inserted or {}).get("duplicate_count", 0)
    audit.error_message = sanitize_fec_error(error) if error else None
    db.add(audit)
    db.commit()


def _store_fec_query_run(db: Session, watchlist: Watchlist, audit: SourceAuditLog, query: dict, fetched, inserted, errors: list[str]) -> FECQueryRun:
    status = "completed" if not errors else "partial"
    run = FECQueryRun(
        audit_log_id=audit.id,
        query_json=to_json({"watchlist_id": watchlist.id, **query}),
        request_metadata_json=to_json({"endpoint": "schedule_a", "request_params": fetched.query}),
        result_json=to_json(
            {
                "query": query,
                "records": fetched.records,
                "audit": {
                    "audit_log_id": audit.id,
                    "pages_processed": fetched.pages_processed,
                    "raw_records_fetched": fetched.raw_records_fetched,
                    "inserted_count": inserted.get("inserted_count", 0),
                    "duplicate_count": inserted.get("duplicate_count", 0),
                },
                "errors": errors[:10],
            }
        ),
        normalized_transaction_ids_json=to_json(inserted.get("transaction_ids", [])),
        status=status,
        pages_processed=fetched.pages_processed,
        raw_records_fetched=fetched.raw_records_fetched,
        inserted_count=inserted.get("inserted_count", 0),
        duplicate_count=inserted.get("duplicate_count", 0),
        error_message="; ".join(errors[:5]) if errors else None,
        started_at=audit.started_at,
        completed_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _watchlist_sql_filter(query, entities: list[WatchlistEntity]):
    clauses = []
    for entity in entities:
        name = entity.entity_name.strip()
        if not name:
            continue
        like = f"%{name}%"
        entity_type = (entity.entity_type or "").upper()
        notes = _entity_notes(entity)
        if entity_type in {"EMPLOYER_SIGNAL", "COMPANY_SIGNAL", "BUSINESS"}:
            clauses.append(NormalizedTransaction.contributor_employer.ilike(like))
            clauses.append(NormalizedTransaction.contributor_entity_name.ilike(like))
        else:
            clauses.extend(
                [
                    NormalizedTransaction.recipient_name.ilike(like),
                    NormalizedTransaction.committee_name.ilike(like),
                    NormalizedTransaction.candidate_name.ilike(like),
                ]
            )
        if notes.get("committee_id"):
            clauses.append(NormalizedTransaction.committee_id == notes["committee_id"])
        if notes.get("candidate_id"):
            clauses.append(NormalizedTransaction.candidate_id == notes["candidate_id"])
        if name.upper().startswith("C"):
            clauses.append(NormalizedTransaction.committee_id == name)
        elif name[:1].isalpha() and name[1:].isdigit():
            clauses.append(NormalizedTransaction.candidate_id == name)
    if clauses:
        query = query.filter(or_(*clauses))
    return query


def watchlist_transactions_query(db: Session, watchlist: Watchlist, extra_filters: dict | None = None):
    entities = _watchlist_entities(db, watchlist.id)
    filters = {**_base_watchlist_filters(watchlist), **(extra_filters or {})}
    query = apply_filters(db.query(NormalizedTransaction), filters)
    return _watchlist_sql_filter(query, entities), entities


def linked_watchlist_transactions(db: Session, watchlist_id: int, limit: int = 10000) -> list[NormalizedTransaction]:
    latest_run = (
        db.query(WatchlistRun)
        .filter(WatchlistRun.watchlist_id == watchlist_id)
        .order_by(WatchlistRun.started_at.desc())
        .first()
    )
    if not latest_run:
        watchlist = db.query(Watchlist).filter(Watchlist.id == watchlist_id).one_or_none()
        if not watchlist:
            return []
        query, _ = watchlist_transactions_query(db, watchlist)
        return query.order_by(NormalizedTransaction.transaction_date.desc().nullslast()).limit(limit).all()
    ids = [
        row[0]
        for row in db.query(WatchlistRunTransaction.normalized_transaction_id)
        .filter(WatchlistRunTransaction.watchlist_run_id == latest_run.id)
        .limit(limit)
        .all()
    ]
    if not ids:
        return []
    return (
        db.query(NormalizedTransaction)
        .filter(NormalizedTransaction.id.in_(ids))
        .order_by(NormalizedTransaction.transaction_date.desc().nullslast(), NormalizedTransaction.id.desc())
        .all()
    )


def link_matching_transactions(db: Session, watchlist: Watchlist, run: WatchlistRun) -> int:
    query, entities = watchlist_transactions_query(db, watchlist)
    payload = watchlist_payload(db, watchlist)
    rows = query.order_by(NormalizedTransaction.transaction_date.desc().nullslast()).limit(10000).all()
    count = 0
    for row in rows:
        transaction = serialize_model(row)
        match = match_transaction_to_watchlist(transaction, payload)
        if not match.get("matched_entity_name"):
            continue
        exists = (
            db.query(WatchlistRunTransaction)
            .filter(
                WatchlistRunTransaction.watchlist_run_id == run.id,
                WatchlistRunTransaction.normalized_transaction_id == row.id,
            )
            .first()
        )
        if exists:
            continue
        db.add(
            WatchlistRunTransaction(
                watchlist_run_id=run.id,
                watchlist_id=watchlist.id,
                normalized_transaction_id=row.id,
                matched_entity_name=match.get("matched_entity_name"),
                matched_entity_type=match.get("matched_entity_type"),
                matched_on_field=match.get("matched_on_field"),
                match_confidence=float(match.get("match_confidence", 0.0)),
                match_reason=match.get("match_reason"),
            )
        )
        count += 1
    db.commit()
    return count


def run_watchlist(db: Session, watchlist_id: int, run_type: str = "manual", live: bool = True) -> dict:
    watchlist = db.query(Watchlist).filter(Watchlist.id == watchlist_id).one_or_none()
    if not watchlist:
        raise ValueError(f"Watchlist {watchlist_id} was not found.")
    run = WatchlistRun(watchlist_id=watchlist.id, run_type=run_type, status="running", started_at=datetime.utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)

    audit_ids: list[int] = []
    fec_run_ids: list[int] = []
    errors: list[str] = []
    totals = {"pages": 0, "raw": 0, "inserted": 0, "duplicates": 0}
    entities = _watchlist_entities(db, watchlist.id)
    try:
        if live and os.getenv("FEC_API_KEY"):
            for query in _fec_queries_for_watchlist(watchlist, entities):
                audit = _create_audit(db, watchlist, query)
                audit_ids.append(audit.id)
                try:
                    fetched = fetch_fec_transactions(query)
                    inserted = insert_records(db, "FEC", fetched.records, source_url="https://api.open.fec.gov/v1/schedules/schedule_a/")
                    query_errors = [sanitize_fec_error(error) for error in (fetched.errors + inserted.get("errors", []))]
                    _finish_audit(db, audit, "completed" if not query_errors else "partial", fetched, inserted, "; ".join(query_errors[:5]) if query_errors else None)
                    fec_run = _store_fec_query_run(db, watchlist, audit, query, fetched, inserted, query_errors)
                    fec_run_ids.append(fec_run.id)
                    totals["pages"] += fetched.pages_processed
                    totals["raw"] += fetched.raw_records_fetched
                    totals["inserted"] += inserted.get("inserted_count", 0)
                    totals["duplicates"] += inserted.get("duplicate_count", 0)
                    errors.extend(query_errors)
                except Exception as exc:
                    message = sanitize_fec_error(exc)
                    _finish_audit(db, audit, "failed", error=message)
                    errors.append(message)
        elif live and not os.getenv("FEC_API_KEY"):
            errors.append("FEC_API_KEY is missing; tracker used local records only.")

        matched = link_matching_transactions(db, watchlist, run)
        run.status = "completed" if not errors else "partial"
        run.completed_at = datetime.utcnow()
        run.pages_processed = totals["pages"]
        run.raw_records_fetched = totals["raw"]
        run.inserted_count = totals["inserted"]
        run.duplicate_count = totals["duplicates"]
        run.matched_count = matched
        run.audit_log_ids_json = to_json(audit_ids)
        run.fec_query_run_ids_json = to_json(fec_run_ids)
        run.error_message = "; ".join(errors[:5]) if errors else None
        watchlist.last_run_at = run.completed_at
        watchlist.next_run_at = run.completed_at + timedelta(days=1) if watchlist.enabled and watchlist.cadence == "daily" else None
        db.add(run)
        db.add(watchlist)
        db.commit()
        return serialize_model(run)
    except Exception as exc:
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        run.error_message = sanitize_fec_error(exc)
        db.add(run)
        db.commit()
        raise


def run_due_watchlists(db: Session) -> list[dict]:
    now = datetime.utcnow()
    watchlists = (
        db.query(Watchlist)
        .filter(
            or_(Watchlist.enabled.is_(True), Watchlist.enabled.is_(None)),
            or_(Watchlist.status == "active", Watchlist.status.is_(None)),
            or_(Watchlist.cadence == "daily", Watchlist.cadence.is_(None)),
            or_(Watchlist.next_run_at.is_(None), Watchlist.next_run_at <= now),
        )
        .all()
    )
    return [run_watchlist(db, watchlist.id, run_type="scheduled", live=True) for watchlist in watchlists]


def matched_transaction_payload(db: Session, watchlist: Watchlist, rows: list[NormalizedTransaction]) -> list[dict]:
    payload = watchlist_payload(db, watchlist)
    out = []
    for row in rows:
        item = serialize_model(row)
        match = match_transaction_to_watchlist(item, payload)
        item["matched_entity_name"] = match.get("matched_entity_name")
        item["matched_entity_type"] = match.get("matched_entity_type")
        item["matched_on_field"] = match.get("matched_on_field")
        item["match_confidence_score"] = round(float(match.get("match_confidence", 0.0)), 1)
        item["confidence_label"] = match.get("confidence_label")
        item["match_explanation"] = build_match_explanation(match, watchlist.name)
        out.append(item)
    return out
