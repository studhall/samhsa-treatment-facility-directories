from __future__ import annotations

import pandas as pd


TREATMENT_NAICS = {"621420", "623220"}


def build_cbp_comparison(
    samhsa_counts: pd.DataFrame,
    cbp_cells: pd.DataFrame,
) -> pd.DataFrame:
    required_samhsa = {"county_fips", "state_fips", "year", "samhsa_count"}
    required_cbp = {
        "county_fips",
        "state_fips",
        "year",
        "naics",
        "establishments",
        "publication_status",
    }
    if missing := required_samhsa - set(samhsa_counts):
        raise ValueError(f"SAMHSA counts missing columns: {sorted(missing)}")
    if missing := required_cbp - set(cbp_cells):
        raise ValueError(f"CBP cells missing columns: {sorted(missing)}")

    cbp = cbp_cells.loc[cbp_cells["naics"].astype(str).isin(TREATMENT_NAICS)].copy()
    cbp = cbp.loc[cbp["year"].astype(int).isin(samhsa_counts["year"].astype(int).unique())]
    cbp["establishments"] = pd.to_numeric(cbp["establishments"], errors="coerce")
    cbp["published"] = cbp["publication_status"].isin(
        ["published", "zero"]
    ) & cbp["establishments"].notna()
    pre_break = cbp["year"].astype(int) <= 2016
    cbp["lower_bound"] = cbp["establishments"].where(cbp["published"], 0)
    cbp["upper_bound"] = cbp["establishments"].where(
        cbp["published"],
        pre_break.map({True: 0, False: 2}),
    )

    keys = ["county_fips", "state_fips", "year"]
    grouped = cbp.groupby(keys, dropna=False)
    comparison = grouped.agg(
        cbp_count=("establishments", lambda values: values.sum(min_count=len(values))),
        published_cells=("published", "sum"),
        expected_cells=("naics", "nunique"),
        lower_bound=("lower_bound", "sum"),
        upper_bound=("upper_bound", "sum"),
    ).reset_index()
    comparison["expected_cells"] = len(TREATMENT_NAICS)
    comparison["cell_coverage_rate"] = comparison["published_cells"] / len(TREATMENT_NAICS)
    comparison["common_support"] = (
        comparison["published_cells"] == comparison["expected_cells"]
    )
    comparison["publication_status"] = comparison["common_support"].map(
        {True: "published", False: "partially_or_fully_omitted"}
    )
    comparison.loc[~comparison["common_support"], "cbp_count"] = pd.NA

    output = samhsa_counts.merge(comparison, on=keys, how="outer")
    output["samhsa_count"] = output["samhsa_count"].fillna(0).astype(int)
    output["reporting_break"] = output["year"].astype("Int64").ge(2017)
    return output[
        [
            "county_fips",
            "state_fips",
            "year",
            "samhsa_count",
            "cbp_count",
            "publication_status",
            "lower_bound",
            "upper_bound",
            "cell_coverage_rate",
            "common_support",
            "reporting_break",
        ]
    ]
