import hashlib
import re
import string

_SUFFIXES = {"LLC", "INC", "LTD", "LIMITED", "CORP", "CORPORATION", "CO", "COMPANY", "LP", "LLP", "PLC", "PLLC"}

TOPIC_KEYWORDS = {
    "Infrastructure": ["infrastructure", "public works", "engineering", "project", "capital improvement"],
    "EPC": ["epc", "engineering procurement construction"],
    "Construction": ["construction", "contractor", "builders", "building"],
    "Roads": ["road", "highway", "bridge", "turnpike", "street"],
    "Transportation": ["transit", "transportation", "mobility", "rail", "airport", "port"],
    "Water": ["water", "reservoir", "sewer", "wastewater", "pipeline", "stormwater"],
    "Utilities": ["utility", "utilities", "electric utility", "gas utility"],
    "Energy": ["energy", "oil", "gas", "power", "electric", "renewable", "grid", "solar", "wind"],
    "Public Works": ["public works", "municipal works", "capital projects"],
    "Real Estate / Development": ["real estate", "development", "developer", "housing", "land use", "zoning"],
    "Education": ["education", "school", "university", "college"],
    "Healthcare": ["healthcare", "health care", "hospital", "medical"],
    "Technology": ["technology", "tech", "software", "broadband", "data center"],
}

HIGH_CONFIDENCE_FIELDS = ["recipient_name", "committee_name", "candidate_name", "filer_name"]
MEDIUM_CONFIDENCE_FIELDS = ["memo_text", "description", "purpose", "transaction_type", "form_type"]


def normalize_name(value: str) -> str:
    if not value:
        return ""
    text = value.upper().strip().translate(str.maketrans("", "", string.punctuation))
    tokens = [t for t in re.split(r"\s+", text) if t and t not in _SUFFIXES]
    return " ".join(tokens)


def normalize_search_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def hash_name(value: str) -> str:
    return hashlib.sha256((value or "").encode()).hexdigest()


def mask_person_name(value: str):
    if not value or not value.strip():
        return None
    parts = value.strip().split()
    if len(parts) == 1:
        return f"{parts[0][0]}***"
    return f"{parts[0][0]}*** {parts[-1][0]}****"


def deterministic_source_record_id(source_system: str, payload: dict) -> str:
    material = {
        key: payload.get(key)
        for key in sorted(payload.keys())
        if key not in {"api_key", "raw_payload_json"}
    }
    encoded = repr((source_system, material)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def tag_transaction_topics(record: dict) -> list[dict]:
    tags: dict[str, dict] = {}

    for field in HIGH_CONFIDENCE_FIELDS + MEDIUM_CONFIDENCE_FIELDS:
        value = normalize_search_text(record.get(field))
        if not value:
            continue
        confidence = "High" if field in HIGH_CONFIDENCE_FIELDS else "Medium"
        rank = {"High": 3, "Medium": 2, "Low": 1}
        for tag, keywords in TOPIC_KEYWORDS.items():
            if any(keyword in value for keyword in keywords):
                current = tags.get(tag)
                if not current or rank[confidence] > rank[current["confidence"]]:
                    tags[tag] = {
                        "tag": tag,
                        "confidence": confidence,
                        "evidence_field": field,
                    }

    if not tags:
        weak_context = " ".join(
            normalize_search_text(record.get(field))
            for field in ["recipient_name", "committee_name", "candidate_name", "filer_name", "party", "office"]
            if record.get(field)
        )
        if weak_context:
            tags["General Political"] = {
                "tag": "General Political",
                "confidence": "Low",
                "evidence_field": "political_context",
            }
        else:
            tags["Unknown"] = {"tag": "Unknown", "confidence": "Low", "evidence_field": "none"}

    return list(tags.values())


def topic_labels(record: dict) -> list[str]:
    return [item["tag"] for item in tag_transaction_topics(record)]
