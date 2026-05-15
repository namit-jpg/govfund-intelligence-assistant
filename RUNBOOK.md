# Runbook

## Local Startup

1. Create `.env` from `.env.example`.
2. Set `FEC_API_KEY`.
3. Optionally set `OPENAI_API_KEY`.
4. Set `DATABASE_URL=sqlite:///./govfund_actual.db` for local use.
5. Start the backend:

```bash
uvicorn backend.main:app --reload --port 8000
```

6. Open the portal at `http://127.0.0.1:8000/app/`.

## FEC Ingestion Steps

1. Open FEC Data Pull.
2. Confirm FEC status is enabled.
3. Enter filters such as employer, state, date range, committee ID, candidate ID, or cycle.
4. Set max records.
5. Run FEC ingestion.
6. Review pages processed, raw records fetched, inserted records, duplicates skipped, and audit log status.

## TEC Import Steps

1. Download an official TEC CSV/XLSX export.
2. Open Admin / Data Sources.
3. Upload the file.
4. Preview mapping.
5. Correct mappings if confidence is low.
6. Import.
7. Review audit logs and quality flags.

## Common Errors

- `FEC_API_KEY is missing`: add the key to `.env` and restart the backend.
- OpenFEC 429: wait and retry with narrower filters or a lower max-record limit.
- TEC missing mappings: use manual mapping for date, amount, and recipient fields.
- Backend unavailable: confirm FastAPI is running on port 8000.

## Tracker Runs And Reports

- Create trackers from the Tracker tab using employer signals, committee IDs, candidate IDs, date range, cycle, and thresholds.
- Run a tracker manually from the Tracker tab when validating a demo.
- On the GCP VM, daily tracker refresh is handled by `govfund-tracker.timer`.
- Check the VM timer with `systemctl status govfund-tracker.timer`.
- Check the latest tracker job logs with `journalctl -u govfund-tracker.service -n 100 --no-pager`.
- Export tracker-specific Excel reports from the Tracker tab.

## Verify Record Counts

- Overview shows total, FEC, and TEC record counts.
- Data & Exports shows latest audit logs.
- Data & Exports includes normalized and raw tables.

## Recover From Failed Ingestion

- Previously inserted real records are retained.
- Check the failed audit log error message.
- Narrow the query or correct mappings.
- Rerun ingestion; duplicates will be skipped.

## Rotate API Keys

1. Replace the secret in `.env` or the deployment secret store.
2. Restart backend workers.
3. Run a small FEC query to verify access.
4. Do not commit `.env` or print key values.

## Inspect Audit Logs

- In the portal: Data & Exports.
- Export audit logs from Data & Exports for review.
