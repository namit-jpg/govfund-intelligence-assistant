# Web App Features

Capitol File Assistant (`/app/`) — features available in the current JavaScript portal.

| Feature name | Feature Description |
| --- | --- |
| Donation Tracker | Create monitoring lists for employer/company signals, legislators, recipients, PACs, committees, and candidates; set date range, cycle, cadence, max records, and optional alert thresholds. |
| Saved trackers | View saved monitors with latest run status, matched counts, and raw fetch totals; run on demand, inspect matched evidence, and export tracker reports to Excel. |
| AI Intelligence Query | Ask plain-language questions; analysis is grounded in locally ingested FEC/TEC records when `OPENAI_API_KEY` is configured (otherwise the UI shows that AI is unavailable). |
| AI evidence scope | Restrict analysis to a selected saved watchlist or use all stored local records. |
| AI web/news context | Optionally include web/news context for broader public background; campaign-finance records and other data sources remain separate evidence streams. |
| Search Donations | Search ingested transactions by free text (contributor, employer, recipient, committee, or source ID) and filters such as source system, state, cycle, and amount range. |
| Search export | Export the current search result set to Excel via filtered download. |
| Dataset Overview | Summarize all stored ingested records with KPIs (record count, total amount, FEC records, unique recipients, employer signals, quality warnings)—not limited to a single query. |
| Overview charts | Chart source split, top employer/company signals, top recipients, and topic tag distribution across the full dataset. |
| Recent high-value records | Review a table of the highest-value source-backed transactions in the local database. |
| FEC Data Pull | Submit filtered OpenFEC Schedule A queries (contributor, employer, geography, committee/candidate IDs, cycle, dates, amounts, max records) and ingest results into local storage. |
| FEC stored snapshots | Browse prior FEC query runs, refresh the list, and inspect per-run metrics (pages, raw fetched, inserted, duplicates). |
| FEC results and charts | Review snapshot rows in a table (with warnings for future-dated source rows) and charts for monthly trend, top employers, top recipients, and party distribution. |
| FEC snapshot export | Download a stored FEC snapshot as an Excel workbook. |
| Data & Exports | Download audit logs and data quality flags as CSV; preview normalized transactions, raw records, ingestion audit logs, and quality flags in the portal. |
