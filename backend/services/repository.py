from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import (
    DataQualityFlag,
    Entity,
    EntityAlias,
    EntityRelationship,
    NormalizedTransaction,
    RawRecord,
)
from backend.services.data_quality import evaluate_transaction_quality
from backend.services.normalizer import (
    deterministic_source_record_id,
    hash_name,
    mask_person_name,
    normalize_name,
    tag_transaction_topics,
)

logger = logging.getLogger(__name__)


def to_json(value) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for candidate in (text[:10], text):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def parse_amount(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def serialize_model(row) -> dict:
    payload = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        payload[column.name] = value
    return payload


def _clean_string(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def prepare_normalized_record(record: dict, source_system: str) -> tuple[dict, bool]:
    normalized = {key: value for key, value in record.items() if not key.startswith("_")}
    normalized["source_system"] = source_system

    raw_payload = record.get("_raw_payload") or normalized
    generated = bool(record.get("_generated_source_record_id"))
    if not _clean_string(normalized.get("source_record_id")):
        normalized["source_record_id"] = deterministic_source_record_id(source_system, raw_payload)
        generated = True

    normalized["source_record_id"] = str(normalized["source_record_id"])
    normalized["transaction_date"] = parse_date(normalized.get("transaction_date"))
    normalized["amount"] = parse_amount(normalized.get("amount"))

    for field in [
        "transaction_id",
        "transaction_type",
        "contributor_name",
        "contributor_employer",
        "contributor_entity_name",
        "contributor_occupation",
        "contributor_city",
        "contributor_state",
        "contributor_zip",
        "recipient_name",
        "recipient_type",
        "committee_id",
        "committee_name",
        "recipient_committee_id",
        "candidate_id",
        "candidate_name",
        "filer_id",
        "filer_name",
        "party",
        "office",
        "district",
        "cycle",
        "report_year",
        "form_type",
        "memo_text",
        "purpose",
        "office_sought",
        "committee_type",
        "description",
        "source_url",
    ]:
        normalized[field] = _clean_string(normalized.get(field))

    contributor_name = normalized.get("contributor_name")
    normalized["contributor_name_masked"] = mask_person_name(contributor_name or "")
    normalized["contributor_name_hash"] = hash_name(contributor_name or "")

    if not normalized.get("committee_id") and normalized.get("recipient_committee_id"):
        normalized["committee_id"] = normalized["recipient_committee_id"]
    if not normalized.get("recipient_committee_id") and normalized.get("committee_id"):
        normalized["recipient_committee_id"] = normalized["committee_id"]
    if not normalized.get("committee_name") and normalized.get("recipient_name"):
        normalized["committee_name"] = normalized.get("recipient_name")
    if not normalized.get("recipient_name"):
        normalized["recipient_name"] = (
            normalized.get("committee_name")
            or normalized.get("candidate_name")
            or normalized.get("filer_name")
        )

    normalized["topic_tags_json"] = to_json(tag_transaction_topics(normalized))
    normalized["confidence_score"] = normalized.get("confidence_score") or 1.0
    return normalized, generated


def find_or_create_entity(db: Session, entity_type: str, name: str | None, source_system: str | None = None) -> Entity | None:
    if not name:
        return None
    normalized = normalize_name(name)
    if not normalized:
        return None
    entity = (
        db.query(Entity)
        .filter(Entity.entity_type == entity_type, Entity.normalized_name == normalized)
        .one_or_none()
    )
    if entity:
        return entity
    entity = Entity(
        entity_type=entity_type,
        canonical_name=name,
        normalized_name=normalized,
        source_system=source_system,
        metadata_json=to_json({"created_from": "ingestion"}),
    )
    db.add(entity)
    db.flush()
    return entity


def add_alias(db: Session, entity: Entity | None, alias: str | None, source: str, confidence: float = 1.0) -> None:
    if not entity or not alias:
        return
    normalized_alias = normalize_name(alias)
    if not normalized_alias:
        return
    existing = (
        db.query(EntityAlias)
        .filter(EntityAlias.entity_id == entity.id, EntityAlias.normalized_alias == normalized_alias)
        .first()
    )
    if existing:
        return
    db.add(
        EntityAlias(
            entity_id=entity.id,
            alias_name=alias,
            alias=alias,
            normalized_alias=normalized_alias,
            source=source,
            confidence=confidence,
            confidence_score=confidence,
        )
    )


def resolve_entities_for_transaction(db: Session, transaction: NormalizedTransaction) -> None:
    source = transaction.source_system
    employer = find_or_create_entity(db, "EMPLOYER_SIGNAL", transaction.contributor_employer, source)
    company = find_or_create_entity(db, "COMPANY_SIGNAL", transaction.contributor_entity_name, source)
    contributor = find_or_create_entity(db, "PERSON", transaction.contributor_name, source)
    recipient = find_or_create_entity(db, "COMMITTEE", transaction.committee_name or transaction.recipient_name, source)
    candidate = find_or_create_entity(db, "CANDIDATE", transaction.candidate_name, source)
    filer = find_or_create_entity(db, "FILER", transaction.filer_name, source)

    for entity, alias in [
        (employer, transaction.contributor_employer),
        (company, transaction.contributor_entity_name),
        (contributor, transaction.contributor_name),
        (recipient, transaction.recipient_name),
        (recipient, transaction.committee_name),
        (candidate, transaction.candidate_name),
        (filer, transaction.filer_name),
    ]:
        add_alias(db, entity, alias, source or "ingestion")

    for left, right, relationship in [
        (employer or company, contributor, "reported_by_contributor"),
        (contributor, recipient or candidate or filer, "contributed_to"),
        (employer or company, recipient or candidate or filer, "employer_signal_to_recipient"),
    ]:
        if not left or not right:
            continue
        exists = (
            db.query(EntityRelationship)
            .filter(
                EntityRelationship.from_entity_id == left.id,
                EntityRelationship.to_entity_id == right.id,
                EntityRelationship.relationship_type == relationship,
            )
            .first()
        )
        if not exists:
            db.add(
                EntityRelationship(
                    from_entity_id=left.id,
                    to_entity_id=right.id,
                    relationship_type=relationship,
                    source_system=source,
                    confidence_score=1.0 if relationship != "employer_signal_to_recipient" else 0.75,
                    evidence_json=to_json({"source_record_id": transaction.source_record_id}),
                )
            )


def insert_records(db: Session, source_system: str, records: Iterable[dict], source_url: str | None = None) -> dict:
    inserted = 0
    duplicates = 0
    transaction_ids: list[int] = []
    errors: list[str] = []

    for index, record in enumerate(records, start=1):
        try:
            normalized, generated = prepare_normalized_record(record, source_system)
            raw_payload = record.get("_raw_payload") or normalized
            source_record_id = normalized["source_record_id"]

            existing = (
                db.query(NormalizedTransaction)
                .filter(
                    NormalizedTransaction.source_system == source_system,
                    NormalizedTransaction.source_record_id == source_record_id,
                )
                .one_or_none()
            )
            if existing:
                duplicates += 1
                transaction_ids.append(existing.id)
                if not db.query(DataQualityFlag).filter(
                    DataQualityFlag.transaction_id == existing.id,
                    DataQualityFlag.flag_type == "duplicate_record",
                ).first():
                    db.add(
                        DataQualityFlag(
                            transaction_id=existing.id,
                            flag_type="duplicate_record",
                            severity="info",
                            message="Duplicate source record was skipped during ingestion.",
                        )
                    )
                continue

            raw_record = RawRecord(
                source_name=source_system,
                source_system=source_system,
                source_record_id=source_record_id,
                raw_payload_json=to_json(raw_payload),
                source_url=normalized.get("source_url") or source_url,
                imported_at=datetime.utcnow(),
            )
            db.add(raw_record)
            db.flush()

            allowed = {column.name for column in NormalizedTransaction.__table__.columns}
            payload = {key: value for key, value in normalized.items() if key in allowed}
            payload["raw_record_id"] = raw_record.id
            transaction = NormalizedTransaction(**payload)
            db.add(transaction)
            db.flush()

            for flag in evaluate_transaction_quality(normalized, generated):
                db.add(DataQualityFlag(transaction_id=transaction.id, **flag))

            resolve_entities_for_transaction(db, transaction)
            inserted += 1
            transaction_ids.append(transaction.id)
        except IntegrityError as exc:
            db.rollback()
            duplicates += 1
            logger.info("Duplicate %s record skipped at row %s: %s", source_system, index, exc)
        except Exception as exc:
            db.rollback()
            errors.append(f"Row {index}: {exc}")
            logger.exception("Could not insert %s record at row %s", source_system, index)
        else:
            db.commit()

    db.commit()
    return {
        "inserted_count": inserted,
        "duplicate_count": duplicates,
        "transaction_ids": transaction_ids,
        "errors": errors,
    }
