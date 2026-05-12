from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from backend.models import DataQualityFlag, NormalizedTransaction, SourceAuditLog
from backend.services.normalizer import normalize_name
from backend.services.repository import serialize_model


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _topic_labels(row: NormalizedTransaction) -> list[str]:
    try:
        return [item.get("tag") for item in json.loads(row.topic_tags_json or "[]") if item.get("tag")]
    except json.JSONDecodeError:
        return []


def apply_filters(query, filters: dict):
    filters = filters or {}
    if filters.get("q"):
        raw = str(filters["q"]).strip()
        fields = [
            NormalizedTransaction.contributor_name,
            NormalizedTransaction.contributor_employer,
            NormalizedTransaction.contributor_entity_name,
            NormalizedTransaction.recipient_name,
            NormalizedTransaction.committee_name,
            NormalizedTransaction.candidate_name,
            NormalizedTransaction.filer_name,
            NormalizedTransaction.source_record_id,
        ]
        phrase_clause = None
        token_clause = None
        if raw:
            like = f"%{raw}%"
            phrase_clause = or_(*[field.ilike(like) for field in fields])
        tokens = [part for part in raw.split() if len(part) >= 3]
        if len(tokens) > 1:
            token_clause = and_(
                *[
                    or_(*[field.ilike(f"%{token}%") for field in fields])
                    for token in tokens[:5]
                ]
            )
        if phrase_clause is not None and token_clause is not None:
            query = query.filter(or_(phrase_clause, token_clause))
        elif phrase_clause is not None:
            query = query.filter(phrase_clause)
    if filters.get("source_system") and filters["source_system"] != "All":
        query = query.filter(NormalizedTransaction.source_system == filters["source_system"])
    if filters.get("min_amount") not in (None, ""):
        query = query.filter(NormalizedTransaction.amount >= float(filters["min_amount"]))
    if filters.get("max_amount") not in (None, ""):
        query = query.filter(NormalizedTransaction.amount <= float(filters["max_amount"]))
    if filters.get("min_date"):
        query = query.filter(NormalizedTransaction.transaction_date >= _parse_date(filters["min_date"]))
    if filters.get("max_date"):
        query = query.filter(NormalizedTransaction.transaction_date <= _parse_date(filters["max_date"]))
    if filters.get("contributor_name"):
        query = query.filter(NormalizedTransaction.contributor_name.ilike(f"%{filters['contributor_name']}%"))
    if filters.get("contributor_employer"):
        query = query.filter(NormalizedTransaction.contributor_employer.ilike(f"%{filters['contributor_employer']}%"))
    if filters.get("recipient"):
        term = f"%{filters['recipient']}%"
        query = query.filter(
            or_(
                NormalizedTransaction.recipient_name.ilike(term),
                NormalizedTransaction.committee_name.ilike(term),
                NormalizedTransaction.candidate_name.ilike(term),
                NormalizedTransaction.filer_name.ilike(term),
            )
        )
    if filters.get("party"):
        query = query.filter(NormalizedTransaction.party.ilike(f"%{filters['party']}%"))
    if filters.get("state"):
        query = query.filter(NormalizedTransaction.contributor_state == filters["state"])
    if filters.get("city"):
        query = query.filter(NormalizedTransaction.contributor_city.ilike(f"%{filters['city']}%"))
    if filters.get("cycle"):
        query = query.filter(NormalizedTransaction.cycle == str(filters["cycle"]))
    if filters.get("transaction_type"):
        query = query.filter(NormalizedTransaction.transaction_type.ilike(f"%{filters['transaction_type']}%"))
    if filters.get("topic_tag") and filters["topic_tag"] != "All":
        query = query.filter(NormalizedTransaction.topic_tags_json.ilike(f"%{filters['topic_tag']}%"))
    if filters.get("report_month"):
        month = filters["report_month"]
        query = query.filter(NormalizedTransaction.transaction_date >= f"{month}-01")
        query = query.filter(NormalizedTransaction.transaction_date < f"{month}-32")
    return query


