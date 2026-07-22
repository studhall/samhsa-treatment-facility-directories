# Methodology

## Sources

The build combines 22 historical PDF directories (1998, 2000, 2001, and 2003-2021) with four official SAMHSA spreadsheets (2022-2025). Both `directory_year` and the represented `survey_year` are preserved.

PDFs are parsed one printed column at a time with `pdfplumber`. City-state-ZIP lines anchor listings; source page, column, raw text, warnings, and unknown service tokens remain attached. Layout profiles cover early OCR, three-column, the 2018 transition, and two-column directories.

The spreadsheet importer validates checksums, worksheet names, row counts, states, and service codes before writing the same facility and service contracts. It preserves the source workbook, sheet, and row.

## Services and characteristics

Each year's introductory legend or spreadsheet code reference defines what was asked. This keeps `offered`, `not_offered`, and `not_asked` distinct. A crosswalk harmonizes ownership, center type, care setting, payment, medication services, and service families while retaining original codes.

## Geography and linkage

Census batch geocoding supplies coordinates and county FIPS when a street match is available. A ZIP-to-county crosswalk is used only for unmatched rows and is labeled low confidence. Stable facility IDs use exact normalized matches before geographically constrained fuzzy matching; uncertain matches remain separate.

## Quality assurance

PDF listings receive immutable `source_anchor_id` values based on directory year, page, column, location anchor, and occurrence. Frozen, page-linked gold samples are evaluated separately for every year. Directory years 2003-2021 require 98% name, address, and exact service-set accuracy; 1998, 2000, and 2001 require 95%. Boundary errors are hard blockers.

The 2022-2025 spreadsheet years currently have checksum and structural QA, not equivalent manual gold review. Versioned releases retain explicit QA status until validation is complete.

## County Business Patterns

The comparison uses county CBP files and NAICS 621420 and 623220. Through 2016, absent target cells in the complete county files are treated as exact zeros. Beginning in 2017, omitted county-industry cells are never silently treated as zero; outputs report common support and bounds allowing zero to two establishments per omitted cell.
