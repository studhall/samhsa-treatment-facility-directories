# SAMHSA Treatment Facility Directories

This repository converts historical SAMHSA treatment-facility directory PDFs
into documented, address-level research files. It is deliberately separate
from the treatment-and-mortality paper and from the website that displays
release aggregates.

The intended public release covers directory years 1998, 2000, 2001, and
2003-2021. Most directories describe the prior survey year, so both
`directory_year` and `survey_year` are retained. Dashboard and analytical
outputs use `survey_year`.

## Current Status

The parser, schemas, QA gates, release tooling, geocoding client, and website
export contract are implemented. No dataset should be described as validated
until `release/qa_report.json` reports `"release_ready": true`. The release
gate requires a completed manual gold sample, annual count checks, and
geocoding/linkage review.

## Quick Start

Use Python 3.11 or newer.

```powershell
python -m pip install -e .[dev]
python -m samhsa_dirs verify-manifest `
  --pdf-dir "C:\path\to\N-SUMHHS\pdfs"
python -m samhsa_dirs parse `
  --pdf-dir "C:\path\to\N-SUMHHS\pdfs" `
  --year 2021
python -m samhsa_dirs build `
  --pdf-dir "C:\path\to\N-SUMHSS\pdfs" `
  --through-directory-year 2021
```

On this machine, the Anaconda runtime containing `pdfplumber`, `pandas`,
`pyarrow`, `requests`, and `pytest` is:

```powershell
& "C:\Users\David\anaconda3\python.exe" -m pip install -e .[dev]
```

The RDS export is separate so the Python build remains usable without R:

```powershell
& "C:\Program Files\R\R-4.4.1\bin\Rscript.exe" scripts/export_rds.R
```

## Repository Layout

- `config/year_manifest.csv`: source checksum, year mapping, and PDF layout.
- `src/samhsa_dirs/`: parser, codebook, geocoding, linkage, QA, and release code.
- `tests/`: unit tests and gold-sample schema.
- `scripts/`: RDS export, source-rights audit, PDF archive, and dashboard export.
- `docs/`: methodology, data contracts, source rights, and release process.
- `integrations/`: adapters to be copied into consuming projects.

## Release Outputs

A validated release includes:

- `facilities.csv.gz`, `facilities.parquet`, and `facilities.rds`
- `facility_services.csv.gz` and `facility_services.parquet`
- `service_availability.csv`
- `facility_entities.csv`
- `geocoding_results.csv`
- `source_manifest.csv`
- `data_dictionary.csv`
- `qa_report.json` and `qa_by_year.csv`

Historical phone numbers describe the directory vintage and must not be used
to locate current care. They are included in downloads but excluded from
dashboard exports.

## Source And Legal Notes

The PDFs inspected locally contain SAMHSA public-domain notices permitting
reproduction without permission and requesting source citation. They also
state that the publication may not be distributed for a fee without written
authorization. Run `scripts/audit_public_domain.py` for every release and
review the resulting report. This is source-rights documentation, not legal
advice.

## Citation

Use the repository release DOI or GitHub release citation when available, and
cite the corresponding SAMHSA directories. See `CITATION.cff`.

