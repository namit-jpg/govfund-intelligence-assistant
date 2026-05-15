from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import DataQualityFlag, NormalizedTransaction, RawRecord, Watchlist
from backend.services.analytics_service import apply_filters
from backend.services.entity_matcher import build_match_explanation, match_transaction_to_watchlist
from backend.services.repository import serialize_model
from backend.services.tracker_service import watchlist_payload, watchlist_transactions_query

router = APIRouter(prefix="/transactions")

TRANSACTION_LIST_FIELDS = [
    "id",
    "source_system",
    "source_record_id",
    "transaction_id",
    "transaction_type",
    "transaction_date",
    "amount",
    "contributor_name",
    "contributor_employer",
    "contributor_entity_name",
    "contributor_city",
    "contributor_state",
    "recipient_name",
    "committee_id",
    "committee_name",
    "candidate_id",
    "candidate_name",
    "party",
    "office",
    "district",
    "cycle",
    "topic_tags_json",
    "confidence_score",
]


def _serialize_transaction_compact(row: NormalizedTransaction) -> dict:
    payload = {}
    for field in TRANSACTION_LIST_FIELDS:
        value = getattr(row, field)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        payload[field] = value
    return payload


def _get_watchlist_payload(db: Session, watchlist_id: int | None):
    if not watchlist_id:
        return None
    watchlist = db.query(Watchlist).filter(Watchlist.id == watchlist_id).one_or_none()
    if not watchlist:
        return None
    return watchlist_payload(db, watchlist)


@router.get("")
def list_transactions(
    watchlist_id: int | None = Query(default=None),
    q: str | None = None,
    source_system: str | None = None,
    min_date: str | None = None,
    max_date: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    contributor_name: str | None = None,
    contributor_employer: str | None = None,
    recipient: str | None = None,
    party: str | None = None,
    state: str | None = None,
    city: str | None = None,
    cycle: str | None = None,
    topic_tag: str | None = None,
    transaction_type: str | None = None,
    data_quality_flag: str | None = None,
    limit: int = 100,
    offset: int = 0,
    compact: bool = True,
    db: Session = Depends(get_db),
):
    filters = {
        "q": q,
        "source_system": source_system,
        "min_date": min_date,
        "max_date": max_date,
        "min_amount": min_amount,
        "max_amount": max_amount,
        "contributor_name": contributor_name,
        "contributor_employer": contributor_employer,
        "recipient": recipient,
        "party": party,
        "state": state,
        "city": city,
        "cycle": cycle,
        "topic_tag": topic_tag,
        "transaction_type": transaction_type,
    }
    watchlist_row = db.query(Watchlist).filter(Watchlist.id == watchlist_id).one_or_none() if watchlist_id else None
    if watchlist_row:
        query, _ = watchlist_transactions_query(db, watchlist_row, filters)
    else:
        query = apply_filters(db.query(NormalizedTransaction), filters)
    if data_quality_flag:
        ids = [
            row[0]
            for row in db.query(DataQualityFlag.transaction_id)
            .filter(DataQualityFlag.flag_type == data_quality_flag, DataQualityFlag.transaction_id.is_not(None))
            .all()
        ]
        query = query.filter(NormalizedTransaction.id.in_(ids or [-1]))

    total = query.count()
    rows = (
        query.order_by(NormalizedTransaction.transaction_date.desc().nullslast(), NormalizedTransaction.id.desc())
        .offset(max(0, offset))
        .limit(min(max(1, limit), 500))
        .all()
    )
    watchlist = _get_watchlist_payload(db, watchlist_id)
    payload = []

    for row in rows:
        transaction = _serialize_transaction_compact(row) if compact else serialize_model(row)
        if watchlist:
            match = match_transaction_to_watchlist(transaction, watchlist)
            transaction["matched_watchlist_name"] = watchlist["name"]
            transaction["matched_entity_name"] = match.get("matched_entity_name")
            transaction["matched_entity_type"] = match.get("matched_entity_type")
            transaction["match_confidence_score"] = round(float(match.get("match_confidence", 0.0)), 1)
            transaction["confidence_label"] = match.get("confidence_label")
            transaction["matched_on_field"] = match.get("matched_on_field")
            transaction["match_reason"] = match.get("match_reason")
            transaction["match_explanation"] = build_match_explanation(match, watchlist["name"])
        payload.append(transaction)

    return {"items": payload, "total": total, "limit": limit, "offset": offset}


@router.get("/raw")
def list_raw_records(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    query = db.query(RawRecord).order_by(RawRecord.ingested_at.desc(), RawRecord.id.desc())
    total = query.count()
    rows = query.offset(max(0, offset)).limit(min(max(1, limit), 500)).all()
    return {"items": [serialize_model(row) for row in rows], "total": total, "limit": limit, "offset": offset}
