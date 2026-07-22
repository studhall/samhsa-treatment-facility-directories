from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from . import __version__
from .manifest import sha256_file
from .normalize import VALID_STATE_CODES, clean_text, geography_fields
from .parser import _derived_fields
from .runs import REQUIRED_YEAR_FILES, validate_complete_run, write_run_status


FACILITY_COLUMNS = [
    "name1", "name2", "street1", "street2", "city", "state", "zip", "phone",
    "intake1", "intake2", "intake1a", "intake2a", "service_code_info",
]
CODEBOOK_COLUMNS = [
    "category_code", "category_name", "service_code", "service_name",
    "service_description",
]


@dataclass(frozen=True)
class WorkbookConfig:
    directory_year: int
    survey_year: int
    filename: str
    source_url: str
    sha256: str
    facility_sheet: str
    codebook_sheet: str
    expected_facilities: int

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "WorkbookConfig":
        return cls(
            directory_year=int(row["directory_year"]),
            survey_year=int(row["survey_year"]),
            filename=row["filename"],
            source_url=row["source_url"],
            sha256=row["sha256"],
            facility_sheet=row["facility_sheet"],
            codebook_sheet=row["codebook_sheet"],
            expected_facilities=int(row["expected_facilities"]),
        )


def default_xlsx_manifest_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "xlsx_manifest.csv"


def load_xlsx_manifest(path: Path | None = None) -> list[WorkbookConfig]:
    manifest_path = path or default_xlsx_manifest_path()
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        return [WorkbookConfig.from_row(row) for row in csv.DictReader(handle)]


def verify_xlsx_manifest(
    xlsx_dir: Path, manifest_path: Path | None = None
) -> list[dict[str, object]]:
    rows = []
    for config in load_xlsx_manifest(manifest_path):
        path = xlsx_dir / config.filename
        observed = sha256_file(path) if path.exists() else ""
        rows.append(
            {
                "directory_year": config.directory_year,
                "filename": config.filename,
                "exists": path.exists(),
                "expected_sha256": config.sha256,
                "observed_sha256": observed,
                "checksum_ok": bool(path.exists() and observed == config.sha256),
            }
        )
    return rows


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output.columns = [str(column).strip().lower() for column in output.columns]
    return output


def _text(value: object) -> str:
    return clean_text("" if pd.isna(value) else str(value))


def _zip(value: object) -> str:
    text = _text(value)
    return text[:-2] if text.endswith(".0") and text[:-2].isdigit() else text


def _id(prefix: str, *parts: object) -> str:
    key = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha1(key.encode("utf-8")).hexdigest()[:19]


