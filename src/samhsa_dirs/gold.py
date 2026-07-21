from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pdfplumber

from .manifest import load_manifest
from .normalize import normalize_key
from .runs import validate_complete_run


PRIORITY_YEARS = {1998, 2000, 2001, 2003, 2004, 2017, 2018, 2021}
EARLY_YEARS = {1998, 2000, 2001}
BASELINE_SAMPLE_SIZE = {year: (100 if year in PRIORITY_YEARS else 50) for year in [
    1998, 2000, 2001, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010,
    2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021,
]}
STRATUM_SHARES = {
    "random": 0.50,
    "warning_unknown": 0.20,
    "boundary": 0.10,
    "rare_dense_services": 0.10,
    "complex_record": 0.10,
}
CHECK_VALUES = {"yes", "no", "uncertain"}

REVIEW_COLUMNS = [
    "sample_id",
    "source_anchor_id",
    "listing_id_at_sampling",
    "directory_year",
    "survey_year",
    "source_pdf",
    "source_page",
    "source_column",
    "source_record_order",
    "sample_stratum",
    "review_disposition",
    "replacement_for_sample_id",
    "page_quantile",
    "parsed_name1",
    "parsed_name2",
    "parsed_address1",
    "parsed_city",
    "parsed_state",
    "parsed_zip",
    "parsed_service_codes",
    "raw_record_text",
    "raw_service_text",
    "parser_warnings",
    "unknown_service_tokens",
    "page_image",
    "corrected_name1",
    "corrected_name2",
    "corrected_address1",
    "corrected_city",
    "corrected_state",
    "corrected_zip",
    "corrected_service_codes",
    "name_check",
    "address_check",
    "services_check",
    "boundary_check",
    "review_complete",
    "reviewer",
    "reviewed_at",
    "notes",
]


def _load_run_metadata(run_dir: Path) -> dict[str, object]:
    return json.loads((run_dir / "run.json").read_text(encoding="utf-8"))


def load_run_facilities(run_dir: Path) -> pd.DataFrame:
    expected_years = [config.directory_year for config in load_manifest()]
    errors = validate_complete_run(run_dir, expected_years)
    if errors:
        raise ValueError(
            "Gold sampling requires a structurally passing 22-year run:\n"
            + "\n".join(errors)
        )
    frames = [
        pd.read_parquet(run_dir / "years" / str(year) / "facilities.parquet")
        for year in expected_years
    ]
    return pd.concat(frames, ignore_index=True)


def add_sampling_features(facilities: pd.DataFrame) -> pd.DataFrame:
    frame = facilities.copy()
    ranks = frame.groupby("directory_year")["source_page"].rank(
        method="dense", pct=True
    )
    frame["page_quantile"] = np.minimum(np.ceil(ranks * 5).astype(int), 5)
    frame["has_warning_unknown"] = (
        frame["parser_warnings"].fillna("").ne("[]")
        | frame["unknown_service_tokens"].fillna("").ne("[]")
    )
    page_column = frame.groupby(
        ["directory_year", "source_page", "source_column"]
    )["source_record_order"]
    frame["is_boundary"] = (
        frame["source_record_order"].eq(page_column.transform("min"))
        | frame["source_record_order"].eq(page_column.transform("max"))
    )
    code_lists = frame["service_codes"].fillna("").map(
        lambda value: sorted(set(str(value).split()))
    )
    code_frequency: dict[int, dict[str, int]] = {}
    for year, indexes in frame.groupby("directory_year").groups.items():
        counts: dict[str, int] = {}
        for codes in code_lists.loc[indexes]:
            for code in codes:
                counts[code] = counts.get(code, 0) + 1
        code_frequency[int(year)] = counts
    service_counts = code_lists.map(len)
    dense_threshold = service_counts.groupby(frame["directory_year"]).transform(
        lambda values: max(float(values.quantile(0.90)), 1)
    )
    rare_service = [
        any(code_frequency[int(year)].get(code, 0) <= 10 for code in codes)
        for year, codes in zip(frame["directory_year"], code_lists, strict=True)
    ]
    frame["is_rare_dense"] = pd.Series(rare_service, index=frame.index) | service_counts.ge(
        dense_threshold
    )
    duplicate_address = frame.duplicated(
        ["directory_year", "state", "city", "address1"], keep=False
    )
    complex_text = (
        frame["raw_record_text"].fillna("").str.count("\n").ge(5)
        | frame["name1"].fillna("").str.len().ge(50)
        | frame["name2"].fillna("").ne("")
        | frame["address1"]
        .fillna("")
        .str.contains(r"\b(?:Suite|Ste|Unit|Room|Floor|Building|Bldg|Apt|#)\b", case=False)
        | duplicate_address
    )
    frame["is_complex"] = complex_text
    return frame


