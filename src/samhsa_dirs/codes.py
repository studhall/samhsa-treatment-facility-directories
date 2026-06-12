from __future__ import annotations

import logging
import re
import unicodedata
from collections import OrderedDict
from pathlib import Path

import pandas as pd
import pdfplumber

from .manifest import YearConfig
from .normalize import clean_text

logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfplumber").setLevel(logging.ERROR)


CATEGORY_HEADINGS = [
    "Primary Focus",
    "Services Provided",
    "Type of Care",
    "Type of Care",
    "Service Settings",
    "Hospitals",
    "Opioid Medications",
    "Alcohol Use Disorder",
    "Type of Opioid Treatment",
    "Pharmacotherapies",
    "Treatment Approaches",
    "Facility Operation",
    "License/Certification/Accreditation",
    "Payment/Insurance/Funding Accepted",
    "Payment Assistance",
    "Special Programs/Groups",
    "Assessment/Pre-treatment",
    "Screening & Testing",
    "Transitional Services",
    "Ancillary Services",
    "Other Addictions",
    "Detoxification",
    "Counseling Services and Education",
    "Medical Services",
    "Tobacco/Screening Services",
    "Facility Smoking Policy",
    "Age Groups Accepted",
    "Gender Accepted",
    "Exclusive Services",
    "Language Services",
]

CORE_LABELS = {
    "SA": ("Type of Care", "Substance use treatment"),
    "TX": ("Services Provided", "Substance abuse treatment"),
    "DT": ("Type of Care", "Detoxification"),
    "HH": ("Type of Care", "Transitional housing or halfway house"),
    "SUMH": ("Type of Care", "Co-occurring mental health and substance use treatment"),
    "OP": ("Service Settings", "Outpatient"),
    "RES": ("Service Settings", "Residential"),
    "HI": ("Service Settings", "Hospital inpatient"),
    "OD": ("Service Settings", "Outpatient detoxification"),
    "ODT": ("Service Settings", "Outpatient day treatment"),
    "OIT": ("Service Settings", "Intensive outpatient treatment"),
    "OMB": ("Service Settings", "Outpatient medication treatment"),
    "ORT": ("Service Settings", "Regular outpatient treatment"),
    "RD": ("Service Settings", "Residential detoxification"),
    "RL": ("Service Settings", "Long-term residential"),
    "RS": ("Service Settings", "Short-term residential"),
    "PH": ("Service Settings", "Partial hospitalization/day treatment"),
    "PVTP": ("Facility Operation", "Private for-profit organization"),
    "PVTN": ("Facility Operation", "Private non-profit organization"),
    "LCCG": ("Facility Operation", "Local, county, or community government"),
    "STG": ("Facility Operation", "State government"),
    "TBG": ("Facility Operation", "Tribal government"),
    "DDF": ("Facility Operation", "Department of Defense"),
    "IH": ("Facility Operation", "Indian Health Service"),
    "VAMC": ("Facility Operation", "Department of Veterans Affairs"),
    "MC": ("Payment/Insurance/Funding Accepted", "Medicare"),
    "MD": ("Payment/Insurance/Funding Accepted", "Medicaid"),
    "MI": ("Payment/Insurance/Funding Accepted", "Military insurance"),
    "PI": ("Payment/Insurance/Funding Accepted", "Private health insurance"),
    "SF": ("Payment/Insurance/Funding Accepted", "Cash or self-payment"),
    "SI": ("Payment/Insurance/Funding Accepted", "State-financed insurance"),
    "PA": ("Payment Assistance", "Payment assistance"),
    "SS": ("Payment Assistance", "Sliding fee scale"),
    "MU": ("Medication Services", "Methadone used in treatment"),
    "BU": ("Medication Services", "Buprenorphine used in treatment"),
    "NU": ("Medication Services", "Naltrexone used in treatment"),
    "OTP": ("Medication Services", "SAMHSA-certified opioid treatment program"),
    "MM": ("Medication Services", "Methadone maintenance"),
    "DM": ("Medication Services", "Methadone detoxification"),
    "TELE": ("Telemedicine", "Telemedicine/telehealth"),
    "AH": ("Language Services", "Services for deaf and hard of hearing"),
    "SP": ("Language Services", "Spanish"),
}

