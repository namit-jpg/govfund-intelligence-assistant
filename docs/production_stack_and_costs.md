# Production Stack & Direct Cost Model

For Share Good Tech ↔ WarpDrive pricing discussions.  
**Net Project Margin = Client Revenue − Direct Project Costs**

Direct project costs below are **vendor/infrastructure pass-through** estimates (USD/month). WarpDrive engineering, support, and county-ingestion build labor are **contractor/SOW costs**, not in the infra subtotal unless explicitly agreed.

---

## Recommended production stack (US-hosted)

| Layer | Technology | Why |
| --- | --- | --- |
| Application | **FastAPI** + static JS portal (`web/`) | Current product; Dockerized (`Dockerfile`) |
| Reverse proxy | **nginx** | Already used on GCP VM (`setup_vm.sh`) |
| Database | **PostgreSQL** (GCP Cloud SQL or AWS RDS) | Required for multi-user production; SQLite is MVP-only |
| Object storage | **GCS or S3** | Raw county PDFs, export archives, audit artifacts |
| Compute | **GCP Compute Engine** or **AWS EC2** (US region) | Matches existing GCP VM deployment pattern |
| Secrets | **Secret Manager** / **AWS Secrets Manager** | FEC + OpenAI keys server-side only |
| AI | **OpenAI API** (optional; disabled without key) | Grounded briefings + optional web context |
| Federal data | **OpenFEC API** | Free; paginated Schedule A ingestion |
| County data (planned) | County portals → **PDF store** → extract (**pdfplumber** / **Document AI** for scans) | No county API; per-county adapters |
| Monitoring | **Sentry** + cloud monitoring | Ingestion failures, tracker jobs, API errors |
| CI/CD | **GitHub Actions** + container registry | Deploy Docker image on release |

**Not in v1 production:** LinkedIn scraping; use optional paid enrichment APIs + human review if customer requires employer matching.

---

## Cost tiers (summary)

| Tier | Typical use | Est. monthly direct costs |
| --- | --- | --- |
| **Pilot** | 1 client, light AI, FEC + manual TEC/county uploads | **~$250–350** |
| **Production** | 1–3 clients, daily trackers, moderate AI, Postgres | **~$900–1,200** |
| **Scale** | Multi-client, automated county PDF ingestion, heavy AI + enrichment | **~$2,500–3,500** |

Largest variables: **OpenAI usage**, **PDF/OCR volume**, **optional employer enrichment API**, **storage/egress**.

---

## Spreadsheet

Full line-item table: [`production_cost_model.csv`](./production_cost_model.csv)  
(Open in Excel / Google Sheets.)

---

## Items to confirm with WarpDrive (Cameron)

1. **US entity vs foreign contractor** — W-8BEN-E vs US 1099 affects tax handling only; infra vendors bill USD either way.  
2. **Which tier** is the first paying customer on (pilot vs production).  
3. **AI budget cap** — recommend monthly OpenAI spend alert (e.g. $300 / $1,000).  
4. **County PDF scope** — which counties in phase 1 (drives OCR + storage + labor).  
5. **Employer enrichment** — exclude from base package; price as add-on if customer wants external matching.
