from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .linkage import link_facilities
from .manifest import load_manifest
from .xlsx import load_xlsx_manifest
from .qa import build_qa_report, write_qa


def _read_year_files(interim_dir: Path, stem: str) -> pd.DataFrame:
    files = sorted(interim_dir.glob(f"{stem}_*.parquet"))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)


FIELD_DESCRIPTIONS = {
    "listing_id": "Stable identifier for a source directory listing-year.",
    "facility_id": "Cross-year facility entity identifier.",
    "directory_year": "Year printed on the source directory.",
    "survey_year": "Analytical year represented by the directory.",
    "county_fips": "Five-digit county FIPS assignment.",
    "source_pdf": "Source PDF filename.",
    "source_page": "One-based source PDF page.",
    "source_column": "Positional source page column.",
    "parser_warnings": "JSON array of parser QA warnings.",
    "status": "Service state: offered, not_offered, or not_asked.",
}


def _write_data_dictionary(tables: dict[str, pd.DataFrame], release_dir: Path) -> None:
    rows = []
    for table, frame in tables.items():
        for column, dtype in frame.dtypes.items():
            rows.append(
                {
                    "table": table,
                    "column": column,
                    "dtype": str(dtype),
                    "description": FIELD_DESCRIPTIONS.get(column, ""),
                }
            )
    pd.DataFrame(rows).to_csv(release_dir / "data_dictionary.csv", index=False)


def _write_checksums(release_dir: Path) -> None:
    rows = []
    for path in sorted(release_dir.iterdir()):
        if not path.is_file() or path.name in {
            "checksums.sha256",
            "geocoding_cache.csv",
            "zcta_county_relationship_2020.txt",
        }:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{digest}  {path.name}")
    (release_dir / "checksums.sha256").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )


def _read_run_files(run_dir: Path, filename: str) -> pd.DataFrame:
    files = sorted((run_dir / "years").glob(f"*/{filename}"))
    return (
        pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)
        if files
        else pd.DataFrame()
    )


def _review_counts(review_path: Path | None) -> dict[int, int]:
    if review_path is None or not review_path.exists():
        return {}
    review = pd.read_csv(review_path, dtype=str).fillna("")
    complete = review.loc[review["review_complete"].str.lower().eq("yes")].copy()
    if complete.empty:
        return {}
    return (
        complete.groupby(complete["directory_year"].astype(int))
        .size()
        .astype(int)
        .to_dict()
    )


