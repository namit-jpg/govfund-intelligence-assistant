# Implementation Audit

## Current Structure

- App framework: FastAPI backend plus Streamlit frontend.
- Backend entry point: `backend/main.py`.
- Frontend entry point: `frontend/streamlit_app.py`.
- Existing FEC ingestion: `backend/services/fec_client.py` and `backend/routers/ingestion.py`.
- Existing TEC ingestion: `backend/services/tec_parser.py` via CSV upload.
- Existing storage: SQLAlchemy with SQLite by default.
- Existing UI: Streamlit tabs for dashboard, watchlists, AI, transactions, and export.
- Existing charting: Plotly through Streamlit.
- Existing AI: `backend/services/ai_service.py`.
- Existing export: Excel workbook through `backend/routers/exports.py`.

## What Was Reusable

- FastAPI plus Streamlit is acceptable for a production-oriented MVP because the client needs a stable internal intelligence portal more than a custom frontend shell.
- SQLAlchemy was already present and remains the right abstraction for SQLite now and Postgres later.
- Plotly was already present and supports the required charts and Sankey network.
- The existing watchlist and compliance-guard concepts were reusable after removing demo assumptions.

## What Was Broken

- FEC ingestion was not production reliable. It defaulted through sample/browser-style modes and the API path capped itself at `max_pages=3`, `per_page=20`.
- The app exposed a sample-data route and sample/demo records.
- AI returned mock demo output when `OPENAI_API_KEY` was missing.
- Raw source records, source audit logs, and data quality flags were not stored in the required durable form.
- TEC import had rigid column expectations and no mapping preview.
- UI navigation did not cover the required portal pages.

## Why The Record Count Was Too Low

The `backend/services/fec_client.py` API loop used `for _ in range(params.get("max_pages", 3))` with a default `per_page` of 20 and the UI called ingestion with `max_pages: 1` in the sidebar. That combination could easily stop around one page or a few small pages. It also lacked the full filter surface and did not make OpenFEC API ingestion the default path.

## Streamlit Decision

Streamlit is not blocking this MVP. The app needs credible data ingestion, provenance, filtering, dossiers, exports, and cautious briefings. Streamlit can deliver that quickly with the existing backend. A Next.js migration would add schedule risk without improving the top priority: complete, source-backed ingestion.

## Proposed Implementation Path

1. Keep FastAPI plus Streamlit.
2. Replace sample/browser FEC ingestion with OpenFEC API ingestion using `FEC_API_KEY`.
3. Add keyset pagination, retries, max-record safety limits, audit logs, dedupe, raw record storage, and quality flags.
4. Expand the normalized transaction schema and lightweight entity/topic intelligence.
5. Add TEC CSV/XLSX preview, flexible mapping, validation, and import.
6. Revamp Streamlit into the requested eight-page portal.
7. Disable AI if `OPENAI_API_KEY` is missing; use OpenAI only with grounded facts when configured.
8. Add smoke validation and production docs.

## Files Changed

- `backend/db.py`
- `backend/main.py`
- `backend/models.py`
- `backend/schemas.py`
- `backend/routers/ai.py`
- `backend/routers/analytics.py`
- `backend/routers/exports.py`
- `backend/routers/ingestion.py`
- `backend/routers/transactions.py`
- `backend/routers/watchlists.py`
- `backend/services/ai_service.py`
- `backend/services/analytics_service.py`
- `backend/services/data_quality.py`
- `backend/services/export_service.py`
- `backend/services/fec_client.py`
- `backend/services/normalizer.py`
- `backend/services/repository.py`
- `backend/services/source_config.py`
- `backend/services/tec_parser.py`
- `frontend/streamlit_app.py`
- `scripts/smoke_test.py`
- `tests/fixtures/tec_tiny.csv`
- `.env.example`
- `.gitignore`
- Documentation files in the project root