def get_filtered_rows(db: Session, filters: dict | None = None, limit: int = 1000):
    return (
        apply_filters(db.query(NormalizedTransaction), filters or {})
        .order_by(NormalizedTransaction.transaction_date.desc().nullslast(), NormalizedTransaction.id.desc())
        .limit(limit)
        .all()
    )


def get_kpis(db: Session, filters: dict | None = None):
    rows = get_filtered_rows(db, filters, limit=100000)
    return _kpis_from_rows(db, rows)


def _kpis_from_rows(db: Session, rows: list[NormalizedTransaction]):
    total = sum(row.amount or 0 for row in rows)
    latest_success = (
        db.query(SourceAuditLog)
        .filter(SourceAuditLog.status == "completed")
        .order_by(SourceAuditLog.completed_at.desc())
        .first()
    )
    latest_audit = db.query(SourceAuditLog).order_by(SourceAuditLog.started_at.desc()).first()
    quality_count = db.query(DataQualityFlag).count()
    return {
        "total_records": len(rows),
        "total_contribution_amount": round(total, 2),
        "fec_records": sum(1 for row in rows if row.source_system == "FEC"),
        "tec_records": sum(1 for row in rows if row.source_system == "TEC"),
        "unique_employer_company_signals": len(
            {row.contributor_employer or row.contributor_entity_name for row in rows if row.contributor_employer or row.contributor_entity_name}
        ),
        "unique_contributors": len({row.contributor_name for row in rows if row.contributor_name}),
        "unique_recipients": len({row.recipient_name for row in rows if row.recipient_name}),
        "last_successful_ingestion": latest_success.completed_at.isoformat() if latest_success and latest_success.completed_at else None,
        "latest_source_audit_status": latest_audit.status if latest_audit else None,
        "data_quality_warning_count": quality_count,
        "total_amount": round(total, 2),
        "transaction_count": len(rows),
        "unique_employers": len({row.contributor_employer for row in rows if row.contributor_employer}),
        "federal_amount": round(sum(row.amount or 0 for row in rows if row.source_system == "FEC"), 2),
        "texas_amount": round(sum(row.amount or 0 for row in rows if row.source_system == "TEC"), 2),
    }


def get_monthly_trend(db: Session, filters: dict | None = None):
    rows = get_filtered_rows(db, filters, limit=100000)
    grouped = defaultdict(lambda: {"total_amount": 0.0, "transaction_count": 0})
    for row in rows:
        if not row.transaction_date:
            continue
        key = (row.transaction_date.strftime("%Y-%m"), row.source_system)
        grouped[key]["total_amount"] += row.amount or 0
        grouped[key]["transaction_count"] += 1
    return [
        {
            "month": month,
            "source_system": source,
            "total_amount": round(values["total_amount"], 2),
            "transaction_count": values["transaction_count"],
        }
        for (month, source), values in sorted(grouped.items())
    ]


def _top_by(rows, attr: str, limit: int = 10):
    grouped = defaultdict(lambda: {"total_amount": 0.0, "transaction_count": 0, "source_systems": set()})
    for row in rows:
        value = getattr(row, attr, None)
        if not value:
            continue
        grouped[value]["total_amount"] += row.amount or 0
        grouped[value]["transaction_count"] += 1
        grouped[value]["source_systems"].add(row.source_system)
    out = []
    for value, stats in grouped.items():
        out.append(
            {
                attr: value,
                "total_amount": round(stats["total_amount"], 2),
                "transaction_count": stats["transaction_count"],
                "source_system": ", ".join(sorted(stats["source_systems"])),
            }
        )
    return sorted(out, key=lambda item: item["total_amount"], reverse=True)[:limit]


def get_top_recipients(db: Session, filters: dict | None = None, limit: int = 10):
    return _top_by(get_filtered_rows(db, filters, limit=100000), "recipient_name", limit)


def get_top_employers(db: Session, filters: dict | None = None, limit: int = 10):
    return _top_employers_from_rows(get_filtered_rows(db, filters, limit=100000), limit)


