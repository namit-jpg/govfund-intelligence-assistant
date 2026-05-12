import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.db import get_db
from backend.models import Watchlist, WatchlistEntity
from backend.schemas import WatchlistCreateRequest
from backend.services.normalizer import normalize_name
router=APIRouter(prefix='/watchlists')
@router.post('')
def create_watchlist(payload:WatchlistCreateRequest, db:Session=Depends(get_db)):
    w=Watchlist(
        name=payload.name,
        description=payload.description,
        watchlist_type=payload.watchlist_type,
        filters_json=json.dumps(payload.filters or {}),
    )
    db.add(w); db.flush()
    for e in payload.entities:
        if not e.get('entity_name'):
            continue
        db.add(WatchlistEntity(watchlist_id=w.id, entity_type=e.get('entity_type','EMPLOYER_SIGNAL'), entity_name=e['entity_name'], normalized_entity_name=normalize_name(e['entity_name'])))
    db.commit(); return {'id':w.id}
@router.get('')
def list_watchlists(db:Session=Depends(get_db)):
    return [{'id':w.id,'name':w.name,'description':w.description,'watchlist_type':w.watchlist_type} for w in db.query(Watchlist).order_by(Watchlist.created_at.desc()).all()]