MASTER_CODES = {
    "SA", "TX", "DT", "HH", "SUMH", "TELE", "MH", "MH-SA", "PH", "RR", "DD",
    "OW", "OA", "IHS", "ATR", "SP", "FX", "NX", "HI", "OP", "RES", "HID",
    "HIT", "OD", "ODT", "OIT", "OMB", "ORT", "RD", "RL", "RS", "GH", "PSYH",
    "MU", "BU", "NU", "INPE", "RPE", "PC", "NAUT", "NMAUT", "ACMA", "PMAT",
    "AUINPE", "AURPE", "AUPC", "DB", "BUM", "BMW", "OTP", "DM", "MM", "MMW",
    "UB", "UN", "RPN", "PAIN", "MOA", "NMOA", "ULC", "NOOP", "ACM", "DSF",
    "METH", "BSDM", "BWN", "BWON", "BERI", "NXN", "VTRL", "MPD", "MHIV",
    "MHCV", "LFXD", "CLND", "ANG", "BIA", "CBT", "CMI", "CRV", "DBT", "MOTI",
    "MXM", "REBT", "RELP", "SACA", "TRC", "TWFA", "DDF", "IH", "LCCG", "PVTP",
    "PVTN", "STG", "TBG", "VAMC", "STAG", "STMH", "STDH", "CARF", "COA",
    "HFAP", "HLA", "JC", "NCQA", "FQHC", "FSA", "ITU", "MC", "MD", "MI", "NP",
    "PI", "SF", "SI", "PA", "SS", "AD", "TAY", "WN", "PW", "MN", "SE", "GL",
    "VET", "ADM", "MF", "CJ", "CO", "COPSU", "HV", "XA", "DV", "TRMA", "CMHA",
    "CSAA", "ISC", "OPC", "BABA", "DAOF", "DAUT", "HIVT", "SHB", "SHC",
    "SMHD", "SSA", "STDT", "TBS", "MST", "ACC", "DP", "NOE", "OFD", "ACU",
    "AOSS", "BC", "CCC", "CM", "DVFP", "EIH", "HS", "MHS", "PEER", "RC",
    "SHG", "SSD", "TA", "PIEC", "ADD", "TGD", "TID", "ADTX", "BDTX", "CDTX",
    "ODTX", "MDTX", "MDET", "ICO", "GCO", "FCO", "MCO", "SAE", "TAEC", "HAEC",
    "HEOH", "EMP", "VOC", "HAV", "HBV", "NRT", "NSC", "STU", "TCC", "SMON",
    "SMOP", "SMPD", "ADLT", "CHLD", "SNR", "YAD", "FEM", "MALE", "BMO", "DU",
    "DUO", "MO", "OTPA", "VO", "AUDO", "AH",
}
MASTER_CODES.update(CORE_LABELS)

CODE_RE = re.compile(r"^(?P<code>[A-Z][A-Z0-9-]{0,7}|[FN]\d{1,3})\s+(?P<label>.+)$")
TOKEN_RE = re.compile(r"\b(?:[A-Z][A-Z0-9-]{0,7}|[FN]\d{1,3})\b")
GROUP_MARKER_RE = re.compile(r"(?:^|\s)(?:[1-9]|[12]\d|3[01])(?:\s|$)")
SERVICE_SEPARATOR_RE = re.compile(r"[+&~/]")


def _heading_for(line: str, current: str) -> str:
    upper = line.upper()
    for heading in CATEGORY_HEADINGS:
        if heading.upper() in upper:
            return heading
    return current