def _top_employers_from_rows(rows: list[NormalizedTransaction], limit: int = 10):
    grouped = defaultdict(lambda: {"total_amount": 0.0, "transaction_count": 0, "source_systems": set()})
    for row in rows:
        value = row.contributor_employer or row.contributor_entity_name
        if not value:
            continue
        grouped[value]["total_amount"] += row.amount or 0
        grouped[value]["transaction_count"] += 1
        grouped[value]["source_systems"].add(row.source_system)
    return sorted(
        [
            {
                "contributor_employer": value,
                "employer_company_signal": value,
                "total_amount": round(stats["total_amount"], 2),
                "transaction_count": stats["transaction_count"],
                "source_system": ", ".join(sorted(stats["source_systems"])),
            }
            for value, stats in grouped.items()
        ],
        key=lambda item: item["total_amount"],
        reverse=True,
    )[:limit]


def get_source_split(db: Session, filters: dict | None = None):
    rows = get_filtered_rows(db, filters, limit=100000)
    grouped = defaultdict(lambda: {"total_amount": 0.0, "transaction_count": 0})
    for row in rows:
        grouped[row.source_system]["total_amount"] += row.amount or 0
        grouped[row.source_system]["transaction_count"] += 1
    return [
        {"source_system": source, "total_amount": round(values["total_amount"], 2), "transaction_count": values["transaction_count"]}
        for source, values in sorted(grouped.items())
    ]


def get_party_distribution(db: Session, filters: dict | None = None):
    return _top_by(get_filtered_rows(db, filters, limit=100000), "party", 20)


def get_geo_distribution(db: Session, filters: dict | None = None):
    rows = get_filtered_rows(db, filters, limit=100000)
    states = Counter(row.contributor_state for row in rows if row.contributor_state)
    cities = Counter(row.contributor_city for row in rows if row.contributor_city)
    return {
        "states": [{"state": key, "transaction_count": value} for key, value in states.most_common(15)],
        "cities": [{"city": key, "transaction_count": value} for key, value in cities.most_common(15)],
    }


def get_topic_distribution(db: Session, filters: dict | None = None):
    rows = get_filtered_rows(db, filters, limit=100000)
    counts = Counter()
    totals = Counter()
    for row in rows:
        for label in _topic_labels(row):
            counts[label] += 1
            totals[label] += row.amount or 0
    return [
        {"topic_tag": tag, "transaction_count": counts[tag], "total_amount": round(totals[tag], 2)}
        for tag, _ in counts.most_common()
    ]


def get_available_report_months(db: Session):
    rows = db.query(NormalizedTransaction.transaction_date).filter(NormalizedTransaction.transaction_date.is_not(None)).all()
    return sorted({row[0].strftime("%Y-%m") for row in rows if row[0]}, reverse=True)


def get_recent_high_value_records(db: Session, filters: dict | None = None, limit: int = 10):
    rows = (
        apply_filters(db.query(NormalizedTransaction), filters or {})
        .order_by(NormalizedTransaction.amount.desc().nullslast(), NormalizedTransaction.transaction_date.desc().nullslast())
        .limit(limit)
        .all()
    )
    return [serialize_model(row) for row in rows]


