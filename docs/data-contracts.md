# Public Data Contracts

## facilities

One row per directory listing-year. Important fields include:

- `listing_id`: parser-version record ID used by derived tables.
- `source_anchor_id`: immutable year/page/column/location anchor used to
  reconcile frozen gold records after parser corrections.
- `facility_id`: confidence-scored cross-year entity ID.
- `directory_year` and `survey_year`.
- facility name, historical address, and historical contact fields.
- state, ZIP, county FIPS, coordinates, region, division, and PNW indicator.
- derived ownership, center type, care setting, medication, payment, and telehealth fields.
- source PDF, page, column, raw record text, unknown codes, and parser warnings.

## facility_services

One row per offered service code. `known_code=false` preserves OCR tokens that
could not be reconciled to the year-specific legend.

## service_availability

One row per service code appearing in a directory legend. Join this table to
facility listings to distinguish `not_offered` from `not_asked`.

The optional `facility_service_status.parquet` materializes all
listing-code-year combinations with `offered` and `not_offered` statuses.
Codes absent from `service_availability` are `not_asked`.

## facility_entities

Maps listings to stable facility IDs with linkage method, confidence, and
manual-review status. Ambiguous links remain separate.

## cbp_comparison

Created by the website/paper integration. Required fields are county, state,
year, SAMHSA count, CBP count, publication status, lower and upper bounds, and
common-support flag.
