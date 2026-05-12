# Data Source Notes

## FEC Source Coverage

FEC ingestion uses the OpenFEC Schedule A itemized receipts endpoint:

- `https://api.open.fec.gov/v1/schedules/schedule_a/`

The ingestion client supports contributor name, employer, state, city, committee ID, candidate ID, date range, amount range, cycle/two-year transaction period, page size, and max-record safety limits. It follows OpenFEC pagination metadata until no cursor remains or the configured max-record limit is reached.

## TEC Source Coverage

TEC ingestion is file based for the MVP:

- Official TEC CSV database files.
- TEC advanced-search CSV/XLSX exports.

The importer previews columns, detects likely mappings, allows manual correction, preserves raw payloads, and imports only uploaded real records. Browser scraping is not used as the primary ingestion path.

## Employer / Company Signal Caveat

FEC individual contribution records can include a `contributor_employer` field. This is the employer reported by the individual contributor. It is an employer/company signal, not proof that the company itself donated.

The UI uses labels such as:

- Employer / Company Signal
- Individuals reporting this employer
- Employer-linked donor activity

The app must not describe these records as direct corporate donations unless the source record explicitly supports that.

## Source Audit Logs

Every ingestion run writes a source audit log with:

- Source system
- Operation type
- Query parameters without secrets
- Start and completion timestamps
- Status
- Pages processed
- Raw records fetched
- Inserted records
- Duplicate records skipped
- Error message if applicable

## Confidence Score

The MVP uses conservative confidence values:

- `1.0` for exact source-backed normalized records.
- Topic tags include their own confidence based on evidence field.
- Employer/company entity matching is exact or suffix-normalized unless a later fuzzy workflow explicitly marks lower confidence.

## Known Data Limitations

- Public campaign finance data may lag filing deadlines and source processing.
- TEC exports vary by report type and column naming.
- Topic tagging is deterministic keyword tagging, not legal or political intent analysis.
- Entity resolution is lightweight and should be reviewed for high-stakes external use.
