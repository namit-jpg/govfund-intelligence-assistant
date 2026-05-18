from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime

import requests
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.models import FECQueryRun, InsightRun, NormalizedTransaction, Watchlist, WatchlistRun
from backend.services.analytics_service import (
    get_kpis,
    get_recent_high_value_records,
    get_source_split,
    get_top_employers,
    get_top_recipients,
    get_topic_distribution,
)
from backend.services.compliance_guard import check_question
from backend.services.repository import to_json
from backend.services.tracker_service import linked_watchlist_transactions, run_watchlist, serialize_watchlist

FOOTER = (
    "This summary is based on public campaign finance records. It is for research and transparency only. "
    "It does not infer donor intent, wrongdoing, bribery, pay-to-play activity, or direct corporate donations."
)

BRIEF_SECTIONS = [
    "Direct Answer",
    "Tracked Dataset Evidence",
    "Live OpenFEC Lookup",
    "Public Web Context",
    "Strategic Interpretation",
    "Coverage Limitations",
    "Recommended Next Research Steps",
]

STOP_TERMS = {
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "has",
    "have",
    "had",
    "donated",
    "donation",
    "donations",
    "contributed",
    "contribution",
    "contributions",
    "to",
    "from",
    "for",
    "in",
    "by",
    "the",
    "and",
    "or",
    "fec",
    "pac",
    "committee",
    "committees",
    "legislator",
    "legislators",
    "business",
    "businesses",
    "employer",
    "company",
    "compare",
    "comparison",
    "signal",
    "signals",
    "current",
    "record",
    "records",
    "data",
    "information",
    "show",
    "tell",
    "summarize",
    "summary",
    "pattern",
    "patterns",
    "explain",
    "explains",
    "matter",
    "matters",
    "why",
}

WEB_CONTEXT_TIMEOUT = 40
WEB_CONTEXT_MAX_CHARS = 12000


def ai_status() -> dict:
    configured = bool(os.getenv("OPENAI_API_KEY"))
    return {
        "enabled": configured,
        "web_context_enabled": configured,
        "message": (
            "OpenAI-backed briefing is configured."
            if configured
            else "AI is not configured. Add OPENAI_API_KEY to enable AI briefing."
        ),
    }


def _question_terms(question: str) -> list[str]:
    protected_phrases = re.findall(r'"([^"]+)"', question or "")
    proper_phrases = re.findall(r"\b[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4}\b", question or "")
    words = re.findall(r"[A-Za-z][A-Za-z.'-]{2,}", question or "")
    terms = []
    for value in protected_phrases + proper_phrases + words:
        cleaned_parts = [
            part.strip(" ?.,:;!")
            for part in value.strip(" ?.,:;!").split()
            if part.strip(" ?.,:;!").lower() not in STOP_TERMS
        ]
        cleaned = " ".join(cleaned_parts)
        if not cleaned or cleaned.lower() in STOP_TERMS or cleaned.isdigit():
            continue
        if cleaned.lower() not in {item.lower() for item in terms}:
            terms.append(cleaned)
    return terms[:8]


def _question_years(question: str) -> list[str]:
    return sorted(set(re.findall(r"\b20\d{2}\b", question or "")))


def infer_filters_from_question(question: str) -> dict:
    lower = (question or "").lower()
    filters: dict = {"source_system": "FEC"}
    years = _question_years(question)
    if years:
        filters["cycle"] = years[-1]
    terms = _question_terms(question)
    if terms:
        filters["question_terms"] = terms
    if any(word in lower for word in ["recipient", "received", "gets donation", "got donation", "donated to", "to "]):
        filters["question_focus"] = "recipient"
    elif any(word in lower for word in ["employer", "business", "company", "competitor"]):
        filters["question_focus"] = "employer"
    else:
        filters["question_focus"] = "general"
    return filters


