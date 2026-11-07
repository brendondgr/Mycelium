# Grants Prototype Ingest

This directory contains the first Mycelium grants-ingest prototype. It samples
public funding records from Grants.gov, NIH RePORTER, and the NSF Award Search
API, normalizes a shared subset of fields, preserves each raw source record, and
writes one CSV per source under `data/grants/`.

This phase is intentionally small: CSV source sampling only, no database.

## Directory Structure

```text
ops/scrapers/grants/
  grants_controller.py
  README.md
  retrievers/
    grants_gov.py
    nih_reporter.py
    nsf_awards.py
  normalizers/
    common.py
    grants_gov.py
    nih_reporter.py
    nsf_awards.py
  writers/
    csv_writer.py
```

Generated samples are written to:

```text
data/grants/
  grants_gov_sample.csv
  nih_reporter_sample.csv
  nsf_awards_sample.csv
```

## Run Commands

Run all sources with the default 10-record sample:

```sh
uv run --project web/backend python ops/scrapers/grants/grants_controller.py
```

Run all sources with a 5-record sample:

```sh
uv run --project web/backend python ops/scrapers/grants/grants_controller.py --limit 5
```

Run one source:

```sh
uv run --project web/backend python ops/scrapers/grants/grants_controller.py --limit 10 --sources grants_gov
uv run --project web/backend python ops/scrapers/grants/grants_controller.py --limit 10 --sources nih_reporter
uv run --project web/backend python ops/scrapers/grants/grants_controller.py --limit 10 --sources nsf_awards
```

Options:

- `--limit`: records per source, clamped to `5` through `10`
- `--output-dir`: output directory, default `data/grants`
- `--sources`: comma-separated source list from
  `grants_gov,nih_reporter,nsf_awards`

## Source Endpoints

### Grants.gov

Endpoint:

```text
POST https://api.grants.gov/v1/api/search2
```

Payload:

```json
{
  "oppStatuses": "forecasted|posted",
  "rows": 10,
  "startRecordNum": 0
}
```

Records are read from `data.oppHits`.

### NIH RePORTER

Endpoint:

```text
POST https://api.reporter.nih.gov/v2/projects/search
```

Payload:

```json
{
  "criteria": {
    "include_active_projects": true,
    "fiscal_years": [2026]
  },
  "limit": 10,
  "offset": 0
}
```

Records are read from `results`.

### NSF Award Search

Endpoint:

```text
GET https://api.nsf.gov/services/v1/awards.json
```

Query parameters:

```text
ActiveAwards=true
rpp=10
offset=0
printFields=id,title,abstractText,program,fundProgramName,transType,dirAbbr,divAbbr,expDate,estimatedTotalAmt,awardeeName,startDate,date,pdPIName,piEmail
```

Records are read from `response.award`.

## Normalized CSV Schema

All source CSVs share these columns:

```text
source
source_record_id
source_opportunity_number
title
agency
agency_code
opportunity_type
status
research_domain
eligibility
organization
principal_investigator
deadline
start_date
end_date
amount
url
abstract
tags
retrieved_at_utc
raw_json
```

`raw_json` contains the complete source record as compact JSON. This is
deliberate: early normalized fields are useful for review, while complete raw
records preserve source-specific fields for later database schema design,
deduplication, enrichment, and matching.

Unavailable fields are written as empty strings. `tags` uses pipe-delimited
source taxonomy values where available. `retrieved_at_utc` is an ISO 8601 UTC
timestamp.

## Known Limitations

- No scheduling yet.
- No `grants.db` yet.
- No deduplication yet.
- No pagination beyond the first page.
- No retries or rate-limit backoff.
- No full Grants.gov detail fetch yet.
- NIH only queries active FY2026 projects.
- NSF only queries the first active awards page.
- No lab-profile matching or opportunity scoring.

## Next Phase

The next phase should turn this CSV prototype into a durable daily ingest:

1. Add SQLite storage at `data/grants.db`.
2. Store source records, normalized opportunity records, ingest runs, and source
   errors.
3. Add pagination and incremental sync per source.
4. Add Grants.gov detail fetches by opportunity ID.
5. Add deduplication keys by source and opportunity number.
6. Add a daily scheduler, eventually moving to Celery when the backend worker
   path is ready.
7. Add tests around normalization, CSV writing, and source response fixtures.