def import_workbook(
    workbook_path: Path, config: WorkbookConfig
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    started = time.perf_counter()
    facilities_raw = _normalize_columns(
        pd.read_excel(workbook_path, sheet_name=config.facility_sheet, dtype=str)
    ).fillna("")
    codebook_raw = _normalize_columns(
        pd.read_excel(workbook_path, sheet_name=config.codebook_sheet, dtype=str)
    ).fillna("")
    if list(facilities_raw.columns) != FACILITY_COLUMNS:
        raise ValueError(
            f"Unexpected facility columns for {config.directory_year}: "
            f"{list(facilities_raw.columns)}"
        )
    if list(codebook_raw.columns) != CODEBOOK_COLUMNS:
        raise ValueError(
            f"Unexpected codebook columns for {config.directory_year}: "
            f"{list(codebook_raw.columns)}"
        )

    codebook_raw["service_code"] = codebook_raw["service_code"].map(_text)
    codebook_raw = codebook_raw.loc[codebook_raw["service_code"].ne("")].copy()
    duplicate_codes = sorted(
        codebook_raw.loc[
            codebook_raw["service_code"].duplicated(keep=False), "service_code"
        ].unique()
    )
    codebook = {
        row.service_code: row
        for row in codebook_raw.drop_duplicates("service_code").itertuples(index=False)
    }

    facilities = []
    services = []
    all_unknown: set[str] = set()
    for source_row, row in enumerate(facilities_raw.itertuples(index=False), start=2):
        values = {column: _text(getattr(row, column)) for column in FACILITY_COLUMNS}
        values["zip"] = _zip(getattr(row, "zip"))
        state = values["state"].upper()
        tokens = [token for token in values["service_code_info"].split() if token != "*"]
        known = [token for token in tokens if token in codebook]
        unknown = sorted(set(tokens) - set(known))
        all_unknown.update(unknown)
        warnings = []
        if not values["name1"]:
            warnings.append("missing_facility_name")
        if not values["street1"]:
            warnings.append("missing_street_address")
        if state not in VALID_STATE_CODES:
            warnings.append("invalid_state")
        if unknown:
            warnings.append("unknown_service_tokens")

        listing_id = _id("L", config.directory_year, source_row)
        location = f"{values['city']}, {state} {values['zip']}".strip()
        intake = [
            values[name]
            for name in ["intake1", "intake2", "intake1a", "intake2a"]
            if values[name]
        ]
        facility = {
            "listing_id": listing_id,
            "source_anchor_id": _id(
                "A", config.directory_year, config.facility_sheet, source_row
            ),
            "source_location_anchor": location.upper(),
            "source_anchor_occurrence": 1,
            "source_record_order": source_row - 1,
            "facility_id": "",
            "directory_year": config.directory_year,
            "survey_year": config.survey_year,
            "directory_city_header": values["city"],
            "name1": values["name1"],
            "name2": values["name2"],
            "address1": values["street1"],
            "address2": values["street2"],
            "city": values["city"],
            "state": state,
            "zip": values["zip"],
            "phone": values["phone"],
            "intake_phone": " | ".join(intake),
            "intake1": values["intake1"],
            "intake2": values["intake2"],
            "intake1a": values["intake1a"],
            "intake2a": values["intake2a"],
            "county_fips": "",
            "latitude": pd.NA,
            "longitude": pd.NA,
            "geocode_method": "",
            "geocode_confidence": "",
            "source_pdf": "",
            "source_file": workbook_path.name,
            "source_format": "official_xlsx",
            "source_sheet": config.facility_sheet,
            "source_row": source_row,
            "source_page": pd.NA,
            "source_column": pd.NA,
            "raw_record_text": "\n".join(
                value
                for value in [
                    values["name1"], values["name2"], values["street1"],
                    values["street2"], location, values["phone"],
                ]
                if value
            ),
            "raw_service_text": values["service_code_info"],
            "parser_warnings": json.dumps(warnings),
            **geography_fields(state),
            "unknown_service_tokens": json.dumps(unknown),
            "service_codes": " ".join(sorted(set(known))),
            **_derived_fields(set(known)),
        }
        facilities.append(facility)
        for code in dict.fromkeys(known):
            reference = codebook[code]
            services.append(
                {
                    "listing_id": listing_id,
                    "directory_year": config.directory_year,
                    "survey_year": config.survey_year,
                    "group_index": _text(reference.category_code),
                    "code": code,
                    "category": _text(reference.category_name),
                    "label": _text(reference.service_name),
                    "known_code": True,
                    "status": "offered",
                    "source_file": workbook_path.name,
                    "source_sheet": config.facility_sheet,
                    "source_row": source_row,
                }
            )

    facilities_frame = pd.DataFrame(facilities)
    services_frame = pd.DataFrame(services)
    availability = pd.DataFrame(
        {
            "directory_year": config.directory_year,
            "survey_year": config.survey_year,
            "category": codebook_raw["category_name"].map(_text),
            "code": codebook_raw["service_code"],
            "label": codebook_raw["service_name"].map(_text),
            "description": codebook_raw["service_description"].map(_text),
            "asked": True,
            "source": "xlsx_code_reference",
            "source_file": workbook_path.name,
            "source_sheet": config.codebook_sheet,
        }
    )

    invalid_states = int((~facilities_frame["state"].isin(VALID_STATE_CODES)).sum())
    coverage = services_frame["listing_id"].nunique() / max(len(facilities_frame), 1)
    blocking = []
    if invalid_states:
        blocking.append(f"{invalid_states} invalid state codes")
    if duplicate_codes:
        blocking.append(f"duplicate codebook codes: {duplicate_codes}")
    if all_unknown:
        blocking.append(f"unknown service tokens: {sorted(all_unknown)}")
    if len(facilities_frame) != config.expected_facilities:
        blocking.append(
            f"expected {config.expected_facilities} rows; found {len(facilities_frame)}"
        )
    if coverage < 0.99:
        blocking.append(f"service coverage is {coverage:.1%}")

    metrics = {
        "directory_year": config.directory_year,
        "survey_year": config.survey_year,
        "layout_profile": "official_xlsx",
        "source_format": "official_xlsx",
        "source_filename": workbook_path.name,
        "source_sha256": sha256_file(workbook_path),
        "parser_version": __version__,
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "facility_rows": len(facilities_frame),
        "service_rows": len(services_frame),
        "availability_rows": len(availability),
        "states": sorted(facilities_frame["state"].unique().tolist()),
        "state_count": int(facilities_frame["state"].nunique()),
        "invalid_state_records": invalid_states,
        "warning_records": int(facilities_frame["parser_warnings"].ne("[]").sum()),
        "warning_rate": float(facilities_frame["parser_warnings"].ne("[]").mean()),
        "unknown_tokens": sorted(all_unknown),
        "unknown_token_count": len(all_unknown),
        "service_coverage": coverage,
        "comparison_expected_count": config.expected_facilities,
        "comparison_count_difference_share": (
            abs(len(facilities_frame) - config.expected_facilities)
            / config.expected_facilities
        ),
        "structural_pass": not blocking,
        "blocking_reasons": blocking,
    }
    return {
        "facilities": facilities_frame,
        "facility_services": services_frame,
        "service_availability": availability,
    }, metrics


def _write_year_atomic(
    run_dir: Path,
    config: WorkbookConfig,
    frames: dict[str, pd.DataFrame],
    metrics: dict[str, object],
) -> None:
    years_dir = run_dir / "years"
    years_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{config.directory_year}-", dir=years_dir))
    target = years_dir / str(config.directory_year)
    try:
        for name, frame in frames.items():
            frame.to_csv(temporary / f"{name}.csv", index=False)
            frame.to_parquet(temporary / f"{name}.parquet", index=False)
        (temporary / "metadata.json").write_text(
            json.dumps(metrics, indent=2), encoding="utf-8"
        )
        (temporary / "status.json").write_text(
            json.dumps(
                {
                    "directory_year": config.directory_year,
                    "state": "complete",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "structural_pass": metrics["structural_pass"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if target.exists():
            shutil.rmtree(target)
        temporary.replace(target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def import_xlsx_all(
    xlsx_dir: Path,
    run_dir: Path,
    manifest_path: Path | None = None,
    resume: bool = False,
) -> dict[str, object]:
    configs = load_xlsx_manifest(manifest_path)
    verification = verify_xlsx_manifest(xlsx_dir, manifest_path)
    failed = [row["directory_year"] for row in verification if not row["checksum_ok"]]
    if failed:
        raise ValueError(
            "Workbook manifest verification failed for directory years: "
            + ", ".join(map(str, failed))
        )
    run_path = run_dir / "run.json"
    if not run_path.exists():
        raise FileNotFoundError("Import the workbooks into an existing complete PDF run.")
    run_metadata = json.loads(run_path.read_text(encoding="utf-8"))
    imported = []
    for config in configs:
        target = run_dir / "years" / str(config.directory_year)
        metadata_path = target / "metadata.json"
        if resume and all((target / name).exists() for name in REQUIRED_YEAR_FILES):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("source_sha256") == config.sha256:
                imported.append(config.directory_year)
                continue
        frames, metrics = import_workbook(xlsx_dir / config.filename, config)
        if not metrics["structural_pass"]:
            raise RuntimeError(
                f"Workbook {config.directory_year} failed structural QA: "
                + "; ".join(metrics["blocking_reasons"])
            )
        _write_year_atomic(run_dir, config, frames, metrics)
        imported.append(config.directory_year)

    existing = {int(year) for year in run_metadata.get("expected_years", [])}
    all_years = sorted(existing | {config.directory_year for config in configs})
    run_metadata["expected_years"] = all_years
    run_metadata["xlsx_dir"] = str(xlsx_dir.resolve())
    run_metadata["xlsx_manifest_path"] = str(
        (manifest_path or default_xlsx_manifest_path()).resolve()
    )
    run_metadata["source_formats"] = ["historical_pdf", "official_xlsx"]
    run_metadata["updated_at"] = datetime.now(UTC).isoformat()
    errors = validate_complete_run(run_dir, all_years)
    run_metadata["complete"] = not errors
    run_metadata["blocking_reasons"] = errors
    write_run_status(run_dir, run_metadata)
    return {
        "run_dir": str(run_dir),
        "imported_directory_years": imported,
        "expected_years": len(all_years),
        "complete": not errors,
        "blocking_reasons": errors,
    }
