from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

from .cbp_data import build_cbp_cells_from_archives, download_cbp_county_files
from .geocode import finalize_geocoding, geocode_file
from .gold import (
    build_gold_workbook,
    create_gold_sample,
    evaluate_gold,
    expand_gold_sample,
    import_gold_workbook,
    refresh_gold_sample,
    render_sample_pages,
)
from .manifest import load_manifest, select_year, verify_manifest
from .parser import parse_pdf
from .release import build_preliminary_release, build_release
from .runs import default_run_id, latest_run, parse_all
from .xlsx import import_xlsx_all, verify_xlsx_manifest


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def command_verify(args: argparse.Namespace) -> int:
    results = verify_manifest(Path(args.pdf_dir), Path(args.manifest) if args.manifest else None)
    frame = pd.DataFrame(results)
    print(frame.to_string(index=False))
    return 0 if frame["checksum_ok"].all() else 1


def command_parse(args: argparse.Namespace) -> int:
    config = select_year(args.year)
    pdf_path = Path(args.pdf_dir) / config.filename
    output_dir = Path(args.output_dir or _root() / "data" / "interim")
    result = parse_pdf(pdf_path, config, output_dir, max_pages=args.max_pages)
    print(
        json.dumps(
            {
                "directory_year": args.year,
                "facilities": len(result["facilities"]),
                "offered_services": len(result["facility_services"]),
                "available_codes": len(result["service_availability"]),
            },
            indent=2,
        )
    )
    return 0


def command_build(args: argparse.Namespace) -> int:
    pdf_dir = Path(args.pdf_dir)
    interim = Path(args.interim_dir or _root() / "data" / "interim")
    configs = [
        row
        for row in load_manifest()
        if row.directory_year <= args.through_directory_year
    ]
    if args.from_directory_year:
        configs = [row for row in configs if row.directory_year >= args.from_directory_year]
    for config in configs:
        print(f"Parsing directory year {config.directory_year}: {config.filename}")
        parse_pdf(
            pdf_dir / config.filename,
            config,
            interim,
            max_pages=args.max_pages,
        )

    report = build_release(
        interim,
        Path(args.release_dir or _root() / "release"),
        Path(args.gold_sample or _root() / "tests" / "fixtures" / "gold_sample.csv"),
        Path(args.geocoding) if args.geocoding else None,
        args.linkage_review_accuracy,
        args.materialize_service_status,
        Path(args.expected_counts or _root() / "config" / "expected_counts.csv"),
    )
    print(json.dumps(report, indent=2))
    return 0 if report["release_ready"] else 2


def command_release(args: argparse.Namespace) -> int:
    report = build_release(
        Path(args.interim_dir),
        Path(args.release_dir),
        Path(args.gold_sample),
        Path(args.geocoding) if args.geocoding else None,
        args.linkage_review_accuracy,
        args.materialize_service_status,
        Path(args.expected_counts or _root() / "config" / "expected_counts.csv"),
    )
    print(json.dumps(report, indent=2))
    return 0 if report["release_ready"] else 2



def command_preliminary_release(args: argparse.Namespace) -> int:
    metadata = build_preliminary_release(
        Path(args.run_dir),
        Path(args.release_dir),
        Path(args.review) if args.review else None,
        Path(args.geocoding) if args.geocoding else None,
        Path(args.harmonization_crosswalk) if args.harmonization_crosswalk else None,
        Path(args.cbp_comparison) if args.cbp_comparison else None,
        args.version,
    )
    print(json.dumps(metadata, indent=2))
    return 0


def command_geocode_finalize(args: argparse.Namespace) -> int:
    output = finalize_geocoding(
        Path(args.facilities),
        Path(args.cache),
        Path(args.output),
        Path(args.zip_crosswalk),
    )
    assigned = output["county_fips"].fillna("").ne("")
    high = output["geocode_confidence"].eq("high")
    print(
        json.dumps(
            {
                "rows": len(output),
                "assigned": int(assigned.sum()),
                "assigned_share": float(assigned.mean()),
                "high_confidence": int(high.sum()),
                "high_confidence_share": float(high.mean()),
            },
            indent=2,
        )
    )
    return 0

