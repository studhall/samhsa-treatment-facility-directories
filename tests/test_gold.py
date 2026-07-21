import json
import os
import uuid
from pathlib import Path

import pandas as pd
import pytest

import samhsa_dirs.gold as gold_module
from samhsa_dirs.gold import (
    _canonical_service_codes,
    _gold_name_parts,
    REVIEW_COLUMNS,
    add_sampling_features,
    build_gold_workbook,
    evaluate_year_metrics,
    import_gold_workbook,
    refresh_gold_sample,
    sample_year,
)


def synthetic_facilities(year=2021, rows=300):
    records = []
    for index in range(rows):
        records.append(
            {
                "listing_id": f"L{index}",
                "source_anchor_id": f"A{index}",
                "directory_year": year,
                "survey_year": year - 1,
                "source_pdf": "test.pdf",
                "source_page": 1 + index // 3,
                "source_column": 1 + index % 2,
                "source_record_order": index + 1,
                "name1": f"Facility {index}",
                "name2": "Unit" if index % 9 == 0 else "",
                "address1": f"{index} Main Street"
                + (" Suite 2" if index % 7 == 0 else ""),
                "city": f"City {index % 20}",
                "state": ["OR", "WA", "ID", "CA", "NY"][index % 5],
                "zip": f"{97000 + index % 900:05d}",
                "census_region": [
                    "West",
                    "West",
                    "West",
                    "West",
                    "Northeast",
                ][index % 5],
                "service_codes": "OP SA" + (" RARE" if index < 8 else ""),
                "raw_record_text": "Facility\nAddress\nCity\nPhone\nServices"
                + ("\nExtra" if index % 4 == 0 else ""),
                "raw_service_text": "OP SA",
                "parser_warnings": '["warning"]' if index % 8 == 0 else "[]",
                "unknown_service_tokens": '["UNK"]' if index % 17 == 0 else "[]",
            }
        )
    return pd.DataFrame(records)


def test_stratified_sample_is_deterministic_and_nonduplicated():
    facilities = add_sampling_features(synthetic_facilities())
    first = sample_year(facilities, 2021, 100, 20260612)
    second = sample_year(facilities, 2021, 100, 20260612)
    assert first["source_anchor_id"].tolist() == second["source_anchor_id"].tolist()
    assert first["source_anchor_id"].is_unique
    assert len(first) == 100
    assert set(first["sample_stratum"]) == {
        "random",
        "warning_unknown",
        "boundary",
        "rare_dense_services",
        "complex_record",
    }


def review_metrics_frame(rows, errors):
    return pd.DataFrame(
        {
            "name_accurate": [index >= errors for index in range(rows)],
            "address_accurate": [index >= errors for index in range(rows)],
            "service_accurate": [index >= errors for index in range(rows)],
            "anchor_matched": [True] * rows,
            "name_check": ["yes"] * rows,
            "address_check": ["yes"] * rows,
            "services_check": ["yes"] * rows,
            "boundary_check": ["yes"] * rows,
            "sample_stratum": ["random"] * rows,
        }
    )


def test_gold_name_correction_can_intentionally_clear_second_line():
    row = pd.Series(
        {
            "parsed_name1": "Facility",
            "parsed_name2": "Program",
            "corrected_name1": "Facility Program",
            "corrected_name2": "",
        }
    )

    assert _gold_name_parts(row) == ("Facility Program", "")


def test_gold_service_codes_normalize_known_early_ocr_errors():
    assert _canonical_service_codes("PL SSCM SSTC") == {"PI", "SS", "CM", "TC"}


def test_refresh_preserves_human_review_and_updates_parsed_fields(monkeypatch):
    output_dir = Path("tests/.artifacts") / f"refresh-{uuid.uuid4().hex}"
    output_dir.mkdir(parents=True)
    row = {column: "" for column in REVIEW_COLUMNS}
    row.update(
        {
            "sample_id": "G1",
            "source_anchor_id": "A1",
            "directory_year": "1998",
            "parsed_name1": "Old Name",
            "corrected_name1": "Reviewed Name",
            "name_check": "yes",
            "review_complete": "yes",
            "notes": "Keep this note",
        }
    )
    existing_path = output_dir / "existing.csv"
    pd.DataFrame([row]).to_csv(existing_path, index=False)
    current = synthetic_facilities(1998, 1).copy()
    current.loc[0, "source_anchor_id"] = "A1"
    current.loc[0, "name1"] = "New Parsed Name"
    monkeypatch.setattr(gold_module, "load_run_facilities", lambda _: current)

    refreshed, unmatched = refresh_gold_sample(
        Path("unused-run"),
        existing_path,
        output_dir,
    )

    assert unmatched.empty
    assert refreshed.loc[0, "parsed_name1"] == "New Parsed Name"
    assert refreshed.loc[0, "corrected_name1"] == "Reviewed Name"
    assert refreshed.loc[0, "review_complete"] == "yes"
    assert refreshed.loc[0, "notes"] == "Keep this note"