def _rows_for_question(db: Session, question: str, filters: dict | None = None, limit: int = 250) -> tuple[list[NormalizedTransaction], dict]:
    inferred = infer_filters_from_question(question)
    merged = {**inferred, **(filters or {})}
    query = db.query(NormalizedTransaction)
    if merged.get("source_system") and merged["source_system"] != "All":
        query = query.filter(NormalizedTransaction.source_system == merged["source_system"])
    if merged.get("cycle"):
        query = query.filter(NormalizedTransaction.cycle == str(merged["cycle"]))
    if merged.get("question_terms"):
        fields = [
            NormalizedTransaction.contributor_name,
            NormalizedTransaction.contributor_employer,
            NormalizedTransaction.contributor_entity_name,
            NormalizedTransaction.recipient_name,
            NormalizedTransaction.committee_name,
            NormalizedTransaction.candidate_name,
            NormalizedTransaction.filer_name,
        ]
        phrase_terms = [term for term in merged["question_terms"] if " " in term]
        single_terms = [term for term in merged["question_terms"] if " " not in term]
        clauses = []
        for term in phrase_terms[:3]:
            clauses.append(or_(*[field.ilike(f"%{term}%") for field in fields]))
            tokens = [part for part in term.split() if len(part) >= 3]
            if len(tokens) > 1:
                clauses.append(and_(*[or_(*[field.ilike(f"%{token}%") for field in fields]) for token in tokens]))
        if not clauses:
            for term in single_terms[:5]:
                clauses.append(or_(*[field.ilike(f"%{term}%") for field in fields]))
        query = query.filter(or_(*clauses))
    rows = (
        query.order_by(NormalizedTransaction.transaction_date.desc().nullslast(), NormalizedTransaction.amount.desc().nullslast())
        .limit(limit)
        .all()
    )
    return rows, merged


def _facts_from_rows(rows: list[NormalizedTransaction], context: dict) -> dict:
    total_amount = sum(row.amount or 0 for row in rows)
    monthly = defaultdict(lambda: {"amount": 0.0, "count": 0})
    contributors = Counter()
    contributor_amounts = Counter()
    employers = Counter()
    employer_amounts = Counter()
    recipients = Counter()
    recipient_amounts = Counter()
    parties = Counter()
    states = Counter()
    topics = Counter()
    future_dates = []
    for row in rows:
        if row.transaction_date:
            key = row.transaction_date.strftime("%Y-%m")
            monthly[key]["amount"] += row.amount or 0
            monthly[key]["count"] += 1
            if row.transaction_date > date.today():
                future_dates.append(row.transaction_date.isoformat())
        if row.contributor_name:
            contributors[row.contributor_name] += 1
            contributor_amounts[row.contributor_name] += row.amount or 0
        if row.contributor_employer:
            employers[row.contributor_employer] += 1
            employer_amounts[row.contributor_employer] += row.amount or 0
        if row.recipient_name:
            recipients[row.recipient_name] += 1
            recipient_amounts[row.recipient_name] += row.amount or 0
        if row.party:
            parties[row.party] += 1
        if row.contributor_state:
            states[row.contributor_state] += 1
        try:
            for item in json.loads(row.topic_tags_json or "[]"):
                if item.get("tag"):
                    topics[item["tag"]] += 1
        except json.JSONDecodeError:
            pass
    evidence = [
        {
            "source_record_id": row.source_record_id,
            "date": row.transaction_date.isoformat() if row.transaction_date else None,
            "amount": row.amount,
            "contributor": row.contributor_name,
            "employer_company_signal": row.contributor_employer or row.contributor_entity_name,
            "recipient": row.recipient_name or row.committee_name or row.candidate_name,
            "committee": row.committee_name,
            "party": row.party,
            "cycle": row.cycle,
        }
        for row in sorted(rows, key=lambda item: abs(item.amount or 0), reverse=True)[:30]
    ]
    return {
        "context": context,
        "matching_record_count": len(rows),
        "total_amount": round(total_amount, 2),
        "monthly": [
            {"month": month, "amount": round(values["amount"], 2), "count": values["count"]}
            for month, values in sorted(monthly.items())
        ],
        "top_contributors": [
            {"name": name, "count": contributors[name], "amount": round(contributor_amounts[name], 2)}
            for name, _ in contributor_amounts.most_common(15)
        ],
        "top_employer_company_signals": [
            {"name": name, "count": employers[name], "amount": round(employer_amounts[name], 2)}
            for name, _ in employer_amounts.most_common(15)
        ],
        "top_recipients": [
            {"name": name, "count": recipients[name], "amount": round(recipient_amounts[name], 2)}
            for name, _ in recipient_amounts.most_common(15)
        ],
        "party_distribution": dict(parties.most_common(12)),
        "state_distribution": dict(states.most_common(12)),
        "topic_distribution": dict(topics.most_common(12)),
        "future_transaction_dates_in_matches": sorted(set(future_dates))[:20],
        "evidence_sample_records": evidence,
        "caveat": "FEC employer fields are employer/company signals reported by individual contributors; they are not proof of direct corporate donations.",
    }


