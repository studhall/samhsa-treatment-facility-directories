# Public Data Contracts

## facilities

One row per directory listing-year, including IDs, directory and survey years, historical name/address/contact fields, geography, derived characteristics, provenance, parser warnings, and QA status. Provenance identifies the PDF page and column or the spreadsheet sheet and row.

## facility_services

One row per listing and offered service code. Original tokens and `known_code` are retained.

## service_availability

One row per year-specific service code and question status. Use it to distinguish `not_offered` from `not_asked`.

## facility_entities

Maps listings to stable cross-year facility IDs with linkage method, confidence, and review status. Ambiguous links remain separate.

## geocoding_results

Contains street-geocoder and ZIP-fallback results, county FIPS, method, confidence, and QA flags. An unmatched listing remains in `facilities`.

## cbp_comparison

One row per county and year with the SAMHSA listing count, CBP publication status, published count, lower and upper bounds, and common-support flag. Post-2016 omissions are never converted to exact zeros.
