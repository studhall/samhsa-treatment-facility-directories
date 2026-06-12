from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", default="release")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    release_dir = Path(args.release_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    qa = json.loads((release_dir / "qa_report.json").read_text(encoding="utf-8"))
    if not qa.get("release_ready"):
        raise SystemExit("Dashboard exports are blocked until qa_report.json is release-ready.")

    facilities = pd.read_parquet(release_dir / "facilities.parquet")
    services = pd.read_parquet(release_dir / "facility_services.parquet")
    facilities = facilities.loc[facilities["headline_us"].eq("yes")].copy()

    scopes = []
    for scope_type, field in [
        ("United States", None),
        ("Census region", "census_region"),
        ("Census division", "census_division"),
        ("Pacific Northwest", "pnw"),
    ]:
        data = facilities.assign(scope="United States") if field is None else facilities.assign(scope=facilities[field])
        scopes.append(
            data.groupby(
                ["survey_year", "scope", "ownership_type", "center_types", "care_settings"],
                dropna=False,
            )
            .size()
            .reset_index(name="facility_count")
            .assign(scope_type=scope_type)
        )
    pd.concat(scopes, ignore_index=True).to_csv(output_dir / "overview.csv", index=False)

    offered_codes = (
        services.groupby("listing_id")["code"].apply(lambda x: " ".join(sorted(set(x)))).rename("service_codes")
    )
    map_rows = facilities.merge(offered_codes, on="listing_id", how="left")
    map_cols = [
        "listing_id",
        "survey_year",
        "county_fips",
        "state",
        "ownership_type",
        "center_types",
        "care_settings",
        "service_codes",
    ]
    for year, group in map_rows.groupby("survey_year"):
        group[map_cols].to_csv(output_dir / f"county_facilities_{int(year)}.csv.gz", index=False, compression="gzip")

    status = {"release_ready": True, "version": "v0.1.0", "blocking_reasons": []}
    (output_dir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

