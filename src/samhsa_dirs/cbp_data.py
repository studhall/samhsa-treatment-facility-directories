from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from .cbp import TREATMENT_NAICS


CBP_BASE_URL = "https://www2.census.gov/programs-surveys/cbp/datasets"


def cbp_county_url(year: int) -> str:
    return f"{CBP_BASE_URL}/{year}/cbp{str(year)[-2:]}co.zip"


def download_cbp_county_files(
    output_dir: Path,
    start_year: int = 1998,
    end_year: int = 2023,
    resume: bool = True,
) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for year in range(start_year, end_year + 1):
        url = cbp_county_url(year)
        destination = output_dir / f"cbp{str(year)[-2:]}co.zip"
        if resume and destination.exists() and destination.stat().st_size > 0:
            results.append(
                {
                    "year": year,
                    "url": url,
                    "path": str(destination),
                    "bytes": destination.stat().st_size,
                    "downloaded": False,
                }
            )
            continue
        temporary = destination.with_suffix(".zip.part")
        with requests.get(url, timeout=180, stream=True) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        temporary.replace(destination)
        results.append(
            {
                "year": year,
                "url": url,
                "path": str(destination),
                "bytes": destination.stat().st_size,
                "downloaded": True,
            }
        )
    return results


def read_cbp_county_archive(path: Path, year: int) -> pd.DataFrame:
    raw = pd.read_csv(
        path,
        dtype={"fipstate": str, "fipscty": str, "naics": str},
        low_memory=False,
    )
    raw.columns = [str(column).lower() for column in raw.columns]
    required = {"fipstate", "fipscty", "naics", "est"}
    if missing := required - set(raw):
        raise ValueError(f"{path.name} is missing columns: {sorted(missing)}")
    raw["state_fips"] = raw["fipstate"].astype(str).str.zfill(2)
    raw["county_fips"] = raw["state_fips"] + raw["fipscty"].astype(str).str.zfill(3)
    raw["naics"] = raw["naics"].astype(str).str.strip()
    raw["establishments"] = pd.to_numeric(raw["est"], errors="coerce")

    universe = (
        raw.loc[raw["naics"].eq("------"), ["county_fips", "state_fips"]]
        .drop_duplicates()
        .sort_values("county_fips")
    )
    grid = universe.merge(
        pd.DataFrame({"naics": sorted(TREATMENT_NAICS)}), how="cross"
    )
    observed = raw.loc[
        raw["naics"].isin(TREATMENT_NAICS),
        ["county_fips", "state_fips", "naics", "establishments"],
    ].drop_duplicates(["county_fips", "naics"])
    cells = grid.merge(
        observed,
        on=["county_fips", "state_fips", "naics"],
        how="left",
    )
    cells["year"] = year
    cells["publication_status"] = "published"
    missing = cells["establishments"].isna()
    cells.loc[missing & (year <= 2016), "publication_status"] = "zero"
    cells.loc[missing & (year <= 2016), "establishments"] = 0
    cells.loc[missing & (year >= 2017), "publication_status"] = "omitted_or_zero"
    return cells[
        [
            "county_fips",
            "state_fips",
            "year",
            "naics",
            "establishments",
            "publication_status",
        ]
    ]


def build_cbp_cells_from_archives(
    raw_dir: Path,
    start_year: int = 1998,
    end_year: int = 2023,
) -> pd.DataFrame:
    frames = []
    missing = []
    for year in range(start_year, end_year + 1):
        path = raw_dir / f"cbp{str(year)[-2:]}co.zip"
        if not path.exists():
            missing.append(year)
            continue
        frames.append(read_cbp_county_archive(path, year))
    if missing:
        raise FileNotFoundError(
            "Missing CBP county archives for years: " + ", ".join(map(str, missing))
        )
    return pd.concat(frames, ignore_index=True)


def summarize_cbp_comparison(comparison: pd.DataFrame) -> pd.DataFrame:
    frame = comparison.copy()
    frame["cbp_available"] = frame["publication_status"].notna()
    summary = (
        frame.groupby("year", dropna=False)
        .agg(
            samhsa_count=("samhsa_count", "sum"),
            cbp_published_count=("cbp_count", lambda values: values.sum(min_count=1)),
            cbp_lower_bound=("lower_bound", lambda values: values.sum(min_count=1)),
            cbp_upper_bound=("upper_bound", lambda values: values.sum(min_count=1)),
            published_counties=("common_support", "sum"),
            compared_counties=("cbp_available", "sum"),
        )
        .reset_index()
    )
    denominator = pd.to_numeric(summary["compared_counties"], errors="coerce").replace(
        0, float("nan")
    )
    summary["county_coverage_rate"] = pd.to_numeric(summary["published_counties"]) / denominator
    summary["reporting_break"] = summary["year"].astype(int).ge(2017)
    return summary
