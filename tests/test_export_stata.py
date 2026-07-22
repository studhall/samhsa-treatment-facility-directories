from pathlib import Path

import pandas as pd
import pytest

from scripts.export_stata import export_stata


def test_export_stata_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "facilities.parquet"
    destination = tmp_path / "facilities.dta"
    frame = pd.DataFrame(
        {
            "listing_id": ["a", "b"],
            "directory_year": pd.Series([2021, 2022], dtype="Int64"),
            "raw_record_text": ["short", "x" * 300],
            "warning": pd.Series([False, pd.NA], dtype="boolean"),
        }
    )
    frame.to_parquet(source, index=False)

    result = export_stata(source, destination)

    restored = pd.read_stata(destination)
    assert result["rows"] == 2
    assert result["variables"] == 4
    assert result["strl_columns"] == ["raw_record_text"]
    assert restored["listing_id"].tolist() == ["a", "b"]
    assert restored["raw_record_text"].str.len().tolist() == [5, 300]


def test_export_stata_rejects_long_variable_names(tmp_path: Path) -> None:
    source = tmp_path / "facilities.parquet"
    destination = tmp_path / "facilities.dta"
    pd.DataFrame({"a_variable_name_longer_than_thirty_two_characters": [1]}).to_parquet(
        source,
        index=False,
    )

    with pytest.raises(ValueError, match="exceed 32 characters"):
        export_stata(source, destination)
