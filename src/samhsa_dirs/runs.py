from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pdfplumber

from . import __version__
from .manifest import YearConfig, load_manifest, sha256_file, verify_manifest
from .normalize import VALID_STATE_CODES
from .parser import HEADER_NOISE_RE, parse_pdf


CALIBRATION_WAVES = [
    [1998, 2000, 2001, 2003, 2004, 2017, 2018, 2021],
    list(range(2005, 2017)),
    [2019, 2020],
]

REQUIRED_YEAR_FILES = [
    "facilities.csv",
    "facilities.parquet",
    "facility_services.csv",
    "facility_services.parquet",
    "service_availability.csv",
    "service_availability.parquet",
    "metadata.json",
    "status.json",
]


def parser_signature() -> str:
    digest = hashlib.sha256()
    package_dir = Path(__file__).resolve().parent
    for filename in ["parser.py", "codes.py", "normalize.py", "manifest.py"]:
        digest.update(filename.encode("utf-8"))
        digest.update((package_dir / filename).read_bytes())
    manifest_path = package_dir.parents[1] / "config" / "year_manifest.csv"
    digest.update(manifest_path.read_bytes())
    return digest.hexdigest()


def default_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"run-{stamp}-v{__version__}"


def _json_list(series: pd.Series) -> list[str]:
    output: set[str] = set()
    for value in series.fillna(""):
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            parsed = [str(value)] if value else []
        output.update(str(item) for item in parsed if str(item))
    return sorted(output)


def structural_metrics(
    config: YearConfig,
    facilities: pd.DataFrame,
    services: pd.DataFrame,
    availability: pd.DataFrame,
    runtime_seconds: float,
    checksum: str,
    pdf_page_count: int,
    signature: str,
    expected_count: int | None,
) -> dict[str, object]:
    rows = len(facilities)
    invalid_states = (
        int((~facilities["state"].isin(VALID_STATE_CODES)).sum()) if rows else 0
    )
    header_records = (
        int(
            facilities["name1"]
            .fillna("")
            .str.contains(HEADER_NOISE_RE, regex=True)
            .sum()
        )
        if rows
        else 0
    )
    warning_records = (
        int(facilities["parser_warnings"].fillna("").ne("[]").sum()) if rows else 0
    )
    unknown_tokens = (
        _json_list(facilities["unknown_service_tokens"]) if rows else []
    )
    expected_pages = config.end_page - config.start_page + 1
    observed_pages = (
        sorted(int(value) for value in facilities["source_page"].dropna().unique())
        if rows
        else []
    )
    pages_with_records = len(observed_pages)
    page_coverage_complete = pdf_page_count >= config.end_page
    service_listings = (
        int(services["listing_id"].nunique()) if not services.empty else 0
    )
    missing_name_share = facilities["name1"].fillna("").eq("").mean() if rows else 1.0
    missing_address_share = (
        facilities["address1"].fillna("").eq("").mean() if rows else 1.0
    )
    weak_address_share = (
        facilities["parser_warnings"]
        .fillna("")
        .str.contains("weak_address_pattern")
        .mean()
        if rows
        else 1.0
    )
    service_coverage = service_listings / max(rows, 1)
    minimum_service_coverage = (
        0.60 if config.layout_profile == "early_ocr" else 0.80
    )
    blocking_reasons: list[str] = []
    if invalid_states:
        blocking_reasons.append(f"{invalid_states} malformed state records")
    if header_records:
        blocking_reasons.append(f"{header_records} parsed header records")
    if rows < 1000 or rows > 30000:
        blocking_reasons.append(f"implausible listing count: {rows}")
    if services.empty or service_listings == 0:
        blocking_reasons.append("empty service extraction")
    elif service_coverage < minimum_service_coverage:
        blocking_reasons.append(
            f"service coverage {service_coverage:.1%} is below "
            f"{minimum_service_coverage:.0%}"
        )
    if availability.empty:
        blocking_reasons.append("empty service availability")
    if not page_coverage_complete:
        blocking_reasons.append("PDF ends before the configured final page")
    if missing_name_share > 0.05:
        blocking_reasons.append(
            f"missing facility-name share is {missing_name_share:.1%}"
        )
    if missing_address_share > 0.01:
        blocking_reasons.append(
            f"missing address share is {missing_address_share:.1%}"
        )
    if weak_address_share > 0.25:
        blocking_reasons.append(
            f"weak-address warning share is {weak_address_share:.1%}"
        )
    count_difference_share = None
    if expected_count:
        count_difference_share = abs(rows - expected_count) / expected_count
        if count_difference_share > 0.35:
            blocking_reasons.append(
                "listing count differs from comparison fixture by "
                f"{count_difference_share:.1%}"
            )

    return {
        "directory_year": config.directory_year,
        "survey_year": config.survey_year,
        "layout_profile": config.layout_profile,
        "parser_version": __version__,
        "parser_signature": signature,
        "pdf_filename": config.filename,
        "pdf_sha256": checksum,
        "runtime_seconds": round(runtime_seconds, 3),
        "configured_start_page": config.start_page,
        "configured_end_page": config.end_page,
        "expected_page_count": expected_pages,
        "pdf_page_count": pdf_page_count,
        "processed_start_page": config.start_page,
        "processed_end_page": min(config.end_page, pdf_page_count),
        "page_coverage_complete": page_coverage_complete,
        "first_page_with_record": observed_pages[0] if observed_pages else None,
        "last_page_with_record": observed_pages[-1] if observed_pages else None,
        "pages_with_records": pages_with_records,
        "facility_rows": rows,
        "service_rows": len(services),
        "service_listings": service_listings,
        "availability_rows": len(availability),
        "states": sorted(facilities["state"].dropna().unique().tolist())
        if rows
        else [],
        "state_count": int(facilities["state"].nunique()) if rows else 0,
        "invalid_state_records": invalid_states,
        "header_records": header_records,
        "warning_records": warning_records,
        "warning_rate": warning_records / max(rows, 1),
        "missing_name_share": missing_name_share,
        "missing_address_share": missing_address_share,
        "weak_address_share": weak_address_share,
        "unknown_tokens": unknown_tokens,
        "unknown_token_count": len(unknown_tokens),
        "service_coverage": service_coverage,
        "minimum_service_coverage": minimum_service_coverage,
        "comparison_expected_count": expected_count,
        "comparison_count_difference_share": count_difference_share,
        "structural_pass": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
    }