def build_preliminary_release(
    run_dir: Path,
    release_dir: Path,
    review_path: Path | None = None,
    geocoding_path: Path | None = None,
    harmonization_crosswalk: Path | None = None,
    cbp_comparison_path: Path | None = None,
    version: str = "v1.1.0",
) -> dict[str, object]:
    """Build a public release snapshot without asserting validation gates passed."""
    run_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    expected_years = {int(year) for year in run_metadata["expected_years"]}
    year_dirs = {
        int(path.name)
        for path in (run_dir / "years").iterdir()
        if path.is_dir() and path.name.isdigit()
    }
    if year_dirs != expected_years:
        missing = sorted(expected_years - year_dirs)
        extra = sorted(year_dirs - expected_years)
        raise RuntimeError(f"Run years are incomplete; missing={missing}, extra={extra}")

    required = [
        "facilities.parquet",
        "facility_services.parquet",
        "service_availability.parquet",
        "metadata.json",
    ]
    missing_files = [
        f"{year}/{name}"
        for year in sorted(expected_years)
        for name in required
        if not (run_dir / "years" / str(year) / name).exists()
    ]
    if missing_files:
        raise RuntimeError(f"Run is missing required files: {missing_files}")

    facilities = _read_run_files(run_dir, "facilities.parquet")
    services = _read_run_files(run_dir, "facility_services.parquet")
    availability = _read_run_files(run_dir, "service_availability.parquet")
    if facilities.empty or services.empty or availability.empty:
        raise RuntimeError("Preliminary release inputs are empty.")
    if "group_index" in services:
        services["group_index"] = services["group_index"].fillna("").astype(str)
    else:
        services["group_index"] = ""

    if "source_format" not in facilities:
        facilities["source_format"] = ""
    missing_source = facilities["source_format"].fillna("").eq("")
    facilities.loc[missing_source, "source_format"] = np.where(
        facilities.loc[missing_source, "directory_year"].astype(int).ge(2022),
        "official_xlsx",
        "historical_pdf",
    )
    if "source_file" not in facilities:
        facilities["source_file"] = facilities.get("source_pdf", "")
    else:
        facilities["source_file"] = facilities["source_file"].fillna("")
        missing_file = facilities["source_file"].eq("")
        facilities.loc[missing_file, "source_file"] = facilities.loc[
            missing_file, "source_pdf"
        ].fillna("")
    reviewed = _review_counts(review_path)
    priority_years = {1998, 2000, 2001, 2003, 2004, 2017, 2018, 2021}
    facilities["release_status"] = "preliminary"
    facilities["parser_version"] = run_metadata.get("parser_version", __version__)
    facilities["run_id"] = run_metadata.get("run_id", run_dir.name)
    facilities["has_parser_warning"] = facilities["parser_warnings"].fillna("[]").ne("[]")
    facilities["reviewed_listings_in_year"] = (
        facilities["directory_year"].map(reviewed).fillna(0).astype(int)
    )
    facilities["gold_target_in_year"] = facilities["directory_year"].map(
        lambda year: 0 if int(year) >= 2022 else (100 if int(year) in priority_years else 50)
    )
    facilities["year_qa_status"] = np.select(
        [
            facilities["source_format"].eq("official_xlsx"),
            facilities["reviewed_listings_in_year"].gt(0),
        ],
        ["official_xlsx_checks_passed", "partial_review"],
        default="not_reviewed",
    )
    geocoding = pd.DataFrame()
    if geocoding_path is not None and geocoding_path.exists():
        geocoding = pd.read_csv(geocoding_path, dtype=str).drop_duplicates("listing_id")
        geo_cols = [
            "listing_id",
            "county_fips",
            "latitude",
            "longitude",
            "geocode_method",
            "geocode_confidence",
        ]
        facilities = facilities.drop(columns=geo_cols[1:], errors="ignore").merge(
            geocoding[[col for col in geo_cols if col in geocoding.columns]],
            on="listing_id",
            how="left",
        )

    services["release_status"] = "preliminary"
    services["parser_version"] = run_metadata.get("parser_version", __version__)
    services["run_id"] = run_metadata.get("run_id", run_dir.name)

    qa_by_year = (
        facilities.groupby(["directory_year", "survey_year"], dropna=False)
        .agg(
            facility_count=("listing_id", "size"),
            warning_count=("has_parser_warning", "sum"),
            reviewed_listings=("reviewed_listings_in_year", "first"),
            gold_target=("gold_target_in_year", "first"),
            qa_status=("year_qa_status", "first"),
        )
        .reset_index()
    )
    qa_by_year["warning_share"] = (
        qa_by_year["warning_count"] / qa_by_year["facility_count"]
    )

    release_dir.mkdir(parents=True, exist_ok=True)
    facilities.to_csv(release_dir / "facilities.csv.gz", index=False, compression="gzip")
    facilities.to_parquet(release_dir / "facilities.parquet", index=False)
    for survey_year, year_rows in facilities.groupby("survey_year", sort=True):
        year_rows.to_csv(
            release_dir / f"facilities_{int(survey_year)}.csv.gz",
            index=False,
            compression="gzip",
        )
    services.to_csv(
        release_dir / "facility_services.csv.gz", index=False, compression="gzip"
    )
    services.to_parquet(release_dir / "facility_services.parquet", index=False)
    availability.drop_duplicates().to_csv(
        release_dir / "service_availability.csv", index=False
    )
    qa_by_year.to_csv(release_dir / "qa_by_year.csv", index=False)
    pdf_manifest = pd.DataFrame([row.__dict__ for row in load_manifest()])
    pdf_manifest["source_format"] = "historical_pdf"
    xlsx_manifest = pd.DataFrame([row.__dict__ for row in load_xlsx_manifest()])
    xlsx_manifest["source_format"] = "official_xlsx"
    source_manifest = pd.concat([pdf_manifest, xlsx_manifest], ignore_index=True)
    source_manifest.sort_values("directory_year").to_csv(
        release_dir / "source_manifest.csv", index=False
    )
    if harmonization_crosswalk is not None and harmonization_crosswalk.exists():
        pd.read_csv(harmonization_crosswalk).to_csv(
            release_dir / "harmonization_crosswalk.csv", index=False
        )
    if not geocoding.empty:
        geocoding.to_csv(release_dir / "geocoding_results.csv", index=False)

    cbp_comparison = pd.DataFrame()
    if cbp_comparison_path is not None and cbp_comparison_path.exists():
        cbp_comparison = pd.read_csv(
            cbp_comparison_path,
            dtype={"county_fips": str, "state_fips": str},
        )
        cbp_comparison.to_csv(release_dir / "cbp_comparison.csv", index=False)
    metadata = {
        "version": version,
        "release_status": "preliminary",
        "release_ready": False,
        "run_id": run_metadata.get("run_id", run_dir.name),
        "parser_version": run_metadata.get("parser_version", __version__),
        "directory_years": sorted(expected_years),
        "survey_years": sorted(facilities["survey_year"].astype(int).unique().tolist()),
        "source_formats": sorted(facilities["source_format"].unique().tolist()),
        "facility_rows": int(len(facilities)),
        "service_rows": int(len(services)),
        "reviewed_listings": int(sum(reviewed.values())),
        "limitations": [
            "Manual year-level gold-sample review is incomplete.",
            "Counts, addresses, and service classifications may change during QA.",
            "Historical phone numbers may be stale and must not be used to locate current care.",
            "N-SSATS and N-SUMHSS are not directly trend-comparable across the 2020/2021 transition.",
        ],
    }
    (release_dir / "release_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    _write_data_dictionary(
        {
            "facilities": facilities,
            "facility_services": services,
            "service_availability": availability,
            "qa_by_year": qa_by_year,
            **({"cbp_comparison": cbp_comparison} if not cbp_comparison.empty else {}),
        },
        release_dir,
    )
    _write_checksums(release_dir)
    return metadata