def extract_codebook(pdf_path: Path, config: YearConfig) -> pd.DataFrame:
    rows: OrderedDict[str, dict[str, object]] = OrderedDict()
    current_category = "Unclassified"
    with pdfplumber.open(pdf_path) as pdf:
        legend_end = min(max(config.start_page - 1, 1), len(pdf.pages))
        for page_number in range(1, legend_end + 1):
            text = pdf.pages[page_number - 1].extract_text(x_tolerance=2, y_tolerance=3) or ""
            for raw in text.splitlines():
                line = clean_text(raw)
                if not line:
                    continue
                current_category = _heading_for(line, current_category)
                match = CODE_RE.match(line)
                if not match:
                    continue
                code = match.group("code")
                label = clean_text(match.group("label"))
                if code not in MASTER_CODES and not re.fullmatch(r"[FN]\d{1,3}", code):
                    continue
                if len(code) > 6 and not re.fullmatch(r"[FN]\d{1,3}", code):
                    continue
                fallback = CORE_LABELS.get(code)
                rows.setdefault(
                    code,
                    {
                        "directory_year": config.directory_year,
                        "survey_year": config.survey_year,
                        "category": fallback[0] if fallback else current_category,
                        "code": code,
                        "label": fallback[1] if fallback else label,
                        "asked": True,
                        "source": "pdf_legend",
                    },
                )

    for code in sorted(MASTER_CODES):
        category, label = CORE_LABELS.get(code, ("Unclassified", ""))
        rows.setdefault(
            code,
            {
                "directory_year": config.directory_year,
                "survey_year": config.survey_year,
                "category": category,
                "code": code,
                "label": label,
                "asked": False,
                "source": "fallback_dictionary",
            },
        )
    return pd.DataFrame(rows.values())


def normalize_markers(text: str) -> str:
    output = text or ""
    for char in list(output):
        try:
            numeric = unicodedata.numeric(char)
        except (TypeError, ValueError):
            continue
        name = unicodedata.name(char, "")
        if "CIRCLED" in name and float(numeric).is_integer():
            output = output.replace(char, f" |{int(numeric)}| ")
    output = unicodedata.normalize("NFKC", output)
    output = re.sub(r"\(cid:\d+\)", " | ", output)
    output = re.sub(r"[♦◆◇◊■▪●•·�]+", " | ", output)
    return clean_text(output)


def parse_service_tokens(
    raw_text: str, codebook: pd.DataFrame, delimiter: str
) -> tuple[list[dict[str, object]], list[str]]:
    normalized = normalize_markers(raw_text)
    if delimiter == "slash":
        pieces = re.split(r"\s*/\s*", normalized)
    else:
        pieces = re.split(r"\|\d*\||\|", normalized)

    known = set(codebook.loc[codebook["asked"], "code"].astype(str))
    fallback = MASTER_CODES
    rows: list[dict[str, object]] = []
    unknown: list[str] = []
    seen: set[tuple[int, str]] = set()

    for group_index, piece in enumerate(pieces, start=1):
        for token in TOKEN_RE.findall(piece.upper()):
            if token in {"PHONE", "INTAKE", "TOLL", "FREE", "HOTLINE"}:
                continue
            is_known = token in known or token in fallback or bool(re.fullmatch(r"[FN]\d{1,3}", token))
            if not is_known and len(token) > 4:
                continue
            key = (group_index, token)
            if key in seen:
                continue
            seen.add(key)
            match = codebook.loc[codebook["code"] == token]
            category = match.iloc[0]["category"] if not match.empty else "Unknown"
            label = match.iloc[0]["label"] if not match.empty else ""
            rows.append(
                {
                    "group_index": group_index,
                    "code": token,
                    "category": category,
                    "label": label,
                    "known_code": is_known,
                    "status": "offered",
                }
            )
            if not is_known:
                unknown.append(token)
    return rows, list(dict.fromkeys(unknown))


def looks_like_service_line(line: str, codebook: pd.DataFrame) -> bool:
    normalized = normalize_markers(line)
    if re.search(r"\|\d+\|", normalized):
        return True
    tokens = TOKEN_RE.findall(normalized.upper())
    if not tokens:
        return False
    known = set(codebook.loc[codebook["asked"], "code"].astype(str)) | MASTER_CODES
    hits = sum(token in known or bool(re.fullmatch(r"[FN]\d{1,3}", token)) for token in tokens)
    if GROUP_MARKER_RE.search(normalized) and hits >= 1:
        return True
    if len(SERVICE_SEPARATOR_RE.findall(normalized)) >= 2 and hits >= 1:
        return True
    has_lowercase = any(char.islower() for char in normalized)
    return not has_lowercase and hits >= 1 and hits / len(tokens) >= 0.35
