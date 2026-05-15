from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import Watchlist, WatchlistRun
from backend.schemas import WatchlistCreateRequest
from backend.services.repository import serialize_model
from backend.services.tracker_service import (
    create_watchlist_from_payload,
    linked_watchlist_transactions,
    matched_transaction_payload,
    run_watchlist,
    serialize_watchlist,
)

router = APIRouter(prefix="/watchlists")


@router.post("")
def create_watchlist(payload: WatchlistCreateRequest, db: Session = Depends(get_db)):
    watchlist = create_watchlist_from_payload(db, payload)
    return serialize_watchlist(db, watchlist)


@router.get("")
def list_watchlists(db: Session = Depends(get_db)):
    rows = db.query(Watchlist).order_by(Watchlist.created_at.desc()).all()
    return [serialize_watchlist(db, row) for row in rows]


@router.get("/{watchlist_id}")
def get_watchlist(watchlist_id: int, db: Session = Depends(get_db)):
    watchlist = db.query(Watchlist).filter(Watchlist.id == watchlist_id).one_or_none()
    if not watchlist:
        raise HTTPException(status_code=404, detail="Tracker was not found.")
    return serialize_watchlist(db, watchlist)


@router.post("/{watchlist_id}/run")
def run_watchlist_now(watchlist_id: int, live: bool = Query(default=True), db: Session = Depends(get_db)):
    try:
        return run_watchlist(db, watchlist_id, run_type="manual", live=live)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{watchlist_id}/runs")
def list_watchlist_runs(watchlist_id: int, limit: int = 20, db: Session = Depends(get_db)):
    rows = (
        db.query(WatchlistRun)
        .filter(WatchlistRun.watchlist_id == watchlist_id)
        .order_by(WatchlistRun.started_at.desc())
        .limit(min(max(1, limit), 100))
        .all()
    )
    return [serialize_model(row) for row in rows]


@router.get("/{watchlist_id}/transactions")
def list_watchlist_transactions(watchlist_id: int, limit: int = 250, db: Session = Depends(get_db)):
    watchlist = db.query(Watchlist).filter(Watchlist.id == watchlist_id).one_or_none()
    if not watchlist:
        raise HTTPException(status_code=404, detail="Tracker was not found.")
    rows = linked_watchlist_transactions(db, watchlist_id, min(max(1, limit), 1000))
    return {
        "watchlist": serialize_watchlist(db, watchlist),
        "items": matched_transaction_payload(db, watchlist, rows),
        "total": len(rows),
        "limit": limit,
    }
