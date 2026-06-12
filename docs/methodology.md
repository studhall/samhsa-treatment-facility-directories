# Parsing Methodology

The parser extracts each PDF column separately with `pdfplumber`, then reads
columns from left to right and pages in order. City-state-ZIP lines anchor
facility records. Text before an anchor is split into facility names and
street address; contact and service lines after the anchor remain attached
until the next record begins.

Three layout profiles are configured in `config/year_manifest.csv`:

- `early_ocr`: 1998, 2000, and 2001;
- `three_column`: 2003-2017;
- `two_column`: 2018-2021.

Every listing retains source page, column, raw text, and warnings. Unknown
service tokens are not discarded. The codebook extractor scans each
directory's introductory legend and supplements only a small set of stable
codes used for record detection.

Directory year and survey year are separate. For example, the 2021 directory
reports information collected in the 2020 N-SSATS.

## Quality Gates

Automated QA blocks release for malformed state codes, directory headers
parsed as facilities, unexplained annual discontinuities, incomplete gold
samples, insufficient high-confidence geocoding, or unvalidated linkage.
Nonempty output is not considered evidence of a successful parse.

