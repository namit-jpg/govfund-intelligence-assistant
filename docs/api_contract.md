# API Contract

## Health

- `GET /health`

## Ingestion

- `GET /ingestion/config`
- `POST /ingestion/fec`
- `POST /ingestion/tec-preview`
- `POST /ingestion/tec-file`
- `GET /ingestion/audit-logs`
- `GET /ingestion/data-quality-flags`

## Transactions

- `GET /transactions`
- `GET /transactions/raw`

## Analytics

- `GET /analytics/kpis`
- `GET /analytics/monthly-trend`
- `GET /analytics/top-recipients`
- `GET /analytics/top-employers`
- `GET /analytics/source-split`
- `GET /analytics/party-distribution`
- `GET /analytics/topic-distribution`
- `GET /analytics/geo-distribution`
- `GET /analytics/recent-high-value`
- `GET /analytics/company-dossier`
- `GET /analytics/recipient-dossier`
- `GET /analytics/network`

## AI

- `GET /ai/status`
- `POST /ai/ask`

`POST /ai/ask` returns disabled status when `OPENAI_API_KEY` is missing. It does not return fake AI text.

## Exports

- `GET /exports/csv`
- `GET /exports/excel`
- `GET /exports/audit-logs`
- `GET /exports/data-quality-flags`
