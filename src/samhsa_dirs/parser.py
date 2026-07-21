from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pdfplumber

from .codes import extract_codebook, looks_like_service_line, parse_service_tokens
from .manifest import YearConfig
from .normalize import clean_text, geography_fields, parse_location

logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfplumber").setLevel(logging.ERROR)


PHONE_RE = re.compile(
    r"(?P<label>Phone|Intake|Intakes|Hotline|Toll Free|TTY|Fax)?\s*:?\s*"
    r"(?P<number>\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?:\s*(?:x|ext\.?|#)\s*\d+)?)",
    re.IGNORECASE,
)
PHONE_LIKE_RE = re.compile(r"^\s*\(?\d{3}\)?\s*[-.)]?\s*\d", re.IGNORECASE)
OCR_PHONE_LIKE_RE = re.compile(
    r"^\s*[0O]?\s*\(?\s*[\dOILS]{2,3}\)?[\dOILS().\s-]{4,}",
    re.IGNORECASE,
)
SECONDARY_RE = re.compile(
    r"\b(Suite|Ste\.?|Unit|Room|Rm\.?|Floor|Building|Bldg\.?|Apt\.?|#)\b",
    re.IGNORECASE,
)
CONTACT_NOTE_RE = re.compile(
    r"(?:^\s*w{2,4}|w{2,3}[.~]|https?://|[A-Za-z0-9.~ -]+\.\s*"
    r"(?:com|corn|org|otg|net|gov|edu)\b|"
    r"\w*ethadone.*Only|Buprenorphine.*Only|"
    r"(?:\S+\s+){0,4}Clients?\s+Only|"
    r"(?:Women|Men|Adolescents?|Adults?)\s+Only)",
    re.IGNORECASE,
)
CONTACT_PREFIX_RE = re.compile(
    r"^\s*(?:[A-Z]\s*/?\s*)?(?:Phone|Intake|Intakes|Hotline|Hotlines|"
    r"[I1]-?l?ot(?:line|linc)|Toll Free|TTY|Fax)\s*:",
    re.IGNORECASE,
)
URL_LIKE_RE = re.compile(
    r"(?:^\s*[wv]{2,4}\S*|[A-Za-z0-9-]{2,}\s*\.\s*"
    r"(?:com|corn|org|ol'g|net|gov|edu|mil|bz))",
    re.IGNORECASE,
)
ADDRESS_RE = re.compile(
    r"^(?:\d+[A-Za-z.-]*\s+|P\.?\s*O\.?\s+Box\s+|Post Office Box\s+|"
    r"(?:State|County)?\s*Route\s+\d+|Highway\s+\d+|Rural Route\s+)",
    re.IGNORECASE,
)
HEADER_NOISE_RE = re.compile(
    r"National Directory|For Code Definitions|See KEY|Treatment Facilities|"
    r"Substance Abuse and Mental Health Services Administration|"
    r"(?:ment|treatment)\s+Facilities\s+[A-Z ]+$|^\d+$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PositionedLine:
    page: int
    column: int
    text: str


def _column_boxes(page, config: YearConfig) -> list[tuple[float, float, float, float]]:
    width, height = page.width, page.height
    if config.layout_profile == "three_column_transition":
        return [
            (width * x0, config.crop_top, width * x1, height - config.crop_bottom)
            for x0, x1 in [(0.08, 0.35), (0.36, 0.635), (0.64, 0.91)]
        ]
    usable = width - 2 * config.margin
    column_width = usable / config.n_columns
    boxes = []
    for index in range(config.n_columns):
        x0 = config.margin + index * column_width
        x1 = config.margin + (index + 1) * column_width
        if index > 0:
            x0 += config.overlap
            x1 += config.overlap
        boxes.append((x0, config.crop_top, x1, height - config.crop_bottom))
    if config.directory_year == 1998:
        _, top, right, bottom = boxes[0]
        boxes[0] = (30, top, right, bottom)
    return boxes


def extract_positioned_lines(
    pdf_path: Path, config: YearConfig, max_pages: int | None = None
) -> list[PositionedLine]:
    output: list[PositionedLine] = []
    with pdfplumber.open(pdf_path) as pdf:
        end_page = min(config.end_page, len(pdf.pages))
        if max_pages is not None:
            end_page = min(end_page, config.start_page + max_pages - 1)
        for page_number in range(config.start_page, end_page + 1):
            page = pdf.pages[page_number - 1]
            for column, box in enumerate(_column_boxes(page, config), start=1):
                text = page.crop(box).extract_text(x_tolerance=2, y_tolerance=3) or ""
                for raw in text.splitlines():
                    line = clean_text(raw)
                    if line:
                        output.append(PositionedLine(page_number, column, line))
    return output


def is_city_header(line: str) -> bool:
    text = clean_text(line)
    return (
        bool(text)
        and (text[0].isalpha() or text[0] in "[~")
        and text == text.upper()
        and not any(char.isdigit() for char in text)
        and len(text.split()) <= 6
        and not HEADER_NOISE_RE.search(text)
        and len(text) >= 3
    )


def is_noise(line: str) -> bool:
    return (
        not line
        or bool(HEADER_NOISE_RE.search(line))
        or bool(re.fullmatch(r"[A-Za-z]", line))
        or bool(re.fullmatch(r"(?:[iIl1]\s*){2,}", line))
        or bool(re.fullmatch(r"[^A-Za-z0-9]+", line))
    )


def _split_names_address(buffer: list[str]) -> tuple[str, str, str, list[str]]:
    warnings: list[str] = []
    cleaned = [clean_text(value) for value in buffer if clean_text(value) and not is_noise(value)]
    if not cleaned:
        return "", "", "", ["missing_pre_location_block"]

    address_index = len(cleaned) - 1
    if SECONDARY_RE.search(cleaned[-1]) and len(cleaned) >= 2:
        address_index = len(cleaned) - 2
        address = f"{cleaned[-2]}, {cleaned[-1]}"
    else:
        address = cleaned[-1]

    address = re.sub(r"(?<=\d)(?=[A-Z][a-z])", " ", address)
    address = re.sub(r"\s+[\(\[]\s*$", "", address).strip()

    if not ADDRESS_RE.search(address):
        warnings.append("weak_address_pattern")

    names = cleaned[:address_index]
    if not names:
        warnings.append("missing_facility_name")
        names = [""]
    return names[0], " / ".join(names[1:]), address, warnings


def _listing_id(config: YearConfig, line: PositionedLine, name: str, address: str) -> str:
    key = "|".join(
        [str(config.directory_year), str(line.page), str(line.column), name, address]
    )
    return "L" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:15]