def build_overview(db: Session):
    rows = get_filtered_rows(db, {}, limit=100000)
    source_split = defaultdict(lambda: {"total_amount": 0.0, "transaction_count": 0})
    monthly = defaultdict(lambda: {"total_amount": 0.0, "transaction_count": 0})
    states = Counter()
    cities = Counter()
    topics = Counter()
    topic_totals = Counter()

    for row in rows:
        amount = row.amount or 0
        source_split[row.source_system]["total_amount"] += amount
        source_split[row.source_system]["transaction_count"] += 1
        if row.transaction_date:
            key = (row.transaction_date.strftime("%Y-%m"), row.source_system)
            monthly[key]["total_amount"] += amount
            monthly[key]["transaction_count"] += 1
        if row.contributor_state:
            states[row.contributor_state] += 1
        if row.contributor_city:
            cities[row.contributor_city] += 1
        for label in _topic_labels(row):
            topics[label] += 1
            topic_totals[label] += amount

    return {
        "kpis": _kpis_from_rows(db, rows),
        "monthly_trend": [
            {
                "month": month,
                "source_system": source,
                "total_amount": round(values["total_amount"], 2),
                "transaction_count": values["transaction_count"],
            }
            for (month, source), values in sorted(monthly.items())
        ],
        "source_split": [
            {"source_system": source, "total_amount": round(values["total_amount"], 2), "transaction_count": values["transaction_count"]}
            for source, values in sorted(source_split.items())
        ],
        "top_employers": _top_employers_from_rows(rows, 25),
        "top_recipients": _top_by(rows, "recipient_name", 25),
        "party_distribution": _top_by(rows, "party", 20),
        "topic_distribution": [
            {"topic_tag": tag, "transaction_count": topics[tag], "total_amount": round(topic_totals[tag], 2)}
            for tag, _ in topics.most_common()
        ],
        "geo_distribution": {
            "states": [{"state": key, "transaction_count": value} for key, value in states.most_common(15)],
            "cities": [{"city": key, "transaction_count": value} for key, value in cities.most_common(15)],
        },
        "recent_high_value": [
            serialize_model(row)
            for row in sorted(rows, key=lambda item: (item.amount or 0, item.transaction_date or date.min), reverse=True)[:25]
        ],
    }


def build_monthly_executive_report(db: Session, report_month: str | None = None):
    report_month = report_month or (get_available_report_months(db)[0] if get_available_report_months(db) else None)
    filters = {"report_month": report_month} if report_month else {}
    kpis = get_kpis(db, filters)
    top_recipients = get_top_recipients(db, filters, 3)
    top_employers = get_top_employers(db, filters, 3)
    source_split = get_source_split(db, filters)

    if not report_month:
        return {
            "report_month": None,
            "headline": "No reportable real activity is available yet.",
            "summary": "Ingest OpenFEC records or import official TEC CSV/XLSX files to generate a deterministic monthly report.",
            "highlights": [],
            "risks": ["No records are currently available in the selected dataset."],
            "recommended_actions": ["Configure FEC_API_KEY or import official TEC data."],
            "compliance_note": "Reports are limited to source-backed public records and cautious interpretation.",
        }

    highlights = [
        f"{kpis['transaction_count']} records totaling ${kpis['total_amount']:,.0f} were captured in {report_month}.",
        f"Top recipient: {top_recipients[0]['recipient_name'] if top_recipients else 'not available'}.",
        f"Top employer/company signal: {top_employers[0]['employer_company_signal'] if top_employers else 'not available'}.",
    ]
    risks = [
        "FEC employer fields identify employer names reported by individual contributors, not direct corporate donations.",
        "Public-record activity can lag reporting deadlines and source updates.",
        "Topic tags are deterministic keyword signals and should be reviewed before external circulation.",
    ]
    return {
        "report_month": report_month,
        "headline": f"Source-backed contribution activity for {report_month}",
        "summary": (
            f"The current dataset contains ${kpis['total_amount']:,.0f} across {kpis['transaction_count']} records for {report_month}, "
            f"covering {kpis['unique_recipients']} recipients and {kpis['unique_employer_company_signals']} employer/company signals."
        ),
        "highlights": highlights,
        "risks": risks,
        "recommended_actions": [
            "Review source evidence for high-value or infrastructure-adjacent records.",
            "Export filtered records for counsel or client review.",
            "Run narrower ingestion filters where coverage gaps are suspected.",
        ],
        "top_recipients": top_recipients,
        "top_employers": top_employers,
        "source_split": source_split,
        "compliance_note": "No wrongdoing, donor intent, or direct corporate contribution is inferred.",
    }


