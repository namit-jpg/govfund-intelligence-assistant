from __future__ import annotations

import os


def get_source_config() -> dict:
    fec_ready = bool(os.getenv("FEC_API_KEY"))
    openai_ready = bool(os.getenv("OPENAI_API_KEY"))

    return {
        "fec": {
            "mode": "api",
            "enabled": fec_ready,
            "supports_live_refresh": fec_ready,
            "status_message": (
                "OpenFEC API ingestion is configured."
                if fec_ready
                else "FEC_API_KEY is missing. Add it to .env to enable OpenFEC ingestion."
            ),
        },
        "texas": {
            "mode": "file_import",
            "enabled": True,
            "supports_live_refresh": False,
            "status_message": "TEC ingestion is available through official CSV/XLSX imports.",
            "requires_watchlist": False,
        },
        "ai": {
            "enabled": openai_ready,
            "status_message": (
                "OpenAI-backed briefing is configured."
                if openai_ready
                else "AI is not configured. Add OPENAI_API_KEY to enable AI briefing."
            ),
        },
    }
