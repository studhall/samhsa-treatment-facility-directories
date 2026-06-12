from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .linkage import link_facilities
from .manifest import load_manifest
from .qa import build_qa_report, write_qa


def _read_year_files(interim_dir: Path, stem: str) -> pd.DataFrame:
    files = sorted(interim_dir.glob(f"{stem}_*.parquet"))
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True) if files else pd.DataFrame()


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
        if not path.is_file() or path.name == "checksums.sha256":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{digest}  {path.name}")
    (release_dir / "checksums.sha256").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )


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
