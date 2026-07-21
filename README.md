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

Version 1 Preview publishes the complete 22-directory reconstruction for research
use while manual validation continues. Preview files are explicitly labeled
`preliminary`; they do not set or imply `release_ready=true`. A later validated
`v1.0.0` release remains gated on gold-sample, count, geocoding, and linkage
review.

## Quick Start

Use Python 3.11 or newer.

```powershell
python -m pip install -e .[dev]
python -m samhsa_dirs verify-manifest `
  --pdf-dir "C:\path\to\N-SUMHHS\pdfs"
python -m samhsa_dirs parse `
  --pdf-dir "C:\path\to\N-SUMHHS\pdfs" `
  --year 2021
python -m samhsa_dirs parse-all `
  --pdf-dir "C:\path\to\N-SUMHSS\pdfs" `
  --resume `
  --workers 2
python -m samhsa_dirs gold-create `
  --run-dir "data\interim\runs\<run>" `
  --seed 20260612
```

`parse-all` verifies all 22 checksums, processes calibration waves, and writes
each year atomically to a versioned run directory. Pilot outputs in
`data/interim` never satisfy this full-build gate. The working Excel review and
rendered PDF pages are local-only; `gold-import` creates the tracked
authoritative CSV, and `gold-evaluate` applies year-specific adaptive gates.
After parser corrections, `gold-refresh` updates parsed fields by immutable
`source_anchor_id` while preserving corrections, checks, reviewer fields, and
notes.
If a year needs expansion, rerun `gold-create` with `--existing-review` and
`--evaluation`; it preserves prior rows and appends the recommended records up
to the 200-listing cap.

On this machine, the Anaconda runtime containing `pdfplumber`, `pandas`,
`pyarrow`, `requests`, and `pytest` is:

```powershell
& "C:\Users\David\anaconda3\python.exe" -m pip install -e .[dev]
```

The RDS export is separate so the Python build remains usable without R:

```powershell
& "C:\Program Files\R\R-4.4.1\bin\Rscript.exe" scripts/export_rds.R
```

## Version 1 Preview Build

After a complete 22-year parse, build the preliminary research files without
bypassing or altering the validated release gate:

```powershell
python -m samhsa_dirs preliminary-release `
  --run-dir "data\interim\runs\<run>" `
  --release-dir "release\v1.0.0-preliminary.1" `
  --review "qa\gold\gold_review.csv" `
  --geocoding "data\interim\geocoding_results.csv" `
  --harmonization-crosswalk "config\harmonization_crosswalk.csv" `
  --version "v1.0.0-preliminary.1"
```

Use `geocode-finalize` to combine cached Census geography matches with the
explicitly low-confidence ZIP fallback before the preview build. Run the RDS
export afterward so the R files match the CSV and Parquet assets.

## Repository Layout

- `config/year_manifest.csv`: source checksum, year mapping, and PDF layout.
- `config/expected_counts.csv`: count comparators and acceptance-reference status.
- `src/samhsa_dirs/`: parser, codebook, geocoding, linkage, QA, and release code.
- `qa/gold/`: authoritative gold review export and per-year evaluation.
- `qa/review/`: ignored working workbook, PDF page images, and previews.
- `tests/`: unit and integration tests.
- `scripts/`: RDS export, source-rights audit, PDF archive, and dashboard export.
- `scripts/build_cbp_comparison.py`: suppression-aware Swensen NAICS comparison.
- `docs/`: methodology, data contracts, source rights, and release process.
- `integrations/`: adapters to be copied into consuming projects.

## Release Outputs

Version 1 Preview and the later validated release include:

- `facilities.csv.gz`, `facilities.parquet`, and `facilities.rds`
- `facility_services.csv.gz`, `facility_services.parquet`, and `facility_services.rds`
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
