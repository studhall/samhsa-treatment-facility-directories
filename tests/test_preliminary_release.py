from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from samhsa_dirs.geocode import geocode_batch
from samhsa_dirs.manifest import load_manifest
from samhsa_dirs.release import build_preliminary_release


def _write_year(year_dir: Path, directory_year: int, survey_year: int) -> None:
    year_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "listing_id": f"L{directory_year}",
                "directory_year": directory_year,
                "survey_year": survey_year,
                "name1": "Example Facility",
                "address1": "1 Main St",
                "city": "Example",
                "state": "OR",
                "zip": "97401",
                "phone": "555-0100",
                "parser_warnings": "[]",
            }
        ]
    ).to_parquet(year_dir / "facilities.parquet", index=False)
    pd.DataFrame(
        [
            {
                "listing_id": f"L{directory_year}",
                "directory_year": directory_year,
                "survey_year": survey_year,
                "category": "service",
                "code": "OTP",
                "label": "Opioid treatment program",
                "known_code": True,
            }
        ]
    ).to_parquet(year_dir / "facility_services.parquet", index=False)
    pd.DataFrame(
        [
            {
                "directory_year": directory_year,
                "survey_year": survey_year,
                "category": "service",
                "code": "OTP",
                "label": "Opioid treatment program",
                "asked": True,
            }
        ]
    ).to_parquet(year_dir / "service_availability.parquet", index=False)
    (year_dir / "metadata.json").write_text("{}", encoding="utf-8")


def test_preliminary_release_is_complete_but_never_validated(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    years = list(load_manifest())
    for config in years:
        _write_year(
            run_dir / "years" / str(config.directory_year),
            config.directory_year,
            config.survey_year,
        )
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "test-run",
                "parser_version": "test",
                "expected_years": [row.directory_year for row in years],
            }
        ),
        encoding="utf-8",
    )

    release_dir = tmp_path / "release"
    metadata = build_preliminary_release(run_dir, release_dir)

    assert metadata["release_status"] == "preliminary"
    assert metadata["release_ready"] is False
    assert metadata["facility_rows"] == 22
    assert (release_dir / "facilities.csv.gz").exists()
    assert (release_dir / "facilities.parquet").exists()
    assert (release_dir / "facility_services.csv.gz").exists()
    assert (release_dir / "qa_by_year.csv").exists()
    assert (release_dir / "checksums.sha256").exists()

    facilities = pd.read_parquet(release_dir / "facilities.parquet")
    assert facilities["release_status"].eq("preliminary").all()
    assert facilities["year_qa_status"].eq("not_reviewed").all()


def test_geography_batch_returns_county_fips() -> None:
    response = Mock()
    response.text = (
        'L1,"1 Main St, Example, OR, 97401",Match,Exact,'
        '"1 MAIN ST, EXAMPLE, OR, 97401","-123.1,44.1",123,L,41,039,000100,1000\n'
    )
    response.raise_for_status.return_value = None
    rows = pd.DataFrame(
        [{"listing_id": "L1", "address1": "1 Main St", "city": "Example", "state": "OR", "zip": "97401"}]
    )

    with patch("samhsa_dirs.geocode.requests.post", return_value=response) as post:
        result = geocode_batch(rows)

    assert result.loc[0, "county_fips"] == "41039"
    assert result.loc[0, "geocode_confidence"] == "high"
    assert post.call_args.args[0].endswith("/geographies/addressbatch")

