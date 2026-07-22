# Pre-Publication Transition Audit

## Readiness assessment

**Reviewable release, not a validated dataset.** The reconstruction is sufficiently coherent to publish as Version 1.1 with the existing QA labels. It should not be presented as a continuous statistical series across the 2020/2021 survey transition.

## Findings

### 1. The 2021-to-2022 directory transition is a survey break, not an obvious import failure

The headline U.S. count falls from 14,189 listings in the 2021 directory (2020 N-SSATS survey year) to 12,114 in the 2022 directory (2021 N-SUMHSS survey year), a 14.6% decline. The decline is geographically broad rather than concentrated:

- State counts have a 0.9987 correlation across the transition.
- The median state decline is 14.5%, close to the national decline.
- 82.5% of 2022 listings match a 2021 listing on normalized facility name, ZIP, and state.
- Exact name-address-city-state matching is lower at 54.9%, consistent with differences in address formatting between parsed PDFs and official spreadsheets.

Facility composition is also stable. From the 2021 to 2022 directories, the nonprofit share changes by +1.3 percentage points, for-profit by -0.7 points, government by -0.04 points, OTP by +0.6 points, outpatient by -0.3 points, residential by -0.2 points, and hospital by +0.05 points.

This pattern supports the spreadsheet import and harmonization. It does not establish substantive trend comparability; [SAMHSA identifies N-SUMHSS as a different survey and advises against statistical comparison with N-SSATS/N-MHSS](https://www.samhsa.gov/data/faq/using-n-sumhss-data/should-i-compare-numbers-n-ssats-and-n-mhss-data-and-reports-n-sumhss-data).

### 2. The later spreadsheet years continue plausibly

Headline U.S. listing changes are:

| Directory transition | Change | State-count correlation |
|---|---:|---:|
| 2022 to 2023 | +4.6% | 0.9937 |
| 2023 to 2024 | -4.2% | 0.9930 |
| 2024 to 2025 | +10.4% | 0.9928 |

These transitions preserve the broad state distribution. The 2022-to-2023 composition measures are especially stable: OTP is virtually unchanged, outpatient changes by +0.6 percentage points, residential by +0.3 points, Medicaid acceptance by +0.3 points, and private insurance by -0.2 points.

### 3. The 2025 source workbook omits 556 street addresses

The street-address omissions occur in the official workbook and were not introduced by the importer. These records retain facility name, city, state, ZIP, and phone. They represent 4.15% of headline U.S. 2025-directory listings. The release should preserve them with `missing_street_address` warnings and should not infer street addresses.

### 4. Remaining QA limits matter

Only the beginning of the manual PDF gold review is complete. Cross-year linkage has not passed its precision review, and most county assignments use a lower-confidence ZIP fallback. These limitations do not prevent a clearly labeled preview, but they prevent calling the data validated.

## Publication recommendation

Publish Version 1.1 after:

1. Keeping the dashboard line visually broken between 2020 N-SSATS and 2021 N-SUMHSS.
2. Disclosing the 556 source-missing street addresses in the 2025 directory.
3. Retaining parser warnings and year-level QA fields in every research download.

From an advisor or hiring perspective, the strongest feature is the reproducible reconstruction and unusually transparent diagnostics. The main credibility risk would be describing the count drop across the survey redesign as a substantive change in treatment supply. The preview framing and segmented trend avoid that overclaim.
