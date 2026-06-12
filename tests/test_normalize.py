from samhsa_dirs.normalize import geography_fields, normalize_key, parse_location


def test_parse_location_with_full_state_name():
    parsed = parse_location("Abbeville, Alabama 36310")
    assert parsed is not None
    assert parsed.city == "Abbeville"
    assert parsed.state == "AL"
    assert parsed.zip_code == "36310"


def test_normalize_key_removes_legal_suffixes():
    assert normalize_key("Example Treatment Center, LLC") == "EXAMPLETREATMENT"


def test_pnw_group():
    assert geography_fields("OR")["pnw"] == "PNW"
    assert geography_fields("CA")["pnw"] == "Not PNW"


def test_parse_location_without_space_between_state_and_zip():
    parsed = parse_location("Birmingham, AL35204")
    assert parsed is not None
    assert parsed.state == "AL"
    assert parsed.zip_code == "35204"


def test_parse_location_repairs_ocr_state_code():
    parsed = parse_location("Birmingham, AI.35203")
    assert parsed is not None
    assert parsed.state == "AL"
