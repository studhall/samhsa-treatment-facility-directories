# Parsing Methodology

The parser extracts each PDF column separately with `pdfplumber`, then reads
columns from left to right and pages in order. City-state-ZIP lines anchor
facility records. Text before an anchor is split into facility names and
street address; contact and service lines after the anchor remain attached
until the next record begins.

Three layout profiles are configured in `config/year_manifest.csv`:

- `early_ocr`: 1998, 2000, and 2001;
- `three_column`: 2003-2017;
- `three_column_transition`: 2018;
- `two_column`: 2019-2021.

Every listing retains source page, column, raw text, and warnings. Unknown
service tokens are not discarded. The codebook extractor scans each
directory's introductory legend and supplements only a small set of stable
codes used for record detection.

The full parser writes a versioned run under `data/interim/runs`. Each listing
also receives a `source_anchor_id` built from directory year, PDF page, column,
the printed city-state-ZIP location anchor, and its occurrence number. This ID
does not depend on parsed facility names or addresses, so the same frozen gold
records can be compared after parser corrections.

Directory year and survey year are separate. For example, the 2021 directory
reports information collected in the 2020 N-SSATS.

## Quality Gates

Automated QA blocks release for malformed state codes, directory headers
parsed as facilities, unexplained annual discontinuities, incomplete gold
samples, insufficient high-confidence geocoding, or unvalidated linkage.
Nonempty output is not considered evidence of a successful parse.

Gold review is evaluated separately by year. Directory years 2003-2021 require
98% accuracy for names, addresses, and exact service-code sets; 1998, 2000, and
2001 require 95%. Any record-boundary error is a hard blocker. Failed,
concentrated, or uncertain samples expand by 50 listings up to 200.
`gold-create --existing-review ... --evaluation ...` appends those records
without changing prior source anchors. Unreviewable rows remain as flagged
evidence and receive a replacement from the same sampling stratum.
