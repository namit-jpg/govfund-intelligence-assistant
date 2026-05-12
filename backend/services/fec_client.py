from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import requests

BASE_URL = "https://api.open.fec.gov/v1/schedules/schedule_a/"
MAX_OPENFEC_PER_PAGE = 100
RETRY_STATUSES = {429, 500, 502, 503, 504}
logger = logging.getLogger(__name__)


class FECValidationError(ValueError):
    pass


class FECRequestError(RuntimeError):
    pass


@dataclass
class FECFetchResult:
    records: list[dict]
    pages_processed: int
    raw_records_fetched: int
    query: dict
    errors: list[str]


def _parse_date(value: str | date | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value).strip()
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(raw[:10], pattern).date()
            return parsed.strftime("%m/%d/%Y")
        except ValueError:
            continue
    raise ValueError(f"Unsupported FEC date format: {value}")


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _as_list(value: Any) -> list:
    if value in (None, "", []):
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    return [value]


def build_fec_request_params(filters: dict, api_key: str | None = None, last_indexes: dict | None = None) -> dict:
    per_page = int(filters.get("per_page") or MAX_OPENFEC_PER_PAGE)
    per_page = max(1, min(per_page, MAX_OPENFEC_PER_PAGE))

    query: dict[str, Any] = {
        "sort": "-contribution_receipt_date",
        "per_page": per_page,
    }
    if api_key:
        query["api_key"] = api_key

    direct_filters = {
        "contributor_name": "contributor_name",
        "contributor_employer": "contributor_employer",
        "contributor_state": "contributor_state",
        "contributor_city": "contributor_city",
        "committee_id": "committee_id",
        "candidate_id": "candidate_id",
        "min_amount": "min_amount",
        "max_amount": "max_amount",
    }
    for incoming, outgoing in direct_filters.items():
        value = _clean(filters.get(incoming))
        if value is not None:
            query[outgoing] = value

    for field in ["min_date", "max_date"]:
        value = _parse_date(filters.get(field))
        if value:
            query[field] = value

    cycle = filters.get("two_year_transaction_period") or filters.get("cycle")
    cycle_values = _as_list(cycle)
    if cycle_values:
        query["two_year_transaction_period"] = [str(item) for item in cycle_values]

    if last_indexes:
        for key, value in last_indexes.items():
            if value is not None:
                query[key] = value

    return query


def redact_query(query: dict) -> dict:
    return {key: ("[REDACTED]" if key == "api_key" else value) for key, value in query.items()}


def sanitize_fec_error(value: object) -> str:
    text = str(value or "OpenFEC request failed.")
    text = re.sub(r"([?&])api_key=[^&\s]+&?", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"api_key=[^&\s]+", "[REDACTED_API_KEY_PARAM]", text, flags=re.IGNORECASE)
    text = text.replace("?&", "?").replace("&&", "&")
    key = os.getenv("FEC_API_KEY")
    if key:
        text = text.replace(key, "[REDACTED]")
    return text[:1000]


def validate_fec_query(filters: dict) -> None:
    cycle = filters.get("two_year_transaction_period") or filters.get("cycle")
    cycle_values = _as_list(cycle)
    specific_filters = [
        "committee_id",
        "candidate_id",
        "contributor_id",
        "contributor_name",
        "contributor_employer",
    ]
    has_specific_filter = any(_clean(filters.get(field)) for field in specific_filters)
    if len(cycle_values) != 1 and not has_specific_filter:
        raise FECValidationError(
            "OpenFEC requires a single cycle/two-year transaction period unless the query includes a specific "
            "committee, candidate, contributor name, contributor ID, or employer/company signal."
        )


