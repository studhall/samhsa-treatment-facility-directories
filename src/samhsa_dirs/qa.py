from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .normalize import VALID_STATE_CODES, normalize_key


HEADER_PATTERN = re.compile(
    r"National Directory|For Code Definitions|CLICK HERE|KEY TO FACILITY", re.IGNORECASE
)


def qa_by_year(facilities: pd.DataFrame, services: pd.DataFrame) -> pd.DataFrame:
    service_counts = services.groupby("directory_year")["listing_id"].nunique()
    rows = []
    for year, group in facilities.groupby("directory_year"):
        rows.append(
            {
                "directory_year": int(year),
                "survey_year": int(group["survey_year"].iloc[0]),
                "rows": len(group),
                "states": group["state"].nunique(),
                "missing_name_share": group["name1"].fillna("").eq("").mean(),
                "missing_address_share": group["address1"].fillna("").eq("").mean(),
                "invalid_state_share": (~group["state"].isin(VALID_STATE_CODES)).mean(),
                "header_noise_share": group["name1"].fillna("").str.contains(
                    HEADER_PATTERN
                ).mean(),
                "service_record_share": service_counts.get(year, 0) / max(len(group), 1),
                "weak_address_share": group["parser_warnings"].fillna("").str.contains(
                    "weak_address_pattern"
                ).mean(),
            }
        )
    frame = pd.DataFrame(rows).sort_values("directory_year")
    frame["row_change"] = frame["rows"].pct_change()
    frame["large_discontinuity"] = frame["row_change"].abs() > 0.25
    return frame


def evaluate_gold_sample(facilities: pd.DataFrame, gold_path: Path) -> dict[str, object]:
    if not gold_path.exists():
        return {"completed": False, "rows": 0, "address_accuracy": None, "service_accuracy": None}
    gold = pd.read_csv(gold_path, dtype=str).fillna("")
    completed = gold.loc[gold["review_complete"].str.lower().eq("yes")]
    if completed.empty:
        return {"completed": False, "rows": 0, "address_accuracy": None, "service_accuracy": None}
    merged = completed.merge(facilities, on="listing_id", how="left", suffixes=("_gold", ""))
    address_ok = (
        merged["address1_gold"].map(normalize_key) == merged["address1"].fillna("").map(normalize_key)
    )
    service_ok = merged["service_codes_gold"].map(
        lambda x: set(str(x).split())
    ) == merged["service_codes"].fillna("").map(lambda x: set(str(x).split()))
    return {
        "completed": True,
        "rows": len(merged),
        "address_accuracy": float(address_ok.mean()),
        "service_accuracy": float(service_ok.mean()),
    }


def build_qa_report(
    facilities: pd.DataFrame,
    services: pd.DataFrame,
    gold_path: Path,
    geocoding: pd.DataFrame | None = None,
    linkage_review_accuracy: float | None = None,
    expected_counts_path: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    annual = qa_by_year(facilities, services)
    count_reference_pass = False
    if expected_counts_path is not None and expected_counts_path.exists():
        expected = pd.read_csv(expected_counts_path)
        annual = annual.merge(expected, on="directory_year", how="left")
        annual["count_difference_share"] = (
            (annual["rows"] - annual["expected_listings"]).abs()
            / annual["expected_listings"]
        )
        annual["count_within_2pct"] = annual["count_difference_share"].le(0.02)
        acceptance = (
            annual["acceptance_reference"]
            .fillna("no")
            .astype(str)
            .str.lower()
            .eq("yes")
        )
        count_reference_pass = bool(
            acceptance.all()
            and annual["expected_listings"].notna().all()
            and annual["count_within_2pct"].all()
        )
    gold = evaluate_gold_sample(facilities, gold_path)
    early_target = 0.95
    modern_target = 0.98
    gold_target = early_target if set(annual["directory_year"]) <= {1998, 2000, 2001} else modern_target
    geocode_share = None
    if geocoding is not None and not geocoding.empty:
        geocode_share = float(geocoding["geocode_confidence"].eq("high").mean())

    structural_pass = bool(
        (annual["invalid_state_share"] == 0).all()
        and (annual["header_noise_share"] == 0).all()
        and (~annual["large_discontinuity"].fillna(False)).all()
    )
    gold_pass = bool(
        gold["completed"]
        and gold["address_accuracy"] is not None
        and gold["service_accuracy"] is not None
        and gold["address_accuracy"] >= gold_target
        and gold["service_accuracy"] >= gold_target
    )
    geocode_pass = geocode_share is not None and geocode_share >= 0.90
    linkage_pass = linkage_review_accuracy is not None and linkage_review_accuracy >= 0.98
    report = {
        "release_ready": (
            structural_pass
            and count_reference_pass
            and gold_pass
            and geocode_pass
            and linkage_pass
        ),
        "structural_pass": structural_pass,
        "count_reference_pass": count_reference_pass,
        "gold_sample": gold,
        "gold_target": gold_target,
        "geocoding_high_confidence_share": geocode_share,
        "geocoding_pass": geocode_pass,
        "linkage_review_accuracy": linkage_review_accuracy,
        "linkage_pass": linkage_pass,
        "blocking_reasons": [
            reason
            for passed, reason in [
                (structural_pass, "structural parser QA failed"),
                (
                    count_reference_pass,
                    "independent annual count references are incomplete or outside 2%",
                ),
                (gold_pass, "manual gold sample is incomplete or below target"),
                (geocode_pass, "high-confidence county assignment is below 90% or absent"),
                (linkage_pass, "manual linkage precision is below 98% or absent"),
            ]
            if not passed
        ],
    }
    return annual, report


def write_qa(
    annual: pd.DataFrame, report: dict[str, object], output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    annual.to_csv(output_dir / "qa_by_year.csv", index=False)
    (output_dir / "qa_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