def build_deterministic_facts(db: Session, filters: dict) -> dict:
    if filters.get("watchlist_id"):
        facts = build_watchlist_facts(db, int(filters["watchlist_id"]))
        if facts:
            return facts
    if filters.get("fec_query_run_id"):
        run = db.query(FECQueryRun).filter(FECQueryRun.id == int(filters["fec_query_run_id"])).one_or_none()
        if run:
            ids = []
            try:
                ids = [int(value) for value in json.loads(run.normalized_transaction_ids_json or "[]") if value]
            except (TypeError, ValueError, json.JSONDecodeError):
                ids = []
            rows = []
            if ids:
                rows = db.query(NormalizedTransaction).filter(NormalizedTransaction.id.in_(ids)).all()
            total_amount = sum(row.amount or 0 for row in rows)
            monthly = defaultdict(lambda: {"amount": 0.0, "count": 0})
            employers = Counter()
            employer_amounts = Counter()
            recipients = Counter()
            recipient_amounts = Counter()
            parties = Counter()
            states = Counter()
            topics = Counter()
            for row in rows:
                if row.transaction_date:
                    key = row.transaction_date.strftime("%Y-%m")
                    monthly[key]["amount"] += row.amount or 0
                    monthly[key]["count"] += 1
                if row.contributor_employer:
                    employers[row.contributor_employer] += 1
                    employer_amounts[row.contributor_employer] += row.amount or 0
                if row.recipient_name:
                    recipients[row.recipient_name] += 1
                    recipient_amounts[row.recipient_name] += row.amount or 0
                if row.party:
                    parties[row.party] += 1
                if row.contributor_state:
                    states[row.contributor_state] += 1
                try:
                    for item in json.loads(row.topic_tags_json or "[]"):
                        if item.get("tag"):
                            topics[item["tag"]] += 1
                except json.JSONDecodeError:
                    pass
            evidence = [
                {
                    "source_record_id": row.source_record_id,
                    "date": row.transaction_date.isoformat() if row.transaction_date else None,
                    "amount": row.amount,
                    "employer_company_signal": row.contributor_employer,
                    "contributor": row.contributor_name,
                    "recipient": row.recipient_name,
                    "party": row.party,
                }
                for row in sorted(rows, key=lambda item: item.amount or 0, reverse=True)[:20]
            ]
            return {
                "fec_query_run_id": run.id,
                "query": json.loads(run.query_json or "{}"),
                "status": run.status,
                "pages_processed": run.pages_processed,
                "raw_records_fetched": run.raw_records_fetched,
                "inserted_count": run.inserted_count,
                "duplicate_count": run.duplicate_count,
                "record_count_in_snapshot": run.raw_records_fetched,
                "normalized_records_available": len(rows),
                "total_amount": round(total_amount, 2),
                "monthly": [
                    {"month": month, "amount": round(values["amount"], 2), "count": values["count"]}
                    for month, values in sorted(monthly.items())
                ],
                "top_employer_company_signals": [
                    {"name": name, "count": employers[name], "amount": round(employer_amounts[name], 2)}
                    for name, _ in employer_amounts.most_common(15)
                ],
                "top_recipients": [
                    {"name": name, "count": recipients[name], "amount": round(recipient_amounts[name], 2)}
                    for name, _ in recipient_amounts.most_common(15)
                ],
                "party_distribution": dict(parties.most_common(12)),
                "state_distribution": dict(states.most_common(12)),
                "topic_distribution": dict(topics.most_common(12)),
                "evidence_sample_high_value_records": evidence,
                "caveat": "FEC employer fields are employer/company signals reported by individual contributors; they are not proof of direct corporate donations.",
            }
    return {
        "kpis": get_kpis(db, filters),
        "source_split": get_source_split(db, filters),
        "top_recipients": get_top_recipients(db, filters, 10),
        "top_employer_company_signals": get_top_employers(db, filters, 10),
        "topic_distribution": get_topic_distribution(db, filters),
        "high_value_records": get_recent_high_value_records(db, filters, 25),
        "caveat": "FEC employer fields are employer/company signals reported by individual contributors; they are not proof of direct corporate donations.",
    }