def company_dossier(db: Session, employer: str):
    rows = [row for row in get_filtered_rows(db, {}, 100000) if normalize_name(row.contributor_employer or row.contributor_entity_name or "") == normalize_name(employer)]
    filters = {"contributor_employer": employer}
    return {
        "name": employer,
        "kpis": {
            "matched_records": len(rows),
            "total_amount": round(sum(row.amount or 0 for row in rows), 2),
            "unique_contributors": len({row.contributor_name for row in rows if row.contributor_name}),
            "unique_recipients": len({row.recipient_name for row in rows if row.recipient_name}),
            "date_range": [
                min((row.transaction_date for row in rows if row.transaction_date), default=None),
                max((row.transaction_date for row in rows if row.transaction_date), default=None),
            ],
        },
        "source_split": get_source_split(db, filters),
        "monthly_timeline": get_monthly_trend(db, filters),
        "top_recipients": get_top_recipients(db, filters, 10),
        "party_distribution": get_party_distribution(db, filters),
        "topic_distribution": get_topic_distribution(db, filters),
        "top_contributors": _top_by(rows, "contributor_name", 10),
        "high_value_records": [serialize_model(row) for row in sorted(rows, key=lambda item: item.amount or 0, reverse=True)[:25]],
        "recent_records": [serialize_model(row) for row in sorted(rows, key=lambda item: item.transaction_date or date.min, reverse=True)[:25]],
    }


def recipient_dossier(db: Session, recipient: str):
    rows = [
        row
        for row in get_filtered_rows(db, {}, 100000)
        if normalize_name(row.recipient_name or row.committee_name or row.candidate_name or row.filer_name or "") == normalize_name(recipient)
    ]
    filters = {"recipient": recipient}
    return {
        "name": recipient,
        "kpis": {
            "matched_records": len(rows),
            "total_amount": round(sum(row.amount or 0 for row in rows), 2),
            "unique_contributors": len({row.contributor_name for row in rows if row.contributor_name}),
            "unique_employer_company_signals": len({row.contributor_employer or row.contributor_entity_name for row in rows if row.contributor_employer or row.contributor_entity_name}),
            "party": next((row.party for row in rows if row.party), None),
            "office": next((row.office for row in rows if row.office), None),
            "district": next((row.district for row in rows if row.district), None),
        },
        "monthly_timeline": get_monthly_trend(db, filters),
        "top_employers": get_top_employers(db, filters, 10),
        "top_contributors": _top_by(rows, "contributor_name", 10),
        "topic_distribution": get_topic_distribution(db, filters),
        "source_evidence": [serialize_model(row) for row in sorted(rows, key=lambda item: item.transaction_date or date.min, reverse=True)[:50]],
    }


def network_data(db: Session, filters: dict | None = None, max_nodes: int = 40):
    rows = get_filtered_rows(db, filters, limit=5000)
    links = Counter()
    node_totals = Counter()
    for row in rows:
        signal = row.contributor_employer or row.contributor_entity_name
        contributor = row.contributor_name
        recipient = row.recipient_name or row.committee_name or row.candidate_name or row.filer_name
        topics = _topic_labels(row)[:2] or ["Unknown"]
        amount = float(row.amount or 0)
        if signal and contributor:
            links[(f"Signal: {signal}", f"Contributor: {contributor}")] += amount
            node_totals[f"Signal: {signal}"] += amount
            node_totals[f"Contributor: {contributor}"] += amount
        if contributor and recipient:
            links[(f"Contributor: {contributor}", f"Recipient: {recipient}")] += amount
            node_totals[f"Recipient: {recipient}"] += amount
        for topic in topics:
            if recipient:
                links[(f"Recipient: {recipient}", f"Topic: {topic}")] += amount
                node_totals[f"Topic: {topic}"] += amount

    allowed_nodes = {node for node, _ in node_totals.most_common(max_nodes)}
    labels = sorted(allowed_nodes)
    index = {label: i for i, label in enumerate(labels)}
    filtered_links = [
        {"source": index[src], "target": index[dst], "value": round(value, 2), "source_label": src, "target_label": dst}
        for (src, dst), value in links.items()
        if src in index and dst in index and value > 0
    ]
    return {"nodes": labels, "links": filtered_links}
