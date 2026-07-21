import json
import uuid
from pathlib import Path

from samhsa_dirs.runs import REQUIRED_YEAR_FILES, validate_complete_run


def test_complete_run_requires_every_year_and_file():
    run_dir = Path("tests/.artifacts") / f"run-{uuid.uuid4().hex}"
    year_dir = run_dir / "years" / "2021"
    year_dir.mkdir(parents=True)
    for filename in REQUIRED_YEAR_FILES:
        (year_dir / filename).write_text("", encoding="utf-8")
    (year_dir / "metadata.json").write_text(
        json.dumps({"structural_pass": True}), encoding="utf-8"
    )
    (year_dir / "status.json").write_text(
        json.dumps({"state": "complete"}), encoding="utf-8"
    )
    assert validate_complete_run(run_dir, [2021]) == []
    errors = validate_complete_run(run_dir, [2020, 2021])
    assert len(errors) == 1
    assert errors[0].startswith("2020:")
