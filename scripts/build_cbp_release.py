from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from samhsa_dirs.cbp import build_cbp_comparison
from samhsa_dirs.cbp_data import summarize_cbp_comparison


def read_table(path: Path, **kwargs) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--facilities", type=Path, required=True)
    parser.add_argument("--geocoding", type=Path, required=True)
    parser.add_argument("--cbp-cells", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    facilities = read_table(args.facilities)
    geography = read_table(
        args.geocoding,
        dtype={"listing_id": str, "county_fips": str},
    )[["listing_id", "county_fips"]].drop_duplicates("listing_id")
    facilities = facilities.drop(columns=["county_fips"], errors="ignore").merge(
        geography,
        on="listing_id",
        how="left",
    )
    facilities["county_fips"] = facilities["county_fips"].fillna("").astype(str).str.zfill(5)
    facilities.loc[facilities["county_fips"].eq("00000"), "county_fips"] = ""
    assigned = facilities.loc[facilities["county_fips"].str.fullmatch(r"\d{5}")].copy()
    assigned["state_fips"] = assigned["county_fips"].str[:2]
    assigned["year"] = assigned["survey_year"].astype(int)
    counts = (
        assigned.groupby(["county_fips", "state_fips", "year"])
        .size()
        .rename("samhsa_count")
        .reset_index()
    )

    cbp_cells = read_table(args.cbp_cells)
    comparison = build_cbp_comparison(counts, cbp_cells)
    summary = summarize_cbp_comparison(comparison)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    counts.to_csv(args.output_dir / "samhsa_county_counts.csv", index=False)
    comparison.to_csv(args.output_dir / "cbp_comparison.csv", index=False)
    comparison.to_parquet(args.output_dir / "cbp_comparison.parquet", index=False)
    summary.to_csv(args.output_dir / "cbp_national_summary.csv", index=False)
    print(
        f"Wrote {len(comparison):,} county-year comparisons "
        f"for {comparison['year'].nunique()} survey years."
    )


if __name__ == "__main__":
    main()
