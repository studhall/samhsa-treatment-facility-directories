import pandas as pd

from samhsa_dirs.manifest import YearConfig
from samhsa_dirs.parser import PositionedLine, parse_lines


def config():
    return YearConfig(
        directory_year=2021,
        survey_year=2020,
        filename="test.pdf",
        source_url="",
        sha256="",
        start_page=1,
        end_page=1,
        n_columns=2,
        layout_profile="two_column",
        delimiter="circled",
        margin=0,
        overlap=0,
        crop_top=0,
        crop_bottom=0,
        expected_category_count=31,
    )


def test_parse_record_keeps_provenance_contact_and_services():
    lines = [
        PositionedLine(15, 1, "ABBEVILLE"),
        PositionedLine(15, 1, "SpectraCare"),
        PositionedLine(15, 1, "Henry County/Outpatient"),
        PositionedLine(15, 1, "219 Dothan Road"),
        PositionedLine(15, 1, "Abbeville, Alabama 36310"),
        PositionedLine(15, 1, "Phone: (800) 951-4357"),
        PositionedLine(15, 1, "① SA ③ OP"),
    ]
    codebook = pd.DataFrame(
        [
            {"code": "SA", "category": "Type of Care", "label": "Substance use", "asked": True},
            {"code": "OP", "category": "Settings", "label": "Outpatient", "asked": True},
        ]
    )
    facilities, services = parse_lines(lines, config(), codebook, "test.pdf")
    assert len(facilities) == 1
    assert facilities.iloc[0]["name1"] == "SpectraCare"
    assert facilities.iloc[0]["address1"] == "219 Dothan Road"
    assert facilities.iloc[0]["phone"] == "(800) 951-4357"
    assert facilities.iloc[0]["source_page"] == 15
    assert set(services["code"]) == {"SA", "OP"}


def test_service_continuation_does_not_become_next_facility_name():
    lines = [
        PositionedLine(15, 1, "ANDALUSIA"),
        PositionedLine(15, 1, "South Central Alabama MHC"),
        PositionedLine(15, 1, "Covington Cnty/Adult SA OP"),
        PositionedLine(15, 1, "205 Academy Drive"),
        PositionedLine(15, 1, "Andalusia, Alabama 36420"),
        PositionedLine(15, 1, "Phone: (800) 951-4357"),
        PositionedLine(15, 1, "HAEC HEOH 25 STU TCC 26 SMPD 27 ADLT YAD 28 FEM MALE 29"),
        PositionedLine(15, 2, "ment Facilities ALABAMA"),
        PositionedLine(15, 2, "South Central Alabama MHC"),
        PositionedLine(15, 2, "First Step"),
        PositionedLine(15, 2, "123 Main Street"),
        PositionedLine(15, 2, "Andalusia, Alabama 36420"),
        PositionedLine(15, 2, "1 SA 3 OP"),
    ]
    codebook = pd.DataFrame(
        [
            {"code": "SA", "category": "Type of Care", "label": "Substance use", "asked": True},
            {"code": "OP", "category": "Settings", "label": "Outpatient", "asked": True},
            {"code": "HAEC", "category": "Ancillary", "label": "", "asked": True},
            {"code": "STU", "category": "Groups", "label": "", "asked": True},
        ]
    )
    facilities, _ = parse_lines(lines, config(), codebook, "test.pdf")
    assert list(facilities["name1"]) == [
        "South Central Alabama MHC",
        "South Central Alabama MHC",
    ]
    assert facilities.iloc[1]["name2"] == "First Step"


def test_source_anchor_survives_name_and_address_parser_changes():
    codebook = pd.DataFrame(
        [{"code": "OP", "category": "Settings", "label": "Outpatient", "asked": True}]
    )
    original = [
        PositionedLine(15, 1, "Facility One"),
        PositionedLine(15, 1, "123 Main Street"),
        PositionedLine(15, 1, "Abbeville, Alabama 36310"),
        PositionedLine(15, 1, "1 OP"),
    ]
    corrected = [
        PositionedLine(15, 1, "Facility One Corrected"),
        PositionedLine(15, 1, "123 Main Street Suite 2"),
        PositionedLine(15, 1, "Abbeville, Alabama 36310"),
        PositionedLine(15, 1, "1 OP"),
    ]
    original_facilities, _ = parse_lines(original, config(), codebook, "test.pdf")
    corrected_facilities, _ = parse_lines(corrected, config(), codebook, "test.pdf")
    assert (
        original_facilities.iloc[0]["source_anchor_id"]
        == corrected_facilities.iloc[0]["source_anchor_id"]
    )
    assert (
        original_facilities.iloc[0]["listing_id"]
        != corrected_facilities.iloc[0]["listing_id"]
    )


def test_column_boundary_does_not_bleed_footer_fragment_into_next_record():
    codebook = pd.DataFrame(
        [
            {"code": "TX", "category": "Type", "label": "", "asked": True},
            {"code": "OS", "category": "Setting", "label": "", "asked": True},
        ]
    )
    lines = [
        PositionedLine(15, 1, "Prior Facility"),
        PositionedLine(15, 1, "10 Main Street"),
        PositionedLine(15, 1, "Prior City, Oregon 97000"),
        PositionedLine(15, 1, "TX OS"),
        PositionedLine(15, 1, "e v."),
        PositionedLine(15, 2, "Next Facility"),
        PositionedLine(15, 2, "20 Main Street"),
        PositionedLine(15, 2, "Next City, Oregon 97001"),
        PositionedLine(15, 2, "TX OS"),
    ]

    facilities, _ = parse_lines(lines, config(), codebook, "test.pdf")

    assert len(facilities) == 2
    assert facilities.iloc[1]["name1"] == "Next Facility"


def test_ocr_hotline_prefix_keeps_following_service_lines():
    codebook = pd.DataFrame(
        [
            {"code": "TX", "category": "Type", "label": "", "asked": True},
            {"code": "OS", "category": "Setting", "label": "", "asked": True},
            {"code": "DT", "category": "Type", "label": "", "asked": True},
            {"code": "PI", "category": "Payment", "label": "", "asked": True},
        ]
    )
    lines = [
        PositionedLine(15, 1, "Example Hospital"),
        PositionedLine(15, 1, "100 Main Street"),
        PositionedLine(15, 1, "Portland, Oregon 97201"),
        PositionedLine(15, 1, "(503)555-1111"),
        PositionedLine(15, 1, "W/ Hotline:"),
        PositionedLine(15, 1, "(503)555-2222"),
        PositionedLine(15, 1, "TX OS DT/ PI"),
    ]

    facilities, _ = parse_lines(lines, config(), codebook, "test.pdf")

    assert facilities.iloc[0]["service_codes"] == "DT OS PI TX"