def command_geocode(args: argparse.Namespace) -> int:
    geocode_file(
        Path(args.facilities),
        Path(args.output),
        Path(args.cache),
        Path(args.zip_crosswalk) if args.zip_crosswalk else None,
        args.batch_size,
    )
    return 0


def _resolve_run_dir(value: str | None, resume: bool = False) -> Path:
    runs_dir = _root() / "data" / "interim" / "runs"
    if value:
        return Path(value)
    if resume:
        existing = latest_run(runs_dir)
        if existing is not None:
            return existing
    return runs_dir / default_run_id()


def command_parse_all(args: argparse.Namespace) -> int:
    run_dir = _resolve_run_dir(args.run_dir, args.resume)
    report = parse_all(
        Path(args.pdf_dir),
        run_dir,
        Path(args.manifest) if args.manifest else None,
        args.resume,
        args.workers,
        set(args.years) if args.years else None,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["complete"] else 2

def command_verify_xlsx(args: argparse.Namespace) -> int:
    results = verify_xlsx_manifest(
        Path(args.xlsx_dir), Path(args.manifest) if args.manifest else None
    )
    frame = pd.DataFrame(results)
    print(frame.to_string(index=False))
    return 0 if frame["checksum_ok"].all() else 1


def command_import_xlsx(args: argparse.Namespace) -> int:
    report = import_xlsx_all(
        Path(args.xlsx_dir),
        Path(args.run_dir),
        Path(args.manifest) if args.manifest else None,
        args.resume,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["complete"] else 2

def command_cbp_download(args: argparse.Namespace) -> int:
    rows = download_cbp_county_files(
        Path(args.output_dir),
        args.start_year,
        args.end_year,
        not args.no_resume,
    )
    print(pd.DataFrame(rows).to_string(index=False))
    return 0


def command_cbp_build(args: argparse.Namespace) -> int:
    cells = build_cbp_cells_from_archives(
        Path(args.raw_dir),
        args.start_year,
        args.end_year,
    )
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix == ".parquet":
        cells.to_parquet(destination, index=False)
    else:
        cells.to_csv(destination, index=False)
    print(json.dumps({"rows": len(cells), "output": str(destination)}, indent=2))
    return 0

def _node_path(value: str | None) -> Path | None:
    raw = value or os.environ.get("SAMHSA_NODE")
    return Path(raw) if raw else None


def _node_modules_path(value: str | None) -> Path | None:
    raw = value or os.environ.get("SAMHSA_NODE_MODULES")
    return Path(raw) if raw else None


def command_gold_create(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    output_dir = Path(
        args.output_dir or _root() / "qa" / "review" / run_dir.name
    )
    if args.existing_review:
        target_sizes: dict[int, int] = {}
        if args.evaluation:
            evaluation = pd.read_csv(args.evaluation)
            target_sizes.update(
                {
                    int(row.directory_year): int(row.recommended_sample_size)
                    for row in evaluation.itertuples(index=False)
                }
            )
        for value in args.target_size or []:
            year, size = value.split("=", 1)
            target_sizes[int(year)] = int(size)
        if not target_sizes:
            raise ValueError(
                "Expansion requires --evaluation or at least one --target-size YEAR=N"
            )
        review = expand_gold_sample(
            run_dir,
            Path(args.existing_review),
            output_dir,
            target_sizes,
            args.seed,
        )
    else:
        review = create_gold_sample(run_dir, output_dir, args.seed)
    run_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    pdf_dir = Path(args.pdf_dir or str(run_metadata["pdf_dir"]))
    if not args.skip_page_images:
        review = render_sample_pages(
            review, pdf_dir, output_dir, args.image_resolution
        )
    node = _node_path(args.node)
    workbook_path = output_dir / "gold_review.xlsx"
    if node is not None:
        build_gold_workbook(
            output_dir / "gold_review_source.json",
            workbook_path,
            output_dir / "workbook_previews",
            node,
            _node_modules_path(args.node_modules),
        )
    report = {
        "rows": len(review),
        "output_dir": str(output_dir),
        "workbook": str(workbook_path) if workbook_path.exists() else None,
        "workbook_pending_reason": (
            None
            if workbook_path.exists()
            else "Set --node or SAMHSA_NODE to build the Excel workbook."
        ),
    }
    print(json.dumps(report, indent=2))
    return 0 if workbook_path.exists() or args.allow_csv_only else 2


def command_gold_import(args: argparse.Namespace) -> int:
    node = _node_path(args.node)
    if node is None:
        raise ValueError("gold-import requires --node or SAMHSA_NODE")
    output = Path(args.output or _root() / "qa" / "gold" / "gold_sample.csv")
    frame = import_gold_workbook(
        Path(args.workbook),
        output,
        node,
        _node_modules_path(args.node_modules),
    )
    print(json.dumps({"rows": len(frame), "output": str(output)}, indent=2))
    return 0


def command_gold_refresh(args: argparse.Namespace) -> int:
    output_dir = Path(
        args.output_dir or _root() / "qa" / "review" / Path(args.run_dir).name
    )
    review, unmatched = refresh_gold_sample(
        Path(args.run_dir),
        Path(args.review),
        output_dir,
    )
    node = _node_path(args.node)
    workbook_path = output_dir / "gold_review.xlsx"
    if node is not None:
        build_gold_workbook(
            output_dir / "gold_review_source.json",
            workbook_path,
            output_dir / "workbook_previews",
            node,
            _node_modules_path(args.node_modules),
        )
    print(
        json.dumps(
            {
                "rows": len(review),
                "unmatched_anchors": len(unmatched),
                "output_dir": str(output_dir),
                "workbook": str(workbook_path) if workbook_path.exists() else None,
            },
            indent=2,
        )
    )
    return 0 if unmatched.empty else 2


def command_gold_evaluate(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir or _root() / "qa" / "gold")
    report, summary = evaluate_gold(
        Path(args.run_dir),
        Path(args.gold_sample or output_dir / "gold_sample.csv"),
        output_dir,
    )
    print(report.to_string(index=False))
    print(json.dumps(summary, indent=2))
    return 0 if summary["passing"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="samhsa-dirs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify-manifest")
    verify.add_argument("--pdf-dir", required=True)
    verify.add_argument("--manifest")
    verify.set_defaults(func=command_verify)

    parse = subparsers.add_parser("parse")
    parse.add_argument("--pdf-dir", required=True)
    parse.add_argument("--year", type=int, required=True)
    parse.add_argument("--output-dir")
    parse.add_argument("--max-pages", type=int)
    parse.set_defaults(func=command_parse)

    parse_all_parser = subparsers.add_parser("parse-all")
    parse_all_parser.add_argument("--pdf-dir", required=True)
    parse_all_parser.add_argument("--run-dir")
    parse_all_parser.add_argument("--manifest")
    parse_all_parser.add_argument("--resume", action="store_true")
    parse_all_parser.add_argument("--workers", type=int, default=2)
    parse_all_parser.add_argument("--years", type=int, nargs="+")
    parse_all_parser.set_defaults(func=command_parse_all)

    verify_xlsx = subparsers.add_parser("verify-xlsx")
    verify_xlsx.add_argument("--xlsx-dir", required=True)
    verify_xlsx.add_argument("--manifest")
    verify_xlsx.set_defaults(func=command_verify_xlsx)

    import_xlsx = subparsers.add_parser("import-xlsx-all")
    import_xlsx.add_argument("--xlsx-dir", required=True)
    import_xlsx.add_argument("--run-dir", required=True)
    import_xlsx.add_argument("--manifest")
    import_xlsx.add_argument("--resume", action="store_true")
    import_xlsx.set_defaults(func=command_import_xlsx)

    cbp_download = subparsers.add_parser("cbp-download")
    cbp_download.add_argument("--output-dir", required=True)
    cbp_download.add_argument("--start-year", type=int, default=1998)
    cbp_download.add_argument("--end-year", type=int, default=2023)
    cbp_download.add_argument("--no-resume", action="store_true")
    cbp_download.set_defaults(func=command_cbp_download)

    cbp_build = subparsers.add_parser("cbp-build")
    cbp_build.add_argument("--raw-dir", required=True)
    cbp_build.add_argument("--output", required=True)
    cbp_build.add_argument("--start-year", type=int, default=1998)
    cbp_build.add_argument("--end-year", type=int, default=2023)
    cbp_build.set_defaults(func=command_cbp_build)
    build = subparsers.add_parser("build")
    build.add_argument("--pdf-dir", required=True)
    build.add_argument("--through-directory-year", type=int, default=2021)
    build.add_argument("--from-directory-year", type=int)
    build.add_argument("--interim-dir")
    build.add_argument("--release-dir")
    build.add_argument("--gold-sample")
    build.add_argument("--geocoding")
    build.add_argument("--linkage-review-accuracy", type=float)
    build.add_argument("--materialize-service-status", action="store_true")
    build.add_argument("--expected-counts")
    build.add_argument("--max-pages", type=int)
    build.set_defaults(func=command_build)

    release = subparsers.add_parser("release")
    release.add_argument("--interim-dir", required=True)
    release.add_argument("--release-dir", required=True)
    release.add_argument("--gold-sample", required=True)
    release.add_argument("--geocoding")
    release.add_argument("--linkage-review-accuracy", type=float)
    release.add_argument("--materialize-service-status", action="store_true")
    release.add_argument("--expected-counts")
    release.set_defaults(func=command_release)


    preliminary = subparsers.add_parser("preliminary-release")
    preliminary.add_argument("--run-dir", required=True)
    preliminary.add_argument("--release-dir", required=True)
    preliminary.add_argument("--review")
    preliminary.add_argument("--geocoding")
    preliminary.add_argument("--harmonization-crosswalk")
    preliminary.add_argument("--cbp-comparison")
    preliminary.add_argument("--version", default="v1.1.0")
    preliminary.set_defaults(func=command_preliminary_release)

    geocode = subparsers.add_parser("geocode")
    geocode.add_argument("--facilities", required=True)
    geocode.add_argument("--output", required=True)
    geocode.add_argument("--cache", required=True)
    geocode.add_argument("--zip-crosswalk")
    geocode.add_argument("--batch-size", type=int, default=1000)
    geocode.set_defaults(func=command_geocode)


    geocode_finalize = subparsers.add_parser("geocode-finalize")
    geocode_finalize.add_argument("--facilities", required=True)
    geocode_finalize.add_argument("--cache", required=True)
    geocode_finalize.add_argument("--output", required=True)
    geocode_finalize.add_argument("--zip-crosswalk", required=True)
    geocode_finalize.set_defaults(func=command_geocode_finalize)

    gold_create = subparsers.add_parser("gold-create")
    gold_create.add_argument("--run-dir", required=True)
    gold_create.add_argument("--pdf-dir")
    gold_create.add_argument("--output-dir")
    gold_create.add_argument("--seed", type=int, default=20260612)
    gold_create.add_argument("--existing-review")
    gold_create.add_argument("--evaluation")
    gold_create.add_argument("--target-size", action="append")
    gold_create.add_argument("--image-resolution", type=int, default=110)
    gold_create.add_argument("--skip-page-images", action="store_true")
    gold_create.add_argument("--node")
    gold_create.add_argument("--node-modules")
    gold_create.add_argument("--allow-csv-only", action="store_true")
    gold_create.set_defaults(func=command_gold_create)

    gold_import = subparsers.add_parser("gold-import")
    gold_import.add_argument("--workbook", required=True)
    gold_import.add_argument("--output")
    gold_import.add_argument("--node")
    gold_import.add_argument("--node-modules")
    gold_import.set_defaults(func=command_gold_import)

    gold_refresh = subparsers.add_parser("gold-refresh")
    gold_refresh.add_argument("--run-dir", required=True)
    gold_refresh.add_argument("--review", required=True)
    gold_refresh.add_argument("--output-dir")
    gold_refresh.add_argument("--node")
    gold_refresh.add_argument("--node-modules")
    gold_refresh.set_defaults(func=command_gold_refresh)

    gold_evaluate = subparsers.add_parser("gold-evaluate")
    gold_evaluate.add_argument("--run-dir", required=True)
    gold_evaluate.add_argument("--gold-sample")
    gold_evaluate.add_argument("--output-dir")
    gold_evaluate.set_defaults(func=command_gold_evaluate)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))
