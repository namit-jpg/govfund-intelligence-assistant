import re

BLOCK_PATTERNS = [
    r"who should we donate to", r"how do we influence", r"target donors", r"donor list", r"contact information",
    r"bribe", r"pay to play", r"pressure politician", r"persuade voters", r"campaign strategy", r"political messaging", r"generate outreach list"
]
SAFE_ALT = "I can provide aggregated public-record trends and source-backed summaries, but I cannot help with donor solicitation, political targeting, or influence strategies."

def check_question(question: str) -> dict:
    q = (question or "").lower()
    for p in BLOCK_PATTERNS:
        if re.search(p, q):
            return {"allowed": False, "reason": f"Blocked policy topic: {p}", "safe_alternative": SAFE_ALT}
    return {"allowed": True, "reason": "allowed", "safe_alternative": SAFE_ALT}
