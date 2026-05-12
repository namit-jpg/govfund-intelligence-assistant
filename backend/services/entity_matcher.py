from rapidfuzz import fuzz

from .normalizer import normalize_name


def normalize_entity_name(name: str) -> str:
    return normalize_name(name)


def confidence_label(score: float) -> str:
    if score >= 95:
        return "High"
    if score >= 85:
        return "Medium"
    if score > 0:
        return "Low"
    return "No Match"


def exact_match(transaction_value, watchlist_entities):
    normalized_value = normalize_name(transaction_value)
    for entity in watchlist_entities:
        entity_name = entity.get("entity_name", "")
        if normalized_value == normalize_name(entity_name):
            return {
                "matched_entity_name": entity_name,
                "matched_entity_type": entity.get("entity_type", "employer"),
                "match_confidence": 100.0,
                "match_reason": "exact",
                "normalized_transaction_value": normalized_value,
                "normalized_watchlist_value": normalize_name(entity_name),
            }
    return None


def fuzzy_match(transaction_value, watchlist_entities, threshold=85):
    normalized_value = normalize_name(transaction_value)
    best = None
    for entity in watchlist_entities:
        entity_name = entity.get("entity_name", "")
        score = fuzz.ratio(normalized_value, normalize_name(entity_name))
        if score >= threshold and (not best or score > best[0]):
            best = (score, entity)
    if best:
        entity_name = best[1]["entity_name"]
        return {
            "matched_entity_name": entity_name,
            "matched_entity_type": best[1].get("entity_type", "employer"),
            "match_confidence": float(best[0]),
            "match_reason": "fuzzy",
            "normalized_transaction_value": normalized_value,
            "normalized_watchlist_value": normalize_name(entity_name),
        }
    return None


def build_match_explanation(match: dict, watchlist_name: str | None = None) -> str:
    if not match.get("matched_entity_name"):
        return "No watchlist entity cleared the similarity threshold for this transaction."

    field_name = match.get("matched_on_field", "transaction field").replace("_", " ")
    label = confidence_label(float(match.get("match_confidence", 0)))
    watchlist_fragment = f" in {watchlist_name}" if watchlist_name else ""

    if match.get("match_reason") == "exact":
        return (
            f"{label} confidence exact match on {field_name}{watchlist_fragment}: "
            f"\"{match.get('comparison_value')}\" exactly matches "
            f"\"{match.get('matched_entity_name')}\" after normalization."
        )

    return (
        f"{label} confidence fuzzy match on {field_name}{watchlist_fragment}: "
        f"\"{match.get('comparison_value')}\" is {match.get('match_confidence', 0):.0f}% similar to "
        f"\"{match.get('matched_entity_name')}\" after normalizing punctuation, casing, and spacing."
    )


def match_transaction_to_watchlist(transaction, watchlist):
    entities = watchlist.get("entities", [])
    for key in ["contributor_employer", "recipient_name", "candidate_name"]:
        value = transaction.get(key)
        if not value:
            continue

        match = exact_match(value, entities)
        if match:
            match["matched_on_field"] = key
            match["comparison_value"] = value
            match["confidence_label"] = confidence_label(match["match_confidence"])
            return match

        match = fuzzy_match(value, entities)
        if match:
            match["matched_on_field"] = key
            match["comparison_value"] = value
            match["confidence_label"] = confidence_label(match["match_confidence"])
            return match

    return {
        "matched_entity_name": None,
        "matched_entity_type": "unknown",
        "match_confidence": 0.0,
        "match_reason": "no_match",
        "matched_on_field": None,
        "comparison_value": None,
        "confidence_label": confidence_label(0.0),
    }
