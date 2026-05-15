from pydantic import BaseModel, Field
from typing import Optional

class FECIngestRequest(BaseModel):
    contributor_name: Optional[str] = None
    contributor_employer: Optional[str] = None
    contributor_state: Optional[str] = None
    contributor_city: Optional[str] = None
    committee_id: Optional[str] = None
    candidate_id: Optional[str] = None
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    two_year_transaction_period: Optional[str] = None
    cycle: Optional[str] = None
    per_page: int = 100
    max_records: int = 5000

class AIAskRequest(BaseModel):
    question: str
    filters: dict = Field(default_factory=dict)
    insight_type: str = "custom_question"
    include_web_context: bool = True


class TexasBrowserIngestRequest(BaseModel):
    watchlist_id: Optional[int] = None
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    transaction_type: Optional[str] = None
    max_entities: int = 10


class WatchlistCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    watchlist_type: str = "entity"
    entities: list[dict] = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)
    cadence: str = "daily"
    max_records: int = 250
    enabled: bool = True