def build_watchlist_facts(db: Session, watchlist_id: int) -> dict | None:
    watchlist = db.query(Watchlist).filter(Watchlist.id == watchlist_id).one_or_none()
    if not watchlist:
        return None
    rows = linked_watchlist_transactions(db, watchlist_id)
    latest_run = (
        db.query(WatchlistRun)
        .filter(WatchlistRun.watchlist_id == watchlist_id)
        .order_by(WatchlistRun.started_at.desc())
        .first()
    )
    facts = _facts_from_rows(
        rows,
        {
            "watchlist_id": watchlist_id,
            "watchlist_name": watchlist.name,
            "selection_method": "tracked_watchlist_records",
        },
    )
    facts["selection_method"] = "tracked_watchlist_records"
    facts["watchlist"] = serialize_watchlist(db, watchlist)
    facts["latest_tracker_run"] = {
        "id": latest_run.id,
        "status": latest_run.status,
        "run_type": latest_run.run_type,
        "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
        "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
        "raw_records_fetched": latest_run.raw_records_fetched,
        "inserted_count": latest_run.inserted_count,
        "duplicate_count": latest_run.duplicate_count,
        "matched_count": latest_run.matched_count,
        "error_message": latest_run.error_message,
    } if latest_run else None
    facts["tracker_evidence_label"] = "Based on tracked records linked to this monitoring list."
    return facts


def build_question_facts(db: Session, question: str, filters: dict | None = None) -> dict:
    filters = filters or {}
    if filters.get("watchlist_id"):
        facts = build_watchlist_facts(db, int(filters["watchlist_id"])) or {}
        facts["question"] = question
        facts["selection_method"] = "tracked_watchlist_records"
        return facts
    if filters.get("fec_query_run_id"):
        facts = build_deterministic_facts(db, filters)
        facts["question"] = question
        facts["selection_method"] = "selected_fec_snapshot"
        return facts
    rows, context = _rows_for_question(db, question, filters)
    facts = _facts_from_rows(rows, context)
    facts["question"] = question
    facts["selection_method"] = "question_inferred_local_fec_search"
    if not rows:
        facts["coverage_note"] = (
            "No matching local ingested FEC records were found for the inferred terms. "
            "No matching local ingested contribution records were found for the inferred terms. "
            "Web/news context may still help identify aliases, offices, committees, and next searches, but it is not contribution evidence."
        )
        facts["suggested_next_data_pull"] = {
            "source": "OpenFEC Schedule A",
            "cycle": facts["context"].get("cycle"),
            "search_terms": facts["context"].get("question_terms", []),
            "recommended_filters": "Use candidate/committee/recipient-specific OpenFEC identifiers when available; otherwise run a narrowed recipient or committee search and review aliases.",
        }
    return facts


def _safe_live_fec_query_from_question(question: str, facts: dict) -> dict | None:
    context = facts.get("context") or infer_filters_from_question(question)
    terms = context.get("question_terms") or []
    if not terms:
        return None
    query = {"source_system": "FEC", "per_page": 100, "max_records": 100}
    if context.get("cycle"):
        query["two_year_transaction_period"] = str(context["cycle"])
    focus = context.get("question_focus")
    first = terms[0]
    if first.upper().startswith("C"):
        query["committee_id"] = first
    elif first[:1].isalpha() and first[1:].isdigit():
        query["candidate_id"] = first
    elif focus == "employer":
        query["contributor_employer"] = first
    else:
        return None
    return {key: value for key, value in query.items() if value not in (None, "", "All")}


