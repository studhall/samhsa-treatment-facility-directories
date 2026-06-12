from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


STATE_NAMES = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "DISTRICT OF COLUMBIA": "DC",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
    "PUERTO RICO": "PR",
    "GUAM": "GU",
    "U.S. VIRGIN ISLANDS": "VI",
    "VIRGIN ISLANDS": "VI",
    "AMERICAN SAMOA": "AS",
    "NORTHERN MARIANA ISLANDS": "MP",
    "MICRONESIA": "FM",
    "REPUBLIC OF PALAU": "PW",
}

VALID_STATE_CODES = set(STATE_NAMES.values())

CENSUS_REGION = {
    **dict.fromkeys(["CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"], "Northeast"),
    **dict.fromkeys(
        ["IN", "IL", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD"],
        "Midwest",
    ),
    **dict.fromkeys(
        [
            "DE",
            "DC",
            "FL",
            "GA",
            "MD",
            "NC",
            "SC",
            "VA",
            "WV",
            "AL",
            "KY",
            "MS",
            "TN",
            "AR",
            "LA",
            "OK",
            "TX",
        ],
        "South",
    ),
    **dict.fromkeys(
        ["AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY", "AK", "CA", "HI", "OR", "WA"],
        "West",
    ),
}

CENSUS_DIVISION = {
    **dict.fromkeys(["CT", "ME", "MA", "NH", "RI", "VT"], "New England"),
    **dict.fromkeys(["NJ", "NY", "PA"], "Middle Atlantic"),
    **dict.fromkeys(["IN", "IL", "MI", "OH", "WI"], "East North Central"),
    **dict.fromkeys(["IA", "KS", "MN", "MO", "NE", "ND", "SD"], "West North Central"),
    **dict.fromkeys(["DE", "DC", "FL", "GA", "MD", "NC", "SC", "VA", "WV"], "South Atlantic"),
    **dict.fromkeys(["AL", "KY", "MS", "TN"], "East South Central"),
    **dict.fromkeys(["AR", "LA", "OK", "TX"], "West South Central"),
    **dict.fromkeys(["AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY"], "Mountain"),
    **dict.fromkeys(["AK", "CA", "HI", "OR", "WA"], "Pacific"),
}

LOCATION_RE = re.compile(
    r"^\s*(?P<city>.+?),\s*(?P<state>[A-Za-z0-9 .]+?)\s*(?P<zip>\d{5})(?:-\d{4})?\s*$"
)


@dataclass(frozen=True)
class Location:
    city: str
    state: str
    zip_code: str


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\u00ad", "")
    return re.sub(r"\s+", " ", value).strip()


def parse_location(value: str) -> Location | None:
    match = LOCATION_RE.match(clean_text(value))
    if not match:
        return None
    raw_state = clean_text(match.group("state")).upper().rstrip(".")
    state = raw_state if len(raw_state) == 2 else STATE_NAMES.get(raw_state, raw_state)
    if state not in VALID_STATE_CODES and len(raw_state) == 2:
        repaired = raw_state.replace("1", "L").replace("I", "L")
        if repaired in VALID_STATE_CODES:
            state = repaired
    if state not in VALID_STATE_CODES:
        return None
    return Location(clean_text(match.group("city")), state, match.group("zip"))


def normalize_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    value = value.upper()
    value = re.sub(r"\b(INC|LLC|LTD|CORP|CORPORATION|CENTER|CENTRE)\b", " ", value)
    return re.sub(r"[^A-Z0-9]+", "", value)


def geography_fields(state: str) -> dict[str, str]:
    return {
        "census_region": CENSUS_REGION.get(state, "Territory"),
        "census_division": CENSUS_DIVISION.get(state, "Territory"),
        "pnw": "PNW" if state in {"WA", "OR", "ID"} else "Not PNW",
        "headline_us": "yes" if state in CENSUS_REGION or state == "DC" else "no",
    }
