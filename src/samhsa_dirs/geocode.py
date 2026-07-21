from __future__ import annotations

import csv
import io
import time
from pathlib import Path

import pandas as pd
import requests


BATCH_URL = "https://geocoding.geo.census.gov/geocoder/geographies/addressbatch"
COORD_URL = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"


def _batch_payload(rows: pd.DataFrame) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    for row in rows.itertuples(index=False):
        writer.writerow([row.listing_id, row.address1, row.city, row.state, row.zip])
    return stream.getvalue()


def geocode_batch(rows: pd.DataFrame, timeout: int = 120) -> pd.DataFrame:
    response = requests.post(
        BATCH_URL,
        data={
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
        },
        files={"addressFile": ("addresses.csv", _batch_payload(rows), "text/csv")},
        timeout=timeout,
    )
    response.raise_for_status()
    parsed = pd.read_csv(
        io.StringIO(response.text),
        header=None,
        names=[
            "listing_id",
            "input_address",
            "match_status",
            "match_type",
            "matched_address",
            "coordinates",
            "tiger_line_id",
            "side",
            "state_fips",
            "county_code",
            "tract",
            "block",
        ],
        dtype=str,
    )
    coords = parsed["coordinates"].str.split(",", n=1, expand=True)
    parsed["longitude"] = pd.to_numeric(coords[0], errors="coerce")
    parsed["latitude"] = pd.to_numeric(coords[1], errors="coerce")
    parsed["county_fips"] = (
        parsed["state_fips"].fillna("").str.zfill(2)
        + parsed["county_code"].fillna("").str.zfill(3)
    )
    invalid_county = parsed["state_fips"].isna() | parsed["county_code"].isna()
    parsed.loc[invalid_county, "county_fips"] = ""
    parsed["geocode_method"] = "census_batch"
    parsed["geocode_confidence"] = parsed["match_status"].map(
        {"Match": "high", "No_Match": "unmatched", "Tie": "review"}
    ).fillna("review")
    return parsed


def county_for_coordinates(longitude: float, latitude: float, timeout: int = 30) -> str:
    response = requests.get(
        COORD_URL,
        params={
            "x": longitude,
            "y": latitude,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "format": "json",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    counties = response.json().get("result", {}).get("geographies", {}).get("Counties", [])
    return str(counties[0].get("GEOID", "")) if counties else ""


def apply_zip_fallback(
    geocoded: pd.DataFrame, facilities: pd.DataFrame, zip_crosswalk: Path | None
) -> pd.DataFrame:
    if zip_crosswalk is None or not zip_crosswalk.exists():
        return geocoded
    crosswalk = pd.read_csv(zip_crosswalk, dtype={"zip": str, "county_fips": str})
    weight_col = "res_ratio" if "res_ratio" in crosswalk.columns else None
    if weight_col:
        crosswalk = crosswalk.sort_values(weight_col, ascending=False)
    crosswalk = crosswalk.drop_duplicates("zip")
    fallback = facilities[["listing_id", "zip"]].merge(crosswalk, on="zip", how="left")
    output = geocoded.merge(fallback, on="listing_id", how="outer", suffixes=("", "_fallback"))
    missing = output["county_fips"].isna() | output["county_fips"].eq("")
    output.loc[missing, "county_fips"] = output.loc[missing, "county_fips_fallback"]
    has_fallback = missing & output["county_fips"].notna() & output["county_fips"].ne("")
    output.loc[has_fallback, "geocode_method"] = "zip_crosswalk"
    output.loc[has_fallback, "geocode_confidence"] = "low"
    return output.drop(columns=["county_fips_fallback"], errors="ignore")


def finalize_geocoding(
    facilities_path: Path,
    cache_path: Path,
    output_path: Path,
    zip_crosswalk: Path,
) -> pd.DataFrame:
    """Combine completed Census matches with an explicitly low-confidence fallback."""
    facilities = pd.read_parquet(facilities_path)
    if cache_path.exists():
        geocoded = pd.read_csv(cache_path, dtype=str)
    else:
        geocoded = pd.DataFrame(
            columns=[
                "listing_id",
                "county_fips",
                "geocode_method",
                "geocode_confidence",
            ]
        )
    geocoded = geocoded.drop_duplicates("listing_id", keep="last")
    output = apply_zip_fallback(geocoded, facilities, zip_crosswalk)
    output.to_csv(output_path, index=False)
    return output

def geocode_file(
    facilities_path: Path,
    output_path: Path,
    cache_path: Path,
    zip_crosswalk: Path | None = None,
    batch_size: int = 1000,
    pause_seconds: float = 1.0,
) -> pd.DataFrame:
    facilities = pd.read_parquet(facilities_path)
    cache = pd.read_csv(cache_path, dtype=str) if cache_path.exists() else pd.DataFrame()
    done = set(cache.get("listing_id", pd.Series(dtype=str)))
    pending = facilities.loc[~facilities["listing_id"].isin(done)]
    chunks = [pending.iloc[i : i + batch_size] for i in range(0, len(pending), batch_size)]
    results = [cache] if not cache.empty else []

    for chunk in chunks:
        batch = geocode_batch(chunk)
        results.append(batch)
        pd.concat(results, ignore_index=True).to_csv(cache_path, index=False)
        time.sleep(pause_seconds)

    output = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    output = apply_zip_fallback(output, facilities, zip_crosswalk)
    output.to_csv(output_path, index=False)
    return output
