from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import pandas as pd
from rapidfuzz import fuzz

from backend.services.normalizer import deterministic_source_record_id


FIELD_CANDIDATES = {
    "source_record_id": ["source record id", "record id", "transaction id", "tran id"],
    "transaction_date": ["transaction date", "date", "contribution date", "receipt date", "expenditure date"],
    "amount": ["amount", "contribution amount", "receipt amount", "expenditure amount", "monetary amount"],
    "contributor_name": ["contributor name", "donor name", "name", "individual name"],
    "contributor_entity_name": ["contributor entity name", "entity name", "organization name", "contributor organization"],
    "contributor_employer": ["employer", "contributor employer"],
    "contributor_city": ["city", "contributor city"],
    "contributor_state": ["state", "contributor state"],
    "contributor_zip": ["zip", "zipcode", "zip code", "contributor zip"],
    "recipient_name": ["recipient", "recipient name", "candidate committee", "committee name", "payee name"],
    "filer_id": ["filer id", "filer identification", "committee id"],
    "filer_name": ["filer name", "filer", "committee name"],
    "committee_name": ["committee name", "committee"],
    "candidate_name": ["candidate name", "candidate"],
    "party": ["party", "political party"],
    "office": ["office", "office sought"],
    "district": ["district"],
    "transaction_type": ["transaction type", "record type", "type", "contribution type"],
    "purpose": ["purpose", "description", "memo", "explanation"],
    "description": ["description", "purpose", "memo", "explanation"],
    "report_year": ["report year", "year"],
    "form_type": ["form type", "report type"],
}

REQUIRED_FIELDS = ["transaction_date", "amount"]


@dataclass
class TECParseResult:
    records: list[dict]
    mapping: dict
    confidence: float
    warnings: list[str]
    columns: list[str]
    preview_rows: list[dict]


def _canon(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in str(value)).split())


def _read_table(file_like, filename: str | None = None) -> pd.DataFrame:
    name = (filename or "").lower()
    data = file_like.read()
    if hasattr(file_like, "seek"):
        file_like.seek(0)
    buffer = io.BytesIO(data) if isinstance(data, bytes) else io.StringIO(data)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(buffer)
    return pd.read_csv(buffer)


def detect_tec_mapping(columns: list[str]) -> dict:
    canonical_columns = {_canon(column): column for column in columns}
    mapping: dict[str, str | None] = {}
    scores: list[float] = []

    for field, candidates in FIELD_CANDIDATES.items():
        best_column = None
        best_score = 0.0
        for candidate in candidates:
            canonical_candidate = _canon(candidate)
            if canonical_candidate in canonical_columns:
                best_column = canonical_columns[canonical_candidate]
                best_score = 1.0
                break
            for canonical_column, original_column in canonical_columns.items():
                score = fuzz.token_set_ratio(canonical_candidate, canonical_column) / 100
                if score > best_score:
                    best_column = original_column
                    best_score = score
        threshold = 0.9 if field == "source_record_id" else 0.78
        if best_score >= threshold:
            mapping[field] = best_column
            scores.append(best_score)
        else:
            mapping[field] = None

    required_score = sum(1 for field in REQUIRED_FIELDS if mapping.get(field)) / len(REQUIRED_FIELDS)
    optional_score = sum(scores) / len(scores) if scores else 0
    confidence = round((required_score * 0.7) + (optional_score * 0.3), 2)
    return {"mapping": mapping, "confidence": confidence}


def preview_tec_file(file_like, filename: str | None = None, rows: int = 5) -> dict:
    df = _read_table(file_like, filename)
    df = df.dropna(how="all")
    columns = [str(column).strip() for column in df.columns]
    detected = detect_tec_mapping(columns)
    preview = df.head(rows).where(pd.notna(df), None).to_dict(orient="records")
    warnings = []
    missing = [field for field in REQUIRED_FIELDS if not detected["mapping"].get(field)]
    if not any(detected["mapping"].get(field) for field in ["recipient_name", "filer_name", "committee_name", "candidate_name"]):
        missing.append("recipient_name")
    if missing:
        warnings.append("Missing required mapping fields: " + ", ".join(missing))
    if detected["confidence"] < 0.65:
        warnings.append("Automatic mapping confidence is low. Review mappings before importing.")
    return {
        "columns": columns,
        "mapping": detected["mapping"],
        "confidence": detected["confidence"],
        "warnings": warnings,
        "preview_rows": preview,
    }


