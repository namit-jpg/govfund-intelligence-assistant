# GovFund Intelligence Assistant

GovFund Intelligence Assistant is a source-backed campaign finance intelligence portal for reviewing FEC and Texas Ethics Commission records. It helps users explore employer/company signals, contributors, recipients, committees, topics, trends, dossiers, network relationships, audit logs, and exportable evidence.

The app does not create fake product records, does not use demo mode, and does not make claims about bribery, corruption, pay-to-play, illegality, donor intent, or direct corporate donations.

## Architecture

- Backend: FastAPI, SQLAlchemy, pandas, requests.
- Primary frontend: FastAPI-served JavaScript portal in `web/` for fast tab navigation without Streamlit reruns.
- Legacy frontend: Streamlit handoff page at port 8501. Set `LEGACY_STREAMLIT_UI=1` only if you need the old Streamlit portal.
- Database: SQLite locally through `DATABASE_URL`; Postgres recommended later.
- FEC ingestion: OpenFEC Schedule A API with pagination and retries.
- TEC ingestion: Official CSV/XLSX import with mapping preview.
- AI: OpenAI-backed grounded briefing only when `OPENAI_API_KEY` is configured.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, activate with the environment command appropriate for your local Python installation.

## Environment Variables

Use placeholders only in `.env.example`. Put real values only in `.env` or your deployment secret store.

```bash
FEC_API_KEY=
OPENAI_API_KEY=
DATABASE_URL=sqlite:///./govfund_actual.db
APP_ENV=local
LOG_LEVEL=INFO
```

`OPENAI_API_KEY` is optional. If missing, the AI Briefing Room shows "AI is not configured" and does not generate fake AI text.

## Run Locally

Backend:

```bash
uvicorn backend.main:app --reload --port 8000
```

Primary frontend:

```bash
uvicorn backend.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/app/`.

Legacy Streamlit handoff:

```bash
streamlit run frontend/streamlit_app.py
```

By default this redirects to the fast JS portal. To load the old Streamlit UI, set `LEGACY_STREAMLIT_UI=1`.

## Ingest FEC Data

1. Add `FEC_API_KEY` to `.env`.
2. Start the backend.
3. Open `http://127.0.0.1:8000/app/`.
4. Open the FEC tab.
5. Enter filters and max records.
6. Run FEC ingestion.
7. Review pages processed, raw records fetched, inserted records, duplicates, errors, and audit log status.

The FEC client follows OpenFEC pagination metadata until no cursor remains or `max_records` is reached.

## Import TEC Data

1. Download an official TEC CSV/XLSX export.
2. Open Admin / Data Sources.
3. Upload the file.
4. Preview automatic column mapping.
5. Correct mappings when needed.
6. Import and review quality flags.

No TEC data is fabricated when no file is uploaded.

## Export Data

Data & Exports provides:

- Excel workbook with KPIs, trends, transactions, raw records, audit logs, quality flags, and compliance notes.
- CSV audit logs.
- CSV quality flags.
- CSV export of displayed search records.

## Tests

Run the smoke test:

```bash
python scripts/smoke_test.py
```

The smoke test verifies database initialization, FEC request building without exposing an API key, normalized insert and dedupe, topic tagging, TEC mapping, disabled AI behavior without `OPENAI_API_KEY`, and workbook export.

## Limitations

- Authentication is not implemented yet.
- SQLite is local-MVP storage; move to Postgres for production.
- Topic tagging is deterministic keyword tagging.
- Entity resolution is lightweight and conservative.
- Streamlit was retained only as a legacy handoff because its rerun model was too slow for this portal. The active UI is now JavaScript on FastAPI.

## Data Caveat

FEC employer fields represent the employer reported by individual contributors. They do not prove direct corporate donations.