def _write_frames(result: dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in result.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)


def _parse_one_year(payload: dict[str, object]) -> dict[str, object]:
    config = YearConfig(**payload["config"])
    pdf_path = Path(str(payload["pdf_path"]))
    year_dir = Path(str(payload["year_dir"]))
    checksum = str(payload["checksum"])
    signature = str(payload["parser_signature"])
    expected_count = payload.get("expected_count")
    started = time.perf_counter()
    year_dir.mkdir(parents=True, exist_ok=True)
    status_path = year_dir / "status.json"
    status_path.write_text(
        json.dumps(
            {
                "directory_year": config.directory_year,
                "state": "writing",
                "started_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pdf_page_count = len(pdf.pages)
        result = parse_pdf(pdf_path, config)
        metrics = structural_metrics(
            config,
            result["facilities"],
            result["facility_services"],
            result["service_availability"],
            time.perf_counter() - started,
            checksum,
            pdf_page_count,
            signature,
            int(expected_count) if expected_count else None,
        )
        _write_frames(result, year_dir)
        (year_dir / "metadata.json").write_text(
            json.dumps(metrics, indent=2), encoding="utf-8"
        )
        status_path.write_text(
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
        return metrics
    except Exception as error:
        failure = {
            "directory_year": config.directory_year,
            "survey_year": config.survey_year,
            "layout_profile": config.layout_profile,
            "parser_version": __version__,
            "parser_signature": signature,
            "pdf_filename": config.filename,
            "pdf_sha256": checksum,
            "structural_pass": False,
            "blocking_reasons": [f"{type(error).__name__}: {error}"],
        }
        status_path.write_text(
            json.dumps(
                {
                    "directory_year": config.directory_year,
                    "state": "failed",
                    "failed_at": datetime.now(UTC).isoformat(),
                    **failure,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return failure


def year_is_resumable(
    year_dir: Path, config: YearConfig, checksum: str, signature: str
) -> bool:
    if not all((year_dir / name).exists() for name in REQUIRED_YEAR_FILES):
        return False
    try:
        metadata = json.loads((year_dir / "metadata.json").read_text(encoding="utf-8"))
        status = json.loads((year_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        status.get("state") == "complete"
        and
        metadata.get("parser_version") == __version__
        and metadata.get("parser_signature") == signature
        and metadata.get("pdf_sha256") == checksum
        and int(metadata.get("directory_year", -1)) == config.directory_year
    )


def load_run_status(run_dir: Path) -> pd.DataFrame:
    rows = []
    for year_dir in sorted((run_dir / "years").glob("[0-9][0-9][0-9][0-9]")):
        metadata_path = year_dir / "metadata.json"
        status_path = year_dir / "status.json"
        if metadata_path.exists():
            rows.append(json.loads(metadata_path.read_text(encoding="utf-8")))
        elif status_path.exists():
            rows.append(json.loads(status_path.read_text(encoding="utf-8")))
    return pd.DataFrame(rows)


def write_run_status(run_dir: Path, metadata: dict[str, object]) -> pd.DataFrame:
    frame = load_run_status(run_dir)
    if not frame.empty:
        frame = frame.sort_values("directory_year")
        serializable = frame.copy()
        for column in ["states", "unknown_tokens", "blocking_reasons"]:
            if column in serializable:
                serializable[column] = serializable[column].map(json.dumps)
        serializable.to_csv(run_dir / "run_status.csv", index=False)
    (run_dir / "run.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return frame


def validate_complete_run(run_dir: Path, expected_years: list[int]) -> list[str]:
    errors: list[str] = []
    for year in expected_years:
        year_dir = run_dir / "years" / str(year)
        missing = [name for name in REQUIRED_YEAR_FILES if not (year_dir / name).exists()]
        if missing:
            errors.append(f"{year}: missing {', '.join(missing)}")
            continue
        metadata = json.loads((year_dir / "metadata.json").read_text(encoding="utf-8"))
        status = json.loads((year_dir / "status.json").read_text(encoding="utf-8"))
        if status.get("state") != "complete":
            errors.append(f"{year}: year write did not reach the complete state")
            continue
        if not metadata.get("structural_pass"):
            reasons = "; ".join(metadata.get("blocking_reasons", []))
            errors.append(f"{year}: structural QA failed ({reasons})")
    return errors


def parse_all(
    pdf_dir: Path,
    run_dir: Path,
    manifest_path: Path | None = None,
    resume: bool = False,
    workers: int = 2,
    selected_years: set[int] | None = None,
) -> dict[str, object]:
    configs = load_manifest(manifest_path)
    expected_years = [config.directory_year for config in configs]
    verification = verify_manifest(pdf_dir, manifest_path)
    bad_checksums = [
        row["directory_year"] for row in verification if not row["checksum_ok"]
    ]
    if bad_checksums:
        raise ValueError(
            "Manifest verification failed for directory years: "
            + ", ".join(str(year) for year in bad_checksums)
        )
    checksums = {
        int(row["directory_year"]): str(row["observed_sha256"])
        for row in verification
    }
    signature = parser_signature()
    config_by_year = {config.directory_year: config for config in configs}
    if selected_years:
        unknown_years = sorted(selected_years - set(config_by_year))
        if unknown_years:
            raise ValueError(
                "Requested years are absent from the manifest: "
                + ", ".join(str(year) for year in unknown_years)
            )
    expected_counts_path = (
        Path(__file__).resolve().parents[2] / "config" / "expected_counts.csv"
    )
    expected_counts: dict[int, int] = {}
    if expected_counts_path.exists():
        expected_frame = pd.read_csv(expected_counts_path)
        expected_counts = {
            int(row.directory_year): int(row.expected_listings)
            for row in expected_frame.itertuples(index=False)
            if pd.notna(row.expected_listings)
        }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "years").mkdir(exist_ok=True)
    run_metadata: dict[str, object] = {
        "run_id": run_dir.name,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "parser_version": __version__,
        "parser_signature": signature,
        "pdf_dir": str(pdf_dir.resolve()),
        "manifest_path": str(
            (manifest_path or Path(__file__).resolve().parents[2] / "config" / "year_manifest.csv").resolve()
        ),
        "expected_years": expected_years,
        "calibration_waves": CALIBRATION_WAVES,
        "workers": workers,
        "selected_years": sorted(selected_years) if selected_years else expected_years,
        "complete": False,
    }
    write_run_status(run_dir, run_metadata)

    for wave_number, years in enumerate(CALIBRATION_WAVES, start=1):
        payloads = []
        for year in years:
            if selected_years and year not in selected_years:
                continue
            config = config_by_year[year]
            year_dir = run_dir / "years" / str(year)
            if resume and year_is_resumable(
                year_dir, config, checksums[year], signature
            ):
                continue
            payloads.append(
                {
                    "config": asdict(config),
                    "pdf_path": str(pdf_dir / config.filename),
                    "year_dir": str(year_dir),
                    "checksum": checksums[year],
                    "parser_signature": signature,
                    "expected_count": expected_counts.get(year),
                }
            )
        if payloads:
            if workers == 1:
                results = (_parse_one_year(payload) for payload in payloads)
                for result in results:
                    print(
                        f"Wave {wave_number}: {result['directory_year']} "
                        f"{'passed' if result.get('structural_pass') else 'blocked'}"
                    )
                    run_metadata["updated_at"] = datetime.now(UTC).isoformat()
                    write_run_status(run_dir, run_metadata)
            else:
                with ProcessPoolExecutor(max_workers=workers) as executor:
                    futures = {
                        executor.submit(_parse_one_year, payload): int(
                            payload["config"]["directory_year"]
                        )
                        for payload in payloads
                    }
                    for future in as_completed(futures):
                        result = future.result()
                        print(
                            f"Wave {wave_number}: {result['directory_year']} "
                            f"{'passed' if result.get('structural_pass') else 'blocked'}"
                        )
                        run_metadata["updated_at"] = datetime.now(UTC).isoformat()
                        write_run_status(run_dir, run_metadata)

    errors = validate_complete_run(run_dir, expected_years)
    run_metadata["updated_at"] = datetime.now(UTC).isoformat()
    run_metadata["complete"] = not errors
    run_metadata["blocking_reasons"] = errors
    status = write_run_status(run_dir, run_metadata)
    return {
        "run_dir": str(run_dir),
        "expected_years": len(expected_years),
        "parsed_years": int(len(status)),
        "complete": not errors,
        "blocking_reasons": errors,
    }


def latest_run(runs_dir: Path) -> Path | None:
    candidates = sorted(
        (path for path in runs_dir.glob("run-*") if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )
    return candidates[0] if candidates else None