def _live_fec_fallback(db: Session, question: str, facts: dict) -> dict:
    if not os.getenv("FEC_API_KEY"):
        return {"status": "skipped", "reason": "FEC_API_KEY is not configured."}
    query = _safe_live_fec_query_from_question(question, facts)
    if not query:
        return {
            "status": "skipped",
            "reason": "No safe committee ID, candidate ID, or employer/company signal could be inferred for a constrained OpenFEC lookup.",
        }
    from backend.models import SourceAuditLog
    from backend.services.fec_client import fetch_fec_transactions, redact_query, build_fec_request_params, sanitize_fec_error
    from backend.services.repository import insert_records

    audit = SourceAuditLog(
        source_system="FEC",
        operation_type="ai_live_fec_lookup",
        query_json=to_json(query),
        status="running",
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    try:
        fetched = fetch_fec_transactions(query)
        inserted = insert_records(db, "FEC", fetched.records, source_url="https://api.open.fec.gov/v1/schedules/schedule_a/")
        audit.status = "completed" if not fetched.errors and not inserted.get("errors") else "partial"
        audit.completed_at = datetime.utcnow()
        audit.pages_processed = fetched.pages_processed
        audit.raw_records_fetched = fetched.raw_records_fetched
        audit.inserted_count = inserted.get("inserted_count", 0)
        audit.duplicate_count = inserted.get("duplicate_count", 0)
        errors = [sanitize_fec_error(error) for error in (fetched.errors + inserted.get("errors", []))]
        audit.error_message = "; ".join(errors[:5]) if errors else None
        run = FECQueryRun(
            audit_log_id=audit.id,
            query_json=to_json(query),
            request_metadata_json=to_json({"endpoint": "schedule_a", "request_params": redact_query(build_fec_request_params(query))}),
            result_json=to_json({"query": query, "records": fetched.records, "errors": errors[:10]}),
            normalized_transaction_ids_json=to_json(inserted.get("transaction_ids", [])),
            status=audit.status,
            pages_processed=fetched.pages_processed,
            raw_records_fetched=fetched.raw_records_fetched,
            inserted_count=inserted.get("inserted_count", 0),
            duplicate_count=inserted.get("duplicate_count", 0),
            error_message=audit.error_message,
            completed_at=datetime.utcnow(),
        )
        db.add(audit)
        db.add(run)
        db.commit()
        return {
            "status": audit.status,
            "query": redact_query(build_fec_request_params(query)),
            "fec_query_run_id": run.id,
            "pages_processed": fetched.pages_processed,
            "raw_records_fetched": fetched.raw_records_fetched,
            "inserted_count": inserted.get("inserted_count", 0),
            "duplicate_count": inserted.get("duplicate_count", 0),
            "errors": errors[:5],
        }
    except Exception as exc:
        audit.status = "failed"
        audit.completed_at = datetime.utcnow()
        audit.error_message = sanitize_fec_error(exc)
        db.add(audit)
        db.commit()
        return {"status": "failed", "query": query, "error": audit.error_message}


def _extract_response_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    parts = []
    for item in payload.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []) or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(str(content["text"]))
    return "\n".join(parts).strip()


def _extract_web_citations(payload: dict) -> list[dict]:
    citations: list[dict] = []
    for item in payload.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []) or []:
            for annotation in content.get("annotations", []) or []:
                if annotation.get("type") == "url_citation":
                    citations.append(
                        {
                            "title": annotation.get("title"),
                            "url": annotation.get("url"),
                        }
                    )
    for source in payload.get("sources", []) or []:
        if source.get("url"):
            citations.append({"title": source.get("title"), "url": source.get("url")})
    seen = set()
    unique = []
    for citation in citations:
        url = citation.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(citation)
    return unique[:10]