def _source_anchor_id(
    config: YearConfig,
    line: PositionedLine,
    location_anchor: str,
    occurrence: int,
) -> str:
    key = "|".join(
        [
            str(config.directory_year),
            str(line.page),
            str(line.column),
            clean_text(location_anchor).upper(),
            str(occurrence),
        ]
    )
    return "A" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:19]


def _derived_fields(codes: set[str]) -> dict[str, object]:
    ownership_map = {
        "PVTP": "For-profit",
        "PVTN": "Non-profit",
        "LCCG": "Public",
        "STG": "Public",
        "DDF": "Federal",
        "IH": "Federal/Tribal",
        "TBG": "Tribal",
        "VAMC": "Federal",
    }
    ownership = sorted({label for code, label in ownership_map.items() if code in codes})
    settings = [code for code in ["OP", "RES", "HI", "PH", "OD", "ODT", "OIT", "OMB", "ORT", "RD", "RL", "RS"] if code in codes]
    center_types = [code for code in ["SA", "TX", "DT", "HH", "SUMH", "MH", "GH"] if code in codes]
    medication_codes = [
        code
        for code in ["MU", "BU", "NU", "OTP", "MM", "DM", "BUM", "UB", "UN", "NXN", "VTRL"]
        if code in codes
    ]
    return {
        "ownership_type": "|".join(ownership) if ownership else "",
        "center_types": "|".join(center_types),
        "care_settings": "|".join(settings),
        "medication_services": "|".join(medication_codes),
        "accepts_medicaid": "MD" in codes,
        "accepts_medicare": "MC" in codes,
        "accepts_private_insurance": "PI" in codes,
        "offers_telehealth": "TELE" in codes,
    }