def _quota_counts(total: int) -> dict[str, int]:
    quotas = {
        name: int(round(total * share)) for name, share in STRATUM_SHARES.items()
    }
    quotas["random"] += total - sum(quotas.values())
    return quotas


def _round_robin_sample(
    candidates: pd.DataFrame,
    n: int,
    rng: np.random.Generator,
    group_columns: list[str],
) -> list[int]:
    if n <= 0 or candidates.empty:
        return []
    shuffled = candidates.assign(_random=rng.random(len(candidates))).sort_values(
        [*group_columns, "_random"]
    )
    queues = {
        key: list(group.index)
        for key, group in shuffled.groupby(group_columns, dropna=False, sort=True)
    }
    keys = list(queues)
    rng.shuffle(keys)
    selected: list[int] = []
    while keys and len(selected) < n:
        remaining = []
        for key in keys:
            queue = queues[key]
            if queue and len(selected) < n:
                selected.append(queue.pop(0))
            if queue:
                remaining.append(key)
        keys = remaining
    return selected


def sample_year(
    facilities: pd.DataFrame,
    year: int,
    sample_size: int,
    seed: int,
) -> pd.DataFrame:
    group = facilities.loc[facilities["directory_year"].eq(year)].copy()
    if len(group) < sample_size:
        raise ValueError(f"{year} has only {len(group)} records for a {sample_size}-row sample")
    rng = np.random.default_rng(seed + year)
    quotas = _quota_counts(sample_size)
    selected: set[int] = set()
    strata: dict[int, str] = {}
    candidate_rules = [
        ("warning_unknown", "has_warning_unknown"),
        ("boundary", "is_boundary"),
        ("rare_dense_services", "is_rare_dense"),
        ("complex_record", "is_complex"),
    ]
    for stratum, flag in candidate_rules:
        candidates = group.loc[group[flag] & ~group.index.isin(selected)]
        indexes = _round_robin_sample(
            candidates,
            quotas[stratum],
            rng,
            ["page_quantile", "source_column", "census_region", "state"],
        )
        selected.update(indexes)
        strata.update({index: stratum for index in indexes})

    random_target = sample_size - len(selected)
    random_candidates = group.loc[~group.index.isin(selected)]
    random_indexes = _round_robin_sample(
        random_candidates,
        random_target,
        rng,
        ["page_quantile", "source_column", "census_region", "state"],
    )
    selected.update(random_indexes)
    strata.update({index: "random" for index in random_indexes})
    if len(selected) != sample_size:
        raise RuntimeError(f"Could not construct the requested {year} gold sample")

    sample = group.loc[sorted(selected)].copy()
    sample["sample_stratum"] = sample.index.map(strata)
    sample["_sort"] = rng.random(len(sample))
    return sample.sort_values(["sample_stratum", "_sort"]).drop(columns="_sort")


