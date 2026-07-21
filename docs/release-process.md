# Release Process

## Version 1 Preview

1. Verify all PDF checksums and run the complete 22-year `parse-all` workflow.
2. Complete preliminary structural QA for every year.
3. Finalize cached Census matches and retain ZIP fallbacks as low confidence.
4. Run `preliminary-release`; confirm `release_status=preliminary` and
   `release_ready=false` in the metadata and downloadable files.
5. Export RDS files, rerun the source-rights audit, and build the free PDF archive.
6. Regenerate checksums after every final asset is present.
7. Create the GitHub prerelease and label the website **Version 1 Preview**.

The preview deliberately exposes research files before manual QA is complete. It
must never reuse or override the validated release-ready flag. Warnings, unknown
tokens, and unmatched geography remain in the files so users can make their own
inclusion decisions.

## Validated v1.0.0

1. Complete and evaluate the per-year gold samples.
2. Compare state-year counts with independent SAMHSA totals.
3. Reach and document the formal geocoding and linkage gates.
4. Build the validated release and confirm `qa_report.json` is release-ready.
5. Promote the finished release to `v1.0.0` and update the website label.

`config/expected_counts.csv` intentionally marks legacy parser totals as
comparison fixtures rather than independent acceptance references. Replace or
supplement them with documented SAMHSA or independently verified counts before
the validated release.
