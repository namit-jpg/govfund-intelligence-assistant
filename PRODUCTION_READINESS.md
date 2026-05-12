# Production Readiness

## Production-Ready Now

- FEC API key is read from `FEC_API_KEY`.
- AI is disabled unless `OPENAI_API_KEY` exists.
- No product sample-data route remains.
- FEC ingestion supports pagination, retries, max-record limits, raw record storage, dedupe, audit logs, and quality flags.
- TEC CSV/XLSX import supports preview, mapping, validation, raw payload preservation, audit logs, and dedupe.
- Streamlit portal includes overview, search, dossiers, network, AI room, exports, and admin/source controls.

## Production-Oriented But Needs Hardening

- SQLite is acceptable for local/client-demo use, but Postgres is recommended for multi-user production.
- Schema migration is lightweight. Use Alembic before production.
- Streamlit is workable for MVP but not a substitute for a fully authenticated multi-user web app.
- Network visualizations are intentionally capped to avoid unreadable charts.

## Security Gaps

- No first-class authentication has been added.
- No role-based access control exists.
- Secrets depend on deployment environment hygiene.

## Auth Gaps

Add authentication before broader deployment. Recommended options:

- Reverse proxy auth for a short internal pilot.
- Proper app auth with SSO for client production.

## Database Migration Recommendation

Use `DATABASE_URL` with Postgres for production. Add Alembic migrations for managed schema changes and back up existing SQLite data before migration.

## Deployment Recommendation

For MVP:

- Run FastAPI as a backend service.
- Run Streamlit as the portal service.
- Keep `FEC_API_KEY` and `OPENAI_API_KEY` server-side only.

For production:

- Containerize both services.
- Use Postgres.
- Add auth, monitoring, backups, and error reporting.

## Monitoring And Logging Recommendation

- Capture structured backend logs.
- Monitor ingestion failures and partial runs.
- Alert on repeated OpenFEC 429/5xx responses.
- Track source audit log counts and latest successful ingestion time.

## Risks Before Client Demo

- Confirm the real OpenFEC API key is present.
- Run a broad FEC ingestion that is expected to return multiple pages.
- Import at least one official TEC export.
- Review quality flags and audit logs.
- Confirm no stale sample records exist in the active database.
