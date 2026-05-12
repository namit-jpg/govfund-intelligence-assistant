from __future__ import annotations

from datetime import date, datetime


def _parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def evaluate_transaction_quality(record: dict, generated_source_record_id: bool = False) -> list[dict]:
    flags: list[dict] = []

    def add(flag_type: str, severity: str, message: str) -> None:
        flags.append({"flag_type": flag_type, "severity": severity, "message": message})

    if record.get("amount") in (None, ""):
        add("missing_amount", "warning", "Transaction amount is missing.")
    else:
        try:
            if float(record.get("amount")) < 0:
                add("negative_amount", "warning", "Transaction amount is negative.")
        except (TypeError, ValueError):
            add("missing_amount", "warning", "Transaction amount could not be parsed.")

    tx_date = _parse_date(record.get("transaction_date"))
    if not tx_date:
        add("missing_transaction_date", "warning", "Transaction date is missing or invalid.")
    elif tx_date > date.today():
        add("future_transaction_date", "error", "Transaction date is in the future.")

    if not (record.get("contributor_name") or record.get("contributor_entity_name") or record.get("contributor_employer")):
        add("missing_contributor", "warning", "Contributor or employer/company signal is missing.")

    if not (record.get("recipient_name") or record.get("committee_name") or record.get("candidate_name") or record.get("filer_name")):
        add("missing_recipient", "warning", "Recipient, committee, candidate, or filer is missing.")

    if not record.get("source_record_id"):
        add("missing_source_record_id", "error", "Source record ID is missing.")

    if generated_source_record_id:
        add(
            "generated_source_record_id",
            "warning",
            "No source record ID was available; a deterministic hash was generated from raw fields.",
        )

    for field in ["source_system", "source_record_id"]:
        if not str(record.get(field) or "").strip():
            add("suspiciously_empty_required_field", "error", f"Required field {field} is empty.")

    return flags
