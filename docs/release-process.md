# Release Process

## Version 1.1 release

1. Parse all 22 PDFs and import the four official spreadsheets into one complete run.
2. Confirm checksums, page coverage, workbook structure, state codes, row counts, and service extraction.
3. Merge cached Census geocodes and explicitly low-confidence ZIP fallbacks.
4. Build the suppression-aware CBP comparison.
5. Run `preliminary-release` and confirm `release_status=preliminary` and `release_ready=false`.
6. Export matching RDS and Stata files and assemble the audited source archives.
7. Regenerate SHA-256 checksums after every asset is present.
8. Create the GitHub prerelease and verify each website link.

Warnings, unknown tokens, unmatched geography, and QA status remain in preview files so researchers can make their own inclusion decisions.

## Validated release

A fully validated release requires passing per-year gold samples, independent annual count checks, at least 90% high-confidence county assignment, and a facility-linkage review with at least 98% precision. A failed year remains preliminary rather than being averaged into a pooled pass.