def parse_lines(
    lines: list[PositionedLine],
    config: YearConfig,
    codebook: pd.DataFrame,
    source_pdf: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    facilities: list[dict[str, object]] = []
    services: list[dict[str, object]] = []
    buffer: list[str] = []
    current_header = ""
    open_record: dict[str, object] | None = None
    anchor_occurrences: dict[tuple[int, int, str], int] = {}
    record_order = 0
    previous_position: tuple[int, int] | None = None

    def finalize() -> None:
        nonlocal open_record
        if open_record is None:
            return
        service_rows, unknown = parse_service_tokens(
            str(open_record["raw_service_text"]), codebook, config.delimiter
        )
        listing_id = str(open_record["listing_id"])
        for service in service_rows:
            services.append(
                {
                    "listing_id": listing_id,
                    "directory_year": config.directory_year,
                    "survey_year": config.survey_year,
                    **service,
                }
            )
        code_set = {str(row["code"]) for row in service_rows}
        open_record["unknown_service_tokens"] = json.dumps(unknown)
        open_record["service_codes"] = " ".join(sorted(code_set))
        open_record.update(_derived_fields(code_set))
        facilities.append(open_record)
        open_record = None

    for line in lines:
        position = (line.page, line.column)
        if previous_position is not None and position != previous_position:
            finalize()
            buffer = []
        previous_position = position

        text = line.text
        if is_noise(text):
            continue
        location = parse_location(text)

        if location is not None:
            finalize()
            name1, name2, address1, warnings = _split_names_address(buffer)
            listing_id = _listing_id(config, line, name1, address1)
            location_anchor = clean_text(text).upper()
            occurrence_key = (line.page, line.column, location_anchor)
            occurrence = anchor_occurrences.get(occurrence_key, 0) + 1
            anchor_occurrences[occurrence_key] = occurrence
            record_order += 1
            geography = geography_fields(location.state)
            open_record = {
                "listing_id": listing_id,
                "source_anchor_id": _source_anchor_id(
                    config, line, location_anchor, occurrence
                ),
                "source_location_anchor": location_anchor,
                "source_anchor_occurrence": occurrence,
                "source_record_order": record_order,
                "facility_id": "",
                "directory_year": config.directory_year,
                "survey_year": config.survey_year,
                "directory_city_header": current_header,
                "name1": name1,
                "name2": name2,
                "address1": address1,
                "city": location.city,
                "state": location.state,
                "zip": location.zip_code,
                "phone": "",
                "intake_phone": "",
                "county_fips": "",
                "latitude": pd.NA,
                "longitude": pd.NA,
                "geocode_method": "",
                "geocode_confidence": "",
                "source_pdf": source_pdf,
                "source_page": line.page,
                "source_column": line.column,
                "raw_record_text": "\n".join([*buffer, text]),
                "raw_service_text": "",
                "parser_warnings": json.dumps(warnings),
                **geography,
            }
            buffer = []
            continue

        if open_record is not None:
            phone_match = PHONE_RE.search(text)
            if phone_match:
                number = clean_text(phone_match.group("number"))
                label = (phone_match.group("label") or "Phone").lower()
                target = "intake_phone" if "intake" in label or "hotline" in label else "phone"
                if not open_record[target]:
                    open_record[target] = number
                open_record["raw_record_text"] += f"\n{text}"
                continue
            if (
                PHONE_LIKE_RE.search(text)
                or OCR_PHONE_LIKE_RE.search(text)
                or text.lstrip().startswith("(")
            ):
                open_record["raw_record_text"] += f"\n{text}"
                continue
            if CONTACT_NOTE_RE.search(text) or URL_LIKE_RE.search(text):
                open_record["raw_record_text"] += f"\n{text}"
                continue
            if CONTACT_PREFIX_RE.search(text):
                open_record["raw_record_text"] += f"\n{text}"
                continue
            if looks_like_service_line(text, codebook):
                existing = str(open_record["raw_service_text"])
                open_record["raw_service_text"] = clean_text(f"{existing} {text}")
                open_record["raw_record_text"] += f"\n{text}"
                continue
            if (
                not open_record["raw_service_text"]
                and len(text) <= 8
                and not is_city_header(text)
                and re.fullmatch(r"[A-Za-z0-9'\".-]+", text)
            ):
                open_record["raw_service_text"] = text
                open_record["raw_record_text"] += f"\n{text}"
                continue
            finalize()
            buffer = [text]
            if is_city_header(text):
                current_header = text.title()
                buffer = []
            continue

        if is_city_header(text):
            current_header = text.title()
            buffer = []
        else:
            buffer.append(text)
            if len(buffer) > 10:
                buffer = buffer[-10:]

    finalize()
    return pd.DataFrame(facilities), pd.DataFrame(services)


def parse_pdf(
    pdf_path: Path,
    config: YearConfig,
    output_dir: Path | None = None,
    max_pages: int | None = None,
) -> dict[str, pd.DataFrame]:
    codebook = extract_codebook(pdf_path, config)
    lines = extract_positioned_lines(pdf_path, config, max_pages=max_pages)
    facilities, services = parse_lines(lines, config, codebook, pdf_path.name)
    availability = codebook.loc[codebook["asked"]].copy()
    if not services.empty:
        observed_codes = set(services["code"].astype(str))
        missing_codes = observed_codes - set(availability["code"].astype(str))
        if missing_codes:
            observed = codebook.loc[codebook["code"].isin(missing_codes)].copy()
            observed["asked"] = True
            observed["source"] = "observed_listing_fallback"
            availability = pd.concat([availability, observed], ignore_index=True)

    result = {
        "facilities": facilities,
        "facility_services": services,
        "service_availability": availability,
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, frame in result.items():
            frame.to_parquet(output_dir / f"{name}_{config.directory_year}.parquet", index=False)
            frame.to_csv(output_dir / f"{name}_{config.directory_year}.csv", index=False)
    return result
