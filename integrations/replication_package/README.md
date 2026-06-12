# Treatment Access and Overdose Mortality Replication Package

This is the clean redo of the Treatment and Mortality project. It is designed to be the public GitHub replication package for a health-economics paper tentatively titled:

**Has Treatment Access Lost Its Bite? Treatment Centers and Overdose Mortality in the Modern Opioid Era**

The package replicates Swensen (2015), extends the County Business Patterns (CBP) analysis through 2019 as the headline sample, treats 2020-2022 as a COVID-era stress test, and prepares the N-SSATS facility-directory workflow for a distance-weighted access extension. The facility workflow consumes a pinned, validated release from `studhall/samhsa-treatment-facility-directories`; the legacy local R parser remains available only as an explicit fallback while the first release is being validated.

## Manuscript

The current manuscript draft is in `manuscript/main.tex`. It follows the structure of the original Overleaf draft but reframes the paper for a health-economics journal audience:

- introduction with replication, attenuation, and design-diagnostic contributions;
- background on drug supply, people who use drugs, treatment access, and policy approach;
- CBP, mortality, controls, and NSSATS data sections;
- Swensen-style replication specifications and diagnostic extensions;
- main results through 2019, with 2020-2022 as a COVID-era stress test;
- distance-weighted access extension and heterogeneity roadmap.

Compile from `manuscript/` with:

```powershell
pdflatex -interaction=nonstopmode main.tex
bibtex main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

## One-Command Run

From this folder:

```powershell
& 'C:/Program Files/R/R-4.4.1/bin/Rscript.exe' run_all.R
```

To also attempt full NSSATS PDF extraction with the `pdftools` parser:

```powershell
& 'C:/Program Files/R/R-4.4.1/bin/Rscript.exe' run_all.R --full-nssats
```

To reparse every available NSSATS PDF and use the PDF-reparsed files as the preferred source:

```powershell
& 'C:/Program Files/R/R-4.4.1/bin/Rscript.exe' run_all.R --reparse-all-nssats
```

To bypass the pinned release and use the legacy local workflow:

```powershell
& 'C:/Program Files/R/R-4.4.1/bin/Rscript.exe' run_all.R --legacy-nssats
```

Use `--refresh-samhsa-release` to redownload the configured release. The default run does not reparse thousands of PDF pages. Until the first public release exists, an unavailable download produces a warning and temporarily falls back to the legacy validation path.

## Data Policy

Restricted NCHS mortality microdata and derived restricted analytic files should not be committed publicly unless permissions are confirmed. This package therefore includes:

- Code to rebuild the restricted-data workflow locally.
- Documentation for where restricted inputs belong.
- A public-use workflow note for users who want to adapt the analysis with public mortality downloads.
- Monte Carlo simulation code that can run without publishing restricted source data.

Ignored local folders include `data/restricted/`, `data/interim/`, `data/processed/`, and model-object logs.

## Main Workflow

1. `R/01_inventory.R`: inventories legacy inputs and expected package outputs.
2. `R/02_cbp_audit.R`: audits CBP treatment-center counts, including the 2017 reporting/suppression break.
3. `R/03_build_analysis_panels.R`: builds replication, 1999-2016, 1999-2019, and 1999-2022 panels.
4. `R/03b_descriptive_outputs.R`: writes appendix-ready summary tables and time-series figures.
5. `R/04_estimate_twfe.R`: estimates Swensen-style TWFE specifications.
6. `R/05_design_diagnostics.R`: runs TWFE weight and Goodman-Bacon diagnostic scaffolds.
7. `R/06_serial_correlation.R`: diagnoses persistence and compares inference approaches.
8. `R/00_samhsa_release.R`: downloads and validates the pinned public facility release.
9. `R/07_nssats_extract_validate.R`: legacy local extraction validation and geocoding queue.
10. `R/08_distance_access.R`: constructs distance-weighted access metrics once geocoded facilities and centroids are available.
11. `R/09_monte_carlo_attenuation.R`: simulates annual timing attenuation.
12. `R/10_public_use_workflow.R`: writes public-use replication instructions.
13. `R/11_validate_outputs.R`: checks expected package outputs.

## Important Defaults

- Headline sample: 1999-2019.
- COVID stress-test sample: 1999-2022.
- Clean CBP pre-suppression sample: 1999-2016.
- Primary treatment variable: lagged CBP treatment centers.
- Secondary treatment variable: lagged treatment centers per 100,000 population.
- Distance access extension: NSSATS facilities to county population centroids.

## Legacy Sources

Legacy work is not moved or deleted. See `archive/legacy_work_manifest.md` for the old folders and what each contributes to the clean package.
