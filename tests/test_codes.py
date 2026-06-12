import pandas as pd

from samhsa_dirs.codes import looks_like_service_line, normalize_markers, parse_service_tokens


def test_circled_markers_and_unknown_tokens_are_preserved():
    codebook = pd.DataFrame(
        [
            {"code": "SA", "category": "Type of Care", "label": "Substance use", "asked": True},
            {"code": "OP", "category": "Settings", "label": "Outpatient", "asked": True},
        ]
    )
    rows, unknown = parse_service_tokens("\u2460 SA \u2462 OP ZZ", codebook, "circled")
    assert [row["code"] for row in rows] == ["SA", "OP", "ZZ"]
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
