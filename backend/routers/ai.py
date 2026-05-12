from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.schemas import AIAskRequest
from backend.services.ai_service import ai_status, generate_brief

router = APIRouter(prefix="/ai")


@router.get("/status")
def status():
    return ai_status()


@router.post("/ask")
def ask(body: AIAskRequest, db: Session = Depends(get_db)):
    filters = dict(body.filters or {})
    filters["include_web_context"] = body.include_web_context
    return generate_brief(db, body.question, filters, body.insight_type)
