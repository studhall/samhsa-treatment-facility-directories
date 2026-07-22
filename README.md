# Historical SAMHSA Treatment Facility Data

This project uses SAMHSA's public-use treatment facility directories to reconstruct address-level facility data. The 1998-2021 directories were published as PDFs; the parser converts them to analysis-ready files aligned with SAMHSA's 2022-2025 workbooks.

The parser code is included in this repository. Combined and year-specific data files are available in the [Version 1.1 release](https://github.com/studhall/samhsa-treatment-facility-directories/releases/tag/v1.1.0).

For quality assurance, I compare reconstructed facility counts with pre-2017 County Business Patterns estimates and use SAMHSA's 2022-2025 workbooks to corroborate facilities appearing in earlier directories.

## Download the data

The Version 1.1 release contains:

- facility-year files in CSV.gz, Parquet, RDS, and Stata
- facility-service files in CSV.gz, Parquet, and RDS
- smaller facility files organized by survey year
- the original 22 PDFs and four later SAMHSA spreadsheets
- service codebooks, source manifests, checksums, geocoding fields, and QA status
- a suppression-aware County Business Patterns comparison for NAICS 621420 and 623220

Quality assurance is ongoing. Manual record review is underway, county geography is mostly based on a lower-confidence ZIP fallback, and historical phone numbers should not be used to locate current care.

## Reproduce the build

Python 3.11 or newer is recommended. Download the source PDFs from the Version 1.1 release, then run:

```powershell
python -m pip install -e .[dev]

python -m samhsa_dirs parse-all `
  --pdf-dir "path\to\pdfs" `
  --resume --workers 2

python -m samhsa_dirs import-xlsx-all `
  --xlsx-dir "path\to\spreadsheets" `
  --run-dir "data\interim\runs\<run>" `
  --resume

python -m samhsa_dirs cbp-download `
  --output-dir "data\raw\cbp" `
  --start-year 1998 --end-year 2023

python -m samhsa_dirs cbp-build `
  --raw-dir "data\raw\cbp" `
  --output "data\interim\cbp_cells.parquet" `
  --start-year 1998 --end-year 2023
```

The PDF parser verifies source checksums and writes each directory year atomically. The spreadsheet importer validates the official 2022-2025 workbooks and preserves their source rows. See [methodology](docs/methodology.md) for layout and harmonization details.

## Quality assurance

PDF years are reviewed against frozen, page-linked gold samples; spreadsheet years receive checksum, schema, row-count, state, and service-code checks. Parser warnings remain in the downloads so researchers can choose their own inclusion rules. The [pre-publication transition audit](docs/transition-audit.md) reports continuity diagnostics around the N-SSATS/N-SUMHSS redesign and later spreadsheet years.

County Business Patterns cells are not silently converted to zero after the 2017 reporting change. The comparison reports common support and zero-to-two establishment bounds for omitted county-industry cells.

## The repository contains

- `src/samhsa_dirs/`: parser, import, geocoding, linkage, QA, CBP, and release code
- `config/`: source manifests and expected counts
- `qa/`: gold-sample instructions and tracked review results
- `scripts/`: release and export helpers
- `tests/`: automated tests
- `docs/`: methodology, data contracts, source rights, and release instructions

Raw sources and generated datasets stay out of git history and are attached to GitHub Releases.

## Citation and contact

Please cite this repository release and the underlying SAMHSA directories. Citation metadata are in [CITATION.cff](CITATION.cff).

Questions and corrections are welcome: [dhall7@uoregon.edu](mailto:dhall7@uoregon.edu) or [econdavidhall.com](https://econdavidhall.com).
