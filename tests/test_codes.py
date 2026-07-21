import pandas as pd

from samhsa_dirs.codes import (
    looks_like_service_line,
    normalize_markers,
    parse_service_tokens,
    split_concatenated_code,
)


def test_circled_markers_and_unknown_tokens_are_preserved():
    codebook = pd.DataFrame(
        [
            {"code": "SA", "category": "Type of Care", "label": "Substance use", "asked": True},
            {"code": "OP", "category": "Settings", "label": "Outpatient", "asked": True},
        ]
    )
    rows, unknown = parse_service_tokens("\u2460 SA \u2462 OP ZZ", codebook, "circled")
    assert [row["code"] for row in rows] == ["SA", "OP"]
    assert unknown == ["ZZ"]
    assert "|1|" in normalize_markers("\u2460 SA")


def test_numeric_markers_and_uppercase_continuations_are_service_lines():
    codebook = pd.DataFrame(
        [
            {"code": "HAEC", "category": "Ancillary", "label": "", "asked": True},
            {"code": "STU", "category": "Groups", "label": "", "asked": True},
        ]
    )
    assert looks_like_service_line(
        "25 STU TCC 26 SMPD 27 ADLT YAD 28 FEM MALE 29", codebook
    )
    assert looks_like_service_line(
        "HAEC HEOH STU TCC SMPD ADLT YAD FEM MALE", codebook
    )
    assert not looks_like_service_line("South Central Alabama MHC", codebook)


def test_ocr_lowercase_s_separator_is_normalized():
    codebook = pd.DataFrame(
        [
            {"code": "SA", "category": "Type", "label": "", "asked": True},
            {"code": "OP", "category": "Setting", "label": "", "asked": True},
            {"code": "MD", "category": "Payment", "label": "", "asked": True},
        ]
    )
    text = "SA s OP OIT ORT s SF MD"
    assert looks_like_service_line(text, codebook)
    rows, _ = parse_service_tokens(text, codebook, "diamond")
    assert {row["code"] for row in rows} >= {"SA", "OP", "MD"}


def test_concatenated_codes_are_split_and_debris_is_preserved_only_as_unknown():
    codebook = pd.DataFrame(
        [
            {"code": "TX", "category": "Type", "label": "", "asked": True},
            {"code": "HH", "category": "Type", "label": "", "asked": True},
            {"code": "SF", "category": "Payment", "label": "", "asked": True},
            {"code": "MD", "category": "Payment", "label": "", "asked": True},
        ]
    )
    rows, unknown = parse_service_tokens("TXHH SFMD OCRJUNK", codebook, "diamond")
    assert {row["code"] for row in rows} == {"TX", "HH", "SF", "MD"}
    assert unknown == ["OCRJUNK"]
    assert split_concatenated_code("TXHH", {"TX", "HH"}) == ["TX", "HH"]


def test_early_ocr_service_aliases_and_concatenations():
    codebook = pd.DataFrame(
        [
            {"code": code, "asked": True, "category": "Test", "label": code}
            for code in ["SS", "CM", "TC", "PI"]
        ]
    )

    rows, unknown = parse_service_tokens("SSCM SSTC Pl", codebook, "slash")

    assert {row["code"] for row in rows} == {"SS", "CM", "TC", "PI"}
    assert unknown == []
