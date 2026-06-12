from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from .geocode import geocode_file
from .manifest import load_manifest, select_year, verify_manifest
from .parser import parse_pdf
from .release import build_release


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


def command_geocode(args: argparse.Namespace) -> int:
    geocode_file(
        Path(args.facilities),
        Path(args.output),
        Path(args.cache),
        Path(args.zip_crosswalk) if args.zip_crosswalk else None,
        args.batch_size,
    )
    return 0


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

    geocode = subparsers.add_parser("geocode")
    geocode.add_argument("--facilities", required=True)
    geocode.add_argument("--output", required=True)
    geocode.add_argument("--cache", required=True)
    geocode.add_argument("--zip-crosswalk")
    geocode.add_argument("--batch-size", type=int, default=1000)
    geocode.set_defaults(func=command_geocode)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))
