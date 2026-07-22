from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def prepare_for_stata(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    output = frame.copy()
    long_strings = []
    for column in output.columns:
        series = output[column]
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            output[column] = series.fillna("").astype(str)
            if output[column].str.len().max() > 244:
                long_strings.append(column)
        elif isinstance(series.dtype, pd.Int64Dtype):
            output[column] = (
                series.astype("int64")
                if not series.isna().any()
                else series.astype("float64")
            )
        elif isinstance(series.dtype, pd.BooleanDtype):
            output[column] = series.astype("float64")
    return output, long_strings


def export_stata(source: Path, destination: Path) -> dict[str, object]:
    frame = pd.read_parquet(source)
    if len(set(frame.columns)) != len(frame.columns):
        raise ValueError("Stata export requires unique column names.")
    too_long = [column for column in frame.columns if len(column) > 32]
    if too_long:
        raise ValueError(f"Stata variable names exceed 32 characters: {too_long}")

    output, long_strings = prepare_for_stata(frame)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    output.to_stata(
        temporary,
        write_index=False,
        version=118,
        convert_strl=long_strings,
        data_label="Historical SAMHSA treatment facility listings",
        time_stamp=None,
    )
    temporary.replace(destination)

    with pd.read_stata(destination, iterator=True) as reader:
        reader.read(1)
        rows = reader._nobs
        variables = reader._nvar
    if rows != len(output):
        raise RuntimeError(
            f"Stata row check failed: expected {len(output)}, found {rows}"
        )
    return {
        "path": str(destination),
        "rows": rows,
        "variables": variables,
        "strl_columns": long_strings,
        "bytes": destination.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(export_stata(args.source, args.output))


if __name__ == "__main__":
    main()
