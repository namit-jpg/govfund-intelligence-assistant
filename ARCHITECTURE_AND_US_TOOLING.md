# Architecture And US Tooling Notes

## Backend Pipes

1. Public data sources
   - OpenFEC Schedule A API for federal campaign finance records.
   - Official TEC CSV/XLSX imports remain supported in the backend for Texas Ethics Commission data.

2. Backend API
   - FastAPI serves ingestion, search, analytics, AI briefing, watchlists, exports, and the fast web portal.
   - The FEC API key is read server-side from `FEC_API_KEY`; it is not exposed to the browser.

3. Persistence and provenance
   - SQLAlchemy models write to `DATABASE_URL`.
   - Local MVP uses SQLite.
   - Production should use Postgres.
   - Key evidence tables include raw records, normalized transactions, source audit logs, data quality flags, insight runs, watchlists, and FEC query snapshots.

4. Frontend
   - The active client-facing portal is static JavaScript/CSS served from `/app/` by FastAPI.
   - Streamlit is retained only as a handoff unless `LEGACY_STREAMLIT_UI=1` is set.

5. AI path
   - AI is disabled unless `OPENAI_API_KEY` is configured.
   - The backend first builds deterministic facts from local records.
   - The LLM receives only those facts and the user question.
   - The system does not invent records or use general model knowledge as evidence.

## US Tooling / Political-Use Notes

- OpenFEC is an official US federal public data source.
- The app can be deployed with US-hosted infrastructure.
- For production, use US-hosted Postgres, managed secrets, authentication, and access logging.
- If required, OpenAI usage can be replaced or routed through an approved US-region provider such as Azure OpenAI.
- The app does not infer bribery, corruption, pay-to-play, donor intent, illegality, or direct corporate donations.
- FEC employer fields are treated only as employer/company signals reported by individual contributors.

## Current Demo-Safe Features

- AI-first free-form query over locally ingested records.
- Donation tracker workflow preview and monitor list creation.
- Search Donations with free-text search and filtered Excel export.
- FEC Data Pull for supporting OpenFEC ingestion.
- Dataset Overview with explicit all-stored-record scope.
- Architecture tab for CTO-style questions.

## Remaining Production Gaps

- Authentication and role-based access.
- Production Postgres migration.
- Background ingestion jobs.
- Real alert delivery.
- Broader TEC UI in the fast portal.
- More robust entity alias management for candidate/committee names.
