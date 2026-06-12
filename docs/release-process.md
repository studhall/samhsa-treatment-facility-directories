# Release Process

1. Verify all PDF checksums with `samhsa-dirs verify-manifest`.
2. Parse all 22 directory years.
3. Complete the stratified manual gold sample.
4. Compare state-year counts with independent SAMHSA totals.
5. Run Census geocoding and review unmatched and low-confidence records.
6. Review fuzzy facility links and record measured precision.
7. Build release files and confirm `qa_report.json` is release-ready.
8. Export RDS files.
9. Run the source-rights audit and build the free PDF archive.
10. Generate dashboard exports.
11. Tag the commit and attach release assets.

Never bypass the QA result when publishing website data.

