from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class RawRecord(Base):
    __tablename__ = "raw_records"
    __table_args__ = (UniqueConstraint("source_system", "source_record_id", name="uq_raw_records_source_record"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_system: Mapped[str] = mapped_column(String(20), index=True)
    source_record_id: Mapped[str] = mapped_column(String(160), index=True)
    raw_payload_json: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NormalizedTransaction(Base):
    __tablename__ = "normalized_transactions"
    __table_args__ = (UniqueConstraint("source_system", "source_record_id", name="uq_normalized_transactions_source_record"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system: Mapped[str] = mapped_column(String(20), index=True)
    source_record_id: Mapped[str] = mapped_column(String(160), index=True)
    transaction_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    contributor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contributor_name_masked: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contributor_name_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contributor_employer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contributor_entity_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contributor_occupation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contributor_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contributor_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contributor_zip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    committee_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    committee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_committee_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    candidate_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    candidate_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    filer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    party: Mapped[str | None] = mapped_column(String(120), nullable=True)
    office: Mapped[str | None] = mapped_column(String(80), nullable=True)
    district: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cycle: Mapped[str | None] = mapped_column(String(20), nullable=True)
    report_year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    form_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    memo_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    office_sought: Mapped[str | None] = mapped_column(String(50), nullable=True)
    committee_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_confidence: Mapped[float] = mapped_column(Float, default=0)
    matched_entity_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id"), nullable=True)
    is_duplicate_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_record_id: Mapped[int | None] = mapped_column(ForeignKey("raw_records.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    canonical_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    source_system: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    aliases = relationship("EntityAlias", back_populates="entity")


class EntityAlias(Base):
    __tablename__ = "entity_aliases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"))
    alias_name: Mapped[str] = mapped_column(String(255))
    normalized_alias: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    entity = relationship("Entity", back_populates="aliases")


class EntityRelationship(Base):
    __tablename__ = "entity_relationships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"))
    to_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"))
    relationship_type: Mapped[str] = mapped_column(String(80))
    source_system: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SourceAuditLog(Base):
    __tablename__ = "source_audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system: Mapped[str] = mapped_column(String(20), index=True)
    operation_type: Mapped[str] = mapped_column(String(80))
    query_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="running")
    pages_processed: Mapped[int] = mapped_column(Integer, default=0)
    raw_records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class FECQueryRun(Base):
    __tablename__ = "fec_query_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    audit_log_id: Mapped[int | None] = mapped_column(ForeignKey("source_audit_logs.id"), nullable=True)
    query_json: Mapped[str] = mapped_column(Text)
    request_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_transaction_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="running")
    pages_processed: Mapped[int] = mapped_column(Integer, default=0)
    raw_records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DataQualityFlag(Base):
    __tablename__ = "data_quality_flags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("normalized_transactions.id"), nullable=True)
    flag_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InsightRun(Base):
    __tablename__ = "insight_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    insight_type: Mapped[str] = mapped_column(String(100))
    input_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_record_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Watchlist(Base):
    __tablename__ = "watchlists"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watchlist_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id"), nullable=True)
    filters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    min_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    sources: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WatchlistEntity(Base):
    __tablename__ = "watchlist_entities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_name: Mapped[str] = mapped_column(String(255))
    normalized_entity_name: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class AISummary(Base):
    __tablename__ = "ai_summaries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    summary_type: Mapped[str] = mapped_column(String(100))
    user_question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    source_filters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_type: Mapped[str] = mapped_column(String(100))
    actor: Mapped[str] = mapped_column(String(100), default="system")
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    filters_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