def materialize_service_status(
    facilities: pd.DataFrame,
    offered: pd.DataFrame,
    availability: pd.DataFrame,
) -> pd.DataFrame:
    listing_years = facilities[["listing_id", "directory_year", "survey_year"]]
    reference = (
        availability.sort_values("asked", ascending=False)
        .drop_duplicates("code")[["code", "category", "label"]]
    )
    status = listing_years.merge(reference, how="cross")
    asked = (
        availability.loc[
            availability["asked"],
            ["directory_year", "survey_year", "code"],
        ]
        .drop_duplicates()
        .assign(asked=True)
    )
    status = status.merge(
        asked,
        on=["directory_year", "survey_year", "code"],
        how="left",
    )
    offered_keys = offered[["listing_id", "code"]].drop_duplicates().assign(offered=True)
    status = status.merge(offered_keys, on=["listing_id", "code"], how="left")
    status["status"] = np.select(
        [
            status["offered"].eq(True),
            status["asked"].eq(True),
        ],
        ["offered", "not_offered"],
        default="not_asked",
    )
    return status.drop(columns=["offered", "asked"])


def build_release(
    interim_dir: Path,
    release_dir: Path,
    gold_path: Path,
    geocoding_path: Path | None = None,
    linkage_review_accuracy: float | None = None,
    include_full_service_status: bool = False,
    expected_counts_path: Path | None = None,
) -> dict[str, object]:
    facilities = _read_year_files(interim_dir, "facilities")
    offered = _read_year_files(interim_dir, "facility_services")
    availability = _read_year_files(interim_dir, "service_availability")
    if facilities.empty:
        raise RuntimeError("No parsed facility files were found in the interim directory.")

    linkage = link_facilities(facilities)
    facilities = facilities.drop(columns=["facility_id"], errors="ignore").merge(
        linkage[["listing_id", "facility_id"]], on="listing_id", how="left"
    )
    geocoding = None
    if geocoding_path is not None and geocoding_path.exists():
        geocoding = pd.read_csv(geocoding_path, dtype=str)
        geo_cols = [
            "listing_id",
            "county_fips",
            "latitude",
            "longitude",
            "geocode_method",
            "geocode_confidence",
        ]
        facilities = facilities.drop(columns=geo_cols[1:], errors="ignore").merge(
            geocoding[[col for col in geo_cols if col in geocoding.columns]],
            on="listing_id",
            how="left",
        )

    annual, report = build_qa_report(
        facilities,
        offered,
        gold_path,
        geocoding,
        linkage_review_accuracy,
        expected_counts_path,
    )
    release_dir.mkdir(parents=True, exist_ok=True)
    write_qa(annual, report, release_dir)

    facilities.to_csv(release_dir / "facilities.csv.gz", index=False, compression="gzip")
    facilities.to_parquet(release_dir / "facilities.parquet", index=False)
    for survey_year, year_rows in facilities.groupby("survey_year", sort=True):
        year_rows.to_csv(
            release_dir / f"facilities_{int(survey_year)}.csv.gz",
            index=False,
            compression="gzip",
        )
    offered.to_csv(
        release_dir / "facility_services.csv.gz", index=False, compression="gzip"
    )
    offered.to_parquet(release_dir / "facility_services.parquet", index=False)
    availability.drop_duplicates().to_csv(
        release_dir / "service_availability.csv", index=False
    )
    linkage.to_csv(release_dir / "facility_entities.csv", index=False)
    if geocoding is not None:
        geocoding.to_csv(release_dir / "geocoding_results.csv", index=False)
    service_status = pd.DataFrame()
    if include_full_service_status:
        service_status = materialize_service_status(facilities, offered, availability)
        service_status.to_parquet(
            release_dir / "facility_service_status.parquet", index=False
        )

    manifest = pd.DataFrame([row.__dict__ for row in load_manifest()])
    manifest.to_csv(release_dir / "source_manifest.csv", index=False)
    tables = {
        "facilities": facilities,
        "facility_services": offered,
        "service_availability": availability,
        "facility_entities": linkage,
    }
    if not service_status.empty:
        tables["facility_service_status"] = service_status
    if geocoding is not None:
        tables["geocoding_results"] = geocoding
    _write_data_dictionary(tables, release_dir)
    _write_checksums(release_dir)
    return report


def write_dashboard_status(release_dir: Path, output_dir: Path) -> None:
    report_path = release_dir / "qa_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    output_dir.mkdir(parents=True, exist_ok=True)
    status = {
        "release_ready": bool(report.get("release_ready", False)),
        "version": "v0.1.0",
        "blocking_reasons": report.get("blocking_reasons", ["release has not been built"]),
    }
    (output_dir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
