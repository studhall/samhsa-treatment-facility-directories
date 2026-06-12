from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class YearConfig:
    directory_year: int
    survey_year: int
    filename: str
    source_url: str
    sha256: str
    start_page: int
    end_page: int
    n_columns: int
    layout_profile: str
    delimiter: str
    margin: float
    overlap: float
    crop_top: float
    crop_bottom: float
    expected_category_count: int

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "YearConfig":
        integer_fields = {
            "directory_year",
            "survey_year",
            "start_page",
            "end_page",
            "n_columns",
            "expected_category_count",
        }
        float_fields = {"margin", "overlap", "crop_top", "crop_bottom"}
        values: dict[str, object] = dict(row)
        for field in integer_fields:
            values[field] = int(row[field])
        for field in float_fields:
            values[field] = float(row[field])
        return cls(**values)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_manifest_path() -> Path:
    return repository_root() / "config" / "year_manifest.csv"


def load_manifest(path: Path | None = None) -> list[YearConfig]:
    manifest_path = path or default_manifest_path()
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        return [YearConfig.from_row(row) for row in csv.DictReader(handle)]


def select_year(
    directory_year: int, manifest: list[YearConfig] | None = None
) -> YearConfig:
    rows = manifest or load_manifest()
    for row in rows:
        if row.directory_year == directory_year:
            return row
    raise KeyError(f"No manifest configuration for directory year {directory_year}.")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(pdf_dir: Path, manifest_path: Path | None = None) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for config in load_manifest(manifest_path):
        pdf_path = pdf_dir / config.filename
        exists = pdf_path.exists()
        observed = sha256_file(pdf_path) if exists else ""
        results.append(
            {
                "directory_year": config.directory_year,
                "filename": config.filename,
                "exists": exists,
                "expected_sha256": config.sha256,
                "observed_sha256": observed,
                "checksum_ok": exists and observed.lower() == config.sha256.lower(),
            }
        )
    return results