def build_web_context(question: str, facts: dict) -> dict:
    if not os.getenv("OPENAI_API_KEY"):
        return {"enabled": False, "status": "disabled", "summary": "", "citations": []}
    terms = facts.get("context", {}).get("question_terms") or []
    evidence_count = facts.get("matching_record_count") or facts.get("normalized_records_available") or 0
    prompt = (
        "Search the web for recent, reputable public context that could make the answer more insightful. "
        "Prioritize independent news coverage, local political reporting, campaign-finance trackers, watchdog/nonprofit sources, public-record explainers, and official government records. "
        "Useful examples include OpenSecrets, FollowTheMoney, Ballotpedia, FEC pages, state ethics portals, reputable local news, national political news, and public affairs reporting. "
        "Avoid relying primarily on company websites, campaign marketing pages, press releases, or generic corporate bios unless they are needed only to identify an entity. "
        "Do not claim any contribution happened unless it appears in the provided local FEC/TEC facts. "
        "Clearly separate public background context from verified contribution facts, but include useful strategic context: office sought, public profile, policy areas, industry relevance, controversies if reported by reputable sources, and likely aliases/committees to search next. "
        "Focus on the named people, companies, PACs, committees, offices, and policy topics in the question. "
        "Return a detailed context memo with citations, not a short answer. Prefer third-party and public-record citations over self-published company/campaign pages. Do not make accusations.\n\n"
        f"Question: {question}\n"
        f"Extracted local-data terms: {json.dumps(terms)}\n"
        f"Local matching record count: {evidence_count}\n"
        f"Local top recipients: {json.dumps(facts.get('top_recipients', [])[:5], default=str)}\n"
        f"Local top employer/company signals: {json.dumps(facts.get('top_employer_company_signals', [])[:5], default=str)}"
    )
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                "Content-Type": "application/json",
            },
            json={
                "model": os.getenv("OPENAI_WEB_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")),
                "tools": [{"type": os.getenv("OPENAI_WEB_SEARCH_TOOL", "web_search")}],
                "tool_choice": "auto",
                "input": prompt,
            },
            timeout=WEB_CONTEXT_TIMEOUT,
        )
        if not response.ok:
            return {
                "enabled": True,
                "status": "error",
                "summary": "",
                "citations": [],
                "error": f"Web context failed with HTTP {response.status_code}.",
            }
        payload = response.json()
        return {
            "enabled": True,
            "status": "ok",
            "summary": _extract_response_text(payload)[:WEB_CONTEXT_MAX_CHARS],
            "citations": _extract_web_citations(payload),
        }
    except Exception as exc:
        return {"enabled": True, "status": "error", "summary": "", "citations": [], "error": str(exc)}


def _disabled_response() -> dict:
    return {
        "enabled": False,
        "mode": "disabled",
        "message": "AI is not configured. Add OPENAI_API_KEY to enable AI briefing.",
        "output_text": "",
        "facts": [],
        "compliance_footer": FOOTER,
    }


def _store_run(db: Session, insight_type: str, filters: dict, output_text: str, facts: dict, model_name: str | None) -> None:
    source_ids = [
        row.get("source_record_id")
        for row in facts.get("high_value_records", []) + facts.get("evidence_sample_records", []) + facts.get("evidence_sample_high_value_records", [])
        if row.get("source_record_id")
    ]
    db.add(
        InsightRun(
            insight_type=insight_type,
            input_json=to_json({"filters": filters}),
            output_text=output_text,
            source_record_ids_json=to_json(source_ids),
            model_name=model_name,
        )
    )
    db.commit()


def _chat_completion_options(model_name: str, messages: list[dict]) -> dict:
    options = {
        "model": model_name,
        "messages": messages,
    }
    if not model_name.lower().startswith("gpt-5"):
        options["temperature"] = 0.05
    return options