def _pick(row: dict, mapping: dict, field: str) -> Any:
    column = mapping.get(field)
    if not column:
        return None
    value = row.get(column)
    if pd.isna(value):
        return None
    return value


def _transaction_type(value) -> str:
    text = str(value or "contribution").strip().lower()
    if text.startswith("expend") or "expenditure" in text:
        return "expenditure"
    if text.startswith("loan"):
        return "loan"
    if text.startswith("pledge"):
        return "pledge"
    return "contribution"


def parse_tec_file(file_like, filename: str | None = None, mapping: dict | None = None) -> TECParseResult:
    df = _read_table(file_like, filename)
    df = df.dropna(how="all")
    if df.empty:
        raise ValueError("The uploaded TEC file has no data rows.")

    df.columns = [str(column).strip() for column in df.columns]
    detected = detect_tec_mapping(list(df.columns))
    mapping = {**detected["mapping"], **(mapping or {})}
    missing = [field for field in REQUIRED_FIELDS if not mapping.get(field)]
    if not any(mapping.get(field) for field in ["recipient_name", "filer_name", "committee_name", "candidate_name"]):
        missing.append("recipient_name")
    if missing:
        raise ValueError("TEC import needs mappings for: " + ", ".join(missing))

    records: list[dict] = []
    warnings: list[str] = []
    for index, row in df.where(pd.notna(df), None).iterrows():
        raw = row.to_dict()
        source_record_id = _pick(raw, mapping, "source_record_id")
        generated = False
        if not source_record_id:
            source_record_id = deterministic_source_record_id("TEC", raw)
            generated = True

        record = {
            "source_system": "TEC",
            "source_record_id": str(source_record_id),
            "transaction_id": _pick(raw, mapping, "source_record_id"),
            "transaction_type": _transaction_type(_pick(raw, mapping, "transaction_type")),
            "transaction_date": _pick(raw, mapping, "transaction_date"),
            "amount": _pick(raw, mapping, "amount"),
            "contributor_name": _pick(raw, mapping, "contributor_name"),
            "contributor_entity_name": _pick(raw, mapping, "contributor_entity_name"),
            "contributor_employer": _pick(raw, mapping, "contributor_employer"),
            "contributor_city": _pick(raw, mapping, "contributor_city"),
            "contributor_state": _pick(raw, mapping, "contributor_state"),
            "contributor_zip": _pick(raw, mapping, "contributor_zip"),
            "recipient_name": _pick(raw, mapping, "recipient_name") or _pick(raw, mapping, "filer_name"),
            "recipient_type": "Filer/Committee",
            "filer_id": _pick(raw, mapping, "filer_id"),
            "filer_name": _pick(raw, mapping, "filer_name"),
            "committee_name": _pick(raw, mapping, "committee_name") or _pick(raw, mapping, "recipient_name"),
            "candidate_name": _pick(raw, mapping, "candidate_name"),
            "party": _pick(raw, mapping, "party"),
            "office": _pick(raw, mapping, "office"),
            "district": _pick(raw, mapping, "district"),
            "report_year": _pick(raw, mapping, "report_year"),
            "form_type": _pick(raw, mapping, "form_type"),
            "purpose": _pick(raw, mapping, "purpose"),
            "description": _pick(raw, mapping, "description") or _pick(raw, mapping, "purpose"),
            "source_url": filename,
            "_raw_payload": raw,
            "_generated_source_record_id": generated,
        }
        records.append(record)

    unmapped = [column for column in df.columns if column not in set(value for value in mapping.values() if value)]
    if unmapped:
        warnings.append("Unmapped TEC columns were preserved in raw payload only: " + ", ".join(unmapped[:12]))

    return TECParseResult(
        records=records,
        mapping=mapping,
        confidence=detected["confidence"],
        warnings=warnings,
        columns=list(df.columns),
        preview_rows=df.head(5).where(pd.notna(df), None).to_dict(orient="records"),
    )
