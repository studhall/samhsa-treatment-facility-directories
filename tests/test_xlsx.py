from pathlib import Path

import pandas as pd

from samhsa_dirs.xlsx import (
    FACILITY_COLUMNS,
    CODEBOOK_COLUMNS,
    WorkbookConfig,
    import_workbook,
)


def write_workbook(path: Path, first_name: str = "Alpha Treatment") -> None:
    facilities = pd.DataFrame(
        [
            {
                "name1": first_name,
                "name2": "",
                "street1": "1 Main St",
                "street2": "",
                "city": "Eugene",
                "state": "OR",
                "zip": "97401",
                "phone": "541-555-0100",
                "intake1": "",
                "intake2": "",
                "intake1a": "",
                "intake2a": "",
                "service_code_info": "OTP OP",
            },
            {
                "name1": "Beta Recovery",
                "name2": "",
                "street1": "2 Oak St",
                "street2": "Unit 4",
                "city": "Boise",
                "state": "ID",
                "zip": "83702",
                "phone": "",
                "intake1": "208-555-0100",
                "intake2": "",
                "intake1a": "",
                "intake2a": "",
                "service_code_info": "OP",
            },
        ],
        columns=FACILITY_COLUMNS,
    )
    codebook = pd.DataFrame(
        [
            ["T", "Treatment", "OTP", "Opioid treatment program", ""],
            ["T", "Treatment", "OP", "Outpatient", ""],
        ],
        columns=CODEBOOK_COLUMNS,
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        facilities.to_excel(writer, sheet_name="Facilities List", index=False)
        codebook.to_excel(writer, sheet_name="Service Code Reference", index=False)


def config() -> WorkbookConfig:
    return WorkbookConfig(
        directory_year=2025,
        survey_year=2024,
        filename="directory.xlsx",
        source_url="https://example.test/directory.xlsx",
        sha256="unused",
        facility_sheet="Facilities List",
        codebook_sheet="Service Code Reference",
        expected_facilities=2,
    )


def test_workbook_import_preserves_provenance_and_services(tmp_path):
    workbook = tmp_path / "directory.xlsx"
    write_workbook(workbook)

    frames, metrics = import_workbook(workbook, config())

    assert metrics["structural_pass"]
    assert metrics["service_coverage"] == 1
    assert frames["facilities"]["source_row"].tolist() == [2, 3]
    assert frames["facilities"]["source_format"].unique().tolist() == ["official_xlsx"]
    assert set(frames["facility_services"]["code"]) == {"OTP", "OP"}
    assert set(frames["service_availability"]["code"]) == {"OTP", "OP"}


def test_source_anchor_is_stable_when_parsed_content_changes(tmp_path):
    workbook = tmp_path / "directory.xlsx"
    write_workbook(workbook, "Original Name")
    first, _ = import_workbook(workbook, config())

    write_workbook(workbook, "Corrected Name")
    second, _ = import_workbook(workbook, config())

    assert (
        first["facilities"].loc[0, "source_anchor_id"]
        == second["facilities"].loc[0, "source_anchor_id"]
    )
    assert (
        first["facilities"].loc[0, "listing_id"]
        == second["facilities"].loc[0, "listing_id"]
    )