def generate_brief(db: Session, question: str, filters: dict, insight_type: str = "custom_question") -> dict:
    guard = check_question(question)
    if not guard["allowed"]:
        return {
            "enabled": True,
            "mode": "compliance_block",
            "message": guard["safe_alternative"],
            "output_text": guard["safe_alternative"],
            "facts": [],
            "compliance_footer": FOOTER,
        }

    if not os.getenv("OPENAI_API_KEY"):
        return _disabled_response()

    filters = filters or {}
    include_web_context = bool(filters.pop("include_web_context", True))
    facts = build_question_facts(db, question, filters)
    live_fec_lookup = {"status": "not_needed"}
    evidence_count = facts.get("matching_record_count") or facts.get("normalized_records_available") or 0
    if filters.get("watchlist_id") and not evidence_count:
        try:
            live_fec_lookup = {
                "status": "tracker_refresh",
                "result": run_watchlist(db, int(filters["watchlist_id"]), run_type="ai_fallback", live=True),
            }
            facts = build_question_facts(db, question, filters)
            evidence_count = facts.get("matching_record_count") or facts.get("normalized_records_available") or 0
        except Exception as exc:
            live_fec_lookup = {"status": "tracker_refresh_failed", "error": str(exc)}
    if not evidence_count:
        live_fec_lookup = _live_fec_fallback(db, question, facts)
        if live_fec_lookup.get("status") in {"completed", "partial"}:
            facts = build_question_facts(db, question, filters)
    facts["live_fec_lookup"] = live_fec_lookup
    web_context = build_web_context(question, facts) if include_web_context else {"enabled": False, "status": "not_requested", "summary": "", "citations": []}
    facts["web_context"] = web_context
    try:
        from openai import OpenAI

        model_name = os.getenv("OPENAI_MODEL", "gpt-5-mini")
        client = OpenAI()
        prompt = {
            "role": "user",
            "content": (
                "Answer like a sharp campaign-finance intelligence analyst, not a database narrator. "
                "Use local public-record facts for donation/transaction claims. "
                "If facts.selection_method is tracked_watchlist_records, lead with 'Based on tracked records' and explain the tracker run date/counts. "
                "Use web_context for broader strategic context, entity background, issue relevance, likely aliases, committees, offices, and next research angles. "
                "Use facts.live_fec_lookup to explain whether a live OpenFEC lookup was attempted, completed, skipped, or failed. "
                "Do not treat web/news context as verified contribution evidence, but do use it to make the analysis more insightful. "
                "Start with a direct answer. If local contribution facts do not answer the question, say that clearly, then use web context to explain what is known publicly and what exact data pull would close the gap. "
                "Use source_record_id values as evidence references when discussing specific records. "
                "Do not invent records, use general model knowledge as evidence, or infer donor intent. "
                "Do not allege bribery, corruption, pay-to-play, illegality, or direct corporate donations unless a provided source explicitly proves that. "
                "When FEC employer fields are relevant, call them employer/company signals reported by individual contributors. "
                "Be substantially more verbose than a short summary. Write a client-ready analyst memo, roughly 900-1,500 words when enough facts/context exist. "
                "Each section should contain multiple detailed bullets or short paragraphs, not one-line observations. "
                "For each major claim, explain: what was observed, why it may matter, what source or record supports it, and what uncertainty remains. "
                "Use named entities, amounts, dates/months, source IDs, local record counts, industry context, public-policy relevance, and concrete next research steps. "
                "Make comparisons where possible: who appears more active, which recipients recur, whether activity is concentrated or diffuse, whether the timing looks clustered, and whether the pattern is likely a data-coverage issue. "
                "Avoid generic boilerplate. Make the output feel like something a public affairs, government relations, or legal/compliance team could actually use. "
                "For the Relevant Public Context section, cite web URLs from web_context.citations when available and say if web context failed or was not requested. "
                f"Return markdown with exactly these sections: {', '.join(BRIEF_SECTIONS)}.\n\n"
                f"Question: {question}\n"
                f"Facts JSON: {json.dumps(facts, default=str)}"
            ),
        }
        messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a senior campaign-finance intelligence analyst for a client-facing portal. "
                        "Your job is to produce insight-rich, client-useful analysis from local FEC/TEC records plus clearly labeled public web context. "
                        "Be specific, strategic, candid about gaps, non-accusatory, and useful for an executive or legal review audience."
                    ),
                },
                prompt,
            ]
        response = client.chat.completions.create(**_chat_completion_options(model_name, messages))
        output = response.choices[0].message.content or ""
        _store_run(db, insight_type, filters or {}, output, facts, model_name)
        return {
            "enabled": True,
            "mode": "openai",
            "message": "AI briefing generated from selected ingested records.",
            "output_text": output,
            "facts": facts,
            "web_context": web_context,
            "compliance_footer": FOOTER,
        }
    except Exception as exc:
        return {
            "enabled": True,
            "mode": "error",
            "message": f"AI generation failed: {exc}",
            "output_text": "",
            "facts": facts,
            "web_context": web_context,
            "compliance_footer": FOOTER,
        }
