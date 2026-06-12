from __future__ import annotations

import hashlib
from difflib import SequenceMatcher

import pandas as pd

from .normalize import normalize_key


def _entity_id(seed: str) -> str:
    return "F" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:14]


def link_facilities(
    facilities: pd.DataFrame,
    fuzzy_threshold: float = 0.93,
) -> pd.DataFrame:
    frame = facilities.copy().sort_values(
        ["survey_year", "state", "zip", "name1", "listing_id"]
    )
    frame["name_key"] = frame["name1"].fillna("").map(normalize_key)
    frame["address_key"] = frame["address1"].fillna("").map(normalize_key)
    frame["exact_key"] = (
        frame["state"].fillna("")
        + "|"
        + frame["zip"].fillna("")
        + "|"
        + frame["name_key"]
        + "|"
        + frame["address_key"]
    )

    entities: dict[str, dict[str, object]] = {}
    exact_index: dict[str, str] = {}
    rows: list[dict[str, object]] = []

    for record in frame.to_dict("records"):
        exact = exact_index.get(record["exact_key"])
        method = "new_entity"
        confidence = 1.0
        review = "not_required"

        if exact:
            facility_id = exact
            method = "exact_name_address"
        else:
            candidates = [
                (facility_id, entity)
                for facility_id, entity in entities.items()
                if entity["state"] == record["state"] and entity["zip"] == record["zip"]
            ]
            scored = []
            for facility_id, entity in candidates:
                name_score = SequenceMatcher(
                    None, record["name_key"], str(entity["name_key"])
                ).ratio()
                address_score = SequenceMatcher(
                    None, record["address_key"], str(entity["address_key"])
                ).ratio()
                score = 0.65 * name_score + 0.35 * address_score
                scored.append((score, facility_id))
            scored.sort(reverse=True)
            if scored and scored[0][0] >= fuzzy_threshold:
                confidence, facility_id = scored[0]
                method = "fuzzy_within_zip"
                review = "manual_review" if confidence < 0.97 else "not_required"
            else:
                facility_id = _entity_id(record["exact_key"] + "|" + record["listing_id"])
                entities[facility_id] = record

        exact_index[record["exact_key"]] = facility_id
        rows.append(
            {
                "listing_id": record["listing_id"],
                "facility_id": facility_id,
                "linkage_method": method,
                "linkage_confidence": round(float(confidence), 4),
                "review_status": review,
            }
        )
    return pd.DataFrame(rows)

