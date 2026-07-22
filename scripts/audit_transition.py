from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd


AUDIT_YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
TRANSITIONS = [
    (2019, 2020),
    (2020, 2021),
    (2021, 2022),
    (2022, 2023),
    (2023, 2024),
    (2024, 2025),
]


def normalize_text(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.upper()
        .str.replace(r"[^A-Z0-9]", "", regex=True)
    )


def has_code(series: pd.Series, code: str) -> pd.Series:
    return series.fillna("").astype(str).str.contains(
        rf"(?:^|\|){re.escape(code)}(?:\||$)",
        regex=True,
    )


def add_match_keys(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    name = normalize_text(output["name1"])
    address = normalize_text(output["address1"])
    city = normalize_text(output["city"])
    state = normalize_text(output["state"])
    zipcode = normalize_text(output["zip"]).str[:5]
    output["strict_key"] = name + "|" + address + "|" + city + "|" + state
    output.loc[name.eq("") | address.eq("") | state.eq(""), "strict_key"] = ""
    output["name_zip_key"] = name + "|" + zipcode + "|" + state
    output.loc[name.eq("") | zipcode.eq("") | state.eq(""), "name_zip_key"] = ""
    return output


def year_summary(facilities: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for directory_year in AUDIT_YEARS:
        all_rows = facilities.loc[facilities["directory_year"].eq(directory_year)]
        frame = all_rows.loc[all_rows["headline_us"].eq("yes")].copy()
        service_count = frame["service_codes"].fillna("").str.split().map(len)
        ownership = frame["ownership_type"].fillna("")
        rows.append(
            {
                "directory_year": directory_year,
                "survey_year": int(frame["survey_year"].iloc[0]),
                "source_format": frame["source_format"].iloc[0],
                "all_listings": len(all_rows),
                "headline_us_listings": len(frame),
                "territory_listings": len(all_rows) - len(frame),
                "missing_name_share": frame["name1"].fillna("").eq("").mean(),
                "missing_address_share": frame["address1"].fillna("").eq("").mean(),
                "missing_zip_share": frame["zip"].fillna("").eq("").mean(),
                "warning_share": frame["has_parser_warning"].fillna(False).mean(),
                "mean_service_codes": service_count.mean(),
                "median_service_codes": service_count.median(),
                "nonprofit_share": ownership.str.contains("Non-profit").mean(),
                "forprofit_share": ownership.str.contains("For-profit").mean(),
                "government_share": ownership.str.contains(
                    "Public|Federal|Tribal", regex=True
                ).mean(),
                "otp_share": has_code(frame["medication_services"], "OTP").mean(),
                "outpatient_share": has_code(frame["care_settings"], "OP").mean(),
                "residential_share": has_code(frame["care_settings"], "RES").mean(),
                "hospital_share": has_code(frame["care_settings"], "HI").mean(),
                "medicaid_share": frame["accepts_medicaid"].fillna(False).mean(),
                "medicare_share": frame["accepts_medicare"].fillna(False).mean(),
                "private_insurance_share": frame[
                    "accepts_private_insurance"
                ].fillna(False).mean(),
            }
        )
    return pd.DataFrame(rows)


def match_rate(
    earlier: pd.DataFrame,
    later: pd.DataFrame,
    key: str,
) -> tuple[float, float]:
    earlier_keys = set(earlier.loc[earlier[key].ne(""), key])
    later_keys = set(later.loc[later[key].ne(""), key])
    later_valid = later[key].ne("")
    earlier_valid = earlier[key].ne("")
    later_rate = later.loc[later_valid, key].isin(earlier_keys).mean()
    earlier_rate = earlier.loc[earlier_valid, key].isin(later_keys).mean()
    return float(later_rate), float(earlier_rate)


def transition_outputs(
    facilities: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    headline = facilities.loc[facilities["headline_us"].eq("yes")].copy()
    headline = add_match_keys(headline)
    transition_rows = []
    state_frames = []
    for earlier_year, later_year in TRANSITIONS:
        earlier = headline.loc[headline["directory_year"].eq(earlier_year)]
        later = headline.loc[headline["directory_year"].eq(later_year)]
        earlier_states = earlier.groupby("state").size().rename("earlier_count")
        later_states = later.groupby("state").size().rename("later_count")
        states = pd.concat([earlier_states, later_states], axis=1).fillna(0).reset_index()
        states["earlier_count"] = states["earlier_count"].astype(int)
        states["later_count"] = states["later_count"].astype(int)
        states["count_change"] = states["later_count"] - states["earlier_count"]
        states["percent_change"] = states["count_change"].div(
            states["earlier_count"].replace(0, pd.NA)
        )
        states["transition"] = f"{earlier_year}_to_{later_year}"
        state_frames.append(states)

        strict_later, strict_earlier = match_rate(earlier, later, "strict_key")
        zip_later, zip_earlier = match_rate(earlier, later, "name_zip_key")
        transition_rows.append(
            {
                "transition": f"{earlier_year}_to_{later_year}",
                "earlier_directory_year": earlier_year,
                "later_directory_year": later_year,
                "earlier_survey_year": int(earlier["survey_year"].iloc[0]),
                "later_survey_year": int(later["survey_year"].iloc[0]),
                "earlier_count": len(earlier),
                "later_count": len(later),
                "national_percent_change": len(later) / len(earlier) - 1,
                "state_count_correlation": states[
                    ["earlier_count", "later_count"]
                ].corr().iloc[0, 1],
                "median_state_percent_change": states["percent_change"].median(),
                "later_strict_match_share": strict_later,
                "earlier_strict_match_share": strict_earlier,
                "later_name_zip_match_share": zip_later,
                "earlier_name_zip_match_share": zip_earlier,
            }
        )
    return pd.DataFrame(transition_rows), pd.concat(state_frames, ignore_index=True)


def run_audit(facilities_path: Path, output_dir: Path) -> dict[str, object]:
    columns = [
        "directory_year",
        "survey_year",
        "name1",
        "address1",
        "city",
        "state",
        "zip",
        "headline_us",
        "source_format",
        "has_parser_warning",
        "service_codes",
        "ownership_type",
        "care_settings",
        "medication_services",
        "accepts_medicaid",
        "accepts_medicare",
        "accepts_private_insurance",
    ]
    facilities = pd.read_parquet(facilities_path, columns=columns)
    summary = year_summary(facilities)
    transitions, states = transition_outputs(facilities)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_dir / "year_summary.csv", index=False)
    transitions.to_csv(output_dir / "transition_summary.csv", index=False)
    states.to_csv(output_dir / "state_transitions.csv", index=False)
    result = {
        "years": len(summary),
        "transitions": len(transitions),
        "output_dir": str(output_dir),
    }
    (output_dir / "audit_metadata.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--facilities", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(run_audit(args.facilities, args.output_dir))


if __name__ == "__main__":
    main()
