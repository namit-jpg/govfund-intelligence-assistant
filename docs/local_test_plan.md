# Local Test Plan

## 1. Install And Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --reload --port 8000
```

In a second terminal:

```bash
source .venv/bin/activate
streamlit run frontend/streamlit_app.py
```

## 2. Portal Checks

1. Open Overview and confirm it loads with zero-state messaging or real ingested records.
2. Open Admin / Data Sources and confirm FEC shows enabled only when `FEC_API_KEY` is present.
3. Run a small FEC query with a real key.
4. Upload an official TEC CSV/XLSX export, preview mappings, and import.
5. Open Search Explorer and filter by source, amount, employer/company signal, recipient, and topic.
6. Open Company / Employer Dossier and confirm the FEC caveat is visible.
7. Open Recipient / Committee Dossier.
8. Open Network Map and confirm it draws or explains insufficient data.
9. Open AI Briefing Room with no `OPENAI_API_KEY` and confirm it is disabled.
10. Download exports from Data & Exports.

## 3. API Smoke Checks

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ingestion/config
curl http://localhost:8000/analytics/kpis
curl http://localhost:8000/transactions
curl http://localhost:8000/ai/status
```

## 4. Scripted Smoke Test

```bash
python scripts/smoke_test.py
```