def test_refresh_reanchors_exact_page_column_record_match(monkeypatch):
    output_dir = Path("tests/.artifacts") / f"reanchor-{uuid.uuid4().hex}"
    output_dir.mkdir(parents=True)
    row = {column: "" for column in REVIEW_COLUMNS}
    row.update(
        {
            "sample_id": "G1",
            "source_anchor_id": "A-old",
            "directory_year": "1998",
            "source_page": "12",
            "source_column": "1",
            "source_record_order": "1",
        }
    )
    existing_path = output_dir / "existing.csv"
    pd.DataFrame([row]).to_csv(existing_path, index=False)
    current = synthetic_facilities(1998, 1).copy()
    current.loc[0, "source_anchor_id"] = "A-new"
    current.loc[0, "source_page"] = 12
    current.loc[0, "source_column"] = 1
    current.loc[0, "source_record_order"] = 1
    monkeypatch.setattr(gold_module, "load_run_facilities", lambda _: current)

    refreshed, unmatched = refresh_gold_sample(
        Path("unused-run"),
        existing_path,
        output_dir,
    )

    assert unmatched.empty
    assert refreshed.loc[0, "source_anchor_id"] == "A-new"
    audit = pd.read_csv(output_dir / "gold_refresh_reanchored.csv")
    assert audit.loc[0, "old_source_anchor_id"] == "A-old"
    assert audit.loc[0, "new_source_anchor_id"] == "A-new"


def test_year_thresholds_and_adaptive_expansion():
    early = evaluate_year_metrics(2001, review_metrics_frame(100, 5))
    modern = evaluate_year_metrics(2021, review_metrics_frame(100, 3))
    blocked = evaluate_year_metrics(2021, review_metrics_frame(200, 5))
    assert early["target"] == 0.95
    assert early["pass"]
    assert modern["target"] == 0.98
    assert not modern["pass"]
    assert modern["recommended_sample_size"] == 150
    assert blocked["blocked_at_200"]


@pytest.mark.skipif(
    not os.environ.get("SAMHSA_NODE"),
    reason="Set SAMHSA_NODE for the artifact-tool workbook integration test",
)
def test_excel_creation_import_round_trip():
    output_dir = Path("tests/.artifacts") / f"workbook-{uuid.uuid4().hex}"
    output_dir.mkdir(parents=True)
    years = [
        1998, 2000, 2001, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010,
        2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021,
    ]
    rows = []
    for year in years:
        row = {column: "" for column in REVIEW_COLUMNS}
        row.update(
            {
                "sample_id": f"G{year}",
                "source_anchor_id": f"A{year}",
                "listing_id_at_sampling": f"L{year}",
                "directory_year": year,
                "survey_year": year - 1,
                "source_pdf": "test.pdf",
                "source_page": 1,
                "source_column": 1,
                "source_record_order": 1,
                "sample_stratum": "random",
                "page_quantile": 1,
                "parsed_name1": "Test Facility",
                "parsed_address1": "1 Main Street",
                "parsed_city": "Eugene",
                "parsed_state": "OR",
                "parsed_zip": "97401",
                "parsed_service_codes": "OP",
                "raw_record_text": "Test Facility\n1 Main Street",
                "raw_service_text": "OP",
                "page_image": "assets/test.png",
            }
        )
        rows.append(row)
    source = output_dir / "source.json"
    source.write_text(json.dumps(rows), encoding="utf-8")
    workbook = output_dir / "gold.xlsx"
    node_modules = (
        Path(os.environ["SAMHSA_NODE_MODULES"])
        if os.environ.get("SAMHSA_NODE_MODULES")
        else None
    )
    build_gold_workbook(
        source,
        workbook,
        output_dir / "previews",
        Path(os.environ["SAMHSA_NODE"]),
        node_modules,
    )
    output = output_dir / "gold.csv"
    imported = import_gold_workbook(
        workbook,
        output,
        Path(os.environ["SAMHSA_NODE"]),
        node_modules,
    )
    assert workbook.exists()
    assert len(imported) == 22
    assert imported["source_anchor_id"].tolist() == [f"A{year}" for year in years]