def create_gold_sample(
    run_dir: Path,
    output_dir: Path,
    seed: int = 20260612,
    sample_sizes: dict[int, int] | None = None,
) -> pd.DataFrame:
    facilities = add_sampling_features(load_run_facilities(run_dir))
    sizes = sample_sizes or BASELINE_SAMPLE_SIZE
    samples = [
        sample_year(facilities, year, sizes[year], seed)
        for year in sorted(sizes)
    ]
    sample = pd.concat(samples, ignore_index=True)
    if sample["source_anchor_id"].duplicated().any():
        raise RuntimeError("Gold sample contains duplicate source anchors")
    sample["sample_id"] = [
        "G"
        + hashlib.sha1(
            f"{seed}|{anchor}".encode("utf-8")
        ).hexdigest()[:15]
        for anchor in sample["source_anchor_id"]
    ]
    review = pd.DataFrame(
        {
            "sample_id": sample["sample_id"],
            "source_anchor_id": sample["source_anchor_id"],
            "listing_id_at_sampling": sample["listing_id"],
            "directory_year": sample["directory_year"],
            "survey_year": sample["survey_year"],
            "source_pdf": sample["source_pdf"],
            "source_page": sample["source_page"],
            "source_column": sample["source_column"],
            "source_record_order": sample["source_record_order"],
            "sample_stratum": sample["sample_stratum"],
            "review_disposition": "active",
            "replacement_for_sample_id": "",
            "page_quantile": sample["page_quantile"],
            "parsed_name1": sample["name1"],
            "parsed_name2": sample["name2"],
            "parsed_address1": sample["address1"],
            "parsed_city": sample["city"],
            "parsed_state": sample["state"],
            "parsed_zip": sample["zip"].astype(str).str.replace(r"\.0$", "", regex=True),
            "parsed_service_codes": sample["service_codes"],
            "raw_record_text": sample["raw_record_text"],
            "raw_service_text": sample["raw_service_text"],
            "parser_warnings": sample["parser_warnings"],
            "unknown_service_tokens": sample["unknown_service_tokens"],
            "page_image": "",
        }
    )
    for column in REVIEW_COLUMNS:
        if column not in review:
            review[column] = ""
    review = review[REVIEW_COLUMNS]
    output_dir.mkdir(parents=True, exist_ok=True)
    review.to_csv(output_dir / "gold_review_source.csv", index=False)
    (output_dir / "gold_review_source.json").write_text(
        json.dumps(review.fillna("").to_dict(orient="records"), indent=2),
        encoding="utf-8",
    )
    metadata = {
        "run_dir": str(run_dir.resolve()),
        "seed": seed,
        "total_rows": len(review),
        "sample_sizes": {str(year): int(size) for year, size in sizes.items()},
        "stratum_counts": review["sample_stratum"].value_counts().to_dict(),
    }
    (output_dir / "gold_sample_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return review


def _sample_ids(anchors: pd.Series, seed: int) -> list[str]:
    return [
        "G" + hashlib.sha1(f"{seed}|{anchor}".encode("utf-8")).hexdigest()[:15]
        for anchor in anchors
    ]


def _sample_to_review(
    sample: pd.DataFrame,
    seed: int,
    replacement_for: dict[str, str] | None = None,
) -> pd.DataFrame:
    replacement_for = replacement_for or {}
    review = pd.DataFrame(
        {
            "sample_id": _sample_ids(sample["source_anchor_id"], seed),
            "source_anchor_id": sample["source_anchor_id"],
            "listing_id_at_sampling": sample["listing_id"],
            "directory_year": sample["directory_year"],
            "survey_year": sample["survey_year"],
            "source_pdf": sample["source_pdf"],
            "source_page": sample["source_page"],
            "source_column": sample["source_column"],
            "source_record_order": sample["source_record_order"],
            "sample_stratum": sample["sample_stratum"],
            "review_disposition": "active",
            "replacement_for_sample_id": [
                replacement_for.get(str(anchor), "")
                for anchor in sample["source_anchor_id"]
            ],
            "page_quantile": sample["page_quantile"],
            "parsed_name1": sample["name1"],
            "parsed_name2": sample["name2"],
            "parsed_address1": sample["address1"],
            "parsed_city": sample["city"],
            "parsed_state": sample["state"],
            "parsed_zip": sample["zip"].astype(str).str.replace(
                r"\.0$", "", regex=True
            ),
            "parsed_service_codes": sample["service_codes"],
            "raw_record_text": sample["raw_record_text"],
            "raw_service_text": sample["raw_service_text"],
            "parser_warnings": sample["parser_warnings"],
            "unknown_service_tokens": sample["unknown_service_tokens"],
            "page_image": "",
        }
    )
    for column in REVIEW_COLUMNS:
        if column not in review:
            review[column] = ""
    return review[REVIEW_COLUMNS]


def expand_gold_sample(
    run_dir: Path,
    existing_review_path: Path,
    output_dir: Path,
    target_sizes: dict[int, int],
    seed: int = 20260612,
) -> pd.DataFrame:
    facilities = add_sampling_features(load_run_facilities(run_dir))
    existing = pd.read_csv(existing_review_path, dtype=str).fillna("")
    for column in REVIEW_COLUMNS:
        if column not in existing:
            existing[column] = ""
    existing = existing[REVIEW_COLUMNS]
    existing.loc[
        existing["review_disposition"].eq(""), "review_disposition"
    ] = "active"
    uncertain = existing[
        ["name_check", "address_check", "services_check", "boundary_check"]
    ].apply(lambda column: column.str.lower().eq("uncertain")).any(axis=1)
    existing.loc[uncertain, "review_disposition"] = "unreviewable_replaced"

    additions: list[pd.DataFrame] = []
    used_anchors = set(existing["source_anchor_id"])
    feature_rules = {
        "warning_unknown": "has_warning_unknown",
        "boundary": "is_boundary",
        "rare_dense_services": "is_rare_dense",
        "complex_record": "is_complex",
    }
    for year in sorted(target_sizes):
        target = min(int(target_sizes[year]), 200)
        year_existing = existing.loc[existing["directory_year"].astype(int).eq(year)]
        active_count = int(
            year_existing["review_disposition"].str.lower().eq("active").sum()
        )
        needed = max(target - active_count, 0)
        if needed == 0:
            continue
        candidates = facilities.loc[
            facilities["directory_year"].eq(year)
            & ~facilities["source_anchor_id"].isin(used_anchors)
        ].copy()
        rng = np.random.default_rng(seed + year + 10_000)
        replacement_map: dict[str, str] = {}
        replacement_indexes: list[int] = []
        replacement_strata: list[str] = []
        unreviewable = year_existing.loc[
            year_existing["review_disposition"].eq("unreviewable_replaced")
        ]
        for old in unreviewable.itertuples(index=False):
            stratum = str(old.sample_stratum)
            pool = candidates.loc[~candidates.index.isin(replacement_indexes)]
            if stratum in feature_rules:
                pool = pool.loc[pool[feature_rules[stratum]]]
            indexes = _round_robin_sample(
                pool,
                1,
                rng,
                ["page_quantile", "source_column", "census_region", "state"],
            )
            if not indexes:
                continue
            index = indexes[0]
            replacement_indexes.append(index)
            replacement_strata.append(stratum)
            replacement_map[str(candidates.loc[index, "source_anchor_id"])] = str(
                old.sample_id
            )
            if len(replacement_indexes) >= needed:
                break
        if replacement_indexes:
            replacements = candidates.loc[replacement_indexes].copy()
            replacements["sample_stratum"] = replacement_strata
            additions.append(
                _sample_to_review(replacements, seed, replacement_map)
            )
            used_anchors.update(replacements["source_anchor_id"])

        remaining = needed - len(replacement_indexes)
        if remaining:
            available = facilities.loc[
                facilities["directory_year"].eq(year)
                & ~facilities["source_anchor_id"].isin(used_anchors)
            ]
            expansion = sample_year(available, year, remaining, seed + 20_000)
            additions.append(_sample_to_review(expansion, seed))
            used_anchors.update(expansion["source_anchor_id"])

    review = pd.concat([existing, *additions], ignore_index=True)
    if review["source_anchor_id"].duplicated().any():
        raise RuntimeError("Expanded gold sample contains duplicate source anchors")
    output_dir.mkdir(parents=True, exist_ok=True)
    review.to_csv(output_dir / "gold_review_source.csv", index=False)
    (output_dir / "gold_review_source.json").write_text(
        json.dumps(review.fillna("").to_dict(orient="records"), indent=2),
        encoding="utf-8",
    )
    return review


def refresh_gold_sample(
    run_dir: Path,
    existing_review_path: Path,
    output_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    current = load_run_facilities(run_dir)
    existing = pd.read_csv(existing_review_path, dtype=str).fillna("")
    for column in REVIEW_COLUMNS:
        if column not in existing:
            existing[column] = ""
    existing = existing[REVIEW_COLUMNS]

    if current["source_anchor_id"].duplicated().any():
        raise RuntimeError("Current run contains duplicate source anchors")
    reanchored_rows: list[dict[str, object]] = []
    current_lookup = current.copy()
    unmatched_initial = ~existing["source_anchor_id"].isin(
        current_lookup["source_anchor_id"]
    )
    for index, row in existing.loc[unmatched_initial].iterrows():
        candidates = current_lookup.loc[
            current_lookup["directory_year"].astype(str).eq(
                str(row["directory_year"])
            )
            & current_lookup["source_page"].astype(str).eq(
                str(row["source_page"])
            )
            & current_lookup["source_column"].astype(str).eq(
                str(row["source_column"])
            )
            & current_lookup["source_record_order"].astype(str).eq(
                str(row["source_record_order"])
            )
        ]
        if len(candidates) != 1:
            continue
        replacement_anchor = str(candidates.iloc[0]["source_anchor_id"])
        reanchored_rows.append(
            {
                "sample_id": row["sample_id"],
                "old_source_anchor_id": row["source_anchor_id"],
                "new_source_anchor_id": replacement_anchor,
                "directory_year": row["directory_year"],
                "source_page": row["source_page"],
                "source_column": row["source_column"],
                "source_record_order": row["source_record_order"],
                "review_complete": row["review_complete"],
                "reason": "exact page-column-record-order fallback",
            }
        )
        existing.at[index, "source_anchor_id"] = replacement_anchor

    current = current_lookup.set_index("source_anchor_id")
    matched = existing["source_anchor_id"].isin(current.index)
    refresh_fields = {
        "parsed_name1": "name1",
        "parsed_name2": "name2",
        "parsed_address1": "address1",
        "parsed_city": "city",
        "parsed_state": "state",
        "parsed_zip": "zip",
        "parsed_service_codes": "service_codes",
        "raw_record_text": "raw_record_text",
        "raw_service_text": "raw_service_text",
        "parser_warnings": "parser_warnings",
        "unknown_service_tokens": "unknown_service_tokens",
    }
    anchors = existing.loc[matched, "source_anchor_id"]
    for review_column, current_column in refresh_fields.items():
        values = anchors.map(current[current_column]).fillna("").astype(str)
        if review_column == "parsed_zip":
            values = values.str.replace(r"\.0$", "", regex=True)
        existing.loc[matched, review_column] = values.to_numpy()

    unmatched = existing.loc[
        ~matched,
        [
            "sample_id",
            "source_anchor_id",
            "directory_year",
            "source_page",
            "source_column",
            "sample_stratum",
        ],
    ].copy()
    output_dir.mkdir(parents=True, exist_ok=True)
    existing.to_csv(output_dir / "gold_review_source.csv", index=False)
    (output_dir / "gold_review_source.json").write_text(
        json.dumps(existing.fillna("").to_dict(orient="records"), indent=2),
        encoding="utf-8",
    )
    unmatched.to_csv(output_dir / "gold_refresh_unmatched.csv", index=False)
    pd.DataFrame(reanchored_rows).to_csv(
        output_dir / "gold_refresh_reanchored.csv",
        index=False,
    )
    return existing, unmatched


def render_sample_pages(
    review: pd.DataFrame,
    pdf_dir: Path,
    output_dir: Path,
    resolution: int = 110,
) -> pd.DataFrame:
    rendered = review.copy()
    for (year, source_pdf), group in rendered.groupby(
        ["directory_year", "source_pdf"]
    ):
        image_dir = output_dir / "assets" / str(year)
        image_dir.mkdir(parents=True, exist_ok=True)
        with pdfplumber.open(pdf_dir / str(source_pdf)) as pdf:
            for page_number in sorted(group["source_page"].astype(int).unique()):
                image_path = image_dir / f"page_{page_number:04d}.png"
                if not image_path.exists():
                    page = pdf.pages[page_number - 1]
                    page.to_image(resolution=resolution).save(
                        image_path, format="PNG"
                    )
                mask = (
                    rendered["directory_year"].eq(year)
                    & rendered["source_page"].astype(int).eq(page_number)
                )
                rendered.loc[mask, "page_image"] = image_path.relative_to(
                    output_dir
                ).as_posix()
    rendered.to_csv(output_dir / "gold_review_source.csv", index=False)
    (output_dir / "gold_review_source.json").write_text(
        json.dumps(rendered.fillna("").to_dict(orient="records"), indent=2),
        encoding="utf-8",
    )
    return rendered


def _node_environment(node_modules: Path | None) -> dict[str, str]:
    environment = os.environ.copy()
    if node_modules:
        environment["NODE_PATH"] = str(node_modules)
    return environment


def build_gold_workbook(
    source_json: Path,
    workbook_path: Path,
    preview_dir: Path,
    node: Path,
    node_modules: Path | None = None,
) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "build_gold_workbook.mjs"
    subprocess.run(
        [
            str(node),
            str(script),
            str(source_json),
            str(workbook_path),
            str(preview_dir),
        ],
        check=True,
        env=_node_environment(node_modules),
        cwd=script.parent.parent,
    )


def import_gold_workbook(
    workbook_path: Path,
    output_path: Path,
    node: Path,
    node_modules: Path | None = None,
) -> pd.DataFrame:
    script = Path(__file__).resolve().parents[2] / "scripts" / "import_gold_workbook.mjs"
    json_path = output_path.with_suffix(".import.json")
    subprocess.run(
        [str(node), str(script), str(workbook_path), str(json_path)],
        check=True,
        env=_node_environment(node_modules),
        cwd=script.parent.parent,
    )
    records = json.loads(json_path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(records).fillna("")
    missing = [column for column in REVIEW_COLUMNS if column not in frame]
    if missing:
        raise ValueError(f"Workbook is missing review columns: {', '.join(missing)}")
    for column in ["name_check", "address_check", "services_check", "boundary_check"]:
        invalid = sorted(
            set(frame[column].str.lower()) - CHECK_VALUES - {""}
        )
        if invalid:
            raise ValueError(f"Invalid {column} values: {invalid}")
    frame["review_complete"] = frame["review_complete"].str.lower()
    if not set(frame["review_complete"]) <= {"", "yes", "no"}:
        raise ValueError("review_complete must be yes, no, or blank")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    try:
        json_path.unlink(missing_ok=True)
    except PermissionError:
        # OneDrive may briefly retain the import file after Node exits.
        pass
    return frame


def _canonical_service_codes(value: object) -> set[str]:
    output: set[str] = set()
    for token in re.split(r"[\s,;|]+", str(value or "").strip()):
        token = token.upper()
        if not token:
            continue
        if token == "PL":
            output.add("PI")
        elif token == "SSCM":
            output.update({"SS", "CM"})
        elif token == "SSTC":
            output.update({"SS", "TC"})
        else:
            output.add(token)
    return output


def _gold_value(row: pd.Series, corrected: str, parsed: str) -> str:
    value = str(row.get(corrected, "") or "").strip()
    return value if value else str(row.get(parsed, "") or "").strip()


def _gold_name_parts(row: pd.Series) -> tuple[str, str]:
    corrected_name1 = str(row.get("corrected_name1", "") or "").strip()
    corrected_name2 = str(row.get("corrected_name2", "") or "").strip()
    if corrected_name1 or corrected_name2:
        return corrected_name1, corrected_name2
    return (
        str(row.get("parsed_name1", "") or "").strip(),
        str(row.get("parsed_name2", "") or "").strip(),
    )


def year_threshold(directory_year: int) -> float:
    return 0.95 if directory_year in EARLY_YEARS else 0.98


def evaluate_year_metrics(year: int, group: pd.DataFrame) -> dict[str, object]:
    target = year_threshold(year)
    uncertain = group[
        ["name_check", "address_check", "services_check", "boundary_check"]
    ].apply(lambda column: column.str.lower().eq("uncertain")).any(axis=1)
    boundary_errors = group["boundary_check"].str.lower().eq("no")
    concentrated = (
        group.loc[
            ~(
                group["name_accurate"]
                & group["address_accurate"]
                & group["service_accurate"]
            ),
            "sample_stratum",
        ]
        .value_counts(normalize=True)
        .max()
    )
    concentrated = float(concentrated) if pd.notna(concentrated) else 0.0
    metrics: dict[str, object] = {
        "directory_year": year,
        "reviewed_rows": len(group),
        "target": target,
        "name_accuracy": float(group["name_accurate"].mean()),
        "address_accuracy": float(group["address_accurate"].mean()),
        "service_accuracy": float(group["service_accurate"].mean()),
        "uncertain_share": float(uncertain.mean()),
        "unmatched_anchors": int((~group["anchor_matched"]).sum()),
        "boundary_errors": int(boundary_errors.sum()),
        "largest_error_stratum_share": concentrated,
    }
    threshold_pass = all(
        float(metrics[column]) >= target
        for column in ["name_accuracy", "address_accuracy", "service_accuracy"]
    )
    metrics["pass"] = bool(
        threshold_pass
        and float(metrics["uncertain_share"]) <= 0.05
        and metrics["unmatched_anchors"] == 0
        and metrics["boundary_errors"] == 0
    )
    metrics["expansion_required"] = bool(
        not metrics["pass"] or concentrated >= 0.50
    )
    metrics["recommended_sample_size"] = (
        min(len(group) + 50, 200)
        if metrics["expansion_required"] and len(group) < 200
        else len(group)
    )
    metrics["blocked_at_200"] = bool(
        metrics["expansion_required"] and len(group) >= 200
    )
    return metrics


def evaluate_gold(
    run_dir: Path,
    gold_path: Path,
    output_dir: Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    current = load_run_facilities(run_dir)
    gold = pd.read_csv(gold_path, dtype=str).fillna("")
    merged = gold.merge(
        current,
        on="source_anchor_id",
        how="left",
        suffixes=("", "_current"),
        indicator=True,
    )
    merged["anchor_matched"] = merged["_merge"].eq("both")
    reviewed = merged.loc[merged["review_complete"].str.lower().eq("yes")].copy()
    if "review_disposition" in reviewed:
        reviewed = reviewed.loc[
            reviewed["review_disposition"].str.lower().isin(["", "active"])
        ]
    if reviewed.empty:
        raise ValueError("No completed gold reviews were found")

    reviewed["name_gold"] = reviewed.apply(
        lambda row: " ".join(filter(None, _gold_name_parts(row))),
        axis=1,
    )
    reviewed["name_current"] = (
        reviewed["name1"].fillna("") + " " + reviewed["name2"].fillna("")
    ).str.strip()
    reviewed["address_gold"] = reviewed.apply(
        lambda row: "|".join(
            [
                _gold_value(row, "corrected_address1", "parsed_address1"),
                _gold_value(row, "corrected_city", "parsed_city"),
                _gold_value(row, "corrected_state", "parsed_state"),
                _gold_value(row, "corrected_zip", "parsed_zip"),
            ]
        ),
        axis=1,
    )
    reviewed["address_current"] = (
        reviewed["address1"].fillna("")
        + "|"
        + reviewed["city"].fillna("")
        + "|"
        + reviewed["state"].fillna("")
        + "|"
        + reviewed["zip"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    )
    reviewed["name_accurate"] = (
        reviewed["name_gold"].map(normalize_key)
        == reviewed["name_current"].map(normalize_key)
    )
    reviewed["address_accurate"] = (
        reviewed["address_gold"].map(normalize_key)
        == reviewed["address_current"].map(normalize_key)
    )
    reviewed["service_accurate"] = reviewed.apply(
        lambda row: _canonical_service_codes(
            _gold_value(row, "corrected_service_codes", "parsed_service_codes")
        )
        == _canonical_service_codes(row.get("service_codes", "")),
        axis=1,
    )
    rows = []
    for year, group in reviewed.groupby("directory_year"):
        year_int = int(year)
        rows.append(evaluate_year_metrics(year_int, group))

    report = pd.DataFrame(rows).sort_values("directory_year")
    expected_years = set(BASELINE_SAMPLE_SIZE)
    missing_years = sorted(expected_years - set(report["directory_year"]))
    passing = (
        not missing_years
        and bool(report["pass"].all())
        and not bool(report["boundary_errors"].gt(0).any())
    )
    summary = {
        "run_dir": str(run_dir.resolve()),
        "gold_path": str(gold_path.resolve()),
        "passing": passing,
        "missing_review_years": missing_years,
        "blocked_years": report.loc[~report["pass"], "directory_year"].tolist(),
        "unresolved_boundary_errors": int(report["boundary_errors"].sum()),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_dir / "gold_evaluation_by_year.csv", index=False)
    (output_dir / "gold_evaluation.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return report, summary
