from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from samhsa_dirs.cbp import build_cbp_comparison


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samhsa-counts", required=True)
    parser.add_argument("--cbp-cells", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    samhsa = pd.read_csv(args.samhsa_counts, dtype={"county_fips": str, "state_fips": str})
    cbp = pd.read_csv(args.cbp_cells, dtype={"county_fips": str, "state_fips": str, "naics": str})
    output = build_cbp_comparison(samhsa, cbp)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix == ".parquet":
        output.to_parquet(destination, index=False)
    else:
        output.to_csv(destination, index=False)


if __name__ == "__main__":
    main()