def _request_with_retries(query: dict, timeout: int = 30, max_retries: int = 6) -> dict:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(BASE_URL, params=query, timeout=(10, timeout))
            if response.status_code not in RETRY_STATUSES:
                if not response.ok:
                    detail = response.text[:500]
                    raise FECRequestError(
                        f"OpenFEC returned HTTP {response.status_code}: {sanitize_fec_error(detail)}"
                    )
                return response.json()
            retry_after = response.headers.get("Retry-After")
            sleep_for = float(retry_after) if retry_after else min(30, 2 ** attempt)
            logger.warning("OpenFEC returned %s; retrying in %.1fs", response.status_code, sleep_for)
            time.sleep(sleep_for)
        except requests.RequestException as exc:
            last_error = exc
            sleep_for = min(60, 2 ** attempt)
            logger.warning("OpenFEC request failed (%s); retrying in %.1fs (attempt %s/%s)", exc, sleep_for, attempt + 1, max_retries + 1)
            time.sleep(sleep_for)

    if last_error:
        raise FECRequestError(sanitize_fec_error(last_error))
    raise FECRequestError(f"OpenFEC returned HTTP {response.status_code}.")


def _normalize_fec_row(row: dict) -> dict:
    source_record_id = (
        row.get("sub_id")
        or row.get("transaction_id")
        or row.get("image_number")
        or row.get("file_number")
    )
    committee_name = row.get("committee_name") or row.get("committee", {}).get("name") if isinstance(row.get("committee"), dict) else row.get("committee_name")
    candidate_name = row.get("candidate_name")
    recipient_name = committee_name or candidate_name

    return {
        "source_system": "FEC",
        "source_record_id": str(source_record_id) if source_record_id else None,
        "transaction_id": row.get("transaction_id"),
        "transaction_type": row.get("receipt_type") or row.get("line_number"),
        "transaction_date": row.get("contribution_receipt_date"),
        "amount": row.get("contribution_receipt_amount"),
        "contributor_name": row.get("contributor_name"),
        "contributor_employer": row.get("contributor_employer"),
        "contributor_occupation": row.get("contributor_occupation"),
        "contributor_city": row.get("contributor_city"),
        "contributor_state": row.get("contributor_state"),
        "contributor_zip": row.get("contributor_zip"),
        "committee_id": row.get("committee_id"),
        "recipient_committee_id": row.get("committee_id"),
        "committee_name": committee_name,
        "candidate_id": row.get("candidate_id"),
        "candidate_name": candidate_name,
        "recipient_name": recipient_name,
        "recipient_type": row.get("committee_type_full") or row.get("committee_type") or "Committee",
        "party": row.get("party_full") or row.get("party") or row.get("committee_party"),
        "office": row.get("office") or row.get("candidate_office"),
        "district": row.get("district") or row.get("candidate_district"),
        "cycle": row.get("two_year_transaction_period"),
        "report_year": row.get("report_year"),
        "form_type": row.get("form_type"),
        "memo_text": row.get("memo_text"),
        "description": row.get("receipt_type_full") or row.get("line_number_label"),
        "source_url": BASE_URL,
        "_raw_payload": row,
    }


def fetch_fec_transactions(filters: dict, api_key: str | None = None) -> FECFetchResult:
    api_key = api_key or os.getenv("FEC_API_KEY")
    if not api_key:
        raise RuntimeError("FEC_API_KEY is required for OpenFEC ingestion.")
    validate_fec_query(filters)

    max_records = int(filters.get("max_records") or 5000)
    max_records = max(1, max_records)
    records: list[dict] = []
    errors: list[str] = []
    pages_processed = 0
    last_indexes = None
    seen_cursors: set[str] = set()

    while len(records) < max_records:
        query = build_fec_request_params(filters, api_key=api_key, last_indexes=last_indexes)
        safe_query = redact_query(query)
        data = _request_with_retries(query)
        results = data.get("results") or []
        pages_processed += 1

        for row in results:
            if len(records) >= max_records:
                break
            records.append(_normalize_fec_row(row))

        pagination = data.get("pagination") or {}
        cursor = pagination.get("last_indexes")
        if not results or not cursor:
            break

        cursor_key = repr(sorted(cursor.items()))
        if cursor_key in seen_cursors:
            errors.append("OpenFEC pagination cursor repeated; ingestion stopped to avoid an infinite loop.")
            break
        seen_cursors.add(cursor_key)
        last_indexes = cursor

        logger.info("Fetched OpenFEC page %s with %s rows", pages_processed, len(results))

    return FECFetchResult(
        records=records,
        pages_processed=pages_processed,
        raw_records_fetched=len(records),
        query=redact_query(build_fec_request_params(filters)),
        errors=errors,
    )
